param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phasev3tc\integrated"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$nativeBuild = Join-Path $OutputDir "native-build"
& (Join-Path $PSScriptRoot "build_wood_native.ps1") -OutputDir $nativeBuild
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$nativeDll = Join-Path $nativeBuild "campfire_wood_native.dll"
$phase3Runner = Join-Path $PSScriptRoot "run_phase3.ps1"
$order = @(
    [ordered]@{ pair = 1; mode = "off" },
    [ordered]@{ pair = 1; mode = "on" },
    [ordered]@{ pair = 2; mode = "on" },
    [ordered]@{ pair = 2; mode = "off" },
    [ordered]@{ pair = 3; mode = "off" },
    [ordered]@{ pair = 3; mode = "on" }
)
$manifestRuns = @()
$nvidiaSmi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
$sequence = 0
foreach ($case in $order) {
    $sequence += 1
    $runName = "pair_{0}_{1}" -f $case.pair, $case.mode
    $runDir = Join-Path $OutputDir $runName
    New-Item -ItemType Directory -Path $runDir -Force | Out-Null
    $gpuCsv = Join-Path $runDir "gpu_samples.csv"
    $gpuError = Join-Path $runDir "gpu_monitor.stderr.log"
    $gpuMonitor = $null
    if ($nvidiaSmi) {
        $gpuMonitor = Start-Process -FilePath $nvidiaSmi.Source -ArgumentList @(
            "--query-gpu=timestamp,utilization.gpu,memory.used",
            "--format=csv,noheader,nounits",
            "--loop-ms=250"
        ) -RedirectStandardOutput $gpuCsv -RedirectStandardError $gpuError -PassThru -WindowStyle Hidden
    }
    try {
        $common = @{
            OutputDir = $runDir
            ResidentSnapshotAdapter = $true
            ResidentSnapshotHandleCache = $true
            ResidentSnapshotLightweightCommit = $true
            ResidentSnapshotSkipUnchanged = $true
            WoodRenderHierarchy = $true
            ResidentNativeBackend = $true
            ResidentNativeLibraryPath = $nativeDll
        }
        if ($case.mode -eq "on") {
            & $phase3Runner @common -WoodVisualV3
        }
        else {
            & $phase3Runner @common
        }
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    finally {
        if ($gpuMonitor -and -not $gpuMonitor.HasExited) {
            Stop-Process -Id $gpuMonitor.Id -Force
            Wait-Process -Id $gpuMonitor.Id -Timeout 5 -ErrorAction SilentlyContinue
        }
    }
    $summaryPath = Join-Path $runDir "summary.json"
    $summary = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json
    $gpuSamples = @()
    if (Test-Path -LiteralPath $gpuCsv) {
        $gpuSamples = @(Get-Content -LiteralPath $gpuCsv | ForEach-Object {
            $columns = $_ -split ','
            if ($columns.Count -ge 3) {
                [PSCustomObject]@{
                    utilization = [double]$columns[1].Trim()
                    memory_mib = [double]$columns[2].Trim()
                }
            }
        })
    }
    $gpu = [ordered]@{
        sample_count = $gpuSamples.Count
        interval_ms = 250
        utilization_mean_percent = $null
        utilization_max_percent = $null
        memory_min_mib = $null
        memory_max_mib = $null
        memory_span_mib = $null
        method = "Whole-GPU nvidia-smi samples; memory is not provider-scoped."
    }
    if ($gpuSamples.Count -gt 0) {
        $utilization = @($gpuSamples | ForEach-Object { $_.utilization })
        $memory = @($gpuSamples | ForEach-Object { $_.memory_mib })
        $gpu.utilization_mean_percent = [math]::Round(($utilization | Measure-Object -Average).Average, 3)
        $gpu.utilization_max_percent = ($utilization | Measure-Object -Maximum).Maximum
        $gpu.memory_min_mib = ($memory | Measure-Object -Minimum).Minimum
        $gpu.memory_max_mib = ($memory | Measure-Object -Maximum).Maximum
        $gpu.memory_span_mib = $gpu.memory_max_mib - $gpu.memory_min_mib
    }
    $summary | Add-Member -NotePropertyName phasev3tc_gpu -NotePropertyValue $gpu -Force
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText(
        $summaryPath,
        ($summary | ConvertTo-Json -Depth 14) + [Environment]::NewLine,
        $utf8NoBom
    )
    $manifestRuns += [ordered]@{
        sequence = $sequence
        pair = $case.pair
        mode = $case.mode
        summary = $summaryPath
        summary_sha256 = (Get-FileHash -LiteralPath $summaryPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$manifest = [ordered]@{
    schema = "campfire.phasev3tc.matrix.v1"
    order = "pair1 OFF/ON, pair2 ON/OFF, pair3 OFF/ON"
    capture_conditions = "two fixed 1280x720 captures per run"
    native_library = $nativeDll
    runs = $manifestRuns
}
$manifestPath = Join-Path $OutputDir "matrix_manifest.json"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText(
    $manifestPath,
    ($manifest | ConvertTo-Json -Depth 8) + [Environment]::NewLine,
    $utf8NoBom
)
Write-Host "Phase V3T-C integrated matrix complete: $manifestPath"
