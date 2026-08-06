param(
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$phase3Runner = Join-Path $PSScriptRoot "run_phase3.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase3_state_diagnostics.py"
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"

if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6ab\state_diagnostics"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)

& $phase3Runner `
    -OutputDir $OutputDir `
    -ArrayBackend python `
    -PythonSurfaceBoundaryPath fast `
    -PythonStateClampPath original `
    -CellPhaseUpdates eager `
    -RuntimeMetrics full `
    -RuntimeTopology dynamic `
    -CollectWoodStateDiagnostics
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $kitPython $analyzer --summary (Join-Path $OutputDir "summary.json")
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
