param(
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"
$sharedRunner = Join-Path $PSScriptRoot "run_shared_soa_proxy.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_shared_soa_adoption.py"
$sharedOutput = Join-Path $repositoryRoot "artifacts\phase3\shared-soa-proxy"
$sharedReport = Join-Path $sharedOutput "shared_soa_proxy_report.json"
$nativeReport = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_native_integration_report.json"
$changeBlockReport = Join-Path $repositoryRoot "docs\devlog\assets\phase6\change_block_adoption_report.json"

if (-not (Test-Path -LiteralPath $kitPython)) { throw "Application is not built." }
if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6bw" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$latestSharedSvg = Join-Path $OutputDir "shared_soa_proxy_latest.svg"
& $sharedRunner -LogCount 20 -ScalarSamples 2000 -BoundarySamples 25 -RunCount 3 -OutputDir $sharedOutput -SvgPath $latestSharedSvg
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$report = Join-Path $repositoryRoot "docs\devlog\assets\phase6\shared_soa_adoption_report.json"
$svg = Join-Path $repositoryRoot "docs\devlog\assets\phase6\shared_soa_adoption_report.svg"
& $kitPython $analyzer --shared $sharedReport --native $nativeReport --change-block $changeBlockReport --report $report --svg $svg
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Copy-Item -LiteralPath $report -Destination (Join-Path $OutputDir "shared_soa_adoption_report.json") -Force
