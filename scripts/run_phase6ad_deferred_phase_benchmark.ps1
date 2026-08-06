param(
    [ValidateRange(3, 7)]
    [int]$PairCount = 3,
    [string]$OutputDir = "",
    [string]$EagerProfileSummary = "",
    [string]$DeferredProfileSummary = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$phase3Runner = Join-Path $PSScriptRoot "run_phase3.ps1"
$comparator = Join-Path $PSScriptRoot "compare_phase3_deferred_phases.py"
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"

if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6ad\formal"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$eagerSummaries = @()
$deferredSummaries = @()

if (-not $EagerProfileSummary -and -not $DeferredProfileSummary) {
    $eagerProfileOutput = Join-Path $OutputDir "profile_eager"
    $deferredProfileOutput = Join-Path $OutputDir "profile_deferred"
    & $phase3Runner -OutputDir $eagerProfileOutput -ArrayBackend python -ConstantHeatCapacityPath original -ProfileWoodInternals -PythonSurfaceBoundaryPath fast -PythonStateClampPath fast -CellPhaseUpdates eager -RuntimeMetrics full -RuntimeTopology dynamic
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $phase3Runner -OutputDir $deferredProfileOutput -ArrayBackend python -ConstantHeatCapacityPath original -ProfileWoodInternals -PythonSurfaceBoundaryPath fast -PythonStateClampPath fast -CellPhaseUpdates deferred -RuntimeMetrics full -RuntimeTopology dynamic
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $EagerProfileSummary = Join-Path $eagerProfileOutput "summary.json"
    $DeferredProfileSummary = Join-Path $deferredProfileOutput "summary.json"
}
elseif (-not $EagerProfileSummary -or -not $DeferredProfileSummary) {
    throw "Supply both profile summaries or neither."
}

for ($pair = 1; $pair -le $PairCount; $pair++) {
    $paths = if ($pair % 2 -eq 1) { @("eager", "deferred") } else { @("deferred", "eager") }
    foreach ($pathName in $paths) {
        $runOutput = Join-Path $OutputDir ("pair_{0}_{1}" -f $pair, $pathName)
        & $phase3Runner -OutputDir $runOutput -ArrayBackend python -ConstantHeatCapacityPath original -PythonSurfaceBoundaryPath fast -PythonStateClampPath fast -CellPhaseUpdates $pathName -RuntimeMetrics full -RuntimeTopology dynamic
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        $summary = Join-Path $runOutput "summary.json"
        if ($pathName -eq "deferred") {
            $deferredSummaries += $summary
        }
        else {
            $eagerSummaries += $summary
        }
    }
}

$compareArgs = @("--eager-summary") + $eagerSummaries + @("--deferred-summary") + $deferredSummaries + @(
    "--eager-profile", [System.IO.Path]::GetFullPath($EagerProfileSummary),
    "--deferred-profile", [System.IO.Path]::GetFullPath($DeferredProfileSummary)
)
& $kitPython $comparator @compareArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
