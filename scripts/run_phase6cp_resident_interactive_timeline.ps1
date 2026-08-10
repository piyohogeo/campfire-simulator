param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.benchmark.kit"
$probe = Join-Path $PSScriptRoot "probe_resident_interactive_timeline.py"
if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6cp-interactive" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$sceneDir = Join-Path $OutputDir "scene"
$output = Join-Path $OutputDir "interactive.json"
New-Item -ItemType Directory -Path $sceneDir -Force | Out-Null

$nativeLibrary = Join-Path $repositoryRoot "artifacts\phase3\phase6co-resident\native-build\campfire_wood_native.dll"
if (-not (Test-Path -LiteralPath $nativeLibrary)) {
    throw "Phase 6CP requires the existing Phase 6CO native build: $nativeLibrary"
}
& $kit @(
    $app,
    "--no-window",
    "--/app/quitAfter=300",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=true",
    "--/exts/campfire.app/phase=phase3",
    "--/exts/campfire.app/captureOnStartup=false",
    "--/exts/campfire.app/sceneOutputDir=$sceneDir",
    "--/exts/campfire.app/residentPointApplicationEnabled=true",
    "--/exts/campfire.app/woodRenderHierarchyEnabled=false",
    "--/exts/campfire.app/woodVisualV3Enabled=false",
    "--/exts/campfire.app/residentNativeLibraryPath=$nativeLibrary",
    "--/phase6cp/output=$output",
    "--/renderer/enabled=false",
    "--/rtx/flow/enabled=true",
    "--exec",
    $probe
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$result = Get-Content -LiteralPath $output -Raw | ConvertFrom-Json
if ($result.status -ne "ok") { throw "Phase 6CP interactive probe failed: $output" }
Write-Host ("Phase 6CP interactive: play={0}, advanced={1}, stops={2}, revision={3}->{4}" -f $result.timeline.remained_playing, $result.timeline.advanced_from_zero, $result.timeline.stop_event_count, $result.owner_evidence.point_revision_before, $result.owner_evidence.point_revision_after)
