param([Parameter(Mandatory = $true)][string]$OutputRoot)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $root) { throw "Phase 6FZ CDB fixture refuses root reuse: $root" }
New-Item -ItemType Directory -Path $root | Out-Null
. (Join-Path $PSScriptRoot "kit_shutdown_policy.ps1")
$powershell = (Get-Process -Id $PID).Path
$helper = Join-Path $PSScriptRoot "phase6fz_progress_fixture.ps1"
$targetScript = Join-Path $PSScriptRoot "phase6ej_shutdown_target_fixture.ps1"
$cases = @()

function Invoke-GuardCase([string]$Name, [string]$Mode, [int]$DurationMs, [int]$AbsoluteSeconds, [int]$NoProgressSeconds, [string]$ExpectedReason) {
    $dir = Join-Path $root $Name
    New-Item -ItemType Directory -Path $dir | Out-Null
    $artifact = Join-Path $dir "progress.artifact"
    $stdout = Join-Path $dir "stdout.log"
    $stderr = Join-Path $dir "stderr.log"
    $guard = Invoke-Phase6EaGuardedHelper -FilePath $powershell -ArgumentList @(
        "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $helper,
        "-Mode", $Mode, "-ArtifactPath", $artifact, "-DurationMilliseconds", [string]$DurationMs, "-IntervalMilliseconds", "200"
    ) -StdoutPath $stdout -StderrPath $stderr -TimeoutSeconds $AbsoluteSeconds -NoProgressTimeoutSeconds $NoProgressSeconds -ProgressPaths @($artifact) -PrivateBytesLimit 128MB -MaximumStdoutBytes 1MB -MaximumStderrBytes 1MB
    $childPid = if ($Mode -eq "descendant" -and (Test-Path $artifact)) { [int]([IO.File]::ReadAllText($artifact)) } else { 0 }
    $childAbsent = $childPid -eq 0 -or $null -eq (Get-Process -Id $childPid -ErrorAction SilentlyContinue)
    if ([string]::IsNullOrWhiteSpace($ExpectedReason)) {
        $pass = $guard.process_absent -and $childAbsent -and -not $guard.timed_out -and $guard.exit_code -eq 0 -and $guard.progress_change_count -gt 0
    } else {
        $pass = $guard.process_absent -and $childAbsent -and $guard.timeout_reason -eq $ExpectedReason
    }
    if ($Mode -eq "partial") {
        $pass = $pass -and (Test-Path -LiteralPath $artifact -PathType Leaf) -and
            ([IO.File]::ReadAllText($artifact).Contains("ntdll!fixture_wait+0x1"))
    }
    return [ordered]@{ name=$Name; status=if($pass){"pass"}else{"fail"}; expected_timeout_reason=$ExpectedReason; guard=$guard; descendant_pid=$childPid; descendant_absent=$childAbsent }
}

$cases += Invoke-GuardCase "progress-completes" "progress" 2200 6 1 ""
$cases += Invoke-GuardCase "no-progress-timeout" "silent" 6000 5 1 "no_progress"
$cases += Invoke-GuardCase "absolute-timeout-with-progress" "progress" 6000 2 1 "absolute"
$cases += Invoke-GuardCase "partial-stack-preserved" "partial" 6000 5 1 "no_progress"
$cases += Invoke-GuardCase "process-tree-cleanup" "descendant" 6000 5 1 "no_progress"

function Start-Target([string]$Name) {
    $dir = Join-Path $root $Name
    New-Item -ItemType Directory -Path $dir | Out-Null
    $lifecycle = Join-Path $dir "target.json"
    $log = Join-Path $dir "target.log"
    $process = Start-Process -FilePath $powershell -ArgumentList @("-NoLogo", "-NoProfile", "-NonInteractive", "-File", $targetScript, "-LifecyclePath", $lifecycle, "-LogPath", $log, "-SleepSeconds", "180") -PassThru -WindowStyle Hidden
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    while (-not (Test-Path $lifecycle) -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 50 }
    if (-not (Test-Path $lifecycle)) { throw "target did not become ready" }
    return [pscustomobject]@{ Process=$process; StartUtc=$process.StartTime.ToUniversalTime(); Dir=$dir }
}
function Stop-Target($Target) {
    try {
        if ($null -ne (Get-Process -Id $Target.Process.Id -ErrorAction SilentlyContinue)) {
            $null = Test-Phase6EaProcessIdentity -ProcessId $Target.Process.Id -ExpectedExecutable $powershell -ExpectedStartTimeUtc $Target.StartUtc
            Stop-Process -Id $Target.Process.Id -Force
            $Target.Process.WaitForExit(10000) | Out-Null
        }
    } finally { $Target.Process.Dispose() }
}

$target = Start-Target "actual-cdb-progress"
try {
    $diag = Join-Path $target.Dir "diagnostic"
    New-Item -ItemType Directory -Path $diag | Out-Null
    $capture = Invoke-CampfireCdbStackFirstCapture -ProcessId $target.Process.Id -ExpectedExecutable $powershell -ExpectedStartTimeUtc $target.StartUtc -OutputDir $diag -MarkerPath (Join-Path $target.Dir "markers.jsonl") -StackTimeoutSeconds 80 -ModuleTimeoutSeconds 30 -DetachTimeoutSeconds 10 -NoProgressTimeoutSeconds 20
    $pass = $capture.stack_evidence -eq "complete" -and $capture.detach_observed -and $capture.process_absent -and $null -ne (Get-Process -Id $target.Process.Id -ErrorAction SilentlyContinue)
    $cases += [ordered]@{ name="actual-cdb-progress"; status=if($pass){"pass"}else{"fail"}; capture=$capture }
} finally { Stop-Target $target }

$target = Start-Target "actual-detach-failure"
try {
    $diag = Join-Path $target.Dir "diagnostic"
    New-Item -ItemType Directory -Path $diag | Out-Null
    $capture = Invoke-CampfireCdbStackFirstCapture -ProcessId $target.Process.Id -ExpectedExecutable $powershell -ExpectedStartTimeUtc $target.StartUtc -OutputDir $diag -MarkerPath (Join-Path $target.Dir "markers.jsonl") -StackTimeoutSeconds 20 -ModuleTimeoutSeconds 10 -DetachTimeoutSeconds 5 -NoProgressTimeoutSeconds 15 -FixtureDetachCdbSleepMilliseconds 30000
    $pass = -not $capture.detach_observed -and $capture.detach_guard.timed_out -and $capture.detach_guard.process_absent -and $capture.process_absent
    $cases += [ordered]@{ name="actual-detach-failure"; status=if($pass){"pass"}else{"fail"}; capture=$capture }
} finally { Stop-Target $target }

$report = [ordered]@{
    schema="campfire.phase6fz.cdb-progress-fixtures.v1"; phase="phase6fz"
    passed=(@($cases | Where-Object { $_.status -ne "pass" }).Count -eq 0)
    no_progress_timeout_seconds=20; absolute_stack_timeout_seconds=80; absolute_total_timeout_seconds=120
    stack_classifications=@("complete","partial","none"); cases=$cases
    residual=[ordered]@{ cdb=@(Get-Process cdb -ErrorAction SilentlyContinue).Count }
}
Write-CampfireBoundedJson -Path (Join-Path $root "cdb_progress_fixture_report.json") -Value $report -MaximumBytes 4MB
if (-not $report.passed -or $report.residual.cdb -ne 0) { throw "Phase 6FZ CDB progress fixtures failed" }
