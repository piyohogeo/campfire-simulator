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
    $OutputDir = Join-Path $repoRoot "artifacts\phase1\latest"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$gpuCsv = Join-Path $OutputDir "gpu_samples.csv"
$gpuMonitorError = Join-Path $OutputDir "gpu_monitor.stderr.log"
$gpuMonitor = $null
$nvidiaSmi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
if ($nvidiaSmi) {
    $gpuArgs = @(
        "--query-gpu=timestamp,utilization.gpu,memory.used",
        "--format=csv,noheader,nounits",
        "--loop-ms=250"
    )
    # nvidia-smi's --filename option creates an empty file with this Windows
    # driver. Redirecting stdout preserves the continuous query stream.
    $gpuMonitor = Start-Process `
        -FilePath $nvidiaSmi.Source `
        -ArgumentList $gpuArgs `
        -RedirectStandardOutput $gpuCsv `
        -RedirectStandardError $gpuMonitorError `
        -PassThru `
        -WindowStyle Hidden
}

$kitArgs = @(
    $app,
    "--no-window",
    "--/app/quitAfter=900",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=true",
    "--/exts/campfire.app/phase=phase1",
    "--/exts/campfire.app/captureOnStartup=true",
    "--/exts/campfire.app/quitAfterCapture=true",
    "--/exts/campfire.app/outputDir=$OutputDir",
    "--/rtx/flow/enabled=true"
)

$runTimer = [System.Diagnostics.Stopwatch]::StartNew()
try {
    & $kit @kitArgs
    $exitCode = $LASTEXITCODE
}
finally {
    $runTimer.Stop()
    if ($gpuMonitor -and -not $gpuMonitor.HasExited) {
        Stop-Process -Id $gpuMonitor.Id -Force
        Wait-Process -Id $gpuMonitor.Id -Timeout 5 -ErrorAction SilentlyContinue
    }
}

if ($exitCode -ne 0) {
    throw "Phase 1 application failed with exit code $exitCode."
}

$summary = Join-Path $OutputDir "summary.json"
if (-not (Test-Path -LiteralPath $summary)) {
    throw "Phase 1 summary was not produced: $summary"
}

$result = Get-Content -LiteralPath $summary -Raw | ConvertFrom-Json
if ($result.status -ne "ok" -or $result.phase -ne "phase1") {
    throw "Phase 1 summary reported a failure or unexpected phase: $summary"
}
if ($result.images.Count -ne 2) {
    throw "Phase 1 must produce two fixed-frame captures."
}
if (-not $result.emitter_motion.moved) {
    throw "Phase 1 emitter did not reach its expected final position."
}
if ($result.collision.static_log_colliders -ne 4 -or -not $result.collision.physics_collision_enabled) {
    throw "Phase 1 Flow/PhysX collision configuration is incomplete."
}
if ($result.flow.active_blocks_peak -le 0) {
    throw "Phase 1 Flow simulation allocated no active blocks."
}

Add-Type -AssemblyName System.Drawing
foreach ($capture in $result.images) {
    if (-not (Test-Path -LiteralPath $capture.path)) {
        throw "Phase 1 capture was not produced: $($capture.path)"
    }
    $capturedImage = [System.Drawing.Image]::FromFile($capture.path)
    try {
        if ($capturedImage.Width -ne 1280 -or $capturedImage.Height -ne 720) {
            throw "Phase 1 PNG has an unexpected resolution: $($capturedImage.Width)x$($capturedImage.Height)"
        }
    }
    finally {
        $capturedImage.Dispose()
    }
}

$gpuSamples = @()
if (Test-Path -LiteralPath $gpuCsv) {
    $gpuSamples = @(Get-Content -LiteralPath $gpuCsv | ForEach-Object {
        $columns = $_ -split ','
        if ($columns.Count -ge 3) {
            [PSCustomObject]@{
                Timestamp = $columns[0].Trim()
                UtilizationPercent = [double]$columns[1].Trim()
                MemoryUsedMiB = [double]$columns[2].Trim()
            }
        }
    })
}

$gpuMeasurement = [ordered]@{
    samples = $gpuSamples.Count
    interval_ms = 250
    max_utilization_percent = $null
    mean_utilization_percent = $null
    max_memory_used_mib = $null
    estimated_gpu_active_ms = $null
    method = "Whole-GPU nvidia-smi sampling; estimated active time is utilization-weighted and is not Flow kernel timing."
}
if ($gpuSamples.Count -gt 0) {
    $utilization = @($gpuSamples | ForEach-Object { $_.UtilizationPercent })
    $memory = @($gpuSamples | ForEach-Object { $_.MemoryUsedMiB })
    $gpuMeasurement.max_utilization_percent = ($utilization | Measure-Object -Maximum).Maximum
    $gpuMeasurement.mean_utilization_percent = [math]::Round(($utilization | Measure-Object -Average).Average, 2)
    $gpuMeasurement.max_memory_used_mib = ($memory | Measure-Object -Maximum).Maximum
    $gpuMeasurement.estimated_gpu_active_ms = [math]::Round((($utilization | Measure-Object -Sum).Sum / 100.0) * 250.0, 2)
}
elseif ($nvidiaSmi) {
    throw "nvidia-smi was available but produced no GPU samples: $gpuCsv"
}

$result | Add-Member -NotePropertyName runner -NotePropertyValue ([ordered]@{
    wall_seconds = [math]::Round($runTimer.Elapsed.TotalSeconds, 3)
    gpu = $gpuMeasurement
}) -Force
$json = $result | ConvertTo-Json -Depth 12
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($summary, $json + [Environment]::NewLine, $utf8NoBom)

Write-Host "Phase 1 validation succeeded: $OutputDir"
