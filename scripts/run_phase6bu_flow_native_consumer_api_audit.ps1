param(
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.benchmark.kit"
$probe = Join-Path $PSScriptRoot "probe_flow_native_interface.py"

if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) {
    throw "Application is not built. Run .\repo.bat build first."
}
if (-not $Output) {
    $Output = Join-Path $repositoryRoot "artifacts\phase6\phase6bu-flow-native-consumer-api.json"
}
$Output = [System.IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Path (Split-Path -Parent $Output) -Force | Out-Null

& $kit @(
    $app,
    "--no-window",
    "--/app/quitAfter=120",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/phase6bu/output=$Output",
    "--exec",
    $probe
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$report = Get-Content -LiteralPath $Output -Raw | ConvertFrom-Json
if ($report.status -ne "ok" -or $report.phase -ne "phase6bu") {
    throw "Phase 6BU report failed: $Output"
}
if ($report.consumer_write_candidates.Count -ne 0) {
    throw (
        "Phase 6BU found possible public consumer-write members; inspect before changing the availability decision: {0}" -f
        ($report.consumer_write_candidates -join ", ")
    )
}

Write-Host (
    "Phase 6BU audited {0} public IFlowUsd members; no consumer-write candidate found: {1}" -f
    $report.public_members.Count,
    $Output
)
