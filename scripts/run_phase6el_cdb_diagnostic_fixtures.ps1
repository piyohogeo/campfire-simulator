param(
    [Parameter(Mandatory = $true)][string]$OutputRoot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$output = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $output) { throw "Phase 6EL refuses fixture artifact reuse: $output" }
New-Item -ItemType Directory -Path $output | Out-Null
. (Join-Path $PSScriptRoot "kit_shutdown_policy.ps1")
$powershell = (Get-Process -Id $PID).Path
$targetScript = Join-Path $PSScriptRoot "phase6ej_shutdown_target_fixture.ps1"
$helperScript = Join-Path $PSScriptRoot "run_lightweight_shutdown_diagnostic_helper.ps1"
$cdb = Get-CampfireCdbPath
if ($null -eq $cdb) { throw "Phase 6EL could not auto-detect CDB" }
$cdbMetadata = Get-CampfireCdbMetadata -Path $cdb

function Get-MachineDebugConfigurationSnapshot {
    $paths = @(
        "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\AeDebug",
        "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\Windows NT\CurrentVersion\AeDebug",
        "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps"
    )
    $records = @()
    foreach ($path in $paths) {
        $record = [ordered]@{ path=$path; exists=(Test-Path -LiteralPath $path); values=[ordered]@{} }
        if ($record.exists) {
            try {
                $item = Get-ItemProperty -LiteralPath $path -ErrorAction Stop
                foreach ($property in @($item.PSObject.Properties | Where-Object { $_.Name -notmatch '^PS' } | Sort-Object Name)) {
                    $record.values[$property.Name] = [string]$property.Value
                }
            } catch { $record.error = $_.Exception.GetType().Name }
        }
        $records += $record
    }
    $json = $records | ConvertTo-Json -Depth 8 -Compress
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($json)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $hash = [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace("-", "") } finally { $sha.Dispose() }
    return [ordered]@{ sha256=$hash; records=$records }
}

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
    if (-not (Test-Path -LiteralPath $lifecycle -PathType Leaf)) { throw "Phase 6EL target fixture did not become ready: $Name" }
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

function Read-Diagnostic([string]$Directory) {
    return Read-CampfireBoundedJson -Path (Join-Path $Directory "lightweight_shutdown_diagnostic.json")
}

function Invoke-WaitCase([string]$Name, [switch]$ExclusiveLogLock) {
    $target = Start-Target -Name $Name -SleepSeconds 120 -ExclusiveLogLock:$ExclusiveLogLock
    try {
        $diagnosticDir = Join-Path $target.Directory "diagnostic"
        $result = Invoke-CampfireLightweightNgxDiagnostic -ProcessId $target.Process.Id -ExpectedExecutable $powershell -ExpectedStartTimeUtc $target.ExpectedStartUtc -OutputDir $diagnosticDir -LifecyclePath $target.Lifecycle -LogPath $target.Log -DebuggerTimeoutSeconds 30
        $report = Read-Diagnostic $diagnosticDir
        $stackPath = Join-Path $diagnosticDir "cdb-thread-stacks.log"
        $markers = @([IO.File]::ReadLines([string]$result.marker_path, [Text.Encoding]::UTF8) | ForEach-Object { ($_ | ConvertFrom-Json).marker })
        $requiredMarkers = @("cdb_attach_started", "cdb_attach_complete", "cdb_stack_capture_started", "cdb_stack_capture_complete", "cdb_detach_complete", "cdb_cleanup_complete")
        return [ordered]@{
            name = $Name
            status = if ($result.diagnostic_capture_succeeded -and -not ($requiredMarkers | Where-Object { $_ -notin $markers }) -and $report.debugger.process_absent) { "pass" } else { "fail" }
            exclusive_log_lock = [bool]$ExclusiveLogLock
            diagnostic_capture_succeeded = [bool]$result.diagnostic_capture_succeeded
            target_alive_after_detach = ($null -ne (Get-Process -Id $target.Process.Id -ErrorAction SilentlyContinue))
            log_capture_error_recorded = -not [string]::IsNullOrWhiteSpace([string]$report.log_capture_error)
            stack_has_all_threads = Test-CampfireLogPattern -Path $stackPath -Pattern "THREAD_STACKS"
            stack_has_native_frames = Test-CampfireLogPattern -Path $stackPath -Pattern "Child-SP\s+RetAddr|ntdll!|KERNELBASE!"
            stack_has_modules = Test-CampfireLogPattern -Path $stackPath -Pattern "LOADED_MODULES"
            stack_has_detach = Test-CampfireLogPattern -Path $stackPath -Pattern "CDB_DETACHING"
            required_markers = $requiredMarkers
            observed_markers = $markers
            debugger = $report.debugger
            diagnostic_helper = $result.helper_guard
            target_resource_before = $report.process.resource_before
            target_resource_after = $report.process.resource_after
        }
    } finally { Stop-ExactTarget $target }
}

$configurationBefore = Get-MachineDebugConfigurationSnapshot
$cases = @()
$cases += Invoke-WaitCase -Name "wait-target"
$cases += Invoke-WaitCase -Name "locked-log-target" -ExclusiveLogLock

$normalTarget = Start-Target -Name "normal-exit-target" -SleepSeconds 1
try {
    $normalTarget.Process.WaitForExit(10000) | Out-Null
    $diagnosticDir = Join-Path $normalTarget.Directory "diagnostic"
    $result = Invoke-CampfireLightweightNgxDiagnostic -ProcessId $normalTarget.Process.Id -ExpectedExecutable $powershell -ExpectedStartTimeUtc $normalTarget.ExpectedStartUtc -OutputDir $diagnosticDir -LifecyclePath $normalTarget.Lifecycle -LogPath $normalTarget.Log -DebuggerTimeoutSeconds 5
    $cases += [ordered]@{
        name = "normal-exit-target"
        status = if (-not $result.diagnostic_capture_succeeded -and $result.helper_guard.process_absent) { "pass" } else { "fail" }
        diagnostic_capture_succeeded = [bool]$result.diagnostic_capture_succeeded
        diagnostic_helper = $result.helper_guard
        cdb_started = Test-Path -LiteralPath (Join-Path $diagnosticDir "cdb-thread-stacks.log")
    }
} finally { $normalTarget.Process.Dispose() }

$timeoutTarget = Start-Target -Name "cdb-timeout-target" -SleepSeconds 120
try {
    $dir = $timeoutTarget.Directory
    $diagnosticDir = Join-Path $dir "diagnostic"
    $markers = Join-Path $dir "diagnostic.markers.jsonl"
    $guard = Invoke-Phase6EaGuardedHelper -FilePath $powershell -ArgumentList @(
        "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", $helperScript,
        "-ProcessId", [string]$timeoutTarget.Process.Id,
        "-ExpectedExecutable", $powershell,
        "-ExpectedStartTimeUtc", $timeoutTarget.ExpectedStartUtc.ToString("o"),
        "-OutputDir", $diagnosticDir,
        "-LifecyclePath", $timeoutTarget.Lifecycle,
        "-LogPath", $timeoutTarget.Log,
        "-MarkerPath", $markers,
        "-DebuggerTimeoutSeconds", "2",
        "-FixtureCdbSleepMilliseconds", "10000"
    ) -StdoutPath (Join-Path $dir "helper.stdout.log") -StderrPath (Join-Path $dir "helper.stderr.log") -TimeoutSeconds 30 -PrivateBytesLimit 512MB -MaximumStdoutBytes 2MB -MaximumStderrBytes 2MB
    $report = Read-Diagnostic $diagnosticDir
    $cases += [ordered]@{
        name = "cdb-timeout-target"
        status = if ($report.debugger.timed_out -and $report.debugger.process_absent -and $guard.process_absent -and ($null -ne (Get-Process -Id $timeoutTarget.Process.Id -ErrorAction SilentlyContinue))) { "pass" } else { "fail" }
        debugger = $report.debugger
        diagnostic_helper = $guard
        target_alive_after_cdb_timeout = ($null -ne (Get-Process -Id $timeoutTarget.Process.Id -ErrorAction SilentlyContinue))
        target_resource_before = $report.process.resource_before
        target_resource_after = $report.process.resource_after
    }
} finally { Stop-ExactTarget $timeoutTarget }

$abnormalDir = Join-Path $output "cdb-abnormal-exit"
New-Item -ItemType Directory -Path $abnormalDir | Out-Null
$abnormal = Invoke-Phase6EaGuardedHelper -FilePath $cdb -ArgumentList @("-campfire-invalid-switch") -StdoutPath (Join-Path $abnormalDir "cdb.stdout.log") -StderrPath (Join-Path $abnormalDir "cdb.stderr.log") -TimeoutSeconds 10 -PrivateBytesLimit 512MB -MaximumStdoutBytes 2MB -MaximumStderrBytes 2MB
$cases += [ordered]@{
    name = "cdb-abnormal-exit"
    status = if (-not $abnormal.timed_out -and -not $abnormal.private_bytes_exceeded -and $abnormal.process_absent -and $abnormal.exit_code -ne 0) { "pass" } else { "fail" }
    guard = $abnormal
}

$configurationAfter = Get-MachineDebugConfigurationSnapshot
$allPass = -not ($cases | Where-Object { $_.status -ne "pass" })
$report = [ordered]@{
    schema = "campfire.phase6el.cdb-diagnostic-fixtures.v1"
    phase = "phase6el"
    status = if ($allPass -and $configurationBefore.sha256 -eq $configurationAfter.sha256) { "pass" } else { "fail" }
    cdb = $cdbMetadata
    attach_contract = [ordered]@{
        residual_only = $true
        identity = "pid+process_start_time+absolute_executable_path"
        noninvasive = $true
        system_wide_debugger_registration = $false
        stdout_direct_to_file = $true
        stderr_direct_to_file = $true
        stack_log_limit_bytes = $CampfireCdbStackLogLimitBytes
        stderr_limit_bytes = $CampfireCdbStderrLimitBytes
        private_bytes_limit = $CampfireShutdownHelperPrivateBytesLimit
        known_ngx_requires_accepted_stack_signature = $true
    }
    cases = $cases
    machine_debug_configuration = [ordered]@{
        before_sha256 = $configurationBefore.sha256
        after_sha256 = $configurationAfter.sha256
        changed = ($configurationBefore.sha256 -ne $configurationAfter.sha256)
        inspected_paths = @($configurationBefore.records | ForEach-Object { $_.path })
    }
    process_remainder = [ordered]@{
        fixture_targets = 0
        cdb = @(Get-Process cdb -ErrorAction SilentlyContinue).Count
    }
}
Write-CampfireBoundedJson -Path (Join-Path $output "report.json") -Value $report
if ($report.status -ne "pass") { throw "Phase 6EL CDB diagnostic fixtures failed" }
Write-Host "Phase 6EL CDB diagnostic fixtures passed"
