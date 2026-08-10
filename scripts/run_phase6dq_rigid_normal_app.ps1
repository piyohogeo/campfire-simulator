param([string]$OutputDir = "", [string]$ReportDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$buildScript = Join-Path $PSScriptRoot "build_wood_native.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6dq_rigid_normal_app.py"
$kitPython = Join-Path $releaseRoot "kit\python\python.exe"
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6dq"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$nativeBuild = Join-Path $OutputDir "native-build"
$nativeDll = Join-Path $nativeBuild "campfire_wood_native.dll"
$sceneDir = Join-Path $OutputDir "scene"
$summary = Join-Path $OutputDir "summary.json"
if (-not $ReportDir) {
    $ReportDir = Join-Path $repositoryRoot "docs\devlog\assets\phase6"
}
$ReportDir = [System.IO.Path]::GetFullPath($ReportDir)
$report = Join-Path $ReportDir "rigid_normal_app_report.json"
$svg = Join-Path $ReportDir "rigid_normal_app_report.svg"
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
New-Item -ItemType Directory -Path $sceneDir -Force | Out-Null

if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) {
    throw "Application is not built."
}
& $buildScript -OutputDir $nativeBuild
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $kit @(
    $app,
    "--no-window",
    "--/app/quitAfter=10000",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=true",
    "--/exts/campfire.app/phase=phase3",
    "--/exts/campfire.app/captureOnStartup=true",
    "--/exts/campfire.app/quitAfterCapture=true",
    "--/exts/campfire.app/outputDir=$OutputDir",
    "--/exts/campfire.app/sceneOutputDir=$sceneDir",
    "--/exts/campfire.app/residentPointApplicationEnabled=true",
    "--/exts/campfire.app/residentPointRigidLayoutEnabled=true",
    "--/exts/campfire.app/residentNativeLibraryPath=$nativeDll",
    "--/rtx/flow/enabled=true"
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not (Test-Path -LiteralPath $summary)) {
    throw "Phase 6DQ summary was not written: $summary"
}
$result = Get-Content -Raw -LiteralPath $summary | ConvertFrom-Json
if (
    $result.status -ne "ok" -or
    $result.phase -ne "phase6dq" -or
    $result.scope.layout_representation -ne "rigid_frame_v1"
) {
    throw "Phase 6DQ rigid normal-app qualification failed: $summary"
}
& $kitPython $analyzer --raw $summary --report $report --svg $svg
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host ("Phase 6DQ qualified: gates={0}, representation={1}, revision={2}" -f `
    @($result.gates.PSObject.Properties).Count, `
    $result.scope.layout_representation, `
    $result.publication.revisions[0])
