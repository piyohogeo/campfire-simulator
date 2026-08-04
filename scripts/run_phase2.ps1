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
    $OutputDir = Join-Path $repoRoot "artifacts\phase2\latest"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$kitArgs = @(
    $app,
    "--no-window",
    "--/app/quitAfter=900",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=true",
    "--/exts/campfire.app/phase=phase2",
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
    throw "Phase 2 application failed with exit code $exitCode."
}

$summary = Join-Path $OutputDir "summary.json"
if (-not (Test-Path -LiteralPath $summary)) {
    throw "Phase 2 summary was not produced: $summary"
}

$result = Get-Content -LiteralPath $summary -Raw | ConvertFrom-Json
if ($result.status -ne "ok" -or $result.phase -ne "phase2") {
    throw "Phase 2 summary reported a failure or unexpected phase: $summary"
}
if ($result.logs.count_before_add -ne 4 -or $result.logs.count_after_add -ne 5) {
    throw "Phase 2 did not preserve four logs and add exactly one log."
}
if (-not $result.logs.identity_preserved) {
    throw "An existing log ID was lost while adding the Phase 2 log."
}
if ($result.rigid_body.dropped_distance_m -lt 1.0) {
    throw "The added log did not fall at least one meter."
}
if (-not $result.rigid_body.settled) {
    throw "The added log did not settle during the final simulated second."
}
if (-not $result.rigid_body.inside_stone_ring -or -not $result.rigid_body.resting_above_ground) {
    throw "The added log did not finish in the expected campfire support region."
}
if (-not $result.emitter_follow.followed) {
    throw "The Flow emitter did not follow the added rigid log."
}
if ($result.flow.active_blocks_peak -le 0) {
    throw "Phase 2 Flow simulation allocated no active blocks."
}
if ($result.images.Count -ne 2) {
    throw "Phase 2 must produce two fixed-frame captures."
}

Add-Type -AssemblyName System.Drawing
foreach ($capture in $result.images) {
    if (-not (Test-Path -LiteralPath $capture.path)) {
        throw "Phase 2 capture was not produced: $($capture.path)"
    }
    $image = [System.Drawing.Image]::FromFile($capture.path)
    try {
        if ($image.Width -ne 1280 -or $image.Height -ne 720) {
            throw "Phase 2 PNG has an unexpected resolution: $($image.Width)x$($image.Height)"
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

Write-Host "Phase 2 validation succeeded: $OutputDir"
