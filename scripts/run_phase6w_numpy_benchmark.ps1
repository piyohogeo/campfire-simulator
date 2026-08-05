$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"
$benchmark = Join-Path $PSScriptRoot "benchmark_wood_numpy_backend.py"
$renderer = Join-Path $PSScriptRoot "render_wood_numpy_prototype_report.py"

& $kitPython $benchmark @args
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $kitPython $renderer
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
