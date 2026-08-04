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
    $OutputDir = Join-Path $repoRoot "artifacts\phase4\latest"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

& $kit @(
    $app,
    "--no-window",
    "--/app/quitAfter=600",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=true",
    "--/exts/campfire.app/phase=phase4",
    "--/exts/campfire.app/captureOnStartup=true",
    "--/exts/campfire.app/quitAfterCapture=true",
    "--/exts/campfire.app/outputDir=$OutputDir",
    "--/app/viewport/grid/enabled=false",
    "--/persistent/app/viewport/displayOptions=1152"
)
if ($LASTEXITCODE -ne 0) {
    throw "Phase 4 application failed with exit code $LASTEXITCODE."
}

$summaryPath = Join-Path $OutputDir "summary.json"
if (-not (Test-Path -LiteralPath $summaryPath)) {
    throw "Phase 4 summary was not produced."
}
$result = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json
if ($result.status -ne "ok" -or $result.phase -ne "phase4") {
    throw "Phase 4 summary reported failure."
}
if ($result.comparison.cabin.oxygen_factor -le $result.comparison.dense.oxygen_factor) {
    throw "Log cabin oxygen factor did not exceed dense stack."
}
if ($result.comparison.cabin.ignition_seconds -ge $result.comparison.dense.ignition_seconds) {
    throw "Log cabin did not ignite before dense stack."
}
if ($result.comparison.cabin.emitted_pyrolysis_gas_kg -le $result.comparison.dense.emitted_pyrolysis_gas_kg) {
    throw "Log cabin did not emit more pyrolysis gas."
}
foreach ($name in @("dense", "cabin")) {
    if ([math]::Abs($result.comparison.$name.mass_balance_error_kg) -gt 0.000001) {
        throw "Phase 4 $name comparison violated mass conservation."
    }
}
if (-not (Test-Path -LiteralPath $result.image)) {
    throw "Phase 4 comparison image was not produced."
}
Add-Type -AssemblyName System.Drawing
$image = [System.Drawing.Image]::FromFile($result.image)
try {
    if ($image.Width -ne 1280 -or $image.Height -ne 720) {
        throw "Phase 4 PNG has an unexpected resolution."
    }
}
finally {
    $image.Dispose()
}
Write-Host "Phase 4 validation succeeded: $OutputDir"
