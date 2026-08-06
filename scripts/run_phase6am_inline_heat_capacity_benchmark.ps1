param(
    [ValidateRange(3, 7)]
    [int]$PairCount = 3,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$phase3Runner = Join-Path $PSScriptRoot "run_phase3.ps1"
$comparator = Join-Path $PSScriptRoot "compare_phase3_inline_heat_capacity.py"
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"

if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6am\formal"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$baselineSummaries = @()
$inlineSummaries = @()
$commonArguments = @{
    ArrayBackend = "python"
    ConstantHeatCapacityPath = "fast"
    HomogeneousHeatCapacityPath = "fast"
    PythonSurfaceBoundaryPath = "fast"
    PythonStateClampPath = "fast"
    CellPhaseUpdates = "deferred"
    RuntimeMetrics = "compact"
    RuntimeTopology = "dynamic"
}

for ($pair = 1; $pair -le $PairCount; $pair++) {
    $paths = if ($pair % 2 -eq 1) {
        @("baseline", "inline")
    }
    else {
        @("inline", "baseline")
    }
    foreach ($pathName in $paths) {
        $runOutput = Join-Path $OutputDir ("pair_{0}_{1}" -f $pair, $pathName)
        $inlinePath = if ($pathName -eq "inline") { "fast" } else { "original" }
        & $phase3Runner -OutputDir $runOutput -InlineHomogeneousSensibleHeatCapacityPath $inlinePath @commonArguments
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        $summary = Join-Path $runOutput "summary.json"
        if ($pathName -eq "inline") {
            $inlineSummaries += $summary
        }
        else {
            $baselineSummaries += $summary
        }
    }
}

$compareArguments = @("--baseline-summary") + $baselineSummaries + @("--inline-summary") + $inlineSummaries
& $kitPython $comparator @compareArguments
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
