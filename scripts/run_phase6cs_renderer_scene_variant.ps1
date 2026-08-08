param(
    [ValidateSet("unchanged", "no_flow", "no_physics", "render_only", "minimal_camera")][string]$Variant = "no_flow",
    [string]$SourceScene = "",
    [string]$OutputDir = "",
    [switch]$WindowedProbe,
    [int]$PostViewportSettleFrames = 0,
    [double]$PostViewportSettleSeconds = 0.0,
    [switch]$RetryAfterStop,
    [ValidateSet("campfire", "editor_base", "editor_base_flow", "editor_base_campfire", "editor_base_developer", "editor_base_shell")][string]$ProbeApp = "campfire",
    [switch]$AsyncRendererInit,
    [ValidateSet("app_default", "true", "false")][string]$ViewportFillDefault = "app_default",
    [switch]$EditorPresentTiming,
    [switch]$EditorRunLoopTiming,
    [switch]$DisableFirstOpenAutoFrame,
    [switch]$EditorGraphicsDefaults,
    [switch]$EditorPersistentResolution
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$probeAppPath = if ($ProbeApp -in ("editor_base", "editor_base_flow", "editor_base_campfire", "editor_base_developer", "editor_base_shell")) {
    Join-Path $releaseRoot "kit\apps\omni.app.editor.base.kit"
} else {
    $app
}
$prepare = Join-Path $PSScriptRoot "prepare_renderer_scene_variant.py"
$probe = Join-Path $PSScriptRoot "probe_plain_renderer_timeline.py"
if (-not $SourceScene) { $SourceScene = Join-Path $repositoryRoot "artifacts\phase3\phase6cq-renderer\scene\phase3_point_application.usda" }
if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot ("artifacts\phase3\phase6cs-" + $Variant.Replace("_", "-")) }
$SourceScene = [System.IO.Path]::GetFullPath($SourceScene)
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$scene = Join-Path $OutputDir ("phase3_point_application_" + $Variant + ".usda")
$manifest = Join-Path $OutputDir "variant_manifest.json"
$probeMode = if ($WindowedProbe) { "windowed" } else { "headless" }
$output = Join-Path $OutputDir ("plain_renderer_timeline_" + $probeMode + "_" + $ProbeApp + ".json")
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

& $kit @(
    $app,
    "--no-window",
    "--/app/file/ignoreUnsavedOnExit=true",
    "--/app/quitAfter=120",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/renderer/enabled=false",
    "--/phase6cs/source=$SourceScene",
    "--/phase6cs/variantScene=$scene",
    "--/phase6cs/manifest=$manifest",
    "--/phase6cs/variant=$Variant",
    "--exec",
    $prepare
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$probeArgs = @(
    $probeAppPath,
    "--/app/file/ignoreUnsavedOnExit=true",
    "--/app/quitAfter=900",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/phase6cr/scene=$scene",
    "--/phase6cr/output=$output",
    "--/phase6cr/probeApp=$ProbeApp",
    "--/phase6cr/postViewportSettleFrames=$PostViewportSettleFrames",
    "--/phase6cr/postViewportSettleSeconds=$PostViewportSettleSeconds",
    "--/phase6cr/retryAfterStop=$($RetryAfterStop.IsPresent.ToString().ToLowerInvariant())",
    "--/rtx/flow/enabled=true",
    "--exec",
    $probe
)
if ($ProbeApp -in ("editor_base_flow", "editor_base_campfire", "editor_base_developer", "editor_base_shell")) {
    $probeArgs = @($probeAppPath, "--enable", "omni.flowusd") + $probeArgs[1..($probeArgs.Count - 1)]
}
if ($ProbeApp -in ("editor_base_campfire", "editor_base_developer", "editor_base_shell")) {
    $probeArgs = @(
        $probeAppPath,
        "--ext-folder",
        (Join-Path $releaseRoot "exts"),
        "--enable",
        "campfire.app"
    ) + $probeArgs[1..($probeArgs.Count - 1)]
}
if ($ProbeApp -in ("editor_base_developer", "editor_base_shell")) {
    $probeArgs = @(
        $probeAppPath,
        "--enable",
        "omni.kit.developer.bundle"
    ) + $probeArgs[1..($probeArgs.Count - 1)]
}
if ($ProbeApp -eq "editor_base_shell") {
    $probeArgs = @(
        $probeAppPath,
        "--enable",
        "omni.kit.menu.common",
        "--enable",
        "omni.kit.ui.actions"
    ) + $probeArgs[1..($probeArgs.Count - 1)]
}
if ($AsyncRendererInit) {
    $probeArgs = @($probeAppPath, "--/renderer/asyncInit=true") + $probeArgs[1..($probeArgs.Count - 1)]
}
if ($ViewportFillDefault -ne "app_default") {
    $probeArgs = @(
        $probeAppPath,
        "--/app/viewport/defaults/fillViewport=$ViewportFillDefault"
    ) + $probeArgs[1..($probeArgs.Count - 1)]
}
if ($EditorPresentTiming) {
    $probeArgs = @(
        $probeAppPath,
        "--/exts/omni.kit.renderer.core/present/enabled=true",
        "--/exts/omni.kit.renderer.core/present/presentAfterRendering=true",
        "--/persistent/app/viewport/defaults/tickRate=60"
    ) + $probeArgs[1..($probeArgs.Count - 1)]
}
if ($EditorRunLoopTiming) {
    $probeArgs = @(
        $probeAppPath,
        "--/app/runLoops/main/rateLimitFrequency=60",
        "--/app/runLoops/main/rateLimitUsePrecisionSleep=true",
        "--/app/runLoops/present/rateLimitUsePrecisionSleep=true",
        "--/app/runLoops/rendering_0/rateLimitFrequency=60",
        "--/app/runLoops/rendering_0/rateLimitUsePrecisionSleep=true",
        "--/app/runLoops/rendering_1/rateLimitEnabled=true",
        "--/app/runLoops/rendering_1/rateLimitFrequency=60",
        "--/app/runLoops/rendering_1/rateLimitUsePrecisionSleep=true",
        "--/app/runLoops/rendering_1/syncToPresent=true"
    ) + $probeArgs[1..($probeArgs.Count - 1)]
}
if ($DisableFirstOpenAutoFrame) {
    $probeArgs = @(
        $probeAppPath,
        "--/persistent/app/viewport/autoFrame/mode="
    ) + $probeArgs[1..($probeArgs.Count - 1)]
}
if ($EditorGraphicsDefaults) {
    $probeArgs = @(
        $probeAppPath,
        "--/renderer/gpuEnumeration/glInterop/enabled=true",
        "--/exts/omni.kit.renderer.core/imgui/enableMips=true"
    ) + $probeArgs[1..($probeArgs.Count - 1)]
}
if ($EditorPersistentResolution) {
    $probeArgs = @(
        $probeAppPath,
        "--/persistent/app/viewport/Viewport/Viewport0/resolution=[1920,1080]"
    ) + $probeArgs[1..($probeArgs.Count - 1)]
}
if (-not $WindowedProbe) {
    $probeArgs = @($probeAppPath, "--no-window") + $probeArgs[1..($probeArgs.Count - 1)]
}
& $kit $probeArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$variantReport = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
$timelineReport = Get-Content -LiteralPath $output -Raw | ConvertFrom-Json
if ($variantReport.status -ne "ok" -or $timelineReport.status -ne "ok") {
    throw "Phase 6CS variant failed: $OutputDir"
}
$after = $timelineReport.cases | Where-Object { $_.name -eq "after_viewport_frame" }
Write-Host ("Phase 6CS {0} {1}/{2}: flowPresent={3}, physicsScene={4}, physicsSchemas={5}, afterPlay={6}, afterStops={7}" -f $Variant, $probeMode, $ProbeApp, $variantReport.flow_root_present, $variantReport.physics_scene_present, $variantReport.physics_schema_count, $after.remained_playing, $after.stop_event_count)
