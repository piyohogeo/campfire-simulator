param(
    [ValidateSet("all_static", "core_only", "root_without_extension", "app_lifecycle_only", "extension_defaults_only", "lock_only", "static_and_lock", "package_only", "static_lock_package", "full_config_absolute_paths")][string]$Variant = "all_static",
    [string]$Scene = "",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$campfireApp = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$editorApp = Join-Path $releaseRoot "kit\apps\omni.app.editor.base.kit"
$prepare = Join-Path $PSScriptRoot "prepare_phase6cv_settings_variants.py"
$probe = Join-Path $PSScriptRoot "probe_plain_renderer_timeline.py"
if (-not $Scene) {
    $Scene = Join-Path $repositoryRoot "artifacts\phase3\phase6cs-minimal-camera\phase3_point_application_minimal_camera.usda"
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot ("artifacts\phase3\phase6cv-" + $Variant.Replace("_", "-"))
}
$Scene = [System.IO.Path]::GetFullPath($Scene)
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$derivedApp = Join-Path $OutputDir ("phase6cv_" + $Variant + ".kit")
$manifest = Join-Path $OutputDir "settings_variant_manifest.json"
$output = Join-Path $OutputDir "plain_renderer_timeline_headless.json"
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

& py -3 $prepare `
    --variant $Variant `
    --campfire-app $campfireApp `
    --editor-app $editorApp `
    --output $derivedApp `
    --manifest $manifest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $kit @(
    $derivedApp,
    "--no-window",
    "--ext-folder", (Join-Path $releaseRoot "exts"),
    "--ext-folder", (Join-Path $releaseRoot "extscache"),
    "--/app/file/ignoreUnsavedOnExit=true",
    "--/app/quitAfter=900",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/app/viewport/defaults/fillViewport=false",
    "--/app/renderer/resolution/width=1280",
    "--/app/renderer/resolution/height=720",
    "--/phase6cr/scene=$Scene",
    "--/phase6cr/output=$output",
    "--/phase6cr/probeApp=phase6cv_$Variant",
    "--/phase6cr/retryAfterStop=true",
    "--/rtx/flow/enabled=true",
    "--exec", $probe
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$variantReport = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
$timelineReport = Get-Content -LiteralPath $output -Raw | ConvertFrom-Json
if ($variantReport.status -ne "ok" -or $timelineReport.status -ne "ok") {
    throw "Phase 6CV variant failed: $OutputDir"
}
$after = $timelineReport.cases | Where-Object { $_.name -eq "after_viewport_frame" }
$retry = $timelineReport.cases | Where-Object { $_.name -eq "after_viewport_frame_retry" }
Write-Host ("Phase 6CV {0}: afterPlay={1}, retryPlay={2}, stops={3}/{4}, resolution={5}x{6}" -f $Variant, $after.remained_playing, $retry.remained_playing, $after.stop_event_count, $retry.stop_event_count, $timelineReport.viewport_readiness.resolution[0], $timelineReport.viewport_readiness.resolution[1])
