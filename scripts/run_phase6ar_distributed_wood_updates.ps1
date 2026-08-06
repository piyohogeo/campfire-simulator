param(
    [ValidateRange(3, 7)]
    [int]$RunCount = 3,
    [ValidateRange(40, 1200)]
    [int]$Cycles = 200,
    [ValidateRange(1, 200)]
    [int]$WarmupCycles = 20,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"
$benchmark = Join-Path $PSScriptRoot "benchmark_distributed_wood_updates.py"
$analyzer = Join-Path $PSScriptRoot "analyze_distributed_wood_updates.py"

if (-not (Test-Path -LiteralPath $kitPython)) {
    throw "Application is not built. Run .\repo.bat build first."
}
if ($WarmupCycles -ge $Cycles) {
    throw "WarmupCycles must be smaller than Cycles."
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6ar"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$rawReport = Join-Path $OutputDir "distributed_wood_updates_raw.json"

& $kitPython $benchmark --active-counts 2 5 10 12 20 --runs $RunCount --cycles $Cycles --warmup-cycles $WarmupCycles --precondition-steps 900 --output $rawReport
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $kitPython $analyzer --raw $rawReport
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
