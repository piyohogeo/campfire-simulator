param(
    [ValidateRange(3, 7)]
    [int]$RunCount = 3,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$phase3Runner = Join-Path $PSScriptRoot "run_phase3.ps1"
$analyzer = Join-Path $PSScriptRoot "compare_phase3_adopted_profile.py"
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"

if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6ag"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$summaries = @()

for ($run = 1; $run -le $RunCount; $run++) {
    $runOutput = Join-Path $OutputDir ("adopted_profile_{0}" -f $run)
    & $phase3Runner -OutputDir $runOutput -ArrayBackend python -ProfileWoodInternals -PythonSurfaceBoundaryPath fast -PythonStateClampPath fast -CellPhaseUpdates deferred -RuntimeMetrics compact -RuntimeTopology dynamic
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $summaries += Join-Path $runOutput "summary.json"
}

& $kitPython $analyzer --summary @summaries
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
