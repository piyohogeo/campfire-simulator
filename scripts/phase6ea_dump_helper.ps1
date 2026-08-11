param(
    [Parameter(Mandatory = $true)][string]$PartialPath,
    [int]$TargetProcessId = 0,
    [string]$ExpectedExecutable = "",
    [string]$ExpectedStartTimeUtc = "",
    [string]$FixtureSourcePath = "",
    [int]$FixtureHangAfterBytes = 0
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$partial = [IO.Path]::GetFullPath($PartialPath)
if (Test-Path -LiteralPath $partial) { throw "Partial output already exists: $partial" }

if ($FixtureSourcePath) {
    $source = [IO.FileStream]::new([IO.Path]::GetFullPath($FixtureSourcePath), [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read, 1048576, [IO.FileOptions]::SequentialScan)
    $destination = [IO.FileStream]::new($partial, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None, 1048576, [IO.FileOptions]::SequentialScan)
    try {
        $buffer = [byte[]]::new(1048576)
        $written = 0L
        while (($count = $source.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $destination.Write($buffer, 0, $count)
            $written += $count
            if ($FixtureHangAfterBytes -gt 0 -and $written -ge $FixtureHangAfterBytes) { $destination.Flush($true); Start-Sleep -Seconds 300 }
        }
        $destination.Flush($true)
    } finally { $destination.Dispose(); $source.Dispose() }
    exit 0
}

if ($TargetProcessId -le 0 -or -not $ExpectedExecutable -or -not $ExpectedStartTimeUtc) { throw "Live dump helper requires PID, executable, and start time" }
$process = Get-Process -Id $TargetProcessId -ErrorAction Stop
if ([IO.Path]::GetFullPath($process.Path) -ne [IO.Path]::GetFullPath($ExpectedExecutable)) { throw "Dump helper executable mismatch" }
if ([math]::Abs(($process.StartTime.ToUniversalTime() - ([datetime]$ExpectedStartTimeUtc).ToUniversalTime()).TotalMilliseconds) -gt 1000) { throw "Dump helper start time mismatch" }

Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class Phase6EaDumpNative {
    [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(uint access, bool inherit, int processId);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    [DllImport("Dbghelp.dll", SetLastError=true)] static extern bool MiniDumpWriteDump(IntPtr process, int processId, SafeFileHandle file, uint dumpType, IntPtr exceptionParam, IntPtr userStreamParam, IntPtr callbackParam);
    public static int Write(int processId, string path) {
        const uint access = 0x0010 | 0x0040 | 0x0400;
        const uint flags = 0x00000002 | 0x00000004 | 0x00000020 | 0x00000800 | 0x00001000 | 0x00040000;
        IntPtr process = OpenProcess(access, false, processId);
        if (process == IntPtr.Zero) return Marshal.GetLastWin32Error();
        try {
            using (var file = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None)) {
                bool ok = MiniDumpWriteDump(process, processId, file.SafeFileHandle, flags, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero);
                file.Flush(true);
                return ok ? 0 : Marshal.GetLastWin32Error();
            }
        } finally { CloseHandle(process); }
    }
}
'@
$code = [Phase6EaDumpNative]::Write($TargetProcessId, $partial)
if ($code -ne 0) { throw "MiniDumpWriteDump failed: $code" }
