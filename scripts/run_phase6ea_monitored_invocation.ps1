param(
    [Parameter(Mandatory = $true)][string]$InvocationScript,
    [Parameter(Mandatory = $true)][string[]]$InvocationArguments,
    [Parameter(Mandatory = $true)][string]$KitExecutable,
    [Parameter(Mandatory = $true)][string]$ConditionOutputDir,
    [Parameter(Mandatory = $true)][string]$MonitorOutputDir,
    [int]$ShutdownObservationSeconds = 45,
    [int]$AbsoluteTimeoutSeconds = 420
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$scriptPath = [IO.Path]::GetFullPath($InvocationScript)
$kitPath = [IO.Path]::GetFullPath($KitExecutable)
$conditionOutput = [IO.Path]::GetFullPath($ConditionOutputDir)
$monitorOutput = [IO.Path]::GetFullPath($MonitorOutputDir)
if (Test-Path -LiteralPath $monitorOutput) { throw "Phase 6EA refuses monitor output reuse: $monitorOutput" }
New-Item -ItemType Directory -Path $monitorOutput | Out-Null
$stdout = Join-Path $monitorOutput "invocation.stdout.log"
$stderr = Join-Path $monitorOutput "invocation.stderr.log"
$evidencePath = Join-Path $monitorOutput "monitor_evidence.json"
$raw = Join-Path $conditionOutput "raw.json"
$kitLog = Join-Path $conditionOutput "kit.log"
$diagnosticDir = Join-Path $monitorOutput "sensitive-hang-diagnostics"

function Get-DescendantProcesses([int]$RootPid) {
    $all = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    $result = @()
    $frontier = @($RootPid)
    while ($frontier.Count -gt 0) {
        $parents = @($frontier)
        $frontier = @()
        foreach ($item in $all) {
            if ([int]$item.ParentProcessId -in $parents -and [int]$item.ProcessId -notin @($result | ForEach-Object { [int]$_.ProcessId })) {
                $result += $item
                $frontier += [int]$item.ProcessId
            }
        }
    }
    return @($result)
}

function Get-LifecycleMarker {
    if (-not (Test-Path -LiteralPath $raw)) { return $null }
    try { return (Get-Content -LiteralPath $raw -Raw -Encoding UTF8 | ConvertFrom-Json).lifecycle_marker } catch { return $null }
}

$powershell = (Get-Process -Id $PID).Path
$childArgs = @("-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $scriptPath) + $InvocationArguments
$started = Get-Date
$outer = Start-Process -FilePath $powershell -ArgumentList $childArgs -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
$kitPid = $null
$shutdownObserved = $null
$hangDetected = $false
$absoluteTimeout = $false
$diagnosticError = $null
$stoppedVerifiedKit = $false

while (-not $outer.HasExited) {
    $now = Get-Date
    if (($now - $started).TotalSeconds -ge $AbsoluteTimeoutSeconds) {
        $absoluteTimeout = $true
        break
    }
    try {
        $descendants = @(Get-DescendantProcesses -RootPid $outer.Id)
        foreach ($candidate in $descendants) {
            if (-not $candidate.ExecutablePath) { continue }
            if ([IO.Path]::GetFullPath([string]$candidate.ExecutablePath) -eq $kitPath) {
                $kitPid = [int]$candidate.ProcessId
                break
            }
        }
    } catch {}
    if ($null -eq $kitPid) {
        $pathMatches = @(
            Get-Process -Name kit -ErrorAction SilentlyContinue |
                Where-Object {
                    try {
                        [IO.Path]::GetFullPath($_.Path) -eq $kitPath -and $_.StartTime -ge $started.AddSeconds(-2)
                    } catch { $false }
                }
        )
        if ($pathMatches.Count -eq 1) { $kitPid = $pathMatches[0].Id }
    }
    $marker = Get-LifecycleMarker
    if ($marker -eq "shutdown_requested" -and $null -eq $shutdownObserved) { $shutdownObserved = $now }
    if ($null -ne $shutdownObserved -and $null -ne $kitPid -and ($now - $shutdownObserved).TotalSeconds -ge $ShutdownObservationSeconds) {
        try {
            $kitProcess = Get-Process -Id $kitPid -ErrorAction Stop
            if ([IO.Path]::GetFullPath($kitProcess.Path) -ne $kitPath) { throw "Kit PID path changed before diagnostic capture" }
            $hangDetected = $true
            & (Join-Path $PSScriptRoot "capture_phase6ea_hang_diagnostics.ps1") -ProcessId $kitPid -ExpectedExecutable $kitPath -OutputDir $diagnosticDir -LifecyclePath $raw -LogPath $kitLog
            $kitProcess = Get-Process -Id $kitPid -ErrorAction Stop
            if ([IO.Path]::GetFullPath($kitProcess.Path) -ne $kitPath) { throw "Refusing to stop unexpected executable after capture" }
            Stop-Process -Id $kitPid -Force
            $stoppedVerifiedKit = $true
        } catch {
            $diagnosticError = $_.Exception.Message
        }
        break
    }
    Start-Sleep -Milliseconds 500
    $outer.Refresh()
}

if ($absoluteTimeout -and $null -ne $kitPid) {
    try {
        $kitProcess = Get-Process -Id $kitPid -ErrorAction Stop
        if ([IO.Path]::GetFullPath($kitProcess.Path) -ne $kitPath) { throw "Refusing timeout diagnostics for unexpected executable" }
        & (Join-Path $PSScriptRoot "capture_phase6ea_hang_diagnostics.ps1") -ProcessId $kitPid -ExpectedExecutable $kitPath -OutputDir $diagnosticDir -LifecyclePath $raw -LogPath $kitLog
        Stop-Process -Id $kitPid -Force
        $stoppedVerifiedKit = $true
    } catch { $diagnosticError = $_.Exception.Message }
}

if (-not $outer.HasExited) { $outer.WaitForExit(30000) | Out-Null }
$outer.Refresh()
$ended = Get-Date
$kitStillPresent = $false
if ($null -ne $kitPid) { $kitStillPresent = $null -ne (Get-Process -Id $kitPid -ErrorAction SilentlyContinue) }
$evidence = [ordered]@{
    schema = "campfire.phase6ea.monitored-invocation.v1"
    phase = "phase6ea"
    invocation_script = $scriptPath
    invocation_arguments = @($InvocationArguments)
    started_local = $started.ToString("o")
    ended_local = $ended.ToString("o")
    duration_seconds = ($ended - $started).TotalSeconds
    outer_pid = $outer.Id
    outer_exit_code = if ($outer.HasExited) { $outer.ExitCode } else { $null }
    kit_pid = $kitPid
    shutdown_marker_observed = ($null -ne $shutdownObserved)
    shutdown_marker_time_local = if ($null -ne $shutdownObserved) { $shutdownObserved.ToString("o") } else { $null }
    shutdown_observation_seconds = $ShutdownObservationSeconds
    hang_detected = $hangDetected
    absolute_timeout = $absoluteTimeout
    diagnostic_error = $diagnosticError
    diagnostic_directory = if (Test-Path -LiteralPath $diagnosticDir) { $diagnosticDir } else { $null }
    stopped_path_verified_kit = $stoppedVerifiedKit
    kit_pid_absent_after_stop = (-not $kitStillPresent)
    automatic_retry = $false
    machine_wide_configuration_changed = $false
}
[IO.File]::WriteAllText($evidencePath, ($evidence | ConvertTo-Json -Depth 12) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))

if ($diagnosticError) { throw "Phase 6EA diagnostic capture failed: $diagnosticError" }
if ($absoluteTimeout) { throw "Phase 6EA invocation reached absolute timeout" }
if ($hangDetected) { throw "Phase 6EA detected a residual Kit process after shutdown_requested" }
if (-not $outer.HasExited) { throw "Phase 6EA outer runner did not exit" }
if ($outer.ExitCode -ne 0) { throw "Phase 6EA invocation failed with exit code $($outer.ExitCode)" }
Write-Host "Phase 6EA monitored invocation exited normally"
