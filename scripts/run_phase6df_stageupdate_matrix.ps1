param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$kitPython = Join-Path $releaseRoot "kit\python\python.exe"
$trial = Join-Path $PSScriptRoot "run_phase6df_stageupdate_trial.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6df_stageupdate_boundary.py"
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6df-stageupdate"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$sequence = @(
    @{ Label = "pair0"; Mode = "enabled" },
    @{ Label = "pair0"; Mode = "disabled" },
    @{ Label = "pair1"; Mode = "disabled" },
    @{ Label = "pair1"; Mode = "enabled" },
    @{ Label = "pair2"; Mode = "enabled" },
    @{ Label = "pair2"; Mode = "disabled" }
)
$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $app).Hash
foreach ($case in $sequence) {
    & $trial -OutputDir $OutputDir -Mode $case.Mode -Label $case.Label
}
$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $app).Hash
if ($productionHashBefore -ne $productionHashAfter) {
    throw "Phase 6DF matrix changed the production app file."
}

$report = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_stageupdate_boundary_report.json"
$svg = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_stageupdate_boundary_report.svg"
& $kitPython $analyzer `
    --root $OutputDir `
    --report $report `
    --svg $svg `
    --production-sha256-before $productionHashBefore `
    --production-sha256-after $productionHashAfter
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$manifest = [ordered]@{
    schema_version = 1
    phase = "phase6df"
    status = "ok"
    case_count = $sequence.Count
    report = $report
    svg = $svg
    production_app_sha256_before = $productionHashBefore
    production_app_sha256_after = $productionHashAfter
    production_changed = ($productionHashBefore -ne $productionHashAfter)
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputDir "manifest.json") -Encoding utf8
Write-Host "Phase 6DF StageUpdate matrix completed."
