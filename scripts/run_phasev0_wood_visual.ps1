param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$probe = Join-Path $PSScriptRoot "probe_phasev0_wood_visual.py"
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phasev0"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$report = Join-Path $OutputDir "wood_visual_probe.json"
$captures = Join-Path $OutputDir "captures"
$video = Join-Path $OutputDir "wood_visual_v0.mp4"
New-Item -ItemType Directory -Path $captures -Force | Out-Null
Remove-Item -LiteralPath $report -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $video -Force -ErrorAction SilentlyContinue

& $kit @(
    $app,
    "--/app/file/ignoreUnsavedOnExit=true",
    "--/app/quitAfter=10000",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/exts/campfire.app/woodVisualV0Enabled=false",
    "--/app/viewport/defaults/fillViewport=false",
    "--/phasev0/output=$report",
    "--/phasev0/captureDir=$captures",
    "--exec",
    $probe
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not (Test-Path -LiteralPath $report)) {
    throw "Wood visual V0 probe report is missing."
}
$result = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ($result.status -ne "ok") {
    throw "Wood visual V0 probe failed: $report"
}

$ffmpeg = Get-Command ffmpeg.exe -ErrorAction Stop
& $ffmpeg.Source -y -framerate 10 -i (Join-Path $captures "frame_%04d.png") -c:v libx264 -preset medium -crf 22 -pix_fmt yuv420p -movflags +faststart $video
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $video)) {
    throw "Wood visual V0 video encoding failed."
}
Write-Host ("Wood visual V0: {0}/{1} gates, p95={2:N4} ms, video={3}" -f @($result.gates.PSObject.Properties | Where-Object Value).Count, @($result.gates.PSObject.Properties).Count, $result.publication.timing.p95_ms, $video)
