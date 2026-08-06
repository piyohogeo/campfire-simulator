param(
    [ValidateRange(3, 7)]
    [int]$PairCount = 3,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$phase3Runner = Join-Path $PSScriptRoot "run_phase3.ps1"
$comparator = Join-Path $PSScriptRoot "compare_phase3_slotted_cells.py"
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"

if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6ao\formal"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$dictionarySummaries = @()
$slottedSummaries = @()
$commonArguments = @{
    ArrayBackend = "python"
    ConstantHeatCapacityPath = "fast"
    HomogeneousHeatCapacityPath = "fast"
    InlineHomogeneousSensibleHeatCapacityPath = "fast"
    PythonSurfaceBoundaryPath = "fast"
    PythonStateClampPath = "fast"
    CellPhaseUpdates = "deferred"
    RuntimeMetrics = "compact"
    RuntimeTopology = "dynamic"
}

for ($pair = 1; $pair -le $PairCount; $pair++) {
    $paths = if ($pair % 2 -eq 1) {
        @("dictionary", "slotted")
    }
    else {
        @("slotted", "dictionary")
    }
    foreach ($pathName in $paths) {
        $runOutput = Join-Path $OutputDir ("pair_{0}_{1}" -f $pair, $pathName)
        $storage = if ($pathName -eq "slotted") { "slots" } else { "dict" }
        & $phase3Runner -OutputDir $runOutput -CellStateStorage $storage @commonArguments
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        $summary = Join-Path $runOutput "summary.json"
        if ($pathName -eq "slotted") {
            $slottedSummaries += $summary
        }
        else {
            $dictionarySummaries += $summary
        }
    }
}

$compareArguments = @("--dictionary-summary") + $dictionarySummaries + @("--slotted-summary") + $slottedSummaries
& $kitPython $comparator @compareArguments
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
