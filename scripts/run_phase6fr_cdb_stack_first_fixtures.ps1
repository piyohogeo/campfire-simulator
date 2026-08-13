param(
    [Parameter(Mandatory = $true)][string]$OutputRoot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$output = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $output) { throw "Phase 6FR refuses fixture artifact reuse: $output" }
New-Item -ItemType Directory -Path $output | Out-Null
. (Join-Path $PSScriptRoot "kit_shutdown_policy.ps1")
$powershell = (Get-Process -Id $PID).Path
$targetScript = Join-Path $PSScriptRoot "phase6ej_shutdown_target_fixture.ps1"
$cdb = Get-CampfireCdbPath
if ($null -eq $cdb) { throw "Phase 6FR could not auto-detect CDB" }
$cdbMetadata = Get-CampfireCdbMetadata -Path $cdb

function Start-Target([string]$Name, [int]$SleepSeconds, [switch]$ExclusiveLogLock) {
    $dir = Join-Path $output $Name
    New-Item -ItemType Directory -Path $dir | Out-Null
    $lifecycle = Join-Path $dir "target.json"
    $log = Join-Path $dir "target.log"
    $arguments = @(
        "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", $targetScript, "-LifecyclePath", $lifecycle, "-LogPath", $log,
        "-SleepSeconds", [string]$SleepSeconds
    )
    if ($ExclusiveLogLock) { $arguments += "-ExclusiveLogLock" }
    $process = Start-Process -FilePath $powershell -ArgumentList $arguments -PassThru -WindowStyle Hidden
    $deadline = [datetime]::UtcNow.AddSeconds(10)
    while (-not (Test-Path -LiteralPath $lifecycle -PathType Leaf) -and [datetime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 50 }
    if (-not (Test-Path -LiteralPath $lifecycle -PathType Leaf)) { throw "Phase 6FR target fixture did not become ready: $Name" }
    return [pscustomobject]@{ Process=$process; Directory=$dir; Lifecycle=$lifecycle; Log=$log; ExpectedStartUtc=$process.StartTime.ToUniversalTime() }
}

function Stop-ExactTarget([object]$Target) {
    try {
        if ($null -ne (Get-Process -Id $Target.Process.Id -ErrorAction SilentlyContinue)) {
            $null = Test-Phase6EaProcessIdentity -ProcessId $Target.Process.Id -ExpectedExecutable $powershell -ExpectedStartTimeUtc $Target.ExpectedStartUtc
            Stop-Process -Id $Target.Process.Id -Force
            $Target.Process.WaitForExit(10000) | Out-Null
        }
    } finally { $Target.Process.Dispose() }
}

function Read-Markers([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return @() }
    return @([IO.File]::ReadLines($Path, [Text.Encoding]::UTF8) | ForEach-Object { ($_ | ConvertFrom-Json).marker })
}

function Invoke-DirectCase(
    [string]$Name,
    [int]$StackTimeoutSeconds,
    [int]$ModuleTimeoutSeconds,
    [int]$DetachTimeoutSeconds,
    [int]$StackSleepMilliseconds,
    [int]$ModuleSleepMilliseconds,
    [string]$ExpectedOutcome
) {
    $target = Start-Target -Name $Name -SleepSeconds 180
    try {
        $diagnostic = Join-Path $target.Directory "diagnostic"
        New-Item -ItemType Directory -Path $diagnostic | Out-Null
        $markerPath = Join-Path $target.Directory "cdb.markers.jsonl"
        $capture = Invoke-CampfireCdbStackFirstCapture `
            -ProcessId $target.Process.Id -ExpectedExecutable $powershell -ExpectedStartTimeUtc $target.ExpectedStartUtc `
            -OutputDir $diagnostic -MarkerPath $markerPath `
            -StackTimeoutSeconds $StackTimeoutSeconds -ModuleTimeoutSeconds $ModuleTimeoutSeconds `
            -DetachTimeoutSeconds $DetachTimeoutSeconds -FixtureCdbSleepMilliseconds $StackSleepMilliseconds `
            -FixtureModuleCdbSleepMilliseconds $ModuleSleepMilliseconds
        $markers = Read-Markers $markerPath
        $targetAlive = $null -ne (Get-Process -Id $target.Process.Id -ErrorAction SilentlyContinue)
        $stackComplete = [bool]$capture.all_thread_stack_observed -and [bool]$capture.native_frames_observed
        $requiredCommon = @("cdb_attach_started", "cdb_stack_capture_started", "cdb_detach_started", "cdb_detach_complete", "cdb_cleanup_complete")
        $commonComplete = -not ($requiredCommon | Where-Object { $_ -notin $markers })
        $passed = switch ($ExpectedOutcome) {
            "complete" { $stackComplete -and $capture.modules_observed -and $capture.detach_observed -and $capture.process_absent -and $commonComplete -and $targetAlive }
            "module_timeout_partial" { $stackComplete -and $capture.module_guard.timed_out -and $capture.detach_observed -and $capture.process_absent -and $commonComplete -and $targetAlive }
            "stack_timeout_cleanup" { $capture.stack_guard.timed_out -and -not $capture.all_thread_stack_observed -and $capture.detach_observed -and $capture.process_absent -and $commonComplete -and $targetAlive }
            default { $false }
        }
        return [ordered]@{
            name=$Name; expected_outcome=$ExpectedOutcome; status=if ($passed) { "pass" } else { "fail" }
            target_alive_after_detach=$targetAlive; stack_complete=$stackComplete
            module_complete=[bool]$capture.modules_observed; explicit_detach=[bool]$capture.detach_observed
            cdb_process_absent=[bool]$capture.process_absent; markers=$markers; capture=$capture
        }
    } finally { Stop-ExactTarget $target }
}

$cases = @()
$cases += Invoke-DirectCase "wait-stack-first" 30 20 15 0 0 "complete"
$cases += Invoke-DirectCase "module-timeout-fallback" 30 5 15 0 10000 "module_timeout_partial"
$cases += Invoke-DirectCase "stack-timeout-cleanup" 5 10 15 10000 0 "stack_timeout_cleanup"

$lockedTarget = Start-Target -Name "locked-log-end-to-end" -SleepSeconds 180 -ExclusiveLogLock
try {
    $diagnostic = Join-Path $lockedTarget.Directory "diagnostic"
    $result = Invoke-CampfireLightweightNgxDiagnostic -ProcessId $lockedTarget.Process.Id -ExpectedExecutable $powershell -ExpectedStartTimeUtc $lockedTarget.ExpectedStartUtc -OutputDir $diagnostic -LifecyclePath $lockedTarget.Lifecycle -LogPath $lockedTarget.Log -DebuggerTimeoutSeconds 30
    $report = Read-CampfireBoundedJson -Path (Join-Path $diagnostic "lightweight_shutdown_diagnostic.json")
    $targetAlive = $null -ne (Get-Process -Id $lockedTarget.Process.Id -ErrorAction SilentlyContinue)
    $pass = $result.diagnostic_capture_succeeded -and $report.debugger.all_thread_stack_observed -and $report.debugger.native_frames_observed -and $report.debugger.detach_observed -and $report.debugger.process_absent -and $targetAlive -and -not [string]::IsNullOrWhiteSpace([string]$report.log_capture_error)
    $cases += [ordered]@{
        name="locked-log-end-to-end"; expected_outcome="bounded_log_error_with_complete_stack"; status=if ($pass) { "pass" } else { "fail" }
        target_alive_after_detach=$targetAlive; log_capture_error_recorded=-not [string]::IsNullOrWhiteSpace([string]$report.log_capture_error)
        diagnostic_capture_succeeded=[bool]$result.diagnostic_capture_succeeded; debugger=$report.debugger; helper_guard=$result.helper_guard
    }
} finally { Stop-ExactTarget $lockedTarget }

$normalTarget = Start-Target -Name "normal-exit-before-attach" -SleepSeconds 1
try {
    $normalTarget.Process.WaitForExit(10000) | Out-Null
    $diagnostic = Join-Path $normalTarget.Directory "diagnostic"
    New-Item -ItemType Directory -Path $diagnostic | Out-Null
    $threw = $false
    $capture = $null
    try {
        $capture = Invoke-CampfireCdbStackFirstCapture -ProcessId $normalTarget.Process.Id -ExpectedExecutable $powershell -ExpectedStartTimeUtc $normalTarget.ExpectedStartUtc -OutputDir $diagnostic -MarkerPath (Join-Path $normalTarget.Directory "cdb.markers.jsonl") -StackTimeoutSeconds 5 -ModuleTimeoutSeconds 5 -DetachTimeoutSeconds 5
    } catch { $threw = $true }
    $cdbRemainder = @(Get-Process cdb -ErrorAction SilentlyContinue).Count
    $identityRejected = $threw -or ($null -ne $capture -and -not [string]::IsNullOrWhiteSpace([string]$capture.error) -and $null -eq $capture.stack_guard -and -not $capture.stack_attach_observed)
    $cases += [ordered]@{
        name="normal-exit-before-attach"; expected_outcome="identity_fail_closed"; status=if ($identityRejected -and $cdbRemainder -eq 0) { "pass" } else { "fail" }
        identity_rejected=$identityRejected; error=if ($null -ne $capture) { $capture.error } else { $null }; cdb_remainder=$cdbRemainder
    }
} finally { $normalTarget.Process.Dispose() }

$allPass = -not ($cases | Where-Object { $_.status -ne "pass" })
$report = [ordered]@{
    schema="campfire.phase6fr.cdb-stack-first-fixtures.v1"; phase="phase6fr"
    status=if ($allPass) { "pass" } else { "fail" }; cdb=$cdbMetadata
    contract=[ordered]@{
        stack_first=$true; module_pass_auxiliary=$true; module_timeout_fallback=$true
        symbol_path="local cache only"; microsoft_symbol_server_wait=$false
        explicit_detach_pass=$true; target_identity="pid+creation-time+absolute-path"
        stdout_direct_to_bounded_file=$true; private_bytes_limit=$CampfireShutdownHelperPrivateBytesLimit
        known_ngx_requires_all_five_stack_tokens=$true; full_dump_created=$false
        machine_wide_debugger_configuration_changed=$false
    }
    cases=$cases
    process_remainder=[ordered]@{ cdb=@(Get-Process cdb -ErrorAction SilentlyContinue).Count }
}
Write-CampfireBoundedJson -Path (Join-Path $output "report.json") -Value $report
if ($report.status -ne "pass" -or $report.process_remainder.cdb -ne 0) { throw "Phase 6FR CDB stack-first fixtures failed" }
Write-Host "Phase 6FR CDB stack-first fixtures passed"
