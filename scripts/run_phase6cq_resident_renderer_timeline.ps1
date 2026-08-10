param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$probe = Join-Path $PSScriptRoot "probe_resident_renderer_timeline.py"
$kitPython = Join-Path $releaseRoot "kit\python\python.exe"
$analyzer = Join-Path $PSScriptRoot "analyze_resident_renderer_timeline.py"
if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6cq-renderer" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$sceneDir = Join-Path $OutputDir "scene"
$output = Join-Path $OutputDir "renderer_timeline.json"
$capture = Join-Path $OutputDir "capture_callback.png"
New-Item -ItemType Directory -Path $sceneDir -Force | Out-Null

$nativeLibrary = Join-Path $repositoryRoot "artifacts\phase3\phase6co-resident\native-build\campfire_wood_native.dll"
if (-not (Test-Path -LiteralPath $nativeLibrary)) {
    throw "Phase 6CQ requires the existing Phase 6CO native build: $nativeLibrary"
}
& $kit @(
    $app,
    "--no-window",
    "--/app/quitAfter=30000",
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
    "--/phase6cq/output=$output",
    "--/phase6cq/capture=$capture",
    "--/rtx/flow/enabled=true",
    "--exec",
    $probe
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$result = Get-Content -LiteralPath $output -Raw | ConvertFrom-Json
if ($result.status -ne "ok") { throw "Phase 6CQ renderer probe failed: $output" }
$renderer = $result.cases | Where-Object { $_.name -eq "renderer_viewport" }
$captureCase = $result.cases | Where-Object { $_.name -eq "capture_callback" }
$candidates = @($result.decision.disable_candidates_that_preserve_play) -join ","
$report = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_renderer_timeline_report.json"
$svg = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_renderer_timeline_report.svg"
$poster = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_renderer_timeline_capture.png"
& $kitPython $analyzer --raw $output --capture $capture --report $report --svg $svg --poster $poster
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host ("Phase 6CQ renderer: rendererStop={0}, captureStop={1}, revision={2}->{3}, capture={4}, candidates={5}" -f $renderer.stop_event_count, $captureCase.stop_event_count, $renderer.revision_before, $captureCase.revision_after, $captureCase.capture.completed, $candidates)
