param(
    [ValidateRange(3, 7)]
    [int]$PairCount = 3,
    [string]$OutputDir = "",
    [string]$OriginalProfileSummary = "",
    [string]$FastProfileSummary = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$phase3Runner = Join-Path $PSScriptRoot "run_phase3.ps1"
$comparator = Join-Path $PSScriptRoot "compare_phase3_surface_boundary.py"
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"

if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6aa\formal"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$originalSummaries = @()
$fastSummaries = @()

if (-not $OriginalProfileSummary -and -not $FastProfileSummary) {
    $originalProfileOutput = Join-Path $OutputDir "profile_original"
    $fastProfileOutput = Join-Path $OutputDir "profile_fast"
    & $phase3Runner -OutputDir $originalProfileOutput -ArrayBackend python -ProfileWoodInternals -PythonSurfaceBoundaryPath original -PythonStateClampPath original -CellPhaseUpdates eager -RuntimeMetrics full -RuntimeTopology dynamic
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    & $phase3Runner -OutputDir $fastProfileOutput -ArrayBackend python -ProfileWoodInternals -PythonSurfaceBoundaryPath fast -PythonStateClampPath original -CellPhaseUpdates eager -RuntimeMetrics full -RuntimeTopology dynamic
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    $OriginalProfileSummary = Join-Path $originalProfileOutput "summary.json"
    $FastProfileSummary = Join-Path $fastProfileOutput "summary.json"
}
elseif (-not $OriginalProfileSummary -or -not $FastProfileSummary) {
    throw "Supply both profile summaries or neither."
}

for ($pair = 1; $pair -le $PairCount; $pair++) {
    $paths = if ($pair % 2 -eq 1) { @("original", "fast") } else { @("fast", "original") }
    foreach ($pathName in $paths) {
        $runOutput = Join-Path $OutputDir ("pair_{0}_{1}" -f $pair, $pathName)
        if ($pathName -eq "fast") {
            & $phase3Runner -OutputDir $runOutput -ArrayBackend python -PythonSurfaceBoundaryPath fast -PythonStateClampPath original -CellPhaseUpdates eager -RuntimeMetrics full -RuntimeTopology dynamic
        }
        else {
            & $phase3Runner -OutputDir $runOutput -ArrayBackend python -PythonSurfaceBoundaryPath original -PythonStateClampPath original -CellPhaseUpdates eager -RuntimeMetrics full -RuntimeTopology dynamic
        }
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
        $summary = Join-Path $runOutput "summary.json"
        if ($pathName -eq "fast") {
            $fastSummaries += $summary
        }
        else {
            $originalSummaries += $summary
        }
    }
}

$compareArgs = @("--original-summary") + $originalSummaries + @("--fast-summary") + $fastSummaries + @(
    "--original-profile", [System.IO.Path]::GetFullPath($OriginalProfileSummary),
    "--fast-profile", [System.IO.Path]::GetFullPath($FastProfileSummary)
)

& $kitPython $comparator @compareArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
