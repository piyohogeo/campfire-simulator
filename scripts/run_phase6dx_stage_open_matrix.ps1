param([string]$OutputRoot = "")

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutputRoot) { $OutputRoot = Join-Path $root "artifacts\phase6dx-stage-open-safe-preflight-1" }
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6DX refuses artifact root reuse: $OutputRoot" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
$runner = Join-Path $PSScriptRoot "run_phase6dx_stage_open_case.ps1"
$source = Join-Path $root "artifacts\phase6dt-reference-audit-2\phase6ds_mesh_usd_mesh_collision\run-1\raw.prepared.usda"
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Phase 6DX known-good source missing: $source" }
$modes = @(
    "box_control",
    "box_hull",
    "cylinder_decomposition"
)
$completed = @()
foreach ($mode in $modes) {
    $output = Join-Path $OutputRoot "$mode\run-1"
    try {
        & $runner -Mode $mode -RunIndex 1 -SourceStage $source -OutputDir $output
        $completed += $mode
    } catch {
        $stop = [ordered]@{
            schema = "campfire.phase6dx.matrix-safe-stop.v1"
            phase = "phase6dx"
            status = "safe_stop"
            failed_mode = $mode
            completed = @($completed)
            automatic_retry = $false
            error = $_.Exception.Message
            timestamp_local = (Get-Date).ToString("o")
        }
        [IO.File]::WriteAllText((Join-Path $OutputRoot "matrix_safe_stop.json"), ($stop | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
        throw
    }
}
$result = [ordered]@{
    schema = "campfire.phase6dx.safe-preflight-complete.v1"
    phase = "phase6dx"
    status = "complete"
    completed = @($completed)
    timestamp_local = (Get-Date).ToString("o")
}
[IO.File]::WriteAllText((Join-Path $OutputRoot "matrix_complete.json"), ($result | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host "Phase 6DX stage-open matrix complete: $($completed.Count) process(es)"
