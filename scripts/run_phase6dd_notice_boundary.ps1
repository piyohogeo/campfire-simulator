param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$kitPython = Join-Path $releaseRoot "kit\python\python.exe"
$probe = Join-Path $PSScriptRoot "probe_resident_dynamic_translation.py"
$microbenchmark = Join-Path $PSScriptRoot "benchmark_phase6dd_usd_notice_groups.py"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6dd_notice_boundary.py"
$nativeLibrary = Join-Path $repositoryRoot "artifacts\phase3\phase6co-resident\native-build\campfire_wood_native.dll"
if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6dd-notice-boundary" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$sceneDir = Join-Path $OutputDir "scene"
$base = Join-Path $OutputDir "summary.json"
$raw = Join-Path $OutputDir "dynamic_translation.json"
$micro = Join-Path $OutputDir "usd_microbenchmark.json"
$log = Join-Path $OutputDir "phase6dd.log"

if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) { throw "Application is not built." }
if (-not (Test-Path -LiteralPath $nativeLibrary)) { throw "Phase 6DD requires the existing Phase 6CO native build: $nativeLibrary" }
New-Item -ItemType Directory -Path $sceneDir -Force | Out-Null
foreach ($path in @($base, $raw, $micro, $log)) { Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue }

& $kitPython $microbenchmark --output $micro
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $app).Hash
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
    "--/phase6da/output=$raw",
    "--/rtx/flow/enabled=true",
    "--/log/file=$log",
    "--/log/fileLogLevel=Info",
    "--exec",
    $probe
)
$kitExitCode = $LASTEXITCODE
$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $app).Hash
if ($productionHashBefore -ne $productionHashAfter) { throw "Phase 6DD changed the production app file." }
if (-not (Test-Path -LiteralPath $raw) -or -not (Test-Path -LiteralPath $base) -or -not (Test-Path -LiteralPath $micro)) { throw "Phase 6DD evidence is incomplete." }

$report = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_notice_boundary_report.json"
$svg = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_notice_boundary_report.svg"
& $kitPython $analyzer --base $base --probe $raw --micro $micro --report $report --svg $svg --production-sha256-before $productionHashBefore --production-sha256-after $productionHashAfter --kit-exit-code $kitExitCode
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Phase 6DD notice boundary completed."
