param(
    [ValidateRange(3, 7)]
    [int]$RunCount = 3,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$phase3Runner = Join-Path $PSScriptRoot "run_phase3.ps1"
$summarizer = Join-Path $PSScriptRoot "summarize_phase3_python_profiles.py"
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"

if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6y"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$summaries = @()

for ($run = 1; $run -le $RunCount; $run++) {
    $runOutput = Join-Path $OutputDir ("python_profile_{0}" -f $run)
    & $phase3Runner -OutputDir $runOutput -ArrayBackend python -CellStateStorage dict -ConstantHeatCapacityPath original -ProfileWoodInternals -PythonSurfaceBoundaryPath original -PythonStateClampPath original -CellPhaseUpdates eager -RuntimeMetrics full -RuntimeTopology dynamic
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    $summaries += Join-Path $runOutput "summary.json"
}

& $kitPython $summarizer --summary @summaries
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
