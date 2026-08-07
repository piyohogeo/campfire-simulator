param(
    [ValidateRange(3, 9)]
    [int]$RunCount = 3,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"
$phase3Runner = Join-Path $PSScriptRoot "run_phase3.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_resident_write_audit.py"

if (-not (Test-Path -LiteralPath $kitPython)) { throw "Application is not built." }
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6be-repro"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$summaries = @()
for ($run = 1; $run -le $RunCount; $run++) {
    $runDir = Join-Path $OutputDir ("audit-{0:D2}" -f $run)
    & $phase3Runner -OutputDir $runDir -ResidentSnapshotAdapter -ResidentSnapshotTiming
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $summaries += Join-Path $runDir "summary.json"
}

$analyzerArgs = @($analyzer, "--summary") + $summaries
& $kitPython @analyzerArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
