param(
    [ValidateRange(20, 5000)]
    [int]$Iterations = 120,
    [ValidateRange(1, 500)]
    [int]$Warmup = 20
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"
$benchmark = Join-Path $PSScriptRoot "benchmark_emitter_transport_scalability.py"

if (-not (Test-Path -LiteralPath $kitPython)) {
    throw "Application is not built. Run .\repo.bat build first."
}

& $kitPython $benchmark --iterations $Iterations --warmup $Warmup
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
