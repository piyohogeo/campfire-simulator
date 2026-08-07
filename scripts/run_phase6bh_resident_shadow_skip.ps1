param(
    [ValidateRange(3, 9)]
    [int]$RunCount = 3,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"
$phase3Runner = Join-Path $PSScriptRoot "run_phase3.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_resident_shadow_skip.py"

if (-not (Test-Path -LiteralPath $kitPython)) { throw "Application is not built." }
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6bh-repro"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$baselineSummaries = @()
$candidateSummaries = @()
for ($run = 1; $run -le $RunCount; $run++) {
    $baselineDir = Join-Path $OutputDir ("lightweight-{0:D2}" -f $run)
    $candidateDir = Join-Path $OutputDir ("shadow-skip-{0:D2}" -f $run)
    $baselineArgs = @{
        OutputDir = $baselineDir
        ResidentSnapshotAdapter = $true
        ResidentSnapshotHandleCache = $true
        ResidentSnapshotLightweightCommit = $true
    }
    $candidateArgs = @{
        OutputDir = $candidateDir
        ResidentSnapshotAdapter = $true
        ResidentSnapshotHandleCache = $true
        ResidentSnapshotLightweightCommit = $true
        ResidentSnapshotSkipUnchanged = $true
    }
    if (($run % 2) -eq 1) {
        & $phase3Runner @baselineArgs
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $phase3Runner @candidateArgs
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    else {
        & $phase3Runner @candidateArgs
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $phase3Runner @baselineArgs
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    $baselineSummaries += Join-Path $baselineDir "summary.json"
    $candidateSummaries += Join-Path $candidateDir "summary.json"
}

$analyzerArgs = @($analyzer, "--baseline") + $baselineSummaries + @("--candidate") + $candidateSummaries
& $kitPython @analyzerArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
