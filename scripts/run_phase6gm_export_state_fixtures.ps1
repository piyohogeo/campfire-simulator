param([Parameter(Mandatory = $true)][string]$OutputRoot)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6GM export fixture refuses output reuse: $OutputRoot" }
$release = Join-Path (Split-Path -Parent $PSScriptRoot) "_build\windows-x86_64\release"
$usd = Get-ChildItem (Join-Path $release "extscache") -Directory -Filter "omni.usd.libs*" | Select-Object -First 1
if ($null -eq $usd) { throw "Phase 6GM could not locate the local USD Python package" }
$python = Join-Path $release "kit\python\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Phase 6GM could not locate the local Kit Python executable" }
$before = @(Get-Process -Name kit -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
$savedPythonPath = $env:PYTHONPATH
$savedPath = $env:PATH
try {
    $env:PYTHONPATH = "$($usd.FullName);$(Join-Path $release 'site');$PSScriptRoot"
    $env:PATH = "$(Join-Path $usd.FullName 'bin');$savedPath"
    & $python (Join-Path $PSScriptRoot "phase6gm_export_state_fixtures.py") --output $OutputRoot
    if ($LASTEXITCODE -ne 0) { throw "Phase 6GM offline export-state fixture failed" }
} finally {
    $env:PYTHONPATH = $savedPythonPath
    $env:PATH = $savedPath
}
$after = @(Get-Process -Name kit -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
$newKit = @($after | Where-Object { $_ -notin $before })
if ($newKit.Count -ne 0) { throw "Phase 6GM offline fixture unexpectedly launched Kit" }
$reportPath = Join-Path $OutputRoot "report.json"
$report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
if (-not $report.passed -or $report.kit_process_launched) { throw "Phase 6GM offline report did not pass" }

