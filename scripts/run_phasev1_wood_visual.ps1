param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$probe = Join-Path $PSScriptRoot "probe_phasev1_wood_visual.py"
if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phasev1" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$report = Join-Path $OutputDir "wood_visual_band_probe.json"
$captures = Join-Path $OutputDir "captures"
$video = Join-Path $OutputDir "wood_visual_v0_v1_fixed_snapshot.mp4"
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
    "--/exts/campfire.app/woodVisualV1Enabled=false",
    "--/app/viewport/defaults/fillViewport=false",
    "--/phasev1/output=$report",
    "--/phasev1/captureDir=$captures",
    "--exec",
    $probe
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$result = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ($result.status -ne "ok") { throw "Wood visual V1 probe failed: $report" }
$ffmpeg = Get-Command ffmpeg.exe -ErrorAction Stop
& $ffmpeg.Source -y -framerate 5 -i (Join-Path $captures "frame_%04d.png") -c:v libx264 -preset medium -crf 22 -pix_fmt yuv420p -movflags +faststart $video
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $video)) { throw "Wood visual V1 video encoding failed." }
Write-Host ("Wood visual V1: {0}/{1} gates, 20-log p95={2:N4} ms" -f @($result.gates.PSObject.Properties | Where-Object Value).Count, @($result.gates.PSObject.Properties).Count, $result.twenty_log.timing.p95_ms)
