param(
    [ValidateSet("editor_declared_head", "editor_declared_tail", "campfire_editor_order", "campfire_editor_order_window_extensions")][string]$Variant = "editor_declared_tail",
    [string]$Scene = "",
    [string]$OutputDir = "",
    [switch]$WindowedProbe
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$campfireApp = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$editorApp = Join-Path $releaseRoot "kit\apps\omni.app.editor.base.kit"
$prepare = Join-Path $PSScriptRoot "prepare_phase6cu_app_variants.py"
$probe = Join-Path $PSScriptRoot "probe_plain_renderer_timeline.py"
if (-not $Scene) {
    $Scene = Join-Path $repositoryRoot "artifacts\phase3\phase6cs-minimal-camera\phase3_point_application_minimal_camera.usda"
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot ("artifacts\phase3\phase6cu-" + $Variant.Replace("_", "-"))
}
$Scene = [System.IO.Path]::GetFullPath($Scene)
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$derivedApp = Join-Path $OutputDir ("phase6cu_" + $Variant + ".kit")
$manifest = Join-Path $OutputDir "app_variant_manifest.json"
$probeMode = if ($WindowedProbe) { "windowed" } else { "headless" }
$output = Join-Path $OutputDir ("plain_renderer_timeline_" + $probeMode + ".json")
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

& py -3 $prepare `
    --variant $Variant `
    --campfire-app $campfireApp `
    --editor-app $editorApp `
    --output $derivedApp `
    --manifest $manifest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$probeArgs = @(
    $derivedApp,
    "--ext-folder",
    (Join-Path $releaseRoot "exts"),
    "--ext-folder",
    (Join-Path $releaseRoot "extscache"),
    "--/app/file/ignoreUnsavedOnExit=true",
    "--/app/quitAfter=30000",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/app/viewport/defaults/fillViewport=false",
    "--/app/renderer/resolution/width=1280",
    "--/app/renderer/resolution/height=720",
    "--/phase6cr/scene=$Scene",
    "--/phase6cr/output=$output",
    "--/phase6cr/probeApp=phase6cu_$Variant",
    "--/phase6cr/retryAfterStop=true",
    "--/rtx/flow/enabled=true",
    "--exec",
    $probe
)
if (-not $WindowedProbe) {
    $probeArgs = @($derivedApp, "--no-window") + $probeArgs[1..($probeArgs.Count - 1)]
}
& $kit $probeArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$variantReport = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
$timelineReport = Get-Content -LiteralPath $output -Raw | ConvertFrom-Json
if ($variantReport.status -ne "ok" -or $timelineReport.status -ne "ok") {
    throw "Phase 6CU variant failed: $OutputDir"
}
$after = $timelineReport.cases | Where-Object { $_.name -eq "after_viewport_frame" }
Write-Host ("Phase 6CU {0} {1}: afterPlay={2}, afterStops={3}, resolution={4}x{5}" -f $Variant, $probeMode, $after.remained_playing, $after.stop_event_count, $timelineReport.viewport_readiness.resolution[0], $timelineReport.viewport_readiness.resolution[1])
