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
    $OutputDir = Join-Path $repoRoot "artifacts\phase3\latest"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$kitArgs = @(
    $app,
    "--no-window",
    "--/app/quitAfter=1200",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=true",
    "--/exts/campfire.app/phase=phase3",
    "--/exts/campfire.app/captureOnStartup=true",
    "--/exts/campfire.app/quitAfterCapture=true",
    "--/exts/campfire.app/outputDir=$OutputDir",
    "--/rtx/flow/enabled=true",
    "--/app/viewport/grid/enabled=false",
    "--/persistent/app/viewport/displayOptions=1152"
)

$runTimer = [System.Diagnostics.Stopwatch]::StartNew()
& $kit @kitArgs
$exitCode = $LASTEXITCODE
$runTimer.Stop()
if ($exitCode -ne 0) {
    throw "Phase 3 application failed with exit code $exitCode."
}

$summary = Join-Path $OutputDir "summary.json"
if (-not (Test-Path -LiteralPath $summary)) {
    throw "Phase 3 summary was not produced: $summary"
}

$result = Get-Content -LiteralPath $summary -Raw | ConvertFrom-Json
if ($result.status -ne "ok" -or $result.phase -ne "phase3") {
    throw "Phase 3 summary reported a failure or unexpected phase: $summary"
}
if ($result.scenario.steps -ne 1200 -or $result.scenario.model_duration_seconds -ne 240) {
    throw "Phase 3 did not complete the expected 240 second model scenario."
}
if (-not $result.comparison.both_ignited -or -not $result.comparison.wet_ignition_delayed) {
    throw "Wet wood did not ignite after dry wood as required."
}
if ($result.comparison.wet_delay_seconds -le 0) {
    throw "Wet ignition delay was not positive."
}
foreach ($name in @("dry", "wet")) {
    $wood = $result.wood.$name
    if (-not $wood.all_values_finite -or -not $wood.non_negative_mass) {
        throw "Phase 3 $name wood produced invalid state values."
    }
    if ([math]::Abs($wood.mass_balance_error_kg) -gt 0.000001) {
        throw "Phase 3 $name wood violated mass conservation."
    }
    if ($wood.emitted_pyrolysis_gas_kg -le 0 -or $wood.char_mass_kg -le 0) {
        throw "Phase 3 $name wood produced no gas or char."
    }
}
if ($result.wood.wet.emitted_water_kg -le $result.wood.dry.emitted_water_kg) {
    throw "Wet wood did not evaporate more water than dry wood."
}
if ($result.flow.active_blocks_peak -le 0 -or $result.flow.peak_fuel_input -le 0) {
    throw "Wood-owned Flow input did not produce an active Flow simulation."
}
if (-not (Test-Path -LiteralPath $result.metrics_csv)) {
    throw "Phase 3 metrics CSV was not produced."
}
if ((Get-Content -LiteralPath $result.metrics_csv | Measure-Object).Count -ne 1201) {
    throw "Phase 3 metrics CSV does not contain 1200 data rows."
}
if ($result.images.Count -ne 2) {
    throw "Phase 3 must produce two fixed-step captures."
}

Add-Type -AssemblyName System.Drawing
foreach ($capture in $result.images) {
    if (-not (Test-Path -LiteralPath $capture.path)) {
        throw "Phase 3 capture was not produced: $($capture.path)"
    }
    $image = [System.Drawing.Image]::FromFile($capture.path)
    try {
        if ($image.Width -ne 1280 -or $image.Height -ne 720) {
            throw "Phase 3 PNG has an unexpected resolution: $($image.Width)x$($image.Height)"
        }
    }
    finally {
        $image.Dispose()
    }
}

$result | Add-Member -NotePropertyName runner_wall_seconds -NotePropertyValue ([math]::Round($runTimer.Elapsed.TotalSeconds, 3)) -Force
$json = $result | ConvertTo-Json -Depth 12
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($summary, $json + [Environment]::NewLine, $utf8NoBom)

Write-Host "Phase 3 validation succeeded: $OutputDir"
