param(
    [ValidateRange(3, 7)]
    [int]$PairCount = 3,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$phase3Runner = Join-Path $PSScriptRoot "run_phase3.ps1"
$comparator = Join-Path $PSScriptRoot "compare_phase3_runtime_topology.py"
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"

if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6af\formal"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$dynamicSummaries = @()
$precomputedSummaries = @()

for ($pair = 1; $pair -le $PairCount; $pair++) {
    $paths = if ($pair % 2 -eq 1) { @("dynamic", "precomputed") } else { @("precomputed", "dynamic") }
    foreach ($pathName in $paths) {
        $runOutput = Join-Path $OutputDir ("pair_{0}_{1}" -f $pair, $pathName)
        & $phase3Runner -OutputDir $runOutput -ArrayBackend python -CellStateStorage dict -ConstantHeatCapacityPath original -PythonSurfaceBoundaryPath fast -PythonStateClampPath fast -CellPhaseUpdates deferred -RuntimeMetrics compact -RuntimeTopology $pathName
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        $summary = Join-Path $runOutput "summary.json"
        if ($pathName -eq "precomputed") {
            $precomputedSummaries += $summary
        }
        else {
            $dynamicSummaries += $summary
        }
    }
}

$compareArgs = @("--dynamic-summary") + $dynamicSummaries + @("--precomputed-summary") + $precomputedSummaries
& $kitPython $comparator @compareArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
