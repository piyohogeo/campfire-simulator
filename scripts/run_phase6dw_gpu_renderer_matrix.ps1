param(
    [string]$OutputRoot = "",
    [ValidateSet("normal", "isolated", "both")][string]$CacheScope = "both"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutputRoot) { $OutputRoot = Join-Path $root "artifacts\phase6dw-gpu-renderer-lifecycle-1" }
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6DW refuses artifact root reuse: $OutputRoot" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
$runner = Join-Path $PSScriptRoot "run_phase6dw_gpu_renderer_case.ps1"
$box = Join-Path $root "artifacts\phase6dt-reference-audit-2\phase6ds_mesh_usd_mesh_collision\run-1\raw.prepared.usda"
$flow = Join-Path $root "assets\scenes\phase1_flow.usda"
if (-not (Test-Path -LiteralPath $box -PathType Leaf)) { throw "Known-good Box stage missing: $box" }
if (-not (Test-Path -LiteralPath $flow -PathType Leaf)) { throw "Known-good Flow stage missing: $flow" }
$conditions = @(
    [ordered]@{ name = "kit_only"; source = "" },
    [ordered]@{ name = "openusd_empty"; source = "" },
    [ordered]@{ name = "rtx_empty"; source = "" },
    [ordered]@{ name = "box_openusd"; source = $box },
    [ordered]@{ name = "box_rtx"; source = $box },
    [ordered]@{ name = "flow_load"; source = "" },
    [ordered]@{ name = "flow_sim"; source = $flow }
)
$cacheKinds = if ($CacheScope -eq "both") { @("normal", "isolated") } else { @($CacheScope) }
$completed = @()
foreach ($cacheKind in $cacheKinds) {
    foreach ($condition in $conditions) {
        $output = Join-Path $OutputRoot "$cacheKind\$($condition.name)"
        try {
            & $runner -Condition $condition.name -CacheKind $cacheKind -OutputDir $output -SourceStage $condition.source
            $completed += "$cacheKind/$($condition.name)"
        } catch {
            $stop = [ordered]@{
                schema = "campfire.phase6dw.matrix-safe-stop.v1"
                phase = "phase6dw"
                status = "safe_stop"
                failed_condition = "$cacheKind/$($condition.name)"
                completed = @($completed)
                error = $_.Exception.Message
                timestamp_local = (Get-Date).ToString("o")
            }
            [IO.File]::WriteAllText((Join-Path $OutputRoot "matrix_safe_stop.json"), ($stop | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
            throw
        }
    }
}
$result = [ordered]@{
    schema = "campfire.phase6dw.matrix-complete.v1"
    phase = "phase6dw"
    status = "complete"
    completed = @($completed)
    timestamp_local = (Get-Date).ToString("o")
}
[IO.File]::WriteAllText((Join-Path $OutputRoot "matrix_complete.json"), ($result | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host "Phase 6DW matrix complete: $($completed.Count) process(es)"
