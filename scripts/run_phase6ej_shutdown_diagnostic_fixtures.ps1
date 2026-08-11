param(
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [switch]$ExclusiveLogLock
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$output = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $output) { throw "Phase 6EJ fixture output already exists: $output" }
New-Item -ItemType Directory -Path $output | Out-Null
. (Join-Path $PSScriptRoot "kit_shutdown_policy.ps1")
$powershell = (Get-Process -Id $PID).Path
$targetScript = Join-Path $PSScriptRoot "phase6ej_shutdown_target_fixture.ps1"
$helperScript = Join-Path $PSScriptRoot "run_lightweight_shutdown_diagnostic_helper.ps1"

function Start-Target([string]$Name) {
    $dir = Join-Path $output $Name
    New-Item -ItemType Directory -Path $dir | Out-Null
    $lifecycle = Join-Path $dir "target.json"
    $log = Join-Path $dir "target.log"
    $targetArguments = @(
        "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", $targetScript, "-LifecyclePath", $lifecycle, "-LogPath", $log, "-SleepSeconds", "120"
    )
    if ($ExclusiveLogLock) { $targetArguments += "-ExclusiveLogLock" }
    $process = Start-Process -FilePath $powershell -ArgumentList $targetArguments -PassThru -WindowStyle Hidden
    $deadline = [datetime]::UtcNow.AddSeconds(10)
    while (-not (Test-Path -LiteralPath $lifecycle -PathType Leaf) -and [datetime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 50 }
    if (-not (Test-Path -LiteralPath $lifecycle -PathType Leaf)) { throw "target fixture did not become ready" }
    return [pscustomobject]@{ Process=$process; Directory=$dir; Lifecycle=$lifecycle; Log=$log }
}

function Stop-Target([object]$Target) {
    if ($null -ne (Get-Process -Id $Target.Process.Id -ErrorAction SilentlyContinue)) {
        Stop-Process -Id $Target.Process.Id -Force
        $Target.Process.WaitForExit(10000) | Out-Null
    }
    $Target.Process.Dispose()
}

$results = @()
$target = Start-Target "isolated-child"
try {
    $diagnostic = Invoke-CampfireLightweightNgxDiagnostic `
        -ProcessId $target.Process.Id `
        -ExpectedExecutable $powershell `
        -ExpectedStartTimeUtc $target.Process.StartTime.ToUniversalTime() `
        -OutputDir (Join-Path $target.Directory "diagnostic") `
        -LifecyclePath $target.Lifecycle `
        -LogPath $target.Log `
        -DebuggerTimeoutSeconds 5
    $results += [ordered]@{
        name = "isolated_child"
        diagnostic_capture_succeeded = [bool]$diagnostic.diagnostic_capture_succeeded
        helper_guard = $diagnostic.helper_guard
        marker_path = $diagnostic.marker_path
        result_exists = Test-Path -LiteralPath (Join-Path $target.Directory "diagnostic\lightweight_shutdown_diagnostic.json")
    }
} finally { Stop-Target $target }

$target = Start-Target "timeout-child"
try {
    $dir = $target.Directory
    $markers = Join-Path $dir "diagnostic.markers.jsonl"
    $guard = Invoke-Phase6EaGuardedHelper -FilePath $powershell -ArgumentList @(
        "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", $helperScript,
        "-ProcessId", [string]$target.Process.Id,
        "-ExpectedExecutable", $powershell,
        "-ExpectedStartTimeUtc", $target.Process.StartTime.ToUniversalTime().ToString("o"),
        "-OutputDir", (Join-Path $dir "diagnostic"),
        "-LifecyclePath", $target.Lifecycle,
        "-LogPath", $target.Log,
        "-MarkerPath", $markers,
        "-DebuggerTimeoutSeconds", "5",
        "-FixtureDelayMilliseconds", "5000"
    ) -StdoutPath (Join-Path $dir "helper.stdout.log") -StderrPath (Join-Path $dir "helper.stderr.log") -TimeoutSeconds 1 -PrivateBytesLimit 256MB
    $results += [ordered]@{
        name = "timeout_child"
        timed_out = [bool]$guard.timed_out
        process_absent = [bool]$guard.process_absent
        private_bytes_exceeded = [bool]$guard.private_bytes_exceeded
        helper_guard = $guard
        marker_path = $markers
    }
} finally { Stop-Target $target }

$report = [ordered]@{
    schema = "campfire.phase6ej.shutdown-diagnostic-fixtures.v1"
    status = if ($results.Count -eq 2 -and $results[0].result_exists -and $results[0].helper_guard.process_absent -and $results[1].timed_out -and $results[1].process_absent) { "ok" } else { "failed" }
    results = $results
}
Write-CampfireBoundedJson -Path (Join-Path $output "report.json") -Value $report
if ($report.status -ne "ok") { throw "Phase 6EJ shutdown diagnostic fixtures failed" }
Write-Host "Phase 6EJ shutdown diagnostic fixtures passed"
