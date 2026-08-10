param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$probe = Join-Path $PSScriptRoot "probe_phase6de_profiler_surface.py"
$monitorProbe = Join-Path $PSScriptRoot "probe_phase6de_profile_monitor.py"
$flowProbe = Join-Path $PSScriptRoot "probe_phase6de_flow_profile.py"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6de_profiler_boundary.py"
$nativeLibrary = Join-Path $repositoryRoot "artifacts\phase3\phase6co-resident\native-build\campfire_wood_native.dll"
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6de-profiler-surface"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$raw = Join-Path $OutputDir "runtime_surface.json"
$monitor = Join-Path $OutputDir "profile_monitor.json"
$flowProfile = Join-Path $OutputDir "flow_profile.json"
$base = Join-Path $OutputDir "summary.json"
$sceneDir = Join-Path $OutputDir "scene"
$log = Join-Path $OutputDir "phase6de.log"
$report = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_profiler_boundary_report.json"
$svg = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_profiler_boundary_report.svg"

if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) {
    throw "Application is not built."
}
if (-not (Test-Path -LiteralPath $nativeLibrary)) {
    throw "Phase 6DE requires the existing Phase 6CO native build: $nativeLibrary"
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
New-Item -ItemType Directory -Path $sceneDir -Force | Out-Null
foreach ($path in @($raw, $monitor, $flowProfile, $base, $log)) {
    Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
}

$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $app).Hash
& $kit @(
    $app,
    "--no-window",
    "--/app/file/ignoreUnsavedOnExit=true",
    "--/app/quitAfter=30000",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/renderer/enabled=false",
    "--/phase6de/output=$raw",
    "--/log/file=$log",
    "--/log/fileLogLevel=Info",
    "--exec",
    $probe
)
$kitExitCode = $LASTEXITCODE
$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $app).Hash
if ($kitExitCode -ne 0) { exit $kitExitCode }
if ($productionHashBefore -ne $productionHashAfter) {
    throw "Phase 6DE changed the production app file."
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
    "--/exts/campfire.app/residentPointDynamicTranslationQualificationEnabled=true",
    "--/exts/campfire.app/residentPointSkipUnchangedTranslationLayoutQualificationEnabled=true",
    "--/exts/campfire.app/residentNativeLibraryPath=$nativeLibrary",
    "--/phase6de/flowProfileOutput=$flowProfile",
    "--/rtx/flow/enabled=true",
    "--/log/file=$log",
    "--/log/fileLogLevel=Info",
    "--exec",
    $flowProbe
)
$flowKitExitCode = $LASTEXITCODE
if (-not (Test-Path -LiteralPath $flowProfile) -or -not (Test-Path -LiteralPath $base)) {
    throw "Phase 6DE Flow profile evidence is incomplete."
}
$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $app).Hash
if ($productionHashBefore -ne $productionHashAfter) {
    throw "Phase 6DE changed the production app file."
}
if (-not (Test-Path -LiteralPath $raw)) {
    throw "Phase 6DE runtime surface report is missing."
}

& $kit @(
    $app,
    "--no-window",
    "--/app/file/ignoreUnsavedOnExit=true",
    "--/app/quitAfter=30000",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/renderer/enabled=false",
    "--/phase6de/monitorOutput=$monitor",
    "--/log/file=$log",
    "--/log/fileLogLevel=Info",
    "--exec",
    $monitorProbe
)
$monitorExitCode = $LASTEXITCODE
if ($monitorExitCode -ne 0) { exit $monitorExitCode }
if (-not (Test-Path -LiteralPath $monitor)) {
    throw "Phase 6DE profile monitor report is missing."
}
$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $app).Hash
if ($productionHashBefore -ne $productionHashAfter) {
    throw "Phase 6DE changed the production app file."
}

$manifest = [ordered]@{
    schema_version = 1
    phase = "phase6de"
    status = "ok"
    runtime_surface = $raw
    profile_monitor = $monitor
    flow_profile = $flowProfile
    base_summary = $base
    kit_exit_code = $kitExitCode
    monitor_kit_exit_code = $monitorExitCode
    flow_kit_exit_code = $flowKitExitCode
    production_app_sha256_before = $productionHashBefore
    production_app_sha256_after = $productionHashAfter
    production_changed = ($productionHashBefore -ne $productionHashAfter)
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputDir "manifest.json") -Encoding utf8
$python = Join-Path $releaseRoot "kit\python\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = "python"
}
& $python $analyzer `
    --runtime $raw `
    --monitor $monitor `
    --profile $flowProfile `
    --base $base `
    --manifest (Join-Path $OutputDir "manifest.json") `
    --report $report `
    --svg $svg
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Phase 6DE profiler surface captured: $raw"
