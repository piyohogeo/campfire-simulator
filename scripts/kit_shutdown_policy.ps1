Set-StrictMode -Version 3.0

$phase6EaCommon = Join-Path $PSScriptRoot "phase6ea_diagnostic_common.ps1"
if (-not (Get-Command Invoke-Phase6EaGuardedHelper -ErrorAction SilentlyContinue)) {
    . $phase6EaCommon
}

$CampfireKnownNgxSignature = "ngx_telemetry_shutdown_wait_v1"
$CampfireShutdownHelperPrivateBytesLimit = 512MB

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
    return [pscustomobject]@{
        rows = @($rows)
        evidence = [ordered]@{
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
    $expected = [IO.Path]::GetFullPath($ExpectedExecutable)
    $lockPath = $null
    try {
        $lockPath = Enter-Phase6EaCaptureLock -CanonicalOutputPath $output -TargetProcessId $ProcessId
        if (Test-Path -LiteralPath $output) { throw "Shutdown diagnostic output already exists: $output" }
        New-Item -ItemType Directory -Path $output | Out-Null
        $process = Test-Phase6EaProcessIdentity -ProcessId $ProcessId -ExpectedExecutable $expected -ExpectedStartTimeUtc $ExpectedStartTimeUtc
        $actual = [IO.Path]::GetFullPath($process.Path)
        $lifecycle = $null
        if (Test-Path -LiteralPath $LifecyclePath) {
            try { $lifecycle = Get-Content -LiteralPath $LifecyclePath -Raw -Encoding UTF8 | ConvertFrom-Json } catch {}
        }
        $lastLog = @()
        if (Test-Path -LiteralPath $LogPath) { $lastLog = @(Get-Content -LiteralPath $LogPath -Tail 120 -Encoding UTF8) }
        $cdb = Get-CampfireCdbPath
        $stackLog = Join-Path $output "cdb-thread-stacks.log"
        $stackError = Join-Path $output "cdb-thread-stacks.stderr.log"
        $symbolCache = Join-Path $output "symbols"
        New-Item -ItemType Directory -Path $symbolCache | Out-Null
        $guard = $null
        $cdbError = $null
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
        $gpuInventoryCapture = Get-CampfireGpuInventory -OutputDir $output
        $report = [ordered]@{
            schema = "campfire.kit-lightweight-shutdown-diagnostic.v2"
            timestamp_local = (Get-Date).ToString("o")
            diagnostic_capture_succeeded = $guardSucceeded
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
            lifecycle_history = if ($null -ne $lifecycle -and $null -ne $lifecycle.lifecycle_history) { @($lifecycle.lifecycle_history) } else { @() }
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
        [IO.File]::WriteAllText($reportPath, ($report | ConvertTo-Json -Depth 20) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
        return $report
    } finally {
        if ($null -ne $lockPath) { Exit-Phase6EaCaptureLock -LockPath $lockPath }
    }
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
