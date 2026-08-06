param(
    [ValidateRange(3, 7)]
    [int]$PairCount = 3,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$phase3Runner = Join-Path $PSScriptRoot "run_phase3.ps1"
$comparator = Join-Path $PSScriptRoot "compare_phase3_runtime_metrics.py"
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"

if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6ae\formal"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$fullSummaries = @()
$compactSummaries = @()

for ($pair = 1; $pair -le $PairCount; $pair++) {
    $paths = if ($pair % 2 -eq 1) { @("full", "compact") } else { @("compact", "full") }
    foreach ($pathName in $paths) {
        $runOutput = Join-Path $OutputDir ("pair_{0}_{1}" -f $pair, $pathName)
        & $phase3Runner -OutputDir $runOutput -ArrayBackend python -CellStateStorage dict -ConstantHeatCapacityPath original -PythonSurfaceBoundaryPath fast -PythonStateClampPath fast -CellPhaseUpdates deferred -RuntimeMetrics $pathName -RuntimeTopology dynamic
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        $summary = Join-Path $runOutput "summary.json"
        if ($pathName -eq "compact") {
            $compactSummaries += $summary
        }
        else {
            $fullSummaries += $summary
        }
    }
}

$compareArgs = @("--full-summary") + $fullSummaries + @("--compact-summary") + $compactSummaries
& $kitPython $comparator @compareArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
