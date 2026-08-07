param(
    [ValidateRange(3, 7)]
    [int]$RunCount = 3,
    [ValidateRange(40, 2000)]
    [int]$Iterations = 300,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"
$benchmark = Join-Path $PSScriptRoot "benchmark_resident_revision_boundary.py"
$analyzer = Join-Path $PSScriptRoot "analyze_resident_revision_boundary.py"

if (-not (Test-Path -LiteralPath $kitPython)) { throw "Application is not built." }
if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6az" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$rawReport = Join-Path $OutputDir "resident_revision_boundary_raw.json"
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
& $kitPython $benchmark --logs 20 --iterations $Iterations --runs $RunCount --output $rawReport
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $kitPython $analyzer --raw $rawReport
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
