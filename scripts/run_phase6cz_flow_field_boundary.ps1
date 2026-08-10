param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$probe = Join-Path $PSScriptRoot "probe_resident_flow_field_boundary.py"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6cz_flow_field_boundary.py"
$kitPython = Join-Path $releaseRoot "kit\python\python.exe"
$nativeLibrary = Join-Path $repositoryRoot "artifacts\phase3\phase6co-resident\native-build\campfire_wood_native.dll"
if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6cz-flow-field-boundary" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$sceneDir = Join-Path $OutputDir "scene"
$frames = Join-Path $OutputDir "video_frames"
$base = Join-Path $OutputDir "summary.json"
$raw = Join-Path $OutputDir "flow_field_boundary.json"
$log = Join-Path $OutputDir "phase6cz.log"

if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) { throw "Application is not built." }
if (-not (Test-Path -LiteralPath $nativeLibrary)) { throw "Phase 6CZ requires the existing Phase 6CO native build: $nativeLibrary" }
New-Item -ItemType Directory -Path $sceneDir -Force | Out-Null
$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $app).Hash
foreach ($path in @($base, $raw, $log)) {
    Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
}

& $kit @(
    $app,
    "--no-window",
    "--/app/file/ignoreUnsavedOnExit=true",
    "--/app/quitAfter=30000",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=true",
    "--/exts/campfire.app/phase=phase3",
    "--/exts/campfire.app/captureOnStartup=true",
    "--/exts/campfire.app/quitAfterCapture=true",
    "--/exts/campfire.app/outputDir=$OutputDir",
    "--/exts/campfire.app/sceneOutputDir=$sceneDir",
    "--/exts/campfire.app/residentPointApplicationEnabled=true",
    "--/exts/campfire.app/woodRenderHierarchyEnabled=false",
    "--/exts/campfire.app/woodVisualV3Enabled=false",
    "--/exts/campfire.app/residentPointTimelineContinuityQualificationEnabled=true",
    "--/exts/campfire.app/residentNativeLibraryPath=$nativeLibrary",
    "--/phase6cz/output=$raw",
    "--/rtx/flow/enabled=true",
    "--/log/file=$log",
    "--/log/fileLogLevel=Info",
    "--exec",
    $probe
)
$kitExitCode = $LASTEXITCODE
$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $app).Hash
if ($productionHashBefore -ne $productionHashAfter) { throw "Phase 6CZ changed the production app file." }

$probeResult = Get-Content -LiteralPath $raw -Raw | ConvertFrom-Json
if ($probeResult.status -ne "ok") { throw "Phase 6CZ probe failed: $raw" }
$baseResult = Get-Content -LiteralPath $base -Raw | ConvertFrom-Json
$legacyFalseGates = @(
    "stopped_layout_published_atomically",
    "point_pose_alignment_remained_within_tolerance",
    "point_flow_timeline_stop_reproduced",
    "timeline_held_at_zero_despite_explicit_transport"
)
$unexpectedBaseFailures = @(
    $baseResult.gates.PSObject.Properties |
        Where-Object { -not $_.Value -and $_.Name -notin $legacyFalseGates } |
        ForEach-Object { $_.Name }
)
if ($baseResult.phase -ne "phase6co" -or $unexpectedBaseFailures.Count -ne 0) {
    throw "Phase 6CZ base scenario has unexpected failures: $($unexpectedBaseFailures -join ', ')"
}
if ($kitExitCode -ne 0 -and $baseResult.status -ne "failed") {
    throw "Phase 6CZ Kit exited with $kitExitCode without the expected superseded Phase 6CO gate result."
}

$report = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_flow_field_boundary_report.json"
$svg = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_flow_field_boundary_report.svg"
$poster = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_flow_field_boundary_frame.png"
$video = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_flow_field_boundary.mp4"
& $kitPython $analyzer --raw $raw --base $base --report $report --svg $svg --poster $poster --frames $frames --production-sha256-before $productionHashBefore --production-sha256-after $productionHashAfter
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$ffmpeg = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
if (-not $ffmpeg) { throw "ffmpeg.exe is required to encode the Phase 6CZ video." }
& $ffmpeg.Source -y -framerate 10 -i (Join-Path $frames "frame_%04d.png") -c:v libx264 -preset medium -crf 22 -pix_fmt yuv420p -movflags +faststart $video
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host ("Phase 6CZ sampled Flow boundary: zeroTransition={0}, pointJumpMm={1}" -f $probeResult.observation.no_sampled_zero_field_transition, ($probeResult.layout_boundary.point_centroid_displacement_m * 1000.0))
