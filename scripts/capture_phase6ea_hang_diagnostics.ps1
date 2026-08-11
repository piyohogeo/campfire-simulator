param(
    [Parameter(Mandatory = $true)][int]$ProcessId,
    [Parameter(Mandatory = $true)][string]$ExpectedExecutable,
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [string]$LifecyclePath = "",
    [string]$LogPath = "",
    [string]$ExistingDumpPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$output = [IO.Path]::GetFullPath($OutputDir)
$expected = [IO.Path]::GetFullPath($ExpectedExecutable)
if (Test-Path -LiteralPath $output) { throw "Phase 6EA diagnostic output already exists: $output" }
New-Item -ItemType Directory -Path $output | Out-Null

Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using Microsoft.Win32.SafeHandles;

public static class Phase6EaNativeDiagnostics {
    const int WctThreadType = 8;
    const int WaitChainNodeSize = 280;
    public class WaitNodeResult {
        public int object_type;
        public string object_type_name;
        public int object_status;
        public string object_status_name;
        public string object_name;
        public int process_id;
        public int thread_id;
        public int wait_time_ms;
        public int context_switches;
    }
    public class WaitChainResult {
        public int thread_id;
        public bool call_succeeded;
        public bool is_cycle;
        public int error_code;
        public string diagnostic;
        public List<WaitNodeResult> nodes = new List<WaitNodeResult>();
    }
    static readonly string[] ObjectTypeNames = { "Invalid", "CriticalSection", "SendMessage", "Mutex", "ALPC", "COM", "ThreadWait", "ProcessWait", "Thread", "COMActivation", "Unknown", "SocketIO", "SMBIO", "Max" };
    static readonly string[] ObjectStatusNames = { "Invalid", "NoAccess", "Running", "Blocked", "PidOnly", "PidOnlyRpcss", "Owned", "NotOwned", "Abandoned", "Unknown", "Error", "Max" };
    [DllImport("advapi32.dll", SetLastError = true)]
    static extern IntPtr OpenThreadWaitChainSession(uint flags, IntPtr callback);
    [DllImport("advapi32.dll", SetLastError = true)]
    static extern bool GetThreadWaitChain(IntPtr session, IntPtr context, uint flags, int threadId, ref uint nodeCount, IntPtr nodes, out int isCycle);
    [DllImport("advapi32.dll")]
    static extern void CloseThreadWaitChainSession(IntPtr session);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern IntPtr OpenProcess(uint access, bool inherit, int processId);
    [DllImport("kernel32.dll")]
    static extern bool CloseHandle(IntPtr handle);
    [DllImport("Dbghelp.dll", SetLastError = true)]
    static extern bool MiniDumpWriteDump(IntPtr process, int processId, SafeFileHandle file, uint dumpType, IntPtr exceptionParam, IntPtr userStreamParam, IntPtr callbackParam);

    public static List<WaitChainResult> GetWaitChains(int processId) {
        var result = new List<WaitChainResult>();
        using (var process = Process.GetProcessById(processId)) {
            IntPtr session = OpenThreadWaitChainSession(0, IntPtr.Zero);
            if (session == IntPtr.Zero) return result;
            try {
                foreach (ProcessThread thread in process.Threads) {
                    uint count = 16;
                    IntPtr nodes = Marshal.AllocHGlobal(WaitChainNodeSize * (int)count);
                    try {
                        int cycle;
                        bool ok = GetThreadWaitChain(session, IntPtr.Zero, 0, thread.Id, ref count, nodes, out cycle);
                        var chain = new WaitChainResult { thread_id = thread.Id, call_succeeded = ok, is_cycle = cycle != 0, error_code = ok ? 0 : Marshal.GetLastWin32Error() };
                        if (ok) {
                            for (int index = 0; index < count; ++index) {
                                IntPtr node = IntPtr.Add(nodes, index * WaitChainNodeSize);
                                int objectType = Marshal.ReadInt32(node, 0);
                                bool threadNode = objectType == WctThreadType;
                                chain.nodes.Add(new WaitNodeResult {
                                    object_type = objectType,
                                    object_type_name = objectType >= 0 && objectType < ObjectTypeNames.Length ? ObjectTypeNames[objectType] : "OutOfRange",
                                    object_status = Marshal.ReadInt32(node, 4),
                                    object_status_name = Marshal.ReadInt32(node, 4) >= 0 && Marshal.ReadInt32(node, 4) < ObjectStatusNames.Length ? ObjectStatusNames[Marshal.ReadInt32(node, 4)] : "OutOfRange",
                                    object_name = threadNode ? null : Marshal.PtrToStringUni(IntPtr.Add(node, 8)),
                                    process_id = threadNode ? Marshal.ReadInt32(node, 8) : 0,
                                    thread_id = threadNode ? Marshal.ReadInt32(node, 12) : 0,
                                    wait_time_ms = threadNode ? Marshal.ReadInt32(node, 16) : 0,
                                    context_switches = threadNode ? Marshal.ReadInt32(node, 20) : 0
                                });
                            }
                        }
                        result.Add(chain);
                    } finally {
                        Marshal.FreeHGlobal(nodes);
                    }
                }
            } finally { CloseThreadWaitChainSession(session); }
        }
        return result;
    }

    public static List<WaitChainResult> GetWaitChainsBounded(int processId, int timeoutMilliseconds) {
        var task = Task.Run(() => GetWaitChains(processId));
        try {
            if (task.Wait(timeoutMilliseconds)) return task.Result;
        } catch (Exception error) {
            return new List<WaitChainResult> {
                new WaitChainResult {
                    thread_id = -1,
                    call_succeeded = false,
                    is_cycle = false,
                    error_code = error.HResult,
                    diagnostic = "public WCT collection failed: " + error.GetType().Name
                }
            };
        }
        return new List<WaitChainResult> {
            new WaitChainResult {
                thread_id = -1,
                call_succeeded = false,
                is_cycle = false,
                error_code = 1460,
                diagnostic = "public WCT collection exceeded the bounded timeout; native call was not used as a shutdown gate"
            }
        };
    }

    public static int WriteFullDump(int processId, string path) {
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

function Get-ProcessThreadSnapshot([System.Diagnostics.Process]$Process) {
    $rows = @()
    foreach ($thread in @($Process.Threads)) {
        try {
            $rows += [ordered]@{
                id = $thread.Id
                state = [string]$thread.ThreadState
                wait_reason = if ($thread.ThreadState -eq [Diagnostics.ThreadState]::Wait) { [string]$thread.WaitReason } else { $null }
                total_cpu_ms = $thread.TotalProcessorTime.TotalMilliseconds
                user_cpu_ms = $thread.UserProcessorTime.TotalMilliseconds
                privileged_cpu_ms = $thread.PrivilegedProcessorTime.TotalMilliseconds
                start_address = ('0x{0:X}' -f $thread.StartAddress.ToInt64())
            }
        } catch {
            $rows += [ordered]@{ id = $thread.Id; error = $_.Exception.Message }
        }
    }
    return @($rows)
}

function Get-GpuProcesses {
    $rows = @()
    $lines = & nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv,noheader,nounits 2>$null
    foreach ($line in @($lines)) {
        $parts = @($line -split ',\s*')
        if ($parts.Count -eq 4) { $rows += [ordered]@{ gpu_uuid=$parts[0]; pid=$parts[1]; process_name=$parts[2]; used_memory_mib=$parts[3] } }
    }
    return @($rows)
}

$process = Get-Process -Id $ProcessId -ErrorAction Stop
$actualPath = [IO.Path]::GetFullPath($process.Path)
if ($actualPath -ne $expected) { throw "Refusing diagnostics for unexpected executable: $actualPath" }
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
$threads0 = @(Get-ProcessThreadSnapshot $process)
$cpu0 = $process.TotalProcessorTime.TotalMilliseconds
$time0 = Get-Date
Start-Sleep -Seconds 5
$process.Refresh()
$threads1 = @(Get-ProcessThreadSnapshot $process)
$cpu1 = $process.TotalProcessorTime.TotalMilliseconds
$time1 = Get-Date
$waitChains = @([Phase6EaNativeDiagnostics]::GetWaitChainsBounded($ProcessId, 10000))
$preDump = [ordered]@{
    schema = "campfire.phase6ea.pre-dump-diagnostics.v1"
    phase = "phase6ea"
    timestamp_local = (Get-Date).ToString("o")
    process_identity_verified = $true
    process = [ordered]@{
        pid = $ProcessId
        parent_pid = if ($null -ne $cim) { $cim.ParentProcessId } else { $null }
        executable = $actualPath
        command_line = if ($null -ne $cim) { $cim.CommandLine } else { $null }
        start_time = $process.StartTime.ToString("o")
        handle_count = $process.HandleCount
        thread_count = $process.Threads.Count
        cpu_total_ms_t0 = $cpu0
        cpu_total_ms_t1 = $cpu1
        cpu_delta_ms = ($cpu1 - $cpu0)
        observation_wall_ms = ($time1 - $time0).TotalMilliseconds
    }
    child_processes = @($children)
    modules = @($modules)
    threads_t0 = @($threads0)
    threads_t1 = @($threads1)
    wait_chains = @($waitChains)
    machine_wide_configuration_changed = $false
}
[IO.File]::WriteAllText((Join-Path $output "pre_dump_diagnostics.json"), ($preDump | ConvertTo-Json -Depth 30) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
$dumpPath = if ($ExistingDumpPath) { [IO.Path]::GetFullPath($ExistingDumpPath) } else { Join-Path $output "hang-full.dmp" }
$dumpError = if ($ExistingDumpPath) {
    if (-not (Test-Path -LiteralPath $dumpPath -PathType Leaf)) { throw "Existing hang dump is missing: $dumpPath" }
    0
} else {
    [Phase6EaNativeDiagnostics]::WriteFullDump($ProcessId, $dumpPath)
}
$dump = if (Test-Path -LiteralPath $dumpPath) { Get-Item -LiteralPath $dumpPath } else { $null }
$lastLog = @()
if ($LogPath -and (Test-Path -LiteralPath $LogPath)) { $lastLog = @(Get-Content -LiteralPath $LogPath -Tail 80 -Encoding UTF8) }
$lifecycle = $null
if ($LifecyclePath -and (Test-Path -LiteralPath $LifecyclePath)) { $lifecycle = Get-Content -LiteralPath $LifecyclePath -Raw -Encoding UTF8 | ConvertFrom-Json }
$cpuDelta = $cpu1 - $cpu0
$wallMs = ($time1 - $time0).TotalMilliseconds
$report = [ordered]@{
    schema = "campfire.phase6ea.hang-diagnostics.v1"
    phase = "phase6ea"
    timestamp_local = (Get-Date).ToString("o")
    process_identity_verified = $true
    process = [ordered]@{
        pid = $ProcessId
        parent_pid = if ($null -ne $cim) { $cim.ParentProcessId } else { $null }
        executable = $actualPath
        command_line = if ($null -ne $cim) { $cim.CommandLine } else { $null }
        start_time = $process.StartTime.ToString("o")
        handle_count = $process.HandleCount
        thread_count = $process.Threads.Count
        cpu_total_ms_t0 = $cpu0
        cpu_total_ms_t1 = $cpu1
        cpu_delta_ms = $cpuDelta
        observation_wall_ms = $wallMs
        classification = if ($cpuDelta -ge ($wallMs * 0.25)) { "cpu_spin_candidate" } else { "predominantly_waiting" }
        cim_error = $cimError
    }
    child_processes = @($children)
    modules = @($modules)
    threads_t0 = @($threads0)
    threads_t1 = @($threads1)
    wait_chains = @($waitChains)
    gpu_processes = @(Get-GpuProcesses)
    lifecycle_marker = if ($null -ne $lifecycle) { $lifecycle.lifecycle_marker } else { $null }
    lifecycle_history = if ($null -ne $lifecycle) { @($lifecycle.lifecycle_history) } else { @() }
    final_log_lines = @($lastLog)
    handle_type_target_source = "public WCT wait-object nodes plus MiniDumpWithHandleData; no Handle.exe/Process Explorer and no undocumented NtQuerySystemInformation"
    dump = [ordered]@{
        attempted = (-not [bool]$ExistingDumpPath)
        reused_completed_capture = [bool]$ExistingDumpPath
        error_code = $dumpError
        written = ($null -ne $dump -and $dumpError -eq 0)
        path = if ($null -ne $dump) { $dump.FullName } else { $dumpPath }
        bytes = if ($null -ne $dump) { $dump.Length } else { 0 }
        sha256 = if ($null -ne $dump -and $dumpError -eq 0) { (Get-FileHash -Algorithm SHA256 -LiteralPath $dump.FullName).Hash } else { $null }
        flags = "MiniDumpWithFullMemory|MiniDumpWithHandleData|MiniDumpWithUnloadedModules|MiniDumpWithFullMemoryInfo|MiniDumpWithThreadInfo|MiniDumpWithTokenInformation"
    }
    machine_wide_configuration_changed = $false
}
[IO.File]::WriteAllText((Join-Path $output "hang_diagnostics.json"), ($report | ConvertTo-Json -Depth 30) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host "Phase 6EA hang diagnostics captured for PID $ProcessId"
