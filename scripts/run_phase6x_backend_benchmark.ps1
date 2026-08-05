param(
    [ValidateRange(2, 10)]
    [int]$PairCount = 2,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$phase3Runner = Join-Path $PSScriptRoot "run_phase3.ps1"
$comparator = Join-Path $PSScriptRoot "compare_phase3_backends.py"
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"

if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6x"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$pythonSummaries = @()
$numpySummaries = @()

for ($pair = 1; $pair -le $PairCount; $pair++) {
    $backends = if ($pair % 2 -eq 1) { @("python", "numpy") } else { @("numpy", "python") }
    foreach ($backend in $backends) {
        $runOutput = Join-Path $OutputDir ("pair_{0}_{1}" -f $pair, $backend)
        & $phase3Runner -OutputDir $runOutput -ArrayBackend $backend
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
        $summary = Join-Path $runOutput "summary.json"
        if ($backend -eq "python") {
            $pythonSummaries += $summary
        }
        else {
            $numpySummaries += $summary
        }
    }
}

$compareArgs = @("--python-summary") + $pythonSummaries + @("--numpy-summary") + $numpySummaries
& $kitPython $comparator @compareArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
