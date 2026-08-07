param(
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"
$phase3Runner = Join-Path $PSScriptRoot "run_phase3.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_resident_snapshot_adapter.py"

if (-not (Test-Path -LiteralPath $kitPython)) { throw "Application is not built." }
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6bc-repro"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$baselineDir = Join-Path $OutputDir "baseline"
$adapterDir = Join-Path $OutputDir "adapter"
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

& $phase3Runner -OutputDir $baselineDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $phase3Runner -OutputDir $adapterDir -ResidentSnapshotAdapter
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $kitPython $analyzer `
    --baseline (Join-Path $baselineDir "summary.json") `
    --adapter (Join-Path $adapterDir "summary.json")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
