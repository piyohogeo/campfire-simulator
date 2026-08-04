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
    $OutputDir = Join-Path $repoRoot "artifacts\phase6\latest"
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
    "--/exts/campfire.app/phase=phase6",
    "--/exts/campfire.app/captureOnStartup=true",
    "--/exts/campfire.app/quitAfterCapture=true",
    "--/exts/campfire.app/outputDir=$OutputDir",
    "--/app/viewport/grid/enabled=false",
    "--/persistent/app/viewport/displayOptions=1152"
)
if ($LASTEXITCODE -ne 0) {
    throw "Phase 6 application failed with exit code $LASTEXITCODE."
}

$summaryPath = Join-Path $OutputDir "summary.json"
if (-not (Test-Path -LiteralPath $summaryPath)) {
    throw "Phase 6 summary was not produced."
}
$result = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json
if ($result.status -ne "ok" -or $result.phase -ne "phase6") {
    throw "Phase 6 summary reported failure."
}
$calibration = $result.calibration
if (-not $calibration.improved -or $calibration.improvement_fraction -le 0.0) {
    throw "Phase 6 search did not improve the baseline."
}
if ($calibration.best.score_rmse_relative -ge $calibration.baseline.score_rmse_relative) {
    throw "Phase 6 best score is not lower than the baseline."
}
if ($calibration.candidate_count -lt 30 -or $calibration.best.cases.Count -ne 2) {
    throw "Phase 6 did not evaluate the expected fixed search space."
}
foreach ($case in $calibration.best.cases) {
    if (-not $case.all_values_finite) {
        throw "Phase 6 calibration produced non-finite state."
    }
    if ([math]::Abs($case.mass_balance_error_kg) -gt 0.000001) {
        throw "Phase 6 calibration violated mass conservation."
    }
    if ($null -eq $case.predicted_ignition_seconds) {
        throw "Phase 6 calibration did not predict ignition."
    }
}
if ($calibration.best.cases[0].predicted_ignition_seconds -le $calibration.best.cases[1].predicted_ignition_seconds) {
    throw "Phase 6 lost the expected heat-flux ignition ordering."
}
foreach ($path in @($result.image, $result.report, $result.top_candidates_csv, $result.final_stage)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Phase 6 artifact was not produced: $path"
    }
}
Add-Type -AssemblyName System.Drawing
$image = [System.Drawing.Image]::FromFile($result.image)
try {
    if ($image.Width -ne 1280 -or $image.Height -ne 720) {
        throw "Phase 6 PNG has an unexpected resolution."
    }
}
finally {
    $image.Dispose()
}
Write-Host "Phase 6 calibration validation succeeded: $OutputDir"
