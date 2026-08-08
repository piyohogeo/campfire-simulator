param(
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$campfireApp = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$editorApp = Join-Path $releaseRoot "kit\apps\omni.app.editor.base.kit"
$probe = Join-Path $PSScriptRoot "probe_runtime_settings.py"
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6ct-runtime-settings"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$campfireOutput = Join-Path $OutputDir "campfire.json"
$editorOutput = Join-Path $OutputDir "editor_matched_extensions.json"
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

& $kit @(
    $campfireApp,
    "--no-window",
    "--/app/quitAfter=120",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/renderer/enabled=false",
    "--/phase6ct/label=campfire",
    "--/phase6ct/settingsOutput=$campfireOutput",
    "--exec",
    $probe
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $kit @(
    $editorApp,
    "--no-window",
    "--ext-folder",
    (Join-Path $releaseRoot "exts"),
    "--enable",
    "omni.flowusd",
    "--enable",
    "campfire.app",
    "--enable",
    "omni.kit.developer.bundle",
    "--enable",
    "omni.kit.menu.common",
    "--enable",
    "omni.kit.ui.actions",
    "--/app/quitAfter=120",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/renderer/enabled=false",
    "--/renderer/asyncInit=true",
    "--/app/viewport/defaults/fillViewport=false",
    "--/phase6ct/label=editor_matched_extensions",
    "--/phase6ct/settingsOutput=$editorOutput",
    "--exec",
    $probe
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$campfire = Get-Content -LiteralPath $campfireOutput -Raw | ConvertFrom-Json
$editor = Get-Content -LiteralPath $editorOutput -Raw | ConvertFrom-Json
if ($campfire.status -ne "ok" -or $editor.status -ne "ok") {
    throw "Phase 6CT runtime settings probe failed: $OutputDir"
}
Write-Host "Phase 6CT runtime settings captured: $OutputDir"
