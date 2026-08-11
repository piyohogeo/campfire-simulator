param(
    [Parameter(Mandatory = $true)][string]$LifecyclePath,
    [Parameter(Mandatory = $true)][string]$LogPath,
    [ValidateRange(1, 600)][int]$SleepSeconds = 120,
    [switch]$ExclusiveLogLock
)

$ErrorActionPreference = "Stop"
$lifecycle = [ordered]@{
    schema = "campfire.phase6ej.shutdown-target-fixture.v1"
    status = "ok"
    lifecycle_marker = "shutdown_complete"
    lifecycle_history = @("fixture_started", "timeline_stopped", "stage_closed", "renderer_drained", "shutdown_requested", "shutdown_complete")
    completion_contract = [ordered]@{
        results_saved = $true
        timeline_stopped = $true
        stage_closed = $true
        renderer_drained = $true
        shutdown_requested = $true
    }
}
[IO.File]::WriteAllText($LifecyclePath, (($lifecycle | ConvertTo-Json -Depth 8) + [Environment]::NewLine), [Text.UTF8Encoding]::new($false))
if ($ExclusiveLogLock) {
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes("Phase 6EJ exclusively locked log fixture`r`n")
    $stream = [IO.FileStream]::new($LogPath, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
        Start-Sleep -Seconds $SleepSeconds
    } finally { $stream.Dispose() }
} else {
    [IO.File]::WriteAllText($LogPath, "Phase 6EJ bounded shutdown target fixture`r`n", [Text.UTF8Encoding]::new($false))
    Start-Sleep -Seconds $SleepSeconds
}
