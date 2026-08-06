param(
    [ValidateRange(3, 7)]
    [int]$RunCount = 3,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$phase3Runner = Join-Path $PSScriptRoot "run_phase3.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase3_inline_reprofile.py"
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"

if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6an"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$internalSummaries = @()
$sensibleSummaries = @()
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

for ($run = 1; $run -le $RunCount; $run++) {
    $runOutput = Join-Path $OutputDir ("internal_profile_{0}" -f $run)
    & $phase3Runner -OutputDir $runOutput -ProfileWoodInternals @commonArguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $internalSummaries += Join-Path $runOutput "summary.json"
}

for ($run = 1; $run -le $RunCount; $run++) {
    $runOutput = Join-Path $OutputDir ("sensible_profile_{0}" -f $run)
    & $phase3Runner -OutputDir $runOutput -ProfileWoodInternals -ProfileSensibleHeat @commonArguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $sensibleSummaries += Join-Path $runOutput "summary.json"
}

$analyzerArguments = @("--internal-summary") + $internalSummaries + @("--sensible-summary") + $sensibleSummaries
& $kitPython $analyzer @analyzerArguments
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
