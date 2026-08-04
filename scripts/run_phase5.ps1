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
    $OutputDir = Join-Path $repoRoot "artifacts\phase5\latest"
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
    "--/exts/campfire.app/phase=phase5",
    "--/exts/campfire.app/captureOnStartup=true",
    "--/exts/campfire.app/quitAfterCapture=true",
    "--/exts/campfire.app/outputDir=$OutputDir",
    "--/app/viewport/grid/enabled=false",
    "--/persistent/app/viewport/displayOptions=1152"
)
if ($LASTEXITCODE -ne 0) {
    throw "Phase 5 application failed with exit code $LASTEXITCODE."
}

$summaryPath = Join-Path $OutputDir "summary.json"
if (-not (Test-Path -LiteralPath $summaryPath)) {
    throw "Phase 5 summary was not produced."
}
$result = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json
if ($result.status -ne "ok" -or $result.phase -ne "phase5") {
    throw "Phase 5 summary reported failure."
}
if (-not $result.structure.constraint_released) {
    throw "Phase 5 joint was not released."
}
if ($result.structure.support_ratio_at_release -gt $result.structure.failure_threshold) {
    throw "Phase 5 joint released before the support threshold."
}
if (-not $result.rigid_body.collapsed) {
    throw "Phase 5 segments did not collapse after release."
}
if (-not $result.combustion.reignited -or $result.combustion.reignition_gain -le 1.05) {
    throw "Phase 5 did not show post-collapse reignition."
}
if ([math]::Abs($result.combustion.mass_balance_error_kg) -gt 0.000001) {
    throw "Phase 5 combustion violated mass conservation."
}
if ([math]::Abs($result.combustion.segment_mass_sum_kg - $result.combustion.remaining_mass_kg) -gt 0.000001) {
    throw "Phase 5 segment masses do not sum to remaining mass."
}
if ($result.images.Count -ne 2) {
    throw "Phase 5 did not produce both supported and collapsed captures."
}
Add-Type -AssemblyName System.Drawing
foreach ($capture in $result.images) {
    if (-not (Test-Path -LiteralPath $capture.path)) {
        throw "Phase 5 capture was not produced: $($capture.path)"
    }
    $image = [System.Drawing.Image]::FromFile($capture.path)
    try {
        if ($image.Width -ne 1280 -or $image.Height -ne 720) {
            throw "Phase 5 PNG has an unexpected resolution."
        }
    }
    finally {
        $image.Dispose()
    }
}
Write-Host "Phase 5 validation succeeded: $OutputDir"
