param(
    [Parameter(Mandatory = $true, ParameterSetName = "Live")][int]$ProcessId,
    [Parameter(Mandatory = $true, ParameterSetName = "Live")][string]$ExpectedExecutable,
    [Parameter(Mandatory = $true, ParameterSetName = "Live")][datetime]$ExpectedProcessStartTimeUtc,
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [Parameter(ParameterSetName = "Live")][string]$LifecyclePath = "",
    [Parameter(ParameterSetName = "Live")][string]$LogPath = "",
    [Parameter(Mandatory = $true, ParameterSetName = "Existing")][string]$ExistingDumpPath,
    [Parameter(ParameterSetName = "Existing")][string]$ExpectedExistingDumpSha256 = "",
    [Parameter(ParameterSetName = "Existing")][switch]$ComputeExistingDumpHash,
    [Parameter(ParameterSetName = "Live")][switch]$SkipDump,
    [ValidateRange(1, 3600)][int]$MaximumDiagnosticSeconds = 360,
    [ValidateRange(1, 120)][int]$WctTimeoutSeconds = 10,
    [ValidateRange(1, 1800)][int]$DumpTimeoutSeconds = 300,
    [long]$HelperPrivateBytesLimit = 536870912,
    [long]$MaximumDumpBytes = 17179869184,
    [long]$DiskSafetyMarginBytes = 2147483648
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
. (Join-Path $PSScriptRoot "phase6ea_diagnostic_common.ps1")

$output = [IO.Path]::GetFullPath($OutputDir)
$dumpPath = if ($PSCmdlet.ParameterSetName -eq "Existing") { [IO.Path]::GetFullPath($ExistingDumpPath) } else { Join-Path $output "hang-full.dmp" }
$targetPid = if ($PSCmdlet.ParameterSetName -eq "Live") { $ProcessId } else { 0 }
$lockPath = $null
$stopwatch = [Diagnostics.Stopwatch]::StartNew()

function Assert-DiagnosticTimeBudget {
    if ($stopwatch.Elapsed.TotalSeconds -ge $MaximumDiagnosticSeconds) { throw "Phase 6EA diagnostic exceeded its total time budget" }
}

if (Test-Path -LiteralPath $output) { throw "Phase 6EA diagnostic output already exists: $output" }
$lockPath = Enter-Phase6EaCaptureLock -CanonicalOutputPath $output -TargetProcessId $targetPid -DumpPath $dumpPath
try {
    New-Item -ItemType Directory -Path $output | Out-Null

    if ($PSCmdlet.ParameterSetName -eq "Existing") {
        if (-not (Test-Path -LiteralPath $dumpPath -PathType Leaf)) { throw "Existing hang dump is missing: $dumpPath" }
        $dump = Get-Item -LiteralPath $dumpPath
        if ($dump.Length -le 4 -or $dump.Length -gt $MaximumDumpBytes) { throw "Existing dump size is outside configured bounds: $($dump.Length)" }
        if (-not [Phase6EaFileSafety]::HasMdmpSignature($dumpPath)) { throw "Existing dump lacks MDMP signature" }
        $hashRequested = $ComputeExistingDumpHash.IsPresent -or [bool]$ExpectedExistingDumpSha256
        $hash = if ($hashRequested) { [Phase6EaFileSafety]::ComputeSha256($dumpPath) } else { $null }
        if ($ExpectedExistingDumpSha256 -and $hash -ne $ExpectedExistingDumpSha256.ToUpperInvariant()) { throw "Existing dump SHA-256 mismatch" }
        $report = [ordered]@{
            schema = "campfire.phase6ea.existing-dump-metadata.v2"
            phase = "phase6ea"
            mode = "existing_dump_read_only"
            timestamp_local = (Get-Date).ToString("o")
            live_process_accessed = $false
            wct_invoked = $false
            stop_process_invoked = $false
            dump = [ordered]@{
                path = $dumpPath
                bytes = $dump.Length
                mdmp_signature_valid = $true
                sha256 = $hash
                hash_computed = $hashRequested
                hash_buffer_bytes = [Phase6EaFileSafety]::HashBufferBytes
                read_only = $true
            }
            limits = [ordered]@{ maximum_dump_bytes=$MaximumDumpBytes; maximum_diagnostic_seconds=$MaximumDiagnosticSeconds }
            machine_wide_configuration_changed = $false
        }
        [IO.File]::WriteAllText((Join-Path $output "hang_diagnostics.json"), ($report | ConvertTo-Json -Depth 12) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
        Write-Host "Phase 6EA existing dump metadata recorded read-only"
        return
    }

    $process = Test-Phase6EaProcessIdentity -ProcessId $ProcessId -ExpectedExecutable $ExpectedExecutable -ExpectedStartTimeUtc $ExpectedProcessStartTimeUtc
    $verifiedStartUtc = $process.StartTime.ToUniversalTime()
    $expected = [IO.Path]::GetFullPath($ExpectedExecutable)
    $cimError = $null
    $cim = $null
    try { $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop } catch { $cimError = $_.Exception.Message }
    $children = @()
    if ($null -ne $cim) {
        try { $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" -ErrorAction Stop | Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine,CreationDate) } catch { $cimError = $_.Exception.Message }
    }
    $modules = @()
    try {
        foreach ($module in @($process.Modules)) {
            try { $modules += [ordered]@{ name=$module.ModuleName; path=$module.FileName; base=('0x{0:X}' -f $module.BaseAddress.ToInt64()); size=$module.ModuleMemorySize; version=$module.FileVersionInfo.FileVersion } } catch {}
        }
    } catch {}
    $threads = @()
    foreach ($thread in @($process.Threads)) {
        try { $threads += [ordered]@{ id=$thread.Id; state=[string]$thread.ThreadState; wait_reason=if($thread.ThreadState -eq [Diagnostics.ThreadState]::Wait){[string]$thread.WaitReason}else{$null}; total_cpu_ms=$thread.TotalProcessorTime.TotalMilliseconds; start_address=('0x{0:X}' -f $thread.StartAddress.ToInt64()) } } catch { $threads += [ordered]@{ id=$thread.Id; error=$_.Exception.Message } }
    }
    Assert-DiagnosticTimeBudget

    $powershell = (Get-Process -Id $PID).Path
    $wctOutput = Join-Path $output "wct.json"
    $wctStdout = Join-Path $output "wct.stdout.log"
    $wctStderr = Join-Path $output "wct.stderr.log"
    $wctScript = Join-Path $PSScriptRoot "phase6ea_wct_helper.ps1"
    $wctArgs = @("-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $wctScript, "-TargetProcessId", $ProcessId, "-OutputPath", $wctOutput)
    $wctGuard = Invoke-Phase6EaGuardedHelper -FilePath $powershell -ArgumentList $wctArgs -StdoutPath $wctStdout -StderrPath $wctStderr -TimeoutSeconds $WctTimeoutSeconds -PrivateBytesLimit $HelperPrivateBytesLimit
    $wctStatus = if ($wctGuard.timed_out) { "wct_timeout" } elseif ($wctGuard.private_bytes_exceeded) { "wct_memory_limit" } elseif ($wctGuard.exit_code -ne 0 -or -not (Test-Path -LiteralPath $wctOutput)) { "wct_failed" } else { "ok" }
    $waitChains = @()
    if ($wctStatus -eq "ok") {
        try { $waitChains = @((Get-Content -LiteralPath $wctOutput -Raw -Encoding UTF8 | ConvertFrom-Json).chains) } catch { $wctStatus = "wct_invalid_output" }
    }
    Assert-DiagnosticTimeBudget

    $lastLog = @()
    if ($LogPath -and (Test-Path -LiteralPath $LogPath)) { $lastLog = @(Get-Content -LiteralPath $LogPath -Tail 80 -Encoding UTF8) }
    $lifecycle = $null
    if ($LifecyclePath -and (Test-Path -LiteralPath $LifecyclePath)) { $lifecycle = Get-Content -LiteralPath $LifecyclePath -Raw -Encoding UTF8 | ConvertFrom-Json }
    $preDump = [ordered]@{
        schema = "campfire.phase6ea.pre-dump-diagnostics.v2"
        phase = "phase6ea"
        timestamp_local = (Get-Date).ToString("o")
        process_identity_verified = $true
        process = [ordered]@{ pid=$ProcessId; parent_pid=if($null -ne $cim){$cim.ParentProcessId}else{$null}; executable=$expected; command_line=if($null -ne $cim){$cim.CommandLine}else{$null}; start_time_utc=$verifiedStartUtc.ToString("o"); handle_count=$process.HandleCount; thread_count=$process.Threads.Count; cim_error=$cimError }
        child_processes = @($children)
        modules = @($modules)
        threads = @($threads)
        wct = [ordered]@{ status=$wctStatus; helper=$wctGuard; chains=@($waitChains); advisory_only=$true }
        lifecycle_marker = if($null -ne $lifecycle){$lifecycle.lifecycle_marker}else{$null}
        lifecycle_history = if($null -ne $lifecycle){@($lifecycle.lifecycle_history)}else{@()}
        final_log_lines = @($lastLog)
        machine_wide_configuration_changed = $false
    }
    [IO.File]::WriteAllText((Join-Path $output "pre_dump_diagnostics.json"), ($preDump | ConvertTo-Json -Depth 30) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))

    $dumpResult = if ($SkipDump) {
        [ordered]@{ status="skipped_by_explicit_request"; path=$dumpPath; bytes=0 }
    } else {
        $process = Test-Phase6EaProcessIdentity -ProcessId $ProcessId -ExpectedExecutable $expected -ExpectedStartTimeUtc $verifiedStartUtc
        $predicted = [math]::Min($MaximumDumpBytes, [math]::Max([long]($process.PrivateMemorySize64 * 1.5), 536870912L))
        $freeBefore = Assert-Phase6EaDiskBudget -Path $dumpPath -RequiredBytes ($predicted + $DiskSafetyMarginBytes)
        $remaining = [math]::Max(1, [math]::Min($DumpTimeoutSeconds, $MaximumDiagnosticSeconds - [int]$stopwatch.Elapsed.TotalSeconds))
        $dumpHelper = Join-Path $PSScriptRoot "phase6ea_dump_helper.ps1"
        $helperArgs = @("-TargetProcessId", $ProcessId, "-ExpectedExecutable", $expected, "-ExpectedStartTimeUtc", $verifiedStartUtc.ToString("o"))
        $result = Invoke-Phase6EaDumpHelper -HelperScript $dumpHelper -HelperArguments $helperArgs -FinalDumpPath $dumpPath -TimeoutSeconds $remaining -PrivateBytesLimit $HelperPrivateBytesLimit -MaximumDumpBytes $MaximumDumpBytes -StdoutPath (Join-Path $output "dump.stdout.log") -StderrPath (Join-Path $output "dump.stderr.log")
        $result | Add-Member -NotePropertyName predicted_maximum_bytes -NotePropertyValue $predicted
        $result | Add-Member -NotePropertyName free_disk_bytes_before -NotePropertyValue $freeBefore
        $result
    }
    if ($dumpResult.status -eq "failed") { throw "Full dump helper failed: $($dumpResult.error)" }
    Assert-DiagnosticTimeBudget
    $dump = if (Test-Path -LiteralPath $dumpPath) { Get-Item -LiteralPath $dumpPath } else { $null }
    $hash = if ($null -ne $dump) { [Phase6EaFileSafety]::ComputeSha256($dumpPath) } else { $null }
    $report = [ordered]@{
        schema = "campfire.phase6ea.hang-diagnostics.v2"
        phase = "phase6ea"
        mode = "live_capture"
        timestamp_local = (Get-Date).ToString("o")
        process_identity_verified = $true
        process = $preDump.process
        child_processes = @($children)
        modules = @($modules)
        threads = @($threads)
        wct = $preDump.wct
        lifecycle_marker = $preDump.lifecycle_marker
        lifecycle_history = $preDump.lifecycle_history
        final_log_lines = @($lastLog)
        dump = [ordered]@{ status=$dumpResult.status; path=$dumpPath; bytes=if($null -ne $dump){$dump.Length}else{0}; sha256=$hash; hash_buffer_bytes=[Phase6EaFileSafety]::HashBufferBytes; mdmp_signature_valid=if($null -ne $dump){[Phase6EaFileSafety]::HasMdmpSignature($dumpPath)}else{$null}; helper=$dumpResult }
        limits = [ordered]@{ maximum_diagnostic_seconds=$MaximumDiagnosticSeconds; wct_timeout_seconds=$WctTimeoutSeconds; dump_timeout_seconds=$DumpTimeoutSeconds; helper_private_bytes=$HelperPrivateBytesLimit; maximum_dump_bytes=$MaximumDumpBytes; disk_safety_margin_bytes=$DiskSafetyMarginBytes }
        target_process_stopped_by_capture = $false
        machine_wide_configuration_changed = $false
    }
    [IO.File]::WriteAllText((Join-Path $output "hang_diagnostics.json"), ($report | ConvertTo-Json -Depth 30) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Write-Host "Phase 6EA live hang diagnostics completed for PID $ProcessId"
} finally {
    $stopwatch.Stop()
    if ($null -ne $lockPath) { Exit-Phase6EaCaptureLock -LockPath $lockPath }
}
