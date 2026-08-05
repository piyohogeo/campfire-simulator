param(
    [int]$Steps = 400,
    [int]$Runs = 3
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"
$benchmark = Join-Path $PSScriptRoot "benchmark_wood_array_backends.py"
$renderer = Join-Path $PSScriptRoot "render_wood_array_backend_report.py"
$rawResult = Join-Path $repositoryRoot "artifacts\performance\wood_array_phase6u_latest.json"
$reportJson = Join-Path $repositoryRoot "docs\devlog\assets\phase6\wood_array_backend_report.json"
$reportSvg = Join-Path $repositoryRoot "docs\devlog\assets\phase6\wood_array_backend_report.svg"

if (-not (Test-Path -LiteralPath $kitPython)) {
    throw "Kit Python was not found: $kitPython"
}

& $kitPython $benchmark --steps $Steps --runs $Runs --device cuda:0 --output $rawResult
if ($LASTEXITCODE -ne 0) {
    throw "Phase 6U backend benchmark failed with exit code $LASTEXITCODE"
}

& $kitPython $renderer $rawResult --json $reportJson --svg $reportSvg
if ($LASTEXITCODE -ne 0) {
    throw "Phase 6U report rendering failed with exit code $LASTEXITCODE"
}

Write-Host "Phase 6U benchmark and report completed."
