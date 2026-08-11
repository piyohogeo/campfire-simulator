param(
    [int]$TargetProcessId = 0,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [switch]$ObjectNameBoundaryFixture,
    [int]$FixtureHangSeconds = 0
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
if ($FixtureHangSeconds -gt 0) { Start-Sleep -Seconds $FixtureHangSeconds }

Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;

public static class Phase6EaWctSafe {
    public const int MaxNodeCount = 16;
    public const int WaitChainNodeSize = 280;
    public const int UnionOffset = 8;
    public const int ObjectNameCharacters = 128;
    public const int WctThreadType = 8;

    public class Node {
        public int object_type;
        public int object_status;
        public string object_name;
        public int process_id;
        public int thread_id;
        public int wait_time_ms;
        public int context_switches;
    }
    public class Chain {
        public int thread_id;
        public bool call_succeeded;
        public bool is_cycle;
        public int error_code;
        public List<Node> nodes = new List<Node>();
    }

    [DllImport("advapi32.dll", SetLastError = true)] static extern IntPtr OpenThreadWaitChainSession(uint flags, IntPtr callback);
    [DllImport("advapi32.dll", SetLastError = true)] static extern bool GetThreadWaitChain(IntPtr session, IntPtr context, uint flags, int threadId, ref uint nodeCount, IntPtr nodes, out int isCycle);
    [DllImport("advapi32.dll")] static extern void CloseThreadWaitChainSession(IntPtr session);

    public static string ReadBoundedObjectName(IntPtr node) {
        char[] characters = new char[ObjectNameCharacters];
        Marshal.Copy(IntPtr.Add(node, UnionOffset), characters, 0, ObjectNameCharacters);
        int length = Array.IndexOf(characters, '\0');
        if (length < 0) length = ObjectNameCharacters;
        return new string(characters, 0, length);
    }

    public static string DecodeBoundaryFixture() {
        IntPtr memory = Marshal.AllocHGlobal(WaitChainNodeSize);
        try {
            for (int index = 0; index < WaitChainNodeSize; ++index) Marshal.WriteByte(memory, index, 0x5A);
            char[] characters = new string('X', ObjectNameCharacters).ToCharArray();
            Marshal.Copy(characters, 0, IntPtr.Add(memory, UnionOffset), characters.Length);
            return ReadBoundedObjectName(memory);
        } finally { Marshal.FreeHGlobal(memory); }
    }

    public static List<Chain> Collect(int processId) {
        var result = new List<Chain>();
        using (var process = Process.GetProcessById(processId)) {
            IntPtr session = OpenThreadWaitChainSession(0, IntPtr.Zero);
            if (session == IntPtr.Zero) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            try {
                foreach (ProcessThread thread in process.Threads) {
                    uint count = MaxNodeCount;
                    IntPtr nodes = Marshal.AllocHGlobal(WaitChainNodeSize * MaxNodeCount);
                    try {
                        int cycle;
                        bool ok = GetThreadWaitChain(session, IntPtr.Zero, 0, thread.Id, ref count, nodes, out cycle);
                        if (count > MaxNodeCount) throw new InvalidOperationException("WCT returned a node count beyond the allocated maximum");
                        var chain = new Chain { thread_id=thread.Id, call_succeeded=ok, is_cycle=cycle != 0, error_code=ok ? 0 : Marshal.GetLastWin32Error() };
                        if (ok) {
                            for (int index = 0; index < (int)count; ++index) {
                                IntPtr node = IntPtr.Add(nodes, index * WaitChainNodeSize);
                                int type = Marshal.ReadInt32(node, 0);
                                bool threadNode = type == WctThreadType;
                                chain.nodes.Add(new Node {
                                    object_type=type,
                                    object_status=Marshal.ReadInt32(node, 4),
                                    object_name=threadNode ? null : ReadBoundedObjectName(node),
                                    process_id=threadNode ? Marshal.ReadInt32(node, UnionOffset) : 0,
                                    thread_id=threadNode ? Marshal.ReadInt32(node, UnionOffset + 4) : 0,
                                    wait_time_ms=threadNode ? Marshal.ReadInt32(node, UnionOffset + 8) : 0,
                                    context_switches=threadNode ? Marshal.ReadInt32(node, UnionOffset + 12) : 0
                                });
                            }
                        }
                        result.Add(chain);
                    } finally { Marshal.FreeHGlobal(nodes); }
                }
            } finally { CloseThreadWaitChainSession(session); }
        }
        return result;
    }
}
'@

$payload = if ($ObjectNameBoundaryFixture) {
    $value = [Phase6EaWctSafe]::DecodeBoundaryFixture()
    [ordered]@{
        schema = "campfire.phase6ea.wct-boundary-fixture.v1"
        value = $value
        length = $value.Length
        constants = [ordered]@{ max_node_count=16; node_size=280; union_offset=8; object_name_characters=128 }
    }
} else {
    if ($TargetProcessId -le 0) { throw "TargetProcessId is required outside fixture mode" }
    [ordered]@{
        schema = "campfire.phase6ea.wct-helper.v1"
        target_pid = $TargetProcessId
        status = "ok"
        chains = @([Phase6EaWctSafe]::Collect($TargetProcessId))
        constants = [ordered]@{ max_node_count=16; node_size=280; union_offset=8; object_name_characters=128 }
    }
}
[IO.File]::WriteAllText([IO.Path]::GetFullPath($OutputPath), ($payload | ConvertTo-Json -Depth 30) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
