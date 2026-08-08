param(
    [string]$Scene = "",
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.benchmark.kit"
$probe = Join-Path $PSScriptRoot "probe_resident_timeline_playback.py"

if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) {
    throw "Application is not built. Run .\repo.bat build first."
}
if (-not $Scene) {
    $Scene = Join-Path $repositoryRoot "artifacts\phase3\phase6cn\scene\phase3_point_application.usda"
}
if (-not $Output) {
    $Output = Join-Path $repositoryRoot "artifacts\phase3\phase6co\timeline_probe.json"
}
$Scene = [System.IO.Path]::GetFullPath($Scene)
$Output = [System.IO.Path]::GetFullPath($Output)
if (-not (Test-Path -LiteralPath $Scene)) { throw "Phase 6CO input scene is missing: $Scene" }
New-Item -ItemType Directory -Path (Split-Path -Parent $Output) -Force | Out-Null

& $kit @(
    $app,
    "--no-window",
    "--/app/quitAfter=120",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/phase6co/scene=$Scene",
    "--/phase6co/output=$Output",
    "--/rtx/flow/enabled=true",
    "--exec",
    $probe
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$result = Get-Content -LiteralPath $Output -Raw | ConvertFrom-Json
if ($result.status -ne "ok" -or $result.phase -ne "phase6co") {
    throw "Phase 6CO probe failed: $Output"
}
$result.timeline.strategies | ForEach-Object {
    Write-Host ("Phase 6CO {0}: advanced from zero={1}, remained playing={2}, events={3}" -f $_.name, $_.advanced_from_zero, $_.remained_playing, (($_.events.event) -join ","))
}
