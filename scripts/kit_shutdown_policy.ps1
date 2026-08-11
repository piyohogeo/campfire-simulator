Set-StrictMode -Version 3.0

$phase6EaCommon = Join-Path $PSScriptRoot "phase6ea_diagnostic_common.ps1"
if (-not (Get-Command Invoke-Phase6EaGuardedHelper -ErrorAction SilentlyContinue)) {
    . $phase6EaCommon
}

$CampfireKnownNgxSignature = "ngx_telemetry_shutdown_wait_v1"
$CampfireShutdownHelperPrivateBytesLimit = 512MB
$CampfireShutdownDiagnosticTimeoutSeconds = 90
$CampfireShutdownDiagnosticJsonLimitBytes = 2MB

function Write-CampfireDiagnosticMarker {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Marker,
        [hashtable]$Details = @{}
    )
    $record = [ordered]@{
        schema = "campfire.lightweight-shutdown-diagnostic-marker.v1"
        timestamp_utc = [datetime]::UtcNow.ToString("o")
        process_id = $PID
        marker = $Marker
        details = $Details
    }
    $line = ($record | ConvertTo-Json -Depth 6 -Compress) + [Environment]::NewLine
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($line)
    $stream = [IO.FileStream]::new([IO.Path]::GetFullPath($Path), [IO.FileMode]::Append, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite)
    try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
}

function Read-CampfireBoundedJson {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [long]$MaximumBytes = $CampfireShutdownDiagnosticJsonLimitBytes
    )
    $item = Get-Item -LiteralPath $Path -ErrorAction Stop
    if ($item.Length -le 0 -or $item.Length -gt $MaximumBytes) { throw "JSON size is outside the fixed bound: $($item.Length)" }
    $stream = [IO.FileStream]::new($item.FullName, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        $reader = [IO.StreamReader]::new($stream, [Text.Encoding]::UTF8, $true, 65536, $false)
        try { return $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
    } finally { $stream.Dispose() }
}

function Get-CampfireBoundedTailLines {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [int]$MaximumLines = 120,
        [int]$MaximumCharactersPerLine = 8192
    )
    $queue = [Collections.Generic.Queue[string]]::new($MaximumLines)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return @() }
    foreach ($line in [IO.File]::ReadLines([IO.Path]::GetFullPath($Path), [Text.Encoding]::UTF8)) {
        $bounded = if ($line.Length -gt $MaximumCharactersPerLine) { $line.Substring(0, $MaximumCharactersPerLine) } else { $line }
        if ($queue.Count -eq $MaximumLines) { $null = $queue.Dequeue() }
        $queue.Enqueue($bounded)
    }
    return @($queue.ToArray())
}

function Write-CampfireBoundedJson {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][object]$Value,
        [long]$MaximumBytes = $CampfireShutdownDiagnosticJsonLimitBytes
    )
    $json = ($Value | ConvertTo-Json -Depth 20) + [Environment]::NewLine
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($json)
    if ($bytes.Length -gt $MaximumBytes) { throw "JSON output exceeds fixed bound: $($bytes.Length)" }
    $temporary = "$Path.partial"
    $stream = [IO.FileStream]::new($temporary, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Test-CampfireLogPattern {
    param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)][string]$Pattern)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    return [bool](Select-String -LiteralPath $Path -Pattern $Pattern -Encoding UTF8 -Quiet)
}

function Get-CampfireWindowsExceptionEvidence {
    param([Parameter(Mandatory = $true)][string]$Path)
    $result = [ordered]@{
        available = $false
        windows_exception_present = $false
        access_violation_present = $false
        kind = $null
        line_number = $null
        matched_text = $null
        error = $null
    }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        $result.error = "log_missing_or_not_file"
        return [pscustomobject]$result
    }
    $explicitContextPattern = '(?i)(?:\bexception\s*[_ ]?code\s*[:=]\s*|\bunhandled\s+exception\b[^\r\n]*?|\bprocess\s+exited\s+with\s+(?:exit\s+)?code\s*[:=]?\s*)0xC[0-9A-F]{7}\b'
    $accessViolationPattern = '(?i)\baccess\s+violation\b'
    $accessViolationCodePattern = '(?i)\b0xC0000005\b'
    $benignValueContextPattern = '(?i)\b(?:sub\s*system\s+id|device\s+id|vendor\s+id|bus\s+id|gpu\s+uuid|uuid|driver|firmware|pci|address|hash|colou?r|bitmask|mask)\b[^\r\n]*?(?:[:=]\s*)?0xC0000005\b'
    try {
        $lineNumber = 0
        foreach ($line in [IO.File]::ReadLines([IO.Path]::GetFullPath($Path), [Text.Encoding]::UTF8)) {
            $lineNumber += 1
            $match = [regex]::Match($line, $accessViolationPattern)
            if ($match.Success) {
                $result.available = $true
                $result.windows_exception_present = $true
                $result.access_violation_present = $true
                $result.kind = "access_violation_text"
                $result.line_number = $lineNumber
                $result.matched_text = $match.Value
                return [pscustomobject]$result
            }
            $match = [regex]::Match($line, $explicitContextPattern)
            if ($match.Success) {
                $result.available = $true
                $result.windows_exception_present = $true
                $result.access_violation_present = [regex]::IsMatch($match.Value, $accessViolationCodePattern)
                $result.kind = "explicit_exception_context"
                $result.line_number = $lineNumber
                $result.matched_text = $match.Value
                return [pscustomobject]$result
            }
            $match = [regex]::Match($line, $accessViolationCodePattern)
            if ($match.Success -and -not [regex]::IsMatch($line, $benignValueContextPattern)) {
                $result.available = $true
                $result.windows_exception_present = $true
                $result.access_violation_present = $true
                $result.kind = "access_violation_code"
                $result.line_number = $lineNumber
                $result.matched_text = $match.Value
                return [pscustomobject]$result
            }
        }
        $result.available = $true
    } catch {
        $result.error = "log_unreadable:$($_.Exception.GetType().Name)"
    }
    return [pscustomobject]$result
}

function Get-CampfireLifecycleMarker([string]$LifecyclePath) {
    if (-not (Test-Path -LiteralPath $LifecyclePath -PathType Leaf)) { return $null }
    try { return (Get-Content -LiteralPath $LifecyclePath -Raw -Encoding UTF8 | ConvertFrom-Json).lifecycle_marker } catch { return $null }
}

function Get-CampfireCdbPath {
    $root = "C:\Program Files\WindowsApps"
    $candidates = @(
        Get-ChildItem -LiteralPath $root -Directory -Filter "Microsoft.WinDbg_*_x64__8wekyb3d8bbwe" -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName "amd64\cdb.exe" } |
            Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }
    )
    if ($candidates.Count -eq 0) { return $null }
    return [IO.Path]::GetFullPath($candidates[0])
}

function Get-CampfireGpuInventory {
    param([Parameter(Mandatory = $true)][string]$OutputDir)
    $output = [IO.Path]::GetFullPath($OutputDir)
    $stdout = Join-Path $output "gpu-inventory.stdout.csv"
    $stderr = Join-Path $output "gpu-inventory.stderr.log"
    $guard = $null
    $errorMessage = $null
    $rows = @()
    try {
        $executable = (Get-Command nvidia-smi.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
        $guard = Invoke-Phase6EaGuardedHelper -FilePath $executable -ArgumentList @("--query-gpu=index,uuid,name,pci.bus_id,driver_version,display_active", "--format=csv,noheader,nounits") -StdoutPath $stdout -StderrPath $stderr -TimeoutSeconds 15 -PrivateBytesLimit 128MB
        if ($guard.timed_out -or $guard.private_bytes_exceeded -or -not $guard.process_absent -or $guard.exit_code_error -ne $null -or $guard.exit_code -ne 0) {
            throw "guarded nvidia-smi inventory failed"
        }
        foreach ($line in [IO.File]::ReadLines($stdout, [Text.Encoding]::UTF8)) {
            $values = @($line -split ',\s*')
            if ($values.Count -eq 6) {
                $rows += [ordered]@{ index=$values[0]; uuid=$values[1]; name=$values[2]; pci_bus_id=$values[3]; driver_version=$values[4]; display_active=$values[5] }
            }
        }
    } catch { $errorMessage = $_.Exception.Message }
    $succeeded = $null -eq $errorMessage -and @($rows).Count -gt 0
    return [pscustomobject]@{
        rows = @($rows)
        evidence = [ordered]@{
            succeeded = $succeeded
            isolated_process = $true
            stdout_direct_to_file = $true
            stderr_direct_to_file = $true
            timeout_seconds = 15
            private_bytes_limit = 134217728
            guard = $guard
            error = $errorMessage
            stdout_path = $stdout
            stderr_path = $stderr
        }
    }
}

function Invoke-CampfireLightweightNgxDiagnosticCore {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][string]$ExpectedExecutable,
        [Parameter(Mandatory = $true)][datetime]$ExpectedStartTimeUtc,
        [Parameter(Mandatory = $true)][string]$OutputDir,
        [Parameter(Mandatory = $true)][string]$LifecyclePath,
        [Parameter(Mandatory = $true)][string]$LogPath,
        [Parameter(Mandatory = $true)][string]$MarkerPath,
        [int]$DebuggerTimeoutSeconds = 45
    )
    $output = [IO.Path]::GetFullPath($OutputDir)
    $expected = [IO.Path]::GetFullPath($ExpectedExecutable)
    $lockPath = $null
    try {
        Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "process_identity_started"
        $process = Test-Phase6EaProcessIdentity -ProcessId $ProcessId -ExpectedExecutable $expected -ExpectedStartTimeUtc $ExpectedStartTimeUtc
        Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "process_identity_complete" -Details @{ target_pid = $ProcessId }
        $lockPath = Enter-Phase6EaCaptureLock -CanonicalOutputPath $output -TargetProcessId $ProcessId
        Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "capture_lock_acquired"
        if (Test-Path -LiteralPath $output) { throw "Shutdown diagnostic output already exists: $output" }
        New-Item -ItemType Directory -Path $output | Out-Null
        $actual = [IO.Path]::GetFullPath($process.Path)
        $lifecycle = $null
        Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "kit_log_parse_started"
        if (Test-Path -LiteralPath $LifecyclePath) {
            try { $lifecycle = Read-CampfireBoundedJson -Path $LifecyclePath -MaximumBytes 1MB } catch {}
        }
        $lastLog = @(Get-CampfireBoundedTailLines -Path $LogPath -MaximumLines 120 -MaximumCharactersPerLine 8192)
        Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "kit_log_parse_complete" -Details @{ line_count = $lastLog.Count }

        Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "gpu_inventory_started"
        $gpuInventoryCapture = Get-CampfireGpuInventory -OutputDir $output
        Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "gpu_inventory_complete" -Details @{ succeeded = [bool]$gpuInventoryCapture.evidence.succeeded; row_count = @($gpuInventoryCapture.rows).Count }

        $cdb = Get-CampfireCdbPath
        $stackLog = Join-Path $output "cdb-thread-stacks.log"
        $stackError = Join-Path $output "cdb-thread-stacks.stderr.log"
        $symbolCache = Join-Path $output "symbols"
        New-Item -ItemType Directory -Path $symbolCache | Out-Null
        $guard = $null
        $cdbError = $null
        Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "dump_cdb_decision" -Details @{ dump_required = $false; cdb_available = ($null -ne $cdb) }
        if ($null -ne $cdb) {
            try {
                $symbolPath = "srv*$symbolCache*https://msdl.microsoft.com/download/symbols"
                $commandFile = Join-Path $output "cdb-commands.txt"
                [IO.File]::WriteAllLines($commandFile, @(".reload /f ntdll.dll KERNELBASE.dll", ".echo ===== THREAD_STACKS =====", "~* kPn 48", "qd"), [Text.UTF8Encoding]::new($false))
                $guard = Invoke-Phase6EaGuardedHelper -FilePath $cdb -ArgumentList @("-p", [string]$ProcessId, "-pv", "-y", $symbolPath, "-cf", $commandFile) -StdoutPath $stackLog -StderrPath $stackError -TimeoutSeconds $DebuggerTimeoutSeconds -PrivateBytesLimit $CampfireShutdownHelperPrivateBytesLimit
            } catch { $cdbError = $_.Exception.Message }
        } else {
            $cdbError = "installed WinDbg CDB not found"
        }
        $tokens = [ordered]@{
            gpu_foundation_shutdown = Test-CampfireLogPattern -Path $stackLog -Pattern "gpu_foundation_plugin!carbOnPluginShutdown|gpu\.foundation\.plugin(?:\.dll)?\+0x18F4D3"
            ngx_d3d12_shutdown = Test-CampfireLogPattern -Path $stackLog -Pattern "NVSDK_NGX_D3D12_Shutdown"
            telemetry_uninitialize = Test-CampfireLogPattern -Path $stackLog -Pattern "NvTelemetryAPI64!UninitializeTelemetry"
            telemetry_named_pipe_wait = Test-CampfireLogPattern -Path $stackLog -Pattern "KERNELBASE!WaitNamedPipeW"
            telemetry_bridge_stack = Test-CampfireLogPattern -Path $stackLog -Pattern "NvTelemetryBridge64(?:!|\.dll\+)"
        }
        $guardSucceeded = $null -ne $guard -and -not $guard.timed_out -and -not $guard.private_bytes_exceeded -and $guard.process_absent -and $guard.exit_code_error -eq $null -and $guard.exit_code -eq 0
        $knownSignature = $guardSucceeded -and -not ($tokens.Values -contains $false)
        $fingerprint = [ordered]@{
            name = $CampfireKnownNgxSignature
            matched = $knownSignature
            required_tokens = $tokens
            observed_reference_offsets = [ordered]@{
                gpu_foundation_plugin = "0x18F4D3 (reference dump; live stack may resolve symbol only)"
                ngx_shutdown = "NVSDK_NGX_D3D12_Shutdown1+0x82 (reference dump)"
                telemetry_uninitialize = "UninitializeTelemetry+0xAF (reference dump)"
                telemetry_worker = "NvTelemetryBridge64.dll+0x134F8 (reference dump)"
            }
            known_chain = "gpu.foundation shutdown -> NGX D3D12 shutdown -> NvTelemetryAPI64 UninitializeTelemetry -> telemetry worker WaitNamedPipeW"
        }
        $diagnosticCaptureSucceeded = $guardSucceeded -and [bool]$gpuInventoryCapture.evidence.succeeded
        $report = [ordered]@{
            schema = "campfire.kit-lightweight-shutdown-diagnostic.v2"
            timestamp_local = (Get-Date).ToString("o")
            diagnostic_capture_succeeded = $diagnosticCaptureSucceeded
            process_identity_verified = $true
            process_start_time_verified = $true
            process = [ordered]@{
                pid = $ProcessId
                executable = $actual
                start_time_utc = $process.StartTime.ToUniversalTime().ToString("o")
                thread_count = $process.Threads.Count
                handle_count = $process.HandleCount
                file_version = $process.MainModule.FileVersionInfo.FileVersion
            }
            lifecycle_marker = if ($null -ne $lifecycle) { $lifecycle.lifecycle_marker } else { $null }
            lifecycle_history = if ($null -ne $lifecycle -and $null -ne $lifecycle.lifecycle_history) { @($lifecycle.lifecycle_history | Select-Object -Last 128) } else { @() }
            completion_contract = if ($null -ne $lifecycle -and $null -ne $lifecycle.completion_contract) { $lifecycle.completion_contract } else { $null }
            final_log_lines = @($lastLog)
            gpu_inventory = @($gpuInventoryCapture.rows)
            gpu_inventory_capture = $gpuInventoryCapture.evidence
            debugger = [ordered]@{
                cdb_path = $cdb
                noninvasive_attach = $true
                timeout_seconds = $DebuggerTimeoutSeconds
                timed_out = if ($null -ne $guard) { [bool]$guard.timed_out } else { $false }
                private_bytes_exceeded = if ($null -ne $guard) { [bool]$guard.private_bytes_exceeded } else { $false }
                peak_private_bytes = if ($null -ne $guard) { $guard.peak_private_bytes } else { $null }
                process_absent = if ($null -ne $guard) { [bool]$guard.process_absent } else { $true }
                exit_code = if ($null -ne $guard) { $guard.exit_code } else { $null }
                error = $cdbError
                raw_stack_log = $stackLog
                stderr_log = $stackError
                symbol_cache = $symbolCache
                full_dump_created = $false
            }
            stack_fingerprint = $fingerprint
            machine_wide_configuration_changed = $false
        }
        $reportPath = Join-Path $output "lightweight_shutdown_diagnostic.json"
        Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "diagnostic_json_write_started"
        Write-CampfireBoundedJson -Path $reportPath -Value $report
        Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "diagnostic_json_write_complete" -Details @{ bytes = (Get-Item -LiteralPath $reportPath).Length }
        return $report
    } finally {
        Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "cleanup_started"
        if ($null -ne $lockPath) { Exit-Phase6EaCaptureLock -LockPath $lockPath }
        Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "cleanup_complete"
    }
}

function Invoke-CampfireLightweightNgxDiagnostic {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][string]$ExpectedExecutable,
        [Parameter(Mandatory = $true)][datetime]$ExpectedStartTimeUtc,
        [Parameter(Mandatory = $true)][string]$OutputDir,
        [Parameter(Mandatory = $true)][string]$LifecyclePath,
        [Parameter(Mandatory = $true)][string]$LogPath,
        [int]$DebuggerTimeoutSeconds = 45
    )
    $output = [IO.Path]::GetFullPath($OutputDir)
    $markerPath = "$output.markers.jsonl"
    $stdout = "$output.helper.stdout.log"
    $stderr = "$output.helper.stderr.log"
    $resultPath = Join-Path $output "lightweight_shutdown_diagnostic.json"
    $helper = Join-Path $PSScriptRoot "run_lightweight_shutdown_diagnostic_helper.ps1"
    $powershell = (Get-Process -Id $PID).Path
    $arguments = @(
        "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", $helper,
        "-ProcessId", [string]$ProcessId,
        "-ExpectedExecutable", $ExpectedExecutable,
        "-ExpectedStartTimeUtc", $ExpectedStartTimeUtc.ToUniversalTime().ToString("o"),
        "-OutputDir", $output,
        "-LifecyclePath", $LifecyclePath,
        "-LogPath", $LogPath,
        "-MarkerPath", $markerPath,
        "-DebuggerTimeoutSeconds", [string]$DebuggerTimeoutSeconds
    )
    $guard = Invoke-Phase6EaGuardedHelper -FilePath $powershell -ArgumentList $arguments -StdoutPath $stdout -StderrPath $stderr -TimeoutSeconds $CampfireShutdownDiagnosticTimeoutSeconds -PrivateBytesLimit $CampfireShutdownHelperPrivateBytesLimit
    Write-CampfireDiagnosticMarker -Path $markerPath -Marker "parent_process_returned" -Details @{ helper_exit_code = $guard.exit_code; timed_out = $guard.timed_out; private_bytes_exceeded = $guard.private_bytes_exceeded }
    if ($guard.timed_out -or $guard.private_bytes_exceeded -or -not $guard.process_absent -or $guard.exit_code_error -ne $null -or $guard.exit_code -ne 0) {
        return [ordered]@{
            diagnostic_capture_succeeded = $false
            error = "isolated lightweight diagnostic helper failed"
            helper_guard = $guard
            marker_path = $markerPath
            stack_fingerprint = [ordered]@{ name = $CampfireKnownNgxSignature; matched = $false }
        }
    }
    if (-not (Test-Path -LiteralPath $resultPath -PathType Leaf)) { throw "isolated lightweight diagnostic did not write its bounded result" }
    $result = Read-CampfireBoundedJson -Path $resultPath
    $result | Add-Member -NotePropertyName helper_guard -NotePropertyValue $guard -Force
    $result | Add-Member -NotePropertyName marker_path -NotePropertyValue $markerPath -Force
    return $result
}

function Wait-CampfireKitProcessWithShutdownPolicy {
    param(
        [Parameter(Mandatory = $true)][System.Diagnostics.Process]$Process,
        [Parameter(Mandatory = $true)][string]$ExpectedExecutable,
        [Parameter(Mandatory = $true)][string]$LifecyclePath,
        [Parameter(Mandatory = $true)][string]$LogPath,
        [Parameter(Mandatory = $true)][string]$DiagnosticDir,
        [int]$ShutdownGraceSeconds = 60,
        [int]$AbsoluteTimeoutSeconds = 420
    )
    $expected = [IO.Path]::GetFullPath($ExpectedExecutable)
    $expectedStartUtc = $Process.StartTime.ToUniversalTime()
    $nativeHandle = $Process.Handle
    $started = Get-Date
    $shutdownObserved = $null
    $lastMarker = $null
    $absoluteTimedOut = $false
    while (-not $Process.HasExited) {
        $now = Get-Date
        $lastMarker = Get-CampfireLifecycleMarker -LifecyclePath $LifecyclePath
        if ($lastMarker -in @("shutdown_requested", "shutdown_complete") -and $null -eq $shutdownObserved) { $shutdownObserved = $now }
        if ($null -ne $shutdownObserved -and ($now - $shutdownObserved).TotalSeconds -ge $ShutdownGraceSeconds) { break }
        if (($now - $started).TotalSeconds -ge $AbsoluteTimeoutSeconds) { $absoluteTimedOut = $true; break }
        Start-Sleep -Milliseconds 250
        $Process.Refresh()
    }
    $Process.Refresh()
    if ($Process.HasExited) {
        $lastMarker = Get-CampfireLifecycleMarker -LifecyclePath $LifecyclePath
        if ($lastMarker -in @("shutdown_requested", "shutdown_complete") -and $null -eq $shutdownObserved) { $shutdownObserved = Get-Date }
        $exitCode = $null
        try { $exitCode = [Phase6EaFileSafety]::ReadExitCode($nativeHandle) } catch {}
        return [ordered]@{
            lifecycle_candidate = "normal_exit"
            exit_code = $exitCode
            shutdown_marker_observed = ($null -ne $shutdownObserved)
            shutdown_grace_seconds = $ShutdownGraceSeconds
            exited_within_shutdown_grace = ($null -ne $shutdownObserved)
            pid = $Process.Id
            pid_and_executable_verified = $true
            process_start_time_verified = $true
            known_signature_matched = $false
            known_signature_name = $null
            diagnostic_capture_succeeded = $false
            terminated_by_outer_runner = $false
            pid_absent_after_termination = $true
            residual_process = $false
            absolute_timeout = $absoluteTimedOut
            windows_exception_present = $false
            fault_module = $null
            fault_offset = $null
            dump_count = 0
            diagnostic = $null
            last_lifecycle_marker = $lastMarker
        }
    }
    $identityVerified = $false
    $startTimeVerified = $false
    $diagnostic = $null
    $terminationAttempted = $false
    $terminationSucceeded = $false
    try {
        $live = Test-Phase6EaProcessIdentity -ProcessId $Process.Id -ExpectedExecutable $expected -ExpectedStartTimeUtc $expectedStartUtc
        $identityVerified = $true
        $startTimeVerified = $true
        $diagnostic = Invoke-CampfireLightweightNgxDiagnostic -ProcessId $Process.Id -ExpectedExecutable $expected -ExpectedStartTimeUtc $expectedStartUtc -OutputDir $DiagnosticDir -LifecyclePath $LifecyclePath -LogPath $LogPath
    } catch {
        $diagnostic = [ordered]@{ diagnostic_capture_succeeded = $false; error = $_.Exception.Message; stack_fingerprint = [ordered]@{ name = $CampfireKnownNgxSignature; matched = $false } }
    }
    $diagnosticSucceeded = [bool]($null -ne $diagnostic -and $diagnostic.diagnostic_capture_succeeded)
    if ($diagnosticSucceeded) {
        try {
            $live = Test-Phase6EaProcessIdentity -ProcessId $Process.Id -ExpectedExecutable $expected -ExpectedStartTimeUtc $expectedStartUtc
            $identityVerified = $true
            $startTimeVerified = $true
            $terminationAttempted = $true
            Stop-Process -Id $Process.Id -Force
            $Process.WaitForExit(10000) | Out-Null
            $terminationSucceeded = $null -eq (Get-Process -Id $Process.Id -ErrorAction SilentlyContinue)
        } catch {
            $diagnostic | Add-Member -NotePropertyName termination_error -NotePropertyValue $_.Exception.Message -Force
        }
    }
    $known = [bool]($null -ne $shutdownObserved -and $identityVerified -and $startTimeVerified -and $diagnosticSucceeded -and $diagnostic.stack_fingerprint.name -eq $CampfireKnownNgxSignature -and $diagnostic.stack_fingerprint.matched -and $terminationSucceeded)
    return [ordered]@{
        lifecycle_candidate = if ($known) { "known_ngx_shutdown_residual" } else { "unknown_shutdown_failure" }
        exit_code = $null
        shutdown_marker_observed = ($null -ne $shutdownObserved)
        shutdown_grace_seconds = $ShutdownGraceSeconds
        exited_within_shutdown_grace = $false
        pid = $Process.Id
        pid_and_executable_verified = $identityVerified
        process_start_time_verified = $startTimeVerified
        known_signature_matched = $known
        known_signature_name = if ($known) { $CampfireKnownNgxSignature } else { $diagnostic.stack_fingerprint.name }
        diagnostic_capture_succeeded = $diagnosticSucceeded
        terminated_by_outer_runner = $terminationAttempted
        pid_absent_after_termination = $terminationSucceeded
        residual_process = $true
        absolute_timeout = $absoluteTimedOut
        windows_exception_present = $false
        fault_module = $null
        fault_offset = $null
        dump_count = 0
        diagnostic = $diagnostic
        last_lifecycle_marker = $lastMarker
    }
}

function Invoke-CampfireShutdownOutcomeClassification {
    param(
        [Parameter(Mandatory = $true)][object]$Monitor,
        [Parameter(Mandatory = $true)][object]$ProbeReport,
        [Parameter(Mandatory = $true)][string]$LogPath,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]]$FatalLines,
        [Parameter(Mandatory = $true)][int]$DumpCount,
        [Parameter(Mandatory = $true)][int]$UploadAttemptCount,
        [Parameter(Mandatory = $true)][string]$ProductionHashBefore,
        [Parameter(Mandatory = $true)][string]$ProductionHashAfter,
        [Parameter(Mandatory = $true)][string]$OutputDir
    )
    $windowsExceptionEvidence = Get-CampfireWindowsExceptionEvidence -Path $LogPath
    $windowsException = [bool]$windowsExceptionEvidence.windows_exception_present
    $accessViolation = [bool]$windowsExceptionEvidence.access_violation_present
    $deviceFailure = Test-CampfireLogPattern -Path $LogPath -Pattern "(?i)(device lost|\bTDR\b)"
    $cudaFailure = Test-CampfireLogPattern -Path $LogPath -Pattern "(?i)CUDA illegal address"
    $contract = if ($null -ne $ProbeReport -and $null -ne $ProbeReport.completion_contract) { $ProbeReport.completion_contract } else { [pscustomobject]@{} }
    function Get-ContractBoolean([object]$Value, [string]$Name) {
        $property = $Value.PSObject.Properties[$Name]
        return [bool]($null -ne $property -and $property.Value -eq $true)
    }
    foreach ($field in @(
        @{ Name="dump_count"; Value=$DumpCount },
        @{ Name="windows_exception_present"; Value=$windowsException },
        @{ Name="windows_exception_evidence_available"; Value=[bool]$windowsExceptionEvidence.available },
        @{ Name="windows_exception_evidence_kind"; Value=$windowsExceptionEvidence.kind },
        @{ Name="windows_exception_evidence_line_number"; Value=$windowsExceptionEvidence.line_number },
        @{ Name="fault_module"; Value=if ($windowsException) { "unparsed" } else { $null } },
        @{ Name="fault_offset"; Value=if ($windowsException) { "unparsed" } else { $null } }
    )) {
        if ($Monitor -is [System.Collections.IDictionary]) { $Monitor[$field.Name] = $field.Value }
        else { $Monitor | Add-Member -NotePropertyName $field.Name -NotePropertyValue $field.Value -Force }
    }
    $input = [ordered]@{
        schema = "campfire.kit-shutdown-classification-input.v1"
        completion = [ordered]@{
            probe_complete = ($ProbeReport.status -eq "ok")
            results_saved = Get-ContractBoolean $contract "results_saved"
            timeline_stopped = Get-ContractBoolean $contract "timeline_stopped"
            stage_closed = Get-ContractBoolean $contract "stage_closed"
            renderer_drained = Get-ContractBoolean $contract "renderer_drained"
            shutdown_requested = Get-ContractBoolean $contract "shutdown_requested"
        }
        safety = [ordered]@{
            production_app_unchanged = ($ProductionHashBefore -eq $ProductionHashAfter)
            no_fatal = ($FatalLines.Count -eq 0)
            no_crash_dump = ($DumpCount -eq 0)
            no_windows_exception = ([bool]$windowsExceptionEvidence.available -and -not $windowsException)
            no_access_violation = -not $accessViolation
            no_device_lost_or_tdr = -not $deviceFailure
            no_cuda_illegal_address = -not $cudaFailure
            no_upload_attempt = ($UploadAttemptCount -eq 0)
        }
        process = $Monitor
    }
    $output = [IO.Path]::GetFullPath($OutputDir)
    $inputPath = Join-Path $output "shutdown_classification_input.json"
    $resultPath = Join-Path $output "shutdown_outcome.json"
    [IO.File]::WriteAllText($inputPath, ($input | ConvertTo-Json -Depth 20) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    $classifier = Join-Path $PSScriptRoot "classify_kit_shutdown_outcome.py"
    $classifierStdout = Join-Path $output "shutdown-classifier.stdout.log"
    $classifierStderr = Join-Path $output "shutdown-classifier.stderr.log"
    $guard = Invoke-Phase6EaGuardedHelper -FilePath "py" -ArgumentList @("-3", $classifier, "--input", $inputPath, "--output", $resultPath) -StdoutPath $classifierStdout -StderrPath $classifierStderr -TimeoutSeconds 30 -PrivateBytesLimit 256MB
    if ($guard.timed_out -or $guard.private_bytes_exceeded -or -not $guard.process_absent -or $guard.exit_code -ne 0 -or -not (Test-Path -LiteralPath $resultPath)) { throw "Kit shutdown outcome classifier failed" }
    return Get-Content -LiteralPath $resultPath -Raw -Encoding UTF8 | ConvertFrom-Json
}
