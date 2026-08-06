param(
    [ValidateRange(3, 7)]
    [int]$PairCount = 3,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$phase3Runner = Join-Path $PSScriptRoot "run_phase3.ps1"
$comparator = Join-Path $PSScriptRoot "compare_phase3_heat_capacity.py"
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"

if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6ai\formal"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$originalSummaries = @()
$fastSummaries = @()
$commonArguments = @{
    ArrayBackend = "python"
    PythonSurfaceBoundaryPath = "fast"
    PythonStateClampPath = "fast"
    CellPhaseUpdates = "deferred"
    RuntimeMetrics = "compact"
    RuntimeTopology = "dynamic"
}

foreach ($pathName in @("original", "fast")) {
    $profileOutput = Join-Path $OutputDir ("profile_{0}" -f $pathName)
    & $phase3Runner -OutputDir $profileOutput -ConstantHeatCapacityPath $pathName -ProfileWoodInternals -ProfileSensibleHeat @commonArguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ($pathName -eq "original") {
        $originalProfileSummary = Join-Path $profileOutput "summary.json"
    }
    else {
        $fastProfileSummary = Join-Path $profileOutput "summary.json"
    }
}

for ($pair = 1; $pair -le $PairCount; $pair++) {
    $paths = if ($pair % 2 -eq 1) { @("original", "fast") } else { @("fast", "original") }
    foreach ($pathName in $paths) {
        $runOutput = Join-Path $OutputDir ("pair_{0}_{1}" -f $pair, $pathName)
        & $phase3Runner -OutputDir $runOutput -ConstantHeatCapacityPath $pathName @commonArguments
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        $summary = Join-Path $runOutput "summary.json"
        if ($pathName -eq "fast") {
            $fastSummaries += $summary
        }
        else {
            $originalSummaries += $summary
        }
    }
}

$compareArguments = @("--original-summary") + $originalSummaries + @("--fast-summary") + $fastSummaries + @(
    "--original-profile", $originalProfileSummary,
    "--fast-profile", $fastProfileSummary
)
& $kitPython $comparator @compareArguments
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
