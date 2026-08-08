param(
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$campfireApp = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$editorApp = Join-Path $releaseRoot "kit\apps\omni.app.editor.base.kit"
$prepare = Join-Path $PSScriptRoot "prepare_phase6cv_settings_variants.py"
$identityProbe = Join-Path $PSScriptRoot "probe_phase6cw_app_identity.py"
$timelineProbe = Join-Path $PSScriptRoot "probe_plain_renderer_timeline.py"
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6cw-root-identity"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$namedDir = Join-Path $OutputDir "matching-filename"
$derivedApp = Join-Path $OutputDir "phase6cw_full_config.kit"
$sameNameApp = Join-Path $namedDir "campfire.simulator.kit"
$scene = Join-Path $repositoryRoot "artifacts\phase3\phase6cs-minimal-camera\phase3_point_application_minimal_camera.usda"
$manifest = Join-Path $OutputDir "full_config_manifest.json"
$sameNameManifest = Join-Path $namedDir "full_config_manifest.json"
New-Item -ItemType Directory -Path $namedDir -Force | Out-Null

& py -3 $prepare --variant full_config_absolute_paths --campfire-app $campfireApp --editor-app $editorApp --output $derivedApp --manifest $manifest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& py -3 $prepare --variant full_config_absolute_paths --campfire-app $campfireApp --editor-app $editorApp --output $sameNameApp --manifest $sameNameManifest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

function Invoke-IdentityProbe([string]$AppPath, [string]$Label, [string]$OutputPath) {
    & $kit @(
        $AppPath,
        "--no-window",
        "--ext-folder", (Join-Path $releaseRoot "exts"),
        "--ext-folder", (Join-Path $releaseRoot "extscache"),
        "--/app/file/ignoreUnsavedOnExit=true",
        "--/app/quitAfter=120",
        "--/app/settings/persistent=0",
        "--/app/settings/loadUserConfig=0",
        "--/exts/campfire.app/autoCreateScene=false",
        "--/renderer/enabled=false",
        "--/phase6cw/label=$Label",
        "--/phase6cw/output=$OutputPath",
        "--exec", $identityProbe
    )
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Invoke-IdentityProbe $campfireApp "production_root" (Join-Path $OutputDir "identity_production.json")
Invoke-IdentityProbe $derivedApp "derived_distinct_filename" (Join-Path $OutputDir "identity_derived.json")
Invoke-IdentityProbe $sameNameApp "derived_matching_filename" (Join-Path $OutputDir "identity_matching_filename.json")

$timelineOutput = Join-Path $OutputDir "timeline_matching_filename.json"
& $kit @(
    $sameNameApp,
    "--no-window",
    "--ext-folder", (Join-Path $releaseRoot "exts"),
    "--ext-folder", (Join-Path $releaseRoot "extscache"),
    "--/app/file/ignoreUnsavedOnExit=true",
    "--/app/quitAfter=30000",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/app/viewport/defaults/fillViewport=false",
    "--/app/renderer/resolution/width=1280",
    "--/app/renderer/resolution/height=720",
    "--/phase6cr/scene=$scene",
    "--/phase6cr/output=$timelineOutput",
    "--/phase6cr/probeApp=phase6cw_matching_filename",
    "--/phase6cr/retryAfterStop=true",
    "--/rtx/flow/enabled=true",
    "--exec", $timelineProbe
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Phase 6CW root identity captured: $OutputDir"
