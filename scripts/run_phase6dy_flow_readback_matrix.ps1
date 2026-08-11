param(
    [string]$StageOpenRoot = "",
    [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
if (-not $StageOpenRoot) { $StageOpenRoot = Join-Path $root "artifacts\phase6dy-calibrated-stage-open-1" }
$StageOpenRoot = [IO.Path]::GetFullPath($StageOpenRoot)
if (-not $OutputRoot) { $OutputRoot = Join-Path $StageOpenRoot "flow-readback" }
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (-not (Test-Path -LiteralPath (Join-Path $StageOpenRoot "matrix_complete.json") -PathType Leaf)) {
    throw "Phase 6DY stage-open matrix is not qualified: $StageOpenRoot"
}
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6DY refuses Flow artifact reuse: $OutputRoot" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
$runner = Join-Path $PSScriptRoot "run_phase6dt_flow_collision_case.ps1"
$preparedRoot = Join-Path $StageOpenRoot "prepared-stages"
$productionApp = Join-Path $root "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$cases = @(
    [ordered]@{ label="box_before"; stage="A_box_decomposition.usda" },
    [ordered]@{ label="cylinder_decomposition"; stage="D_cylinder_decomposition.usda" },
    [ordered]@{ label="box_after"; stage="E_box_decomposition.usda" }
)
$completed = @()
foreach ($case in $cases) {
    $source = Join-Path $preparedRoot $case.stage
    $output = Join-Path $OutputRoot $case.label
    try {
        & $runner -Mode phase6dy_prepared_mesh -SourceStage $source -OutputDir $output -AppKind reference -RunIndex 1
        $completed += $case.label
    } catch {
        $stop = [ordered]@{
            schema = "campfire.phase6dy.flow-readback-safe-stop.v1"
            phase = "phase6dy"
            status = "safe_stop"
            failed_condition = $case.label
            completed = @($completed)
            automatic_retry = $false
            error = $_.Exception.Message
            production_app_sha256_before = $productionHashBefore
            production_app_sha256_after = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
            timestamp_local = (Get-Date).ToString("o")
        }
        [IO.File]::WriteAllText((Join-Path $OutputRoot "matrix_safe_stop.json"), ($stop | ConvertTo-Json -Depth 10) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
        throw
    }
}
$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
if ($productionHashBefore -ne $productionHashAfter) { throw "Phase 6DY Flow readback changed production app" }
$result = [ordered]@{
    schema = "campfire.phase6dy.flow-readback-complete.v1"
    phase = "phase6dy"
    status = "complete"
    completed = @($completed)
    shared_mode = "phase6dy_prepared_mesh"
    roi_contract = "Phase 6DT / Phase 6DS fixed ROIs plus a shared cylinder-contained core and above ROI"
    production_app_sha256_before = $productionHashBefore
    production_app_sha256_after = $productionHashAfter
    timestamp_local = (Get-Date).ToString("o")
}
[IO.File]::WriteAllText((Join-Path $OutputRoot "matrix_complete.json"), ($result | ConvertTo-Json -Depth 10) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host "Phase 6DY Flow readback complete: $($completed.Count) processes"
