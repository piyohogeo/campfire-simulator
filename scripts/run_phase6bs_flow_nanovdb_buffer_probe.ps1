param(
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.benchmark.kit"
$probe = Join-Path $PSScriptRoot "probe_flow_nanovdb_buffers.py"

if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) {
    throw "Application is not built. Run .\repo.bat build first."
}
if (-not $Output) {
    $Output = Join-Path $repositoryRoot "artifacts\phase6\phase6bs-nanovdb-buffers.json"
}
$Output = [System.IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Path (Split-Path -Parent $Output) -Force | Out-Null

& $kit @(
    $app,
    "--no-window",
    "--/app/quitAfter=180",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/rtx/flow/enabled=true",
    "--/phase6bs/output=$Output",
    "--exec",
    $probe
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$report = Get-Content -LiteralPath $Output -Raw | ConvertFrom-Json
if ($report.status -ne "ok" -or $report.phase -ne "phase6bs") {
    throw "Phase 6BS report failed: $Output"
}
foreach ($case in $report.cases) {
    if ($case.buffer_count -ne 5) {
        throw "Phase 6BS expected five buffers for $($case.name)."
    }
}

Write-Host "Phase 6BS inspected five buffers across $($report.cases.Count) RGB cases: $Output"
