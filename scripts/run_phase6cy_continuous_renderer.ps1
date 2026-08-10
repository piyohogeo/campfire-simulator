param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$probe = Join-Path $PSScriptRoot "probe_resident_continuous_renderer.py"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6cy_continuous_renderer.py"
$kitPython = Join-Path $releaseRoot "kit\python\python.exe"
if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6cy-continuous-renderer" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$sceneDir = Join-Path $OutputDir "scene"
$raw = Join-Path $OutputDir "continuous_renderer.json"
$capture = Join-Path $OutputDir "continuous_renderer.png"
$log = Join-Path $OutputDir "phase6cy.log"
$nativeLibrary = Join-Path $repositoryRoot "artifacts\phase3\phase6co-resident\native-build\campfire_wood_native.dll"
if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) { throw "Application is not built." }
if (-not (Test-Path -LiteralPath $nativeLibrary)) { throw "Phase 6CY requires the existing Phase 6CO native build: $nativeLibrary" }
New-Item -ItemType Directory -Path $sceneDir -Force | Out-Null
$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $app).Hash
foreach ($path in @($raw, $capture, $log)) {
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
    "--/exts/campfire.app/captureOnStartup=false",
    "--/exts/campfire.app/sceneOutputDir=$sceneDir",
    "--/exts/campfire.app/residentPointApplicationEnabled=true",
    "--/exts/campfire.app/woodRenderHierarchyEnabled=false",
    "--/exts/campfire.app/woodVisualV3Enabled=false",
    "--/exts/campfire.app/residentNativeLibraryPath=$nativeLibrary",
    "--/phase6cy/output=$raw",
    "--/phase6cy/capture=$capture",
    "--/rtx/flow/enabled=true",
    "--/log/file=$log",
    "--/log/fileLogLevel=Info",
    "--exec",
    $probe
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $app).Hash
if ($productionHashBefore -ne $productionHashAfter) { throw "Phase 6CY changed the production app file." }
$result = Get-Content -LiteralPath $raw -Raw | ConvertFrom-Json
if ($result.status -ne "ok") { throw "Phase 6CY probe failed: $raw" }
$report = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_continuous_renderer_report.json"
$svg = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_continuous_renderer_report.svg"
$poster = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_continuous_renderer_frame.png"
& $kitPython $analyzer --raw $raw --capture $capture --log $log --report $report --svg $svg --poster $poster --production-sha256-before $productionHashBefore --production-sha256-after $productionHashAfter
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host ("Phase 6CY continuous renderer: qualified={0}, blocks={1}, capture={2}" -f $result.observation.timeline_continuity_qualified, $result.observation.active_blocks_peak, $result.capture.completed)
