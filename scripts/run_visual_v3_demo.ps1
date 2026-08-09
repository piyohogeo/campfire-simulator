param(
    [string]$OutputDir = "",
    [switch]$CaptureVideo,
    [ValidateRange(1, 1200)]
    [int]$VideoFrameInterval = 20,
    [ValidateRange(1, 60)]
    [int]$VideoFps = 10
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\visual-v3\latest"
}
$nativeBuild = Join-Path $repositoryRoot "artifacts\native\visual-v3"
& (Join-Path $PSScriptRoot "build_wood_native.ps1") -OutputDir $nativeBuild
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$nativeDll = Join-Path $nativeBuild "campfire_wood_native.dll"
$arguments = @{
    OutputDir = $OutputDir
    ResidentSnapshotAdapter = $true
    ResidentSnapshotHandleCache = $true
    ResidentSnapshotLightweightCommit = $true
    ResidentSnapshotSkipUnchanged = $true
    WoodRenderHierarchy = $true
    WoodVisualV3 = $true
    ResidentNativeBackend = $true
    ResidentNativeLibraryPath = $nativeDll
    CaptureVideo = $CaptureVideo.IsPresent
    VideoFrameInterval = $VideoFrameInterval
    VideoFps = $VideoFps
}
& (Join-Path $PSScriptRoot "run_phase3.ps1") @arguments
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "V3 visual demo complete: $([System.IO.Path]::GetFullPath($OutputDir))"
