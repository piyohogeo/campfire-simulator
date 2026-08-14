Set-StrictMode -Version 3.0

$phase6EaCommon = Join-Path $PSScriptRoot "phase6ea_diagnostic_common.ps1"
if (-not (Get-Command Invoke-Phase6EaGuardedHelper -ErrorAction SilentlyContinue)) {
    . $phase6EaCommon
}

$CampfireKnownNgxSignature = "ngx_telemetry_shutdown_wait_v1"
$CampfireShutdownHelperPrivateBytesLimit = 512MB
$CampfireShutdownDiagnosticTimeoutSeconds = 240
$CampfireShutdownDiagnosticJsonLimitBytes = 2MB
$CampfireCdbStackLogLimitBytes = 16MB
$CampfireCdbStderrLimitBytes = 2MB

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
    $candidates = @(
        "C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\cdb.exe",
        "C:\Program Files\Windows Kits\10\Debuggers\x64\cdb.exe"
    ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }
    $windowsAppsRoot = "C:\Program Files\WindowsApps"
    $windowsAppsCandidates = @(
        Get-ChildItem -LiteralPath $windowsAppsRoot -Directory -Filter "Microsoft.WinDbg_*_x64__8wekyb3d8bbwe" -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName "amd64\cdb.exe" } |
            Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }
    )
    $candidates = @($candidates) + @($windowsAppsCandidates)
    if ($candidates.Count -eq 0) { return $null }
    return [IO.Path]::GetFullPath($candidates[0])
}

function Get-CampfireCdbMetadata {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    $item = Get-Item -LiteralPath $Path
    return [ordered]@{
        path = [IO.Path]::GetFullPath($item.FullName)
        file_version = $item.VersionInfo.FileVersion
        product_version = $item.VersionInfo.ProductVersion
        bytes = $item.Length
        sha256 = [Phase6EaFileSafety]::ComputeSha256($item.FullName)
    }
}

function Get-CampfireProcessResourceSnapshot {
    param([Parameter(Mandatory = $true)][System.Diagnostics.Process]$Process)
    try {
        $Process.Refresh()
        return [ordered]@{
            pid = $Process.Id
            private_bytes = $Process.PrivateMemorySize64
            working_set_bytes = $Process.WorkingSet64
            user_cpu_seconds = $Process.UserProcessorTime.TotalSeconds
            kernel_cpu_seconds = $Process.PrivilegedProcessorTime.TotalSeconds
            total_cpu_seconds = $Process.TotalProcessorTime.TotalSeconds
        }
    } catch { return $null }
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

function Invoke-CampfireCdbStackFirstCapture {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][string]$ExpectedExecutable,
        [Parameter(Mandatory = $true)][datetime]$ExpectedStartTimeUtc,
        [Parameter(Mandatory = $true)][string]$OutputDir,
        [Parameter(Mandatory = $true)][string]$MarkerPath,
        [ValidateRange(5, 120)][int]$StackTimeoutSeconds = 80,
        [ValidateRange(5, 120)][int]$ModuleTimeoutSeconds = 30,
        [ValidateRange(5, 60)][int]$DetachTimeoutSeconds = 10,
        [ValidateRange(15, 30)][int]$NoProgressTimeoutSeconds = 20,
        [ValidateRange(0, 60000)][int]$FixtureCdbSleepMilliseconds = 0,
        [ValidateRange(0, 60000)][int]$FixtureModuleCdbSleepMilliseconds = 0,
        [ValidateRange(0, 60000)][int]$FixtureDetachCdbSleepMilliseconds = 0
    )
    $output = [IO.Path]::GetFullPath($OutputDir)
    $expected = [IO.Path]::GetFullPath($ExpectedExecutable)
    $cdb = Get-CampfireCdbPath
    $metadata = Get-CampfireCdbMetadata -Path $cdb
    $symbolCache = Join-Path $output "symbols"
    New-Item -ItemType Directory -Path $symbolCache -Force | Out-Null
    $stackLog = Join-Path $output "cdb-thread-stacks.log"
    $stackError = Join-Path $output "cdb-thread-stacks.stderr.log"
    $moduleLog = Join-Path $output "cdb-modules.log"
    $moduleError = Join-Path $output "cdb-modules.stderr.log"
    $detachLog = Join-Path $output "cdb-detach.log"
    $detachError = Join-Path $output "cdb-detach.stderr.log"
    $stackGuard = $null
    $moduleGuard = $null
    $detachGuard = $null
    $stackAttachObserved = $false
    $stackObserved = $false
    $nativeFramesObserved = $false
    $stackDetached = $false
    $moduleAttachObserved = $false
    $modulesObserved = $false
    $moduleDetached = $false
    $detachAttachObserved = $false
    $detachObserved = $false
    $errorMessage = $null
    if ($null -eq $cdb) {
        return [pscustomobject]@{
            cdb_path=$null; cdb=$null; error="installed WinDbg CDB not found"; stack_guard=$null
            module_guard=$null; detach_guard=$null; stack_attach_observed=$false
            all_thread_stack_observed=$false; native_frames_observed=$false
            modules_observed=$false; detach_observed=$false; process_absent=$true
            raw_stack_log=$stackLog; raw_module_log=$moduleLog; raw_detach_log=$detachLog
            stack_stderr_log=$stackError; module_stderr_log=$moduleError; detach_stderr_log=$detachError
            symbol_cache=$symbolCache
            timeout_seconds=[ordered]@{ no_progress=$NoProgressTimeoutSeconds; stack_absolute=$StackTimeoutSeconds; modules_absolute=$ModuleTimeoutSeconds; detach_absolute=$DetachTimeoutSeconds; worst_case_total=($StackTimeoutSeconds+$ModuleTimeoutSeconds+$DetachTimeoutSeconds) }
            symbol_contract="local cache only; no symbol server wait; raw module+offset evidence accepted as partial"
        }
    }
    try {
        $stackCommands = @(
            ".echo ===== CDB_STACK_ATTACH_CONFIRMED =====",
            ".symopt+ 0x100",
            "!sym quiet",
            ".echo ===== THREAD_STACKS =====",
            "~* kPn 16"
        )
        if ($FixtureCdbSleepMilliseconds -gt 0) { $stackCommands += ".sleep $FixtureCdbSleepMilliseconds" }
        $stackCommands += @(
            ".echo ===== THREAD_STACKS_COMPLETE =====",
            ".echo ===== CDB_STACK_DETACHING =====",
            "qd"
        )
        $stackCommandFile = Join-Path $output "cdb-stack-first-commands.txt"
        [IO.File]::WriteAllLines($stackCommandFile, $stackCommands, [Text.UTF8Encoding]::new($false))

        # Stack evidence is the primary objective.  It is deliberately first,
        # local-cache-only, and independent from module enumeration.
        $null = Test-Phase6EaProcessIdentity -ProcessId $ProcessId -ExpectedExecutable $expected -ExpectedStartTimeUtc $ExpectedStartTimeUtc
        Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "cdb_attach_started" -Details @{ target_pid=$ProcessId; debugger_path=$cdb; pass="stack_first" }
        Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "cdb_stack_capture_started" -Details @{ absolute_timeout_seconds=$StackTimeoutSeconds; no_progress_timeout_seconds=$NoProgressTimeoutSeconds; stack_depth=16; symbol_path="local_cache_only" }
        $stackGuard = Invoke-Phase6EaGuardedHelper -FilePath $cdb -ArgumentList @("-p", [string]$ProcessId, "-pv", "-y", $symbolCache, "-cf", $stackCommandFile) -StdoutPath $stackLog -StderrPath $stackError -TimeoutSeconds $StackTimeoutSeconds -NoProgressTimeoutSeconds $NoProgressTimeoutSeconds -PrivateBytesLimit $CampfireShutdownHelperPrivateBytesLimit -MaximumStdoutBytes $CampfireCdbStackLogLimitBytes -MaximumStderrBytes $CampfireCdbStderrLimitBytes
        $stackAttachObserved = Test-CampfireLogPattern -Path $stackLog -Pattern "CDB_STACK_ATTACH_CONFIRMED"
        $stackObserved = (Test-CampfireLogPattern -Path $stackLog -Pattern "THREAD_STACKS") -and (Test-CampfireLogPattern -Path $stackLog -Pattern "THREAD_STACKS_COMPLETE")
        $nativeFramesObserved = Test-CampfireLogPattern -Path $stackLog -Pattern "Child-SP\s+RetAddr|ntdll!|KERNELBASE!|\w+\.dll\+0x[0-9a-f]+"
        $stackDetached = Test-CampfireLogPattern -Path $stackLog -Pattern "CDB_STACK_DETACHING"
        if ($stackAttachObserved) { Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "cdb_attach_complete" -Details @{ pass="stack_first" } }
        if ($stackObserved -and $nativeFramesObserved) { Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "cdb_stack_capture_complete" -Details @{ bytes=(Get-Item -LiteralPath $stackLog).Length } }

        # Module enumeration is auxiliary and cannot gate already captured
        # stacks.  A timeout here remains explicit partial evidence.
        $moduleCommandFile = Join-Path $output "cdb-module-after-stack-commands.txt"
        $moduleCommands = @(
            ".echo ===== CDB_MODULE_ATTACH_CONFIRMED =====",
            ".echo ===== LOADED_MODULES =====",
            "lm"
        )
        if ($FixtureModuleCdbSleepMilliseconds -gt 0) { $moduleCommands += ".sleep $FixtureModuleCdbSleepMilliseconds" }
        $moduleCommands += @(
            ".echo ===== LOADED_MODULES_COMPLETE =====",
            ".echo ===== CDB_MODULE_DETACHING =====",
            "qd"
        )
        [IO.File]::WriteAllLines($moduleCommandFile, $moduleCommands, [Text.UTF8Encoding]::new($false))
        $null = Test-Phase6EaProcessIdentity -ProcessId $ProcessId -ExpectedExecutable $expected -ExpectedStartTimeUtc $ExpectedStartTimeUtc
        Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "cdb_module_capture_started" -Details @{ absolute_timeout_seconds=$ModuleTimeoutSeconds; no_progress_timeout_seconds=$NoProgressTimeoutSeconds; order="after_stack" }
        $moduleGuard = Invoke-Phase6EaGuardedHelper -FilePath $cdb -ArgumentList @("-p", [string]$ProcessId, "-pv", "-y", $symbolCache, "-cf", $moduleCommandFile) -StdoutPath $moduleLog -StderrPath $moduleError -TimeoutSeconds $ModuleTimeoutSeconds -NoProgressTimeoutSeconds $NoProgressTimeoutSeconds -PrivateBytesLimit $CampfireShutdownHelperPrivateBytesLimit -MaximumStdoutBytes $CampfireCdbStackLogLimitBytes -MaximumStderrBytes $CampfireCdbStderrLimitBytes
        $moduleAttachObserved = Test-CampfireLogPattern -Path $moduleLog -Pattern "CDB_MODULE_ATTACH_CONFIRMED"
        $modulesObserved = (Test-CampfireLogPattern -Path $moduleLog -Pattern "LOADED_MODULES") -and (Test-CampfireLogPattern -Path $moduleLog -Pattern "LOADED_MODULES_COMPLETE")
        $moduleDetached = Test-CampfireLogPattern -Path $moduleLog -Pattern "CDB_MODULE_DETACHING"
        if ($modulesObserved) { Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "cdb_module_capture_complete" -Details @{ bytes=(Get-Item -LiteralPath $moduleLog).Length } }

        # Always perform an independent, bounded attach/detach pass.  This does
        # not terminate the target and makes detach evidence independent from
        # truncated stack or module output.
        $detachCommandFile = Join-Path $output "cdb-explicit-detach-commands.txt"
        $detachCommands = @(
            ".echo ===== CDB_DETACH_ATTACH_CONFIRMED =====",
            ".echo ===== CDB_EXPLICIT_DETACHING ====="
        )
        if ($FixtureDetachCdbSleepMilliseconds -gt 0) { $detachCommands += ".sleep $FixtureDetachCdbSleepMilliseconds" }
        $detachCommands += "qd"
        [IO.File]::WriteAllLines($detachCommandFile, $detachCommands, [Text.UTF8Encoding]::new($false))
        $null = Test-Phase6EaProcessIdentity -ProcessId $ProcessId -ExpectedExecutable $expected -ExpectedStartTimeUtc $ExpectedStartTimeUtc
        Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "cdb_detach_started" -Details @{ absolute_timeout_seconds=$DetachTimeoutSeconds; no_progress_timeout_seconds=[math]::Min($NoProgressTimeoutSeconds, $DetachTimeoutSeconds) }
        $detachGuard = Invoke-Phase6EaGuardedHelper -FilePath $cdb -ArgumentList @("-p", [string]$ProcessId, "-pv", "-y", $symbolCache, "-cf", $detachCommandFile) -StdoutPath $detachLog -StderrPath $detachError -TimeoutSeconds $DetachTimeoutSeconds -NoProgressTimeoutSeconds ([math]::Min($NoProgressTimeoutSeconds, $DetachTimeoutSeconds)) -PrivateBytesLimit $CampfireShutdownHelperPrivateBytesLimit -MaximumStdoutBytes 2MB -MaximumStderrBytes $CampfireCdbStderrLimitBytes
        $detachAttachObserved = Test-CampfireLogPattern -Path $detachLog -Pattern "CDB_DETACH_ATTACH_CONFIRMED"
        $detachObserved = (Test-CampfireLogPattern -Path $detachLog -Pattern "CDB_EXPLICIT_DETACHING") -and $detachGuard.process_absent -and -not $detachGuard.timed_out
        if ($detachObserved) { Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "cdb_detach_complete" -Details @{ independent_cleanup_pass=$true } }
    } catch {
        $errorMessage = $_.Exception.Message
    }
    $guards = @($stackGuard, $moduleGuard, $detachGuard) | Where-Object { $null -ne $_ }
    $allCdbAbsent = -not [bool]($guards | Where-Object { -not $_.process_absent })
    Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "cdb_cleanup_complete" -Details @{
        process_absent=[bool]$allCdbAbsent
        stack_timed_out=if ($null -ne $stackGuard) { [bool]$stackGuard.timed_out } else { $false }
        module_timed_out=if ($null -ne $moduleGuard) { [bool]$moduleGuard.timed_out } else { $false }
        detach_timed_out=if ($null -ne $detachGuard) { [bool]$detachGuard.timed_out } else { $false }
    }
    return [pscustomobject]@{
        cdb_path=$cdb; cdb=$metadata; error=$errorMessage
        stack_guard=$stackGuard; module_guard=$moduleGuard; detach_guard=$detachGuard
        stack_attach_observed=$stackAttachObserved; stack_detached_in_pass=$stackDetached
        module_attach_observed=$moduleAttachObserved; module_detached_in_pass=$moduleDetached
        detach_attach_observed=$detachAttachObserved
        all_thread_stack_observed=$stackObserved; native_frames_observed=$nativeFramesObserved
        modules_observed=$modulesObserved; detach_observed=$detachObserved
        process_absent=[bool]$allCdbAbsent
        raw_stack_log=$stackLog; raw_module_log=$moduleLog; raw_detach_log=$detachLog
        stack_stderr_log=$stackError; module_stderr_log=$moduleError; detach_stderr_log=$detachError
        symbol_cache=$symbolCache
        stack_evidence=if ($stackObserved -and $nativeFramesObserved) { "complete" } elseif ($stackAttachObserved -or $nativeFramesObserved) { "partial" } else { "none" }
        module_evidence=if ($modulesObserved) { "complete" } elseif ($moduleAttachObserved) { "partial" } else { "none" }
        timeout_seconds=[ordered]@{ no_progress=$NoProgressTimeoutSeconds; stack_absolute=$StackTimeoutSeconds; modules_absolute=$ModuleTimeoutSeconds; detach_absolute=$DetachTimeoutSeconds; worst_case_total=($StackTimeoutSeconds+$ModuleTimeoutSeconds+$DetachTimeoutSeconds) }
        symbol_contract="local cache only; no symbol server wait; raw module+offset evidence accepted as partial"
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
        [int]$DebuggerTimeoutSeconds = 120,
        [ValidateRange(0, 60000)][int]$FixtureCdbSleepMilliseconds = 0
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
        $targetResourceBefore = Get-CampfireProcessResourceSnapshot -Process $process
        $lifecycle = $null
        Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "kit_log_parse_started"
        if (Test-Path -LiteralPath $LifecyclePath) {
            try { $lifecycle = Read-CampfireBoundedJson -Path $LifecyclePath -MaximumBytes 1MB } catch {}
        }
        $lastLog = @()
        $logCaptureError = $null
        try {
            $lastLog = @(Get-CampfireBoundedTailLines -Path $LogPath -MaximumLines 120 -MaximumCharactersPerLine 8192)
        } catch {
            # The Kit logger may temporarily hold an exclusive handle during a
            # shutdown hang. Log tailing is auxiliary evidence and must not
            # prevent the bounded diagnostic report from being committed.
            $logCaptureError = $_.Exception.Message
        }
        Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "kit_log_parse_complete" -Details @{ line_count = $lastLog.Count; error = $logCaptureError }

        Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "gpu_inventory_started"
        $gpuInventoryCapture = Get-CampfireGpuInventory -OutputDir $output
        Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "gpu_inventory_complete" -Details @{ succeeded = [bool]$gpuInventoryCapture.evidence.succeeded; row_count = @($gpuInventoryCapture.rows).Count }

        $cdb = Get-CampfireCdbPath
        Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "dump_cdb_decision" -Details @{ dump_required = $false; cdb_available = ($null -ne $cdb); order = "stack_first" }
        $cdbCapture = Invoke-CampfireCdbStackFirstCapture `
            -ProcessId $ProcessId `
            -ExpectedExecutable $expected `
            -ExpectedStartTimeUtc $ExpectedStartTimeUtc `
            -OutputDir $output `
            -MarkerPath $MarkerPath `
            -StackTimeoutSeconds ([math]::Max(5, [math]::Min(80, $DebuggerTimeoutSeconds))) `
            -ModuleTimeoutSeconds ([math]::Max(5, [math]::Min(30, $DebuggerTimeoutSeconds))) `
            -DetachTimeoutSeconds ([math]::Max(5, [math]::Min(10, $DebuggerTimeoutSeconds))) `
            -FixtureCdbSleepMilliseconds $FixtureCdbSleepMilliseconds
        $cdbMetadata = $cdbCapture.cdb
        $moduleLog = $cdbCapture.raw_module_log
        $stackLog = $cdbCapture.raw_stack_log
        $stackError = $cdbCapture.stack_stderr_log
        $symbolCache = $cdbCapture.symbol_cache
        $moduleGuard = $cdbCapture.module_guard
        $stackGuard = $cdbCapture.stack_guard
        $detachGuard = $cdbCapture.detach_guard
        $cdbError = $cdbCapture.error
        $attachObserved = [bool]$cdbCapture.stack_attach_observed
        $stackObserved = [bool]$cdbCapture.all_thread_stack_observed
        $nativeFramesObserved = [bool]$cdbCapture.native_frames_observed
        $modulesObserved = [bool]$cdbCapture.modules_observed
        $detachObserved = [bool]$cdbCapture.detach_observed
        $tokens = [ordered]@{
            gpu_foundation_shutdown = Test-CampfireLogPattern -Path $stackLog -Pattern "gpu_foundation_plugin!carbOnPluginShutdown|gpu\.foundation\.plugin(?:\.dll)?\+0x18F4D3"
            ngx_d3d12_shutdown = Test-CampfireLogPattern -Path $stackLog -Pattern "NVSDK_NGX_D3D12_Shutdown"
            telemetry_uninitialize = Test-CampfireLogPattern -Path $stackLog -Pattern "NvTelemetryAPI64!UninitializeTelemetry"
            telemetry_named_pipe_wait = Test-CampfireLogPattern -Path $stackLog -Pattern "KERNELBASE!WaitNamedPipeW"
            telemetry_bridge_stack = Test-CampfireLogPattern -Path $stackLog -Pattern "NvTelemetryBridge64(?:!|\.dll\+)"
        }
        $cdbGuards = [Collections.Generic.List[object]]::new()
        foreach ($item in @($moduleGuard, $stackGuard, $detachGuard)) { if ($null -ne $item) { $cdbGuards.Add([pscustomobject]$item) } }
        $primaryCdbGuards = @($stackGuard, $detachGuard) | Where-Object { $null -ne $_ }
        $guardSucceeded = $null -ne $stackGuard -and $null -ne $detachGuard -and $detachObserved -and -not ($primaryCdbGuards | Where-Object { $_.timed_out -or $_.private_bytes_exceeded -or $_.output_bytes_exceeded -or -not $_.process_absent -or $_.exit_code_error -ne $null -or $_.exit_code -ne 0 })
        # Module enumeration is auxiliary.  A bounded module timeout must not
        # discard an already complete all-thread stack and explicit detach.
        $cdbCaptureComplete = $attachObserved -and $stackObserved -and $nativeFramesObserved -and $detachObserved
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
        $diagnosticCaptureSucceeded = $guardSucceeded -and $cdbCaptureComplete -and [bool]$gpuInventoryCapture.evidence.succeeded
        $targetResourceAfter = Get-CampfireProcessResourceSnapshot -Process $process
        $report = [ordered]@{
            schema = "campfire.kit-lightweight-shutdown-diagnostic.v3"
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
                resource_before = $targetResourceBefore
                resource_after = $targetResourceAfter
            }
            lifecycle_marker = if ($null -ne $lifecycle) { $lifecycle.lifecycle_marker } else { $null }
            lifecycle_history = if ($null -ne $lifecycle -and $null -ne $lifecycle.lifecycle_history) { @($lifecycle.lifecycle_history | Select-Object -Last 128) } else { @() }
            completion_contract = if ($null -ne $lifecycle -and $null -ne $lifecycle.completion_contract) { $lifecycle.completion_contract } else { $null }
            final_log_lines = @($lastLog)
            log_capture_error = $logCaptureError
            gpu_inventory = @($gpuInventoryCapture.rows)
            gpu_inventory_capture = $gpuInventoryCapture.evidence
            debugger = [ordered]@{
                cdb_path = $cdb
                cdb = $cdbMetadata
                noninvasive_attach = $true
                diagnostic_order = "stack_first_then_auxiliary_modules_then_explicit_detach"
                module_evidence_required = $false
                symbol_contract = $cdbCapture.symbol_contract
                timeout_seconds = $DebuggerTimeoutSeconds
                timed_out = [bool]($cdbGuards | Where-Object { $_.timed_out })
                private_bytes_exceeded = [bool]($cdbGuards | Where-Object { $_.private_bytes_exceeded })
                output_bytes_exceeded = [bool]($cdbGuards | Where-Object { $_.output_bytes_exceeded })
                peak_private_bytes = if ($cdbGuards.Count) { ($cdbGuards | Measure-Object -Property peak_private_bytes -Maximum).Maximum } else { $null }
                user_cpu_seconds = if ($cdbGuards.Count) { ($cdbGuards | Measure-Object -Property user_cpu_seconds -Sum).Sum } else { $null }
                kernel_cpu_seconds = if ($cdbGuards.Count) { ($cdbGuards | Measure-Object -Property kernel_cpu_seconds -Sum).Sum } else { $null }
                total_cpu_seconds = if ($cdbGuards.Count) { ($cdbGuards | Measure-Object -Property total_cpu_seconds -Sum).Sum } else { $null }
                stdout_bytes = if ($cdbGuards.Count) { ($cdbGuards | Measure-Object -Property stdout_bytes -Sum).Sum } else { $null }
                stderr_bytes = if ($cdbGuards.Count) { ($cdbGuards | Measure-Object -Property stderr_bytes -Sum).Sum } else { $null }
                stdout_limit_bytes = $CampfireCdbStackLogLimitBytes
                stderr_limit_bytes = $CampfireCdbStderrLimitBytes
                process_absent = -not [bool]($cdbGuards | Where-Object { -not $_.process_absent })
                exit_code = if ($guardSucceeded) { 0 } else { $null }
                error = $cdbError
                attach_observed = $attachObserved
                all_thread_stack_observed = $stackObserved
                native_frames_observed = $nativeFramesObserved
                loaded_modules_observed = $modulesObserved
                detach_observed = $detachObserved
                raw_stack_log = $stackLog
                raw_module_log = $moduleLog
                raw_detach_log = $cdbCapture.raw_detach_log
                stderr_log = $stackError
                symbol_cache = $symbolCache
                full_dump_created = $false
                stage_timeouts_seconds = $cdbCapture.timeout_seconds
                passes = [ordered]@{ all_thread_stacks = $stackGuard; auxiliary_modules = $moduleGuard; explicit_detach = $detachGuard }
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
        [int]$DebuggerTimeoutSeconds = 120
    )
    $output = [IO.Path]::GetFullPath($OutputDir)
    $markerPath = "$output.markers.jsonl"
    $stdout = "$output.helper.stdout.log"
    $stderr = "$output.helper.stderr.log"
    $resultPath = Join-Path $output "lightweight_shutdown_diagnostic.json"
    $partialResultPath = "$output.partial-diagnostic.json"
    $ownershipPath = "$output.ownership.json"
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
    $ownership = [ordered]@{
        schema="campfire.shutdown-diagnostic-ownership.v1"; owner_pid=$PID
        owner_start_time_utc=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToString("o")
        target_pid=$ProcessId; target_start_time_utc=$ExpectedStartTimeUtc.ToUniversalTime().ToString("o")
        target_path=[IO.Path]::GetFullPath($ExpectedExecutable); acquired_at_utc=[datetime]::UtcNow.ToString("o")
        absolute_deadline_utc=[datetime]::UtcNow.AddSeconds($CampfireShutdownDiagnosticTimeoutSeconds + 15).ToString("o")
    }
    $ownershipBytes = [Text.UTF8Encoding]::new($false).GetBytes(($ownership | ConvertTo-Json -Depth 8) + [Environment]::NewLine)
    $ownershipStream = [IO.FileStream]::new($ownershipPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    try { $ownershipStream.Write($ownershipBytes, 0, $ownershipBytes.Length); $ownershipStream.Flush($true) } finally { $ownershipStream.Dispose() }
    Write-CampfireDiagnosticMarker -Path $markerPath -Marker "diagnostic_ownership_acquired" -Details @{ ownership_path=$ownershipPath; absolute_deadline_utc=$ownership.absolute_deadline_utc }
    $guard = $null
    try {
        $guard = Invoke-Phase6EaGuardedHelper -FilePath $powershell -ArgumentList $arguments -StdoutPath $stdout -StderrPath $stderr -TimeoutSeconds $CampfireShutdownDiagnosticTimeoutSeconds -PrivateBytesLimit $CampfireShutdownHelperPrivateBytesLimit -MaximumStdoutBytes $CampfireShutdownDiagnosticJsonLimitBytes -MaximumStderrBytes $CampfireShutdownDiagnosticJsonLimitBytes
        Write-CampfireDiagnosticMarker -Path $markerPath -Marker "parent_process_returned" -Details @{ helper_exit_code = $guard.exit_code; timed_out = $guard.timed_out; private_bytes_exceeded = $guard.private_bytes_exceeded }
        if ($guard.timed_out -or $guard.private_bytes_exceeded -or $guard.output_bytes_exceeded -or -not $guard.process_absent -or $guard.exit_code_error -ne $null -or $guard.exit_code -ne 0) {
            $partial = [ordered]@{
                schema="campfire.kit-lightweight-shutdown-diagnostic-partial.v1"
                diagnostic_capture_succeeded=$false; error="isolated lightweight diagnostic helper failed"
                helper_guard=$guard; marker_path=$markerPath; target_identity=$ownership
                partial_artifact_committed=$true; committed_at_utc=[datetime]::UtcNow.ToString("o")
                stack_fingerprint=[ordered]@{ name=$CampfireKnownNgxSignature; matched=$false }
            }
            Write-CampfireBoundedJson -Path $partialResultPath -Value $partial
            return $partial
        }
        if (-not (Test-Path -LiteralPath $resultPath -PathType Leaf)) { throw "isolated lightweight diagnostic did not write its bounded result" }
        $result = Read-CampfireBoundedJson -Path $resultPath
        $result | Add-Member -NotePropertyName helper_guard -NotePropertyValue $guard -Force
        $result | Add-Member -NotePropertyName marker_path -NotePropertyValue $markerPath -Force
        return $result
    } finally {
        if (Test-Path -LiteralPath $ownershipPath -PathType Leaf) { Remove-Item -LiteralPath $ownershipPath -Force }
        Write-CampfireDiagnosticMarker -Path $markerPath -Marker "diagnostic_ownership_released"
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
        [int]$AbsoluteTimeoutSeconds = 420,
        [switch]$SkipLowLevelDiagnostic
    )
    $expected = [IO.Path]::GetFullPath($ExpectedExecutable)
    $expectedStartUtc = $Process.StartTime.ToUniversalTime()
    $nativeHandle = $Process.Handle
    $started = Get-Date
    $shutdownObserved = $null
    $lastMarker = $null
    $absoluteTimedOut = $false
    $confirmedExited = $false
    while (-not $confirmedExited) {
        $cachedExited = $false
        try { $cachedExited = [bool]$Process.HasExited } catch { $cachedExited = $false }
        if ($cachedExited) {
            $identityState = Get-Phase6EaProcessIdentityState -ProcessId $Process.Id -ExpectedExecutable $expected -ExpectedStartTimeUtc $expectedStartUtc
            if ($identityState.state -eq "confirmed_exited") { $confirmedExited = $true; break }
            # A cached Process/handle result is never sufficient evidence of
            # absence.  Unknown or a live exact match remains on the bounded
            # diagnostic path; identity mismatch fails closed below.
            if ($identityState.state -eq "alive_identity_mismatch") { break }
        }
        $now = Get-Date
        $lastMarker = Get-CampfireLifecycleMarker -LifecyclePath $LifecyclePath
        if ($lastMarker -in @("shutdown_requested", "shutdown_complete") -and $null -eq $shutdownObserved) { $shutdownObserved = $now }
        if ($null -ne $shutdownObserved -and ($now - $shutdownObserved).TotalSeconds -ge $ShutdownGraceSeconds) { break }
        if (($now - $started).TotalSeconds -ge $AbsoluteTimeoutSeconds) { $absoluteTimedOut = $true; break }
        Start-Sleep -Milliseconds 250
        $Process.Refresh()
    }
    try { $Process.Refresh() } catch {}
    if ($confirmedExited) {
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
        if ($SkipLowLevelDiagnostic.IsPresent) {
            $diagnostic = [ordered]@{
                diagnostic_capture_succeeded = $false
                skipped_by_contract = $true
                stack_fingerprint = [ordered]@{ name = $CampfireKnownNgxSignature; matched = $false }
            }
        } else {
            $diagnostic = Invoke-CampfireLightweightNgxDiagnostic -ProcessId $Process.Id -ExpectedExecutable $expected -ExpectedStartTimeUtc $expectedStartUtc -OutputDir $DiagnosticDir -LifecyclePath $LifecyclePath -LogPath $LogPath
        }
    } catch {
        $diagnostic = [ordered]@{ diagnostic_capture_succeeded = $false; error = $_.Exception.Message; stack_fingerprint = [ordered]@{ name = $CampfireKnownNgxSignature; matched = $false } }
    }
    $diagnosticSucceeded = [bool]($null -ne $diagnostic -and $diagnostic.diagnostic_capture_succeeded)
    if ($identityVerified) {
        try {
            $live = Test-Phase6EaProcessIdentity -ProcessId $Process.Id -ExpectedExecutable $expected -ExpectedStartTimeUtc $expectedStartUtc
            $identityVerified = $true
            $startTimeVerified = $true
            $terminationAttempted = $true
            Stop-Process -Id $Process.Id -Force
            $Process.WaitForExit(10000) | Out-Null
            $absenceState = Get-Phase6EaProcessIdentityState -ProcessId $Process.Id -ExpectedExecutable $expected -ExpectedStartTimeUtc $expectedStartUtc
            $terminationSucceeded = $absenceState.state -eq "confirmed_exited"
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
