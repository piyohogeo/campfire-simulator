param(
    [string]$Scene = "",
    [string]$OutputDir = "",
    [switch]$ReuseExisting
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$probe = Join-Path $PSScriptRoot "probe_stage_update_inventory.py"

if (-not (Test-Path -LiteralPath $kit)) {
    throw "Application is not built. Run .\repo.bat build first."
}
if (-not $Scene) {
    $Scene = Join-Path $repositoryRoot "artifacts\phase3\phase6cn\scene\phase3_point_application.usda"
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6cp"
}
$Scene = [System.IO.Path]::GetFullPath($Scene)
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
if (-not (Test-Path -LiteralPath $Scene)) {
    throw "Phase 6CP input scene is missing: $Scene"
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$appCases = @(
    @{ Label = "normal"; App = "campfire.simulator.kit" },
    @{ Label = "benchmark"; App = "campfire.simulator.benchmark.kit" }
)
foreach ($case in $appCases) {
    $app = Join-Path $releaseRoot ("apps\" + $case.App)
    $output = Join-Path $OutputDir ($case.Label + ".json")
    if ($ReuseExisting -and (Test-Path -LiteralPath $output)) {
        $existing = Get-Content -LiteralPath $output -Raw | ConvertFrom-Json
        if ($existing.status -eq "ok" -and $existing.app_label -eq $case.Label) {
            Write-Host ("Phase 6CP reusing {0}" -f $output)
            continue
        }
    }
    & $kit @(
        $app,
        "--no-window",
        "--/app/quitAfter=120",
        "--/app/settings/persistent=0",
        "--/app/settings/loadUserConfig=0",
        "--/exts/campfire.app/autoCreateScene=false",
        "--/phase6cp/scene=$Scene",
        "--/phase6cp/output=$output",
        "--/phase6cp/appLabel=$($case.Label)",
        "--/renderer/enabled=false",
        "--/rtx/flow/enabled=true",
        "--exec",
        $probe
    )
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$normal = Get-Content -LiteralPath (Join-Path $OutputDir "normal.json") -Raw | ConvertFrom-Json
$benchmark = Get-Content -LiteralPath (Join-Path $OutputDir "benchmark.json") -Raw | ConvertFrom-Json
if ($normal.status -ne "ok" -or $benchmark.status -ne "ok") {
    throw "Phase 6CP inventory probe failed: $OutputDir"
}
$normalNames = @($normal.stage_update.nodes_before_play | ForEach-Object name)
$benchmarkNames = @($benchmark.stage_update.nodes_before_play | ForEach-Object name)
$normalOnly = @($normalNames | Where-Object { $_ -notin $benchmarkNames })
$benchmarkOnly = @($benchmarkNames | Where-Object { $_ -notin $normalNames })
$comparison = [ordered]@{
    schema_version = 1
    phase = "phase6cp"
    status = "ok"
    scene = $Scene
    normal_node_count = $normalNames.Count
    benchmark_node_count = $benchmarkNames.Count
    normal_only_nodes = $normalOnly
    benchmark_only_nodes = $benchmarkOnly
    normal_remained_playing = [bool]$normal.timeline.remained_playing
    benchmark_remained_playing = [bool]$benchmark.timeline.remained_playing
    owner_composed = $false
    production_changed = $false
}
$comparison | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputDir "comparison.json") -Encoding utf8
Write-Host ("Phase 6CP inventory: normal={0} nodes/play={1}, benchmark={2} nodes/play={3}, normal-only={4}" -f $normalNames.Count, $normal.timeline.remained_playing, $benchmarkNames.Count, $benchmark.timeline.remained_playing, ($normalOnly -join ", "))
