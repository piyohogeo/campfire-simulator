param(
    [ValidateRange(3, 7)]
    [int]$RunCount = 3,
    [ValidateRange(40, 1200)]
    [int]$Steps = 200,
    [ValidateRange(1, 200)]
    [int]$WarmupSteps = 20,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"
$benchmark = Join-Path $PSScriptRoot "benchmark_wood_scaling.py"
$analyzer = Join-Path $PSScriptRoot "analyze_wood_scaling.py"

if (-not (Test-Path -LiteralPath $kitPython)) {
    throw "Application is not built. Run .\repo.bat build first."
}
if ($WarmupSteps -ge $Steps) {
    throw "WarmupSteps must be smaller than Steps."
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6aq"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$rawReport = Join-Path $OutputDir "wood_scaling_raw.json"

& $kitPython $benchmark --counts 2 5 10 20 --runs $RunCount --steps $Steps --warmup-steps $WarmupSteps --precondition-steps 900 --output $rawReport
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $kitPython $analyzer --raw $rawReport
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
