param(
    [string]$OutputDir = "",
    [switch]$ReuseBaseline
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$probe = Join-Path $PSScriptRoot "probe_resident_dynamic_translation.py"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6db_translation_performance.py"
$kitPython = Join-Path $releaseRoot "kit\python\python.exe"
$nativeLibrary = Join-Path $repositoryRoot "artifacts\phase3\phase6co-resident\native-build\campfire_wood_native.dll"
if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6db-translation-performance" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)

if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) { throw "Application is not built." }
if (-not (Test-Path -LiteralPath $nativeLibrary)) { throw "Phase 6DB requires the existing Phase 6CO native build: $nativeLibrary" }
$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $app).Hash

function Invoke-TranslationRun([string]$Name, [bool]$SkipUnchanged) {
    $runDir = Join-Path $OutputDir $Name
    $sceneDir = Join-Path $runDir "scene"
    $raw = Join-Path $runDir "dynamic_translation.json"
    $base = Join-Path $runDir "summary.json"
    $log = Join-Path $runDir "phase6db.log"
    New-Item -ItemType Directory -Path $sceneDir -Force | Out-Null
    foreach ($path in @($raw, $base, $log)) {
        Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
    }
    $skipValue = if ($SkipUnchanged) { "true" } else { "false" }
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
        "--/exts/campfire.app/outputDir=$runDir",
        "--/exts/campfire.app/sceneOutputDir=$sceneDir",
        "--/exts/campfire.app/residentPointApplicationEnabled=true",
        "--/exts/campfire.app/residentPointTimelineContinuityQualificationEnabled=true",
        "--/exts/campfire.app/residentPointDynamicTranslationQualificationEnabled=true",
        "--/exts/campfire.app/residentPointSkipUnchangedTranslationLayoutQualificationEnabled=$skipValue",
        "--/exts/campfire.app/residentNativeLibraryPath=$nativeLibrary",
        "--/phase6da/output=$raw",
        "--/rtx/flow/enabled=true",
        "--/log/file=$log",
        "--/log/fileLogLevel=Info",
        "--exec",
        $probe
    )
    # The inherited Phase 6CO summary intentionally fails its stopped/static
    # layout gates while dynamic tracking is enabled.  Treat the independent
    # Phase 6DA probe and evidence files as this spike's completion boundary.
    $kitExitCode = $LASTEXITCODE
    if (-not (Test-Path -LiteralPath $raw) -or -not (Test-Path -LiteralPath $base)) {
        throw "Phase 6DB $Name evidence is incomplete."
    }
    $probeResult = Get-Content -LiteralPath $raw -Raw | ConvertFrom-Json
    if ($probeResult.status -ne "ok") { throw "Phase 6DB $Name probe failed: $raw" }
    Write-Host ("Phase 6DB {0}: probe=ok, inheritedKitExit={1}" -f $Name, $kitExitCode)
}

$baselineRaw = Join-Path $OutputDir "baseline\dynamic_translation.json"
$baselineSummary = Join-Path $OutputDir "baseline\summary.json"
if ($ReuseBaseline -and (Test-Path -LiteralPath $baselineRaw) -and (Test-Path -LiteralPath $baselineSummary)) {
    $baselineProbe = Get-Content -LiteralPath $baselineRaw -Raw | ConvertFrom-Json
    if ($baselineProbe.status -ne "ok") { throw "Reusable Phase 6DB baseline probe is invalid." }
    Write-Host "Phase 6DB baseline: reusing completed evidence."
} else {
    Invoke-TranslationRun "baseline" $false
}
Invoke-TranslationRun "optimized" $true
$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $app).Hash
if ($productionHashBefore -ne $productionHashAfter) { throw "Phase 6DB changed the production app file." }

$report = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_translation_performance_report.json"
$svg = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_translation_performance_report.svg"
$poster = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_translation_performance_frame.png"
$video = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_translation_performance.mp4"
$optimizedFrames = Join-Path $OutputDir "optimized\video_frames"
& $kitPython $analyzer `
    --baseline (Join-Path $OutputDir "baseline\summary.json") `
    --baseline-probe (Join-Path $OutputDir "baseline\dynamic_translation.json") `
    --optimized (Join-Path $OutputDir "optimized\summary.json") `
    --optimized-probe (Join-Path $OutputDir "optimized\dynamic_translation.json") `
    --report $report --svg $svg --poster $poster --frames $optimizedFrames `
    --production-sha256-before $productionHashBefore `
    --production-sha256-after $productionHashAfter
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$ffmpeg = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
if (-not $ffmpeg) { throw "ffmpeg.exe is required to encode the Phase 6DB video." }
& $ffmpeg.Source -y -framerate 10 -i (Join-Path $optimizedFrames "frame_%04d.png") -c:v libx264 -preset medium -crf 22 -pix_fmt yuv420p -movflags +faststart $video
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Phase 6DB translation performance comparison completed."
