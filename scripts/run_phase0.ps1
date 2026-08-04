param(
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repoRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"

if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) {
    throw "Application is not built. Run .\repo.bat build first."
}

if (-not $OutputDir) {
    $OutputDir = Join-Path $repoRoot "artifacts\phase0\latest"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$kitArgs = @(
    $app,
    "--no-window",
    "--/app/quitAfter=600",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=true",
    "--/exts/campfire.app/phase=phase0",
    "--/exts/campfire.app/captureOnStartup=true",
    "--/exts/campfire.app/quitAfterCapture=true",
    "--/exts/campfire.app/outputDir=$OutputDir"
)

& $kit @kitArgs
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    throw "Phase 0 application failed with exit code $exitCode."
}

$image = Join-Path $OutputDir "frame_0000.png"
$summary = Join-Path $OutputDir "summary.json"
if (-not (Test-Path -LiteralPath $image)) {
    throw "Phase 0 capture was not produced: $image"
}
if (-not (Test-Path -LiteralPath $summary)) {
    throw "Phase 0 summary was not produced: $summary"
}

$result = Get-Content -LiteralPath $summary -Raw | ConvertFrom-Json
if ($result.status -ne "ok" -or $result.phase -ne "phase0") {
    throw "Phase 0 summary reported a failure or unexpected phase: $summary"
}
if ($result.camera -ne "/World/Camera") {
    throw "Phase 0 summary reported an unexpected camera: $($result.camera)"
}
if ($result.resolution.Count -ne 2 -or $result.resolution[0] -ne 1280 -or $result.resolution[1] -ne 720) {
    throw "Phase 0 summary reported an unexpected resolution: $($result.resolution -join 'x')"
}

Add-Type -AssemblyName System.Drawing
$capturedImage = [System.Drawing.Image]::FromFile($image)
try {
    if ($capturedImage.Width -ne 1280 -or $capturedImage.Height -ne 720) {
        throw "Phase 0 PNG has an unexpected resolution: $($capturedImage.Width)x$($capturedImage.Height)"
    }
}
finally {
    $capturedImage.Dispose()
}

Write-Host "Phase 0 validation succeeded: $OutputDir"
