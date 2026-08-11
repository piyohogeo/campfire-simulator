param(
    [ValidateSet("tree", "orphan_child", "cdb_path", "gpu_inventory")][string]$Mode = "tree",
    [Parameter(Mandatory = $true)][string]$MarkerPath,
    [ValidateRange(100, 10000)][int]$HoldMilliseconds = 750
)

$ErrorActionPreference = "Stop"
$marker = [IO.Path]::GetFullPath($MarkerPath)
function Write-Marker([string]$Name) {
    [IO.File]::AppendAllText(
        $marker,
        (([ordered]@{ marker=$Name; pid=$PID; timestamp_utc=[datetime]::UtcNow.ToString("o") } | ConvertTo-Json -Compress) + [Environment]::NewLine),
        [Text.UTF8Encoding]::new($false)
    )
}

Write-Marker "fixture_started"
if ($Mode -in @("cdb_path", "gpu_inventory")) {
    . (Join-Path $PSScriptRoot "kit_shutdown_policy.ps1")
    Write-Marker "policy_loaded"
    if ($Mode -eq "cdb_path") {
        $cdb = Get-CampfireCdbPath
        Write-Marker "cdb_path_complete"
        if ($null -ne $cdb) { Write-Marker "cdb_found" }
    } else {
        $inventoryOutput = Join-Path ([IO.Path]::GetDirectoryName($marker)) "gpu-inventory-fixture"
        New-Item -ItemType Directory -Path $inventoryOutput -Force | Out-Null
        $capture = Get-CampfireGpuInventory -OutputDir $inventoryOutput
        [IO.File]::WriteAllText(
            (Join-Path ([IO.Path]::GetDirectoryName($marker)) "gpu_inventory_capture.json"),
            (($capture | ConvertTo-Json -Depth 12) + [Environment]::NewLine),
            [Text.UTF8Encoding]::new($false)
        )
        Write-Marker "gpu_inventory_complete"
        if ($capture.evidence.error) { throw $capture.evidence.error }
        if (@($capture.rows).Count -lt 1) { throw "GPU inventory fixture returned no rows" }
    }
    # Keep the short fixture alive long enough for the streaming sampler to
    # observe steady-state PowerShell allocation rather than only startup.
    Start-Sleep -Milliseconds $HoldMilliseconds
} elseif ($Mode -eq "orphan_child") {
    $self = (Get-Process -Id $PID).Path
    $child = Start-Process -FilePath $self -ArgumentList @("-NoProfile", "-NonInteractive", "-Command", "Start-Sleep -Seconds 30") -PassThru -WindowStyle Hidden
    Write-Marker "orphan_child_started"
    Write-Marker "orphan_child_pid_$($child.Id)"
    $child.Dispose()
    # Keep the parent alive long enough for the streaming guard to observe the
    # child identity before the parent exits and deliberately orphans it.
    Start-Sleep -Milliseconds $HoldMilliseconds
} else {
    $self = (Get-Process -Id $PID).Path
    $child = Start-Process -FilePath $self -ArgumentList @("-NoProfile", "-NonInteractive", "-Command", "Start-Sleep -Milliseconds $HoldMilliseconds") -PassThru -WindowStyle Hidden
    Write-Marker "child_started"
    $child.WaitForExit(5000) | Out-Null
    Write-Marker "child_exited"
}
Write-Marker "fixture_complete"
