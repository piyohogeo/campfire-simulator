param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$probe = Join-Path $PSScriptRoot "probe_phasev3_dynamic_texture.py"
if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phasev3" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$report = Join-Path $OutputDir "dynamic_texture_feasibility.json"
$captures = Join-Path $OutputDir "captures"
$video = Join-Path $OutputDir "dynamic_texture_feasibility.mp4"
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
    "--/app/viewport/defaults/fillViewport=false",
    "--/phasev3/output=$report",
    "--/phasev3/captureDir=$captures",
    "--exec",
    $probe
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$result = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ($result.status -eq "error") { throw "Dynamic texture feasibility probe errored: $report" }
$ffmpeg = Get-Command ffmpeg.exe -ErrorAction Stop
$ordered = @(
    "dynamic_checker_initial.png",
    "dynamic_checker_update_1.png",
    "dynamic_checker_update_2.png",
    "dynamic_checker_update_3.png",
    "dynamic_checker_update_4.png",
    "dynamic_checker_transformed.png",
    "dynamic_checker_reloaded.png"
)
for ($index = 0; $index -lt $ordered.Count; $index++) {
    Copy-Item -LiteralPath (Join-Path $captures $ordered[$index]) -Destination (Join-Path $captures ("frame_{0:D4}.png" -f ($index + 1))) -Force
}
& $ffmpeg.Source -y -framerate 2 -i (Join-Path $captures "frame_%04d.png") -c:v libx264 -preset medium -crf 22 -pix_fmt yuv420p -movflags +faststart $video
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $video)) { throw "Phase V3 feasibility video encoding failed." }
Write-Host ("Phase V3 feasibility: status={0}, UV360={1}, fixedURI={2}" -f $result.status, $result.gates.analytic_cylinder_uv_maps_360_cells, $result.gates.fixed_dynamic_uri_preserved)
