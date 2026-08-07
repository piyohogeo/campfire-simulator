param(
    [ValidateRange(100, 5000)]
    [int]$Iterations = 400,
    [ValidateRange(3, 9)]
    [int]$RunCount = 5
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"
$analyzer = Join-Path $PSScriptRoot "analyze_usd_change_block.py"

if (-not (Test-Path -LiteralPath $kitPython)) {
    throw "Application is not built. Run .\repo.bat build first."
}

& $kitPython $analyzer --iterations $Iterations --runs $RunCount
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
