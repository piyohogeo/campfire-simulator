Set-StrictMode -Version 3.0

if (-not ("Phase6EaFileSafety" -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Security.Cryptography;

public static class Phase6EaFileSafety {
    public const int HashBufferBytes = 1024 * 1024;

    public static string ComputeSha256(string path) {
        using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, HashBufferBytes, FileOptions.SequentialScan))
        using (var hash = SHA256.Create()) {
            byte[] digest = hash.ComputeHash(stream);
            return BitConverter.ToString(digest).Replace("-", "");
        }
    }

    public static bool HasMdmpSignature(string path) {
        byte[] signature = new byte[4];
        using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read)) {
            if (stream.Read(signature, 0, signature.Length) != signature.Length) return false;
        }
        return signature[0] == (byte)'M' && signature[1] == (byte)'D' && signature[2] == (byte)'M' && signature[3] == (byte)'P';
    }
}
'@
}

function Test-Phase6EaProcessIdentity {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][string]$ExpectedExecutable,
        [Parameter(Mandatory = $true)][datetime]$ExpectedStartTimeUtc
    )
    $process = Get-Process -Id $ProcessId -ErrorAction Stop
    $actualPath = [IO.Path]::GetFullPath($process.Path)
    $expectedPath = [IO.Path]::GetFullPath($ExpectedExecutable)
    $actualStartUtc = $process.StartTime.ToUniversalTime()
    if ($actualPath -ne $expectedPath) { throw "Process executable mismatch: $actualPath" }
    if ([math]::Abs(($actualStartUtc - $ExpectedStartTimeUtc.ToUniversalTime()).TotalMilliseconds) -gt 1000) {
        throw "Process start time mismatch for PID $ProcessId"
    }
    return $process
}

function Enter-Phase6EaCaptureLock {
    param(
        [Parameter(Mandatory = $true)][string]$CanonicalOutputPath,
        [int]$TargetProcessId = 0,
        [string]$DumpPath = ""
    )
    $canonical = [IO.Path]::GetFullPath($CanonicalOutputPath).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $lockPath = "$canonical.capture.lock"
    if (Test-Path -LiteralPath $lockPath -PathType Leaf) {
        $prior = $null
        try { $prior = Get-Content -LiteralPath $lockPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch {
            throw "Capture lock is unreadable and will not be removed automatically: $lockPath"
        }
        $ownerAlive = $false
        try {
            $owner = Get-Process -Id ([int]$prior.owner_pid) -ErrorAction Stop
            $ownerAlive = [math]::Abs(($owner.StartTime.ToUniversalTime() - ([datetime]$prior.owner_start_time_utc).ToUniversalTime()).TotalMilliseconds) -le 1000
        } catch { $ownerAlive = $false }
        if ($ownerAlive) { throw "Duplicate Phase 6EA capture is active: owner PID $($prior.owner_pid)" }
        Remove-Item -LiteralPath $lockPath -Force
    }
    $self = Get-Process -Id $PID
    $record = [ordered]@{
        schema = "campfire.phase6ea.capture-lock.v1"
        owner_pid = $PID
        owner_start_time_utc = $self.StartTime.ToUniversalTime().ToString("o")
        started_utc = [datetime]::UtcNow.ToString("o")
        target_pid = $TargetProcessId
        canonical_output_path = $canonical
        dump_path = $DumpPath
    }
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($record | ConvertTo-Json -Depth 6) + [Environment]::NewLine)
    try {
        $stream = [IO.FileStream]::new($lockPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
    } catch [IO.IOException] {
        throw "Duplicate Phase 6EA capture won the atomic lock race: $lockPath"
    }
    return $lockPath
}

function Exit-Phase6EaCaptureLock {
    param([Parameter(Mandatory = $true)][string]$LockPath)
    if (-not (Test-Path -LiteralPath $LockPath -PathType Leaf)) { return }
    try {
        $record = Get-Content -LiteralPath $LockPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $self = Get-Process -Id $PID
        if ([int]$record.owner_pid -eq $PID -and [math]::Abs(($self.StartTime.ToUniversalTime() - ([datetime]$record.owner_start_time_utc).ToUniversalTime()).TotalMilliseconds) -le 1000) {
            Remove-Item -LiteralPath $LockPath -Force
        }
    } catch {}
}

function Stop-Phase6EaHelperTree {
    param([Parameter(Mandatory = $true)][int]$RootProcessId)
    $descendants = @()
    try {
        $all = @(Get-CimInstance Win32_Process -ErrorAction Stop)
        $frontier = @($RootProcessId)
        while ($frontier.Count) {
            $next = @()
            foreach ($item in $all) {
                if ([int]$item.ParentProcessId -in $frontier) { $descendants += [int]$item.ProcessId; $next += [int]$item.ProcessId }
            }
            $frontier = $next
        }
    } catch {}
    foreach ($id in @($descendants | Sort-Object -Descending)) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }
    Stop-Process -Id $RootProcessId -Force -ErrorAction SilentlyContinue
}

function Invoke-Phase6EaGuardedHelper {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$ArgumentList,
        [Parameter(Mandatory = $true)][string]$StdoutPath,
        [Parameter(Mandatory = $true)][string]$StderrPath,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds,
        [Parameter(Mandatory = $true)][long]$PrivateBytesLimit
    )
    $started = Get-Date
    $peak = 0L
    $timedOut = $false
    $memoryExceeded = $false
    $process = $null
    try {
        $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -PassThru -WindowStyle Hidden -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath
        while (-not $process.HasExited) {
            $process.Refresh()
            $peak = [math]::Max($peak, $process.PrivateMemorySize64)
            if ($process.PrivateMemorySize64 -gt $PrivateBytesLimit) { $memoryExceeded = $true; break }
            if (((Get-Date) - $started).TotalSeconds -ge $TimeoutSeconds) { $timedOut = $true; break }
            Start-Sleep -Milliseconds 100
        }
        if ($timedOut -or $memoryExceeded) {
            Stop-Phase6EaHelperTree -RootProcessId $process.Id
            $process.WaitForExit(10000) | Out-Null
        }
        $process.Refresh()
        return [ordered]@{
            pid = $process.Id
            exit_code = if ($process.HasExited) { $process.ExitCode } else { $null }
            timed_out = $timedOut
            private_bytes_exceeded = $memoryExceeded
            private_bytes_limit = $PrivateBytesLimit
            peak_private_bytes = $peak
            duration_seconds = ((Get-Date) - $started).TotalSeconds
            process_absent = ($null -eq (Get-Process -Id $process.Id -ErrorAction SilentlyContinue))
            stdout_path = $StdoutPath
            stderr_path = $StderrPath
        }
    } finally {
        if ($null -ne $process) { $process.Dispose() }
    }
}

function Assert-Phase6EaDiskBudget {
    param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)][long]$RequiredBytes)
    $root = [IO.Path]::GetPathRoot([IO.Path]::GetFullPath($Path))
    $drive = [IO.DriveInfo]::new($root)
    if ($drive.AvailableFreeSpace -lt $RequiredBytes) {
        throw "Insufficient disk space: need $RequiredBytes bytes, have $($drive.AvailableFreeSpace)"
    }
    return $drive.AvailableFreeSpace
}

function Invoke-Phase6EaDumpHelper {
    param(
        [Parameter(Mandatory = $true)][string]$HelperScript,
        [Parameter(Mandatory = $true)][string[]]$HelperArguments,
        [Parameter(Mandatory = $true)][string]$FinalDumpPath,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds,
        [Parameter(Mandatory = $true)][long]$PrivateBytesLimit,
        [Parameter(Mandatory = $true)][long]$MaximumDumpBytes,
        [Parameter(Mandatory = $true)][string]$StdoutPath,
        [Parameter(Mandatory = $true)][string]$StderrPath
    )
    $final = [IO.Path]::GetFullPath($FinalDumpPath)
    $partial = "$final.partial"
    if (Test-Path -LiteralPath $final) { throw "Completed dump already exists and will not be overwritten: $final" }
    if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
    $powershell = (Get-Process -Id $PID).Path
    $args = @("-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $HelperScript) + $HelperArguments + @("-PartialPath", $partial)
    $guard = $null
    try {
        $guard = Invoke-Phase6EaGuardedHelper -FilePath $powershell -ArgumentList $args -StdoutPath $StdoutPath -StderrPath $StderrPath -TimeoutSeconds $TimeoutSeconds -PrivateBytesLimit $PrivateBytesLimit
        if ($guard.exit_code -ne 0 -or $guard.timed_out -or $guard.private_bytes_exceeded) { throw "Dump helper failed its process guard" }
        if (-not (Test-Path -LiteralPath $partial -PathType Leaf)) { throw "Dump helper did not create a partial file" }
        $item = Get-Item -LiteralPath $partial
        if ($item.Length -le 4 -or $item.Length -gt $MaximumDumpBytes) { throw "Dump size is outside the configured bounds: $($item.Length)" }
        if (-not [Phase6EaFileSafety]::HasMdmpSignature($partial)) { throw "Dump helper output lacks MDMP signature" }
        Move-Item -LiteralPath $partial -Destination $final
        return [ordered]@{ status="ok"; guard=$guard; path=$final; bytes=(Get-Item $final).Length }
    } catch {
        if (Test-Path -LiteralPath $partial -PathType Leaf) { Remove-Item -LiteralPath $partial -Force }
        return [ordered]@{ status="failed"; guard=$guard; error=$_.Exception.Message; path=$final; partial_removed=(-not (Test-Path -LiteralPath $partial)) }
    }
}
