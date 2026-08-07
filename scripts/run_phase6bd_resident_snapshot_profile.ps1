param(
    [ValidateRange(3, 9)]
    [int]$RunCount = 3,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"
$phase3Runner = Join-Path $PSScriptRoot "run_phase3.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_resident_snapshot_profile.py"

if (-not (Test-Path -LiteralPath $kitPython)) { throw "Application is not built." }
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6bd-repro"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$plainSummaries = @()
$profileSummaries = @()
for ($run = 1; $run -le $RunCount; $run++) {
    $plainDir = Join-Path $OutputDir ("plain-{0:D2}" -f $run)
    $profileDir = Join-Path $OutputDir ("profile-{0:D2}" -f $run)
    if (($run % 2) -eq 1) {
        & $phase3Runner -OutputDir $plainDir -ResidentSnapshotAdapter
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $phase3Runner -OutputDir $profileDir -ResidentSnapshotAdapter -ResidentSnapshotTiming
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    else {
        & $phase3Runner -OutputDir $profileDir -ResidentSnapshotAdapter -ResidentSnapshotTiming
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $phase3Runner -OutputDir $plainDir -ResidentSnapshotAdapter
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    $plainSummaries += Join-Path $plainDir "summary.json"
    $profileSummaries += Join-Path $profileDir "summary.json"
}

$analyzerArgs = @($analyzer, "--plain") + $plainSummaries + @("--profile") + $profileSummaries
& $kitPython @analyzerArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
