param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$auditScript = Join-Path $PSScriptRoot "audit_phasev3ma_hierarchy.py"
$probeScript = Join-Path $PSScriptRoot "probe_phasev3ma_hierarchy_mesh.py"
$analyzeScript = Join-Path $PSScriptRoot "analyze_phasev3ma.py"
if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phasev3ma" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$audit = Join-Path $OutputDir "hierarchy_audit.json"
$probe = Join-Path $OutputDir "isolated_mesh_probe.json"
$final = Join-Path $OutputDir "phasev3ma_final_report.json"
$captures = Join-Path $OutputDir "captures"
$video = Join-Path $OutputDir "isolated_mesh_checker.mp4"
New-Item -ItemType Directory -Path $captures -Force | Out-Null

python $auditScript --root $repositoryRoot --output $audit
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $kit @(
    $app,
    "--/app/file/ignoreUnsavedOnExit=true",
    "--/app/quitAfter=10000",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/app/viewport/defaults/fillViewport=false",
    "--/phasev3ma/output=$probe",
    "--/phasev3ma/captureDir=$captures",
    "--exec",
    $probeScript
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python $analyzeScript --audit $audit --probe $probe --output $final
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$ffmpeg = Get-Command ffmpeg.exe -ErrorAction Stop
$ordered = @(
    "mesh_checker_right_cap.png",
    "mesh_checker_left_cap.png",
    "mesh_checker_transformed.png",
    "mesh_checker_reloaded.png"
)
for ($index = 0; $index -lt $ordered.Count; $index++) {
    Copy-Item -LiteralPath (Join-Path $captures $ordered[$index]) -Destination (Join-Path $captures ("frame_{0:D4}.png" -f ($index + 1))) -Force
}
& $ffmpeg.Source -y -framerate 2 -i (Join-Path $captures "frame_%04d.png") -c:v libx264 -preset medium -crf 22 -pix_fmt yuv420p -movflags +faststart $video
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $video)) {
    throw "Phase V3M-A video encoding failed."
}
$result = Get-Content -LiteralPath $final -Raw | ConvertFrom-Json
Write-Host ("Phase V3M-A: status={0}, gates={1}/{2}, Mesh={3}" -f $result.status, @($result.gates.psobject.Properties | Where-Object { $_.Value }).Count, @($result.gates.psobject.Properties).Count, $result.decision.phasev3ma_qualified)
