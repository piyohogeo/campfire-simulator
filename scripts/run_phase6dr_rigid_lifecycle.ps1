param([string]$OutputDir = "", [string]$ReportDir = "")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
$release = Join-Path $root "_build\windows-x86_64\release"
$kit = Join-Path $release "kit\kit.exe"
$app = New-CampfireIsolatedKitApp -SourceApp (Join-Path $release "apps\campfire.simulator.kit")
$buildScript = Join-Path $PSScriptRoot "build_wood_native.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6dr_rigid_lifecycle.py"
$kitPython = Join-Path $release "kit\python\python.exe"
if (-not $OutputDir) { $OutputDir = Join-Path $root "artifacts\phase3\phase6dr" }
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $OutputDir) {
    throw "Phase 6DR refuses to reuse output: $OutputDir"
}
$nativeBuild = Join-Path $OutputDir "native-build"
$nativeDll = Join-Path $nativeBuild "campfire_wood_native.dll"
$sceneDir = Join-Path $OutputDir "scene"
$summary = Join-Path $OutputDir "summary.json"
$kitLog = Join-Path $OutputDir "kit.log"
$dumpDir = Join-Path $OutputDir "sensitive-crash-dumps"
if (-not $ReportDir) {
    $ReportDir = Join-Path $root "docs\devlog\assets\phase6"
}
$ReportDir = [IO.Path]::GetFullPath($ReportDir)
$report = Join-Path $ReportDir "rigid_lifecycle_report.json"
$svg = Join-Path $ReportDir "rigid_lifecycle_report.svg"
New-Item -ItemType Directory -Path $sceneDir -Force | Out-Null

if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) {
    throw "Application is not built."
}
& $buildScript -OutputDir $nativeBuild
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$arguments = @(
    $app,
    "--no-window",
    "--/app/file/ignoreUnsavedOnExit=true",
    "--/app/quitAfter=10000",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/app/window/width=1280",
    "--/app/window/height=720",
    "--/app/viewport/defaults/fillViewport=false",
    "--/renderer/multiGpu/enabled=false",
    "--/rtx/ecoMode/enabled=false",
    "--/rtx/rendermode=RealTimePathTracing",
    "--/rtx/post/aa/op=3",
    "--/rtx/post/dlss/execMode=0",
    "--/rtx/rtpt/maxBounces=2",
    "--/exts/campfire.app/autoCreateScene=true",
    "--/exts/campfire.app/phase=phase3",
    "--/exts/campfire.app/captureOnStartup=true",
    "--/exts/campfire.app/quitAfterCapture=true",
    "--/exts/campfire.app/outputDir=$OutputDir",
    "--/exts/campfire.app/sceneOutputDir=$sceneDir",
    "--/exts/campfire.app/residentPointApplicationEnabled=true",
    "--/exts/campfire.app/woodRenderHierarchyEnabled=false",
    "--/exts/campfire.app/woodVisualV3Enabled=false",
    "--/exts/campfire.app/residentPointRigidLayoutEnabled=true",
    "--/exts/campfire.app/residentPointRigidLifecycleQualificationEnabled=true",
    "--/exts/campfire.app/residentNativeLibraryPath=$nativeDll",
    "--/rtx/flow/enabled=true",
    "--/log/file=$kitLog"
) + @(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $dumpDir)

$process = Start-Process $kit -ArgumentList $arguments -PassThru
$process.WaitForExit()
$process.Refresh()
$fatalTokens = @(
    "IRenderSettings::getRenderSettings failed getting a stage-id",
    "Traceback (most recent call last)",
    "CUDA_ERROR_ILLEGAL_ADDRESS",
    "device lost",
    "invalid pointer",
    "[crash] A crash has occurred"
)
$fatalCounts = [ordered]@{}
foreach ($token in $fatalTokens) {
    $fatalCounts[$token] = if (Test-Path -LiteralPath $kitLog) {
        @(Select-String -LiteralPath $kitLog -SimpleMatch $token).Count
    } else { 0 }
}
$crashSafety = Get-CampfireCrashSafetyEvidence -LogPath $kitLog -DumpDir $dumpDir
$uploadAttempts = if (Test-Path -LiteralPath $kitLog) {
    @(Select-String -LiteralPath $kitLog -SimpleMatch "Uploading minidump:").Count
} else { 0 }
if (
    $process.ExitCode -ne 0 -or
    ($fatalCounts.Values | Measure-Object -Sum).Sum -ne 0 -or
    @($crashSafety.dump_inventory).Count -ne 0 -or
    $uploadAttempts -ne 0
) {
    throw "Phase 6DR rejected isolated Kit run; no retry: exit=$($process.ExitCode), fatal=$($fatalCounts | ConvertTo-Json -Compress), dumps=$(@($crashSafety.dump_inventory).Count), uploads=$uploadAttempts"
}
if (-not (Test-Path -LiteralPath $summary)) {
    throw "Phase 6DR summary was not written: $summary"
}
$result = Get-Content -Raw -Encoding UTF8 -LiteralPath $summary | ConvertFrom-Json
if ($result.status -ne "ok" -or $result.phase -ne "phase6dr") {
    throw "Phase 6DR normal-app qualification failed: $summary"
}
& $kitPython $analyzer --raw $summary --report $report --svg $svg
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host ("Phase 6DR qualified: gates={0}, revision={1}, crash/dump/upload=0" -f @($result.gates.PSObject.Properties).Count, $result.publication.revisions[0])
