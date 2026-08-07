param(
    [ValidateSet("all", "small-single", "target-single", "target-few")]
    [string]$Configuration = "all",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$kitPython = Join-Path $releaseRoot "kit\python\python.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.benchmark.kit"
$benchmark = Join-Path $PSScriptRoot "benchmark_point_emitter_core.py"
$analyzer = Join-Path $PSScriptRoot "analyze_point_emitter_core.py"

if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) {
    throw "Application is not built. Run .\repo.bat build first."
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6cb"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

if ($Configuration -eq "all") {
    foreach ($candidate in @("small-single", "target-single", "target-few")) {
        & $PSCommandPath -Configuration $candidate -OutputDir $OutputDir
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    $report = Join-Path $repositoryRoot "docs\devlog\assets\phase6\point_emitter_core_report.json"
    $svg = Join-Path $repositoryRoot "docs\devlog\assets\phase6\point_emitter_core_report.svg"
    $capture = Join-Path $repositoryRoot "docs\devlog\assets\phase6\point_emitter_core_frame.png"
    & $kitPython $analyzer --raw-dir $OutputDir --report $report --svg $svg --capture $capture
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "Phase 6CB all configurations qualified: $report"
    exit 0
}

$pointCount = 16
$emitterCount = 1
$frames = 120
$warmup = 30
if ($Configuration -eq "target-single") {
    $pointCount = 7200
    $frames = 120
}
elseif ($Configuration -eq "target-few") {
    $pointCount = 7200
    $emitterCount = 4
    $frames = 120
}
$output = Join-Path $OutputDir ("point_emitter_core_{0}.json" -f $Configuration)

& $kit @(
    $app,
    "--no-window",
    "--/app/quitAfter=900",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/phase6cb/output=$output",
    "--/phase6cb/pointCount=$pointCount",
    "--/phase6cb/emitterCount=$emitterCount",
    "--/phase6cb/frames=$frames",
    "--/phase6cb/warmup=$warmup",
    "--/rtx/flow/enabled=true",
    "--exec",
    $benchmark
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$result = Get-Content -LiteralPath $output -Raw | ConvertFrom-Json
if ($result.status -ne "ok") {
    throw "Phase 6CB $Configuration failed: $output"
}
Write-Host (
    "Phase 6CB {0}: points={1}, emitters={2}, active blocks peak={3}, image={4}" -f
    $Configuration,
    $result.configuration.point_count,
    $result.configuration.emitter_count,
    $result.timeline.playing_active_blocks_peak,
    $result.viewport.captures[-1].path
)
