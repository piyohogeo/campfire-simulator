param(
    [string]$OutputDir = "",
    [ValidateRange(1, 5)][int]$Runs = 3
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutputDir) { $OutputDir = Join-Path $root "artifacts\phasev3tp" }
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath (Join-Path $OutputDir "manifest.json")) {
    throw "Phase V3T-P refuses to reuse a completed output: $OutputDir"
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$phase3 = Join-Path $PSScriptRoot "run_phase3.ps1"
$native = Join-Path $root "source\extensions\campfire.app\bin\campfire_wood_native.dll"
$nvidiaSmi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
$entries = [Collections.Generic.List[object]]::new()

function Invoke-ProductionRun {
    param([string]$Condition, [int]$Run, [string]$AppKind = "benchmark")
    $name = "{0}_{1}_r{2}" -f $AppKind, $Condition, $Run
    $dir = Join-Path $OutputDir $name
    if (Test-Path -LiteralPath $dir) { throw "Phase V3T-P refuses to reuse $dir" }
    New-Item -ItemType Directory -Path $dir | Out-Null
    $gpuCsv = Join-Path $dir "gpu.csv"
    $gpuMonitor = $null
    if ($nvidiaSmi) {
        $gpuMonitor = Start-Process $nvidiaSmi.Source -ArgumentList @(
            "--query-gpu=timestamp,utilization.gpu,memory.used,power.draw,clocks.current.graphics,clocks.current.sm,temperature.gpu,pstate,power.limit,enforced.power.limit",
            "--format=csv,noheader,nounits",
            "--loop-ms=250"
        ) -RedirectStandardOutput $gpuCsv -PassThru -WindowStyle Hidden
    }
    $started = [DateTimeOffset]::UtcNow
    try {
        $arguments = @{
            OutputDir = $dir
            AppKind = $AppKind
            DisableMilestoneFrames = $true
            RtxVisualPreset = "Inherit"
            IsolatedCrashSafety = $true
        }
        if ($Condition -eq "on_default") {
            $arguments.InheritProductionV3Defaults = $true
        }
        elseif ($Condition -eq "off_explicit") {
            $arguments.ResidentSnapshotAdapter = $true
            $arguments.ResidentSnapshotHandleCache = $true
            $arguments.ResidentSnapshotLightweightCommit = $true
            $arguments.ResidentSnapshotSkipUnchanged = $true
            $arguments.ResidentNativeBackend = $true
            $arguments.ResidentNativeLibraryPath = $native
            $arguments.WoodRenderHierarchy = $true
        }
        else { throw "Unsupported Phase V3T-P condition: $Condition" }
        & $phase3 @arguments
        if ($LASTEXITCODE -ne 0) { throw "Phase V3T-P run failed: $name" }
    }
    finally {
        if ($gpuMonitor -and -not $gpuMonitor.HasExited) {
            Stop-Process -Id $gpuMonitor.Id -Force
            Wait-Process -Id $gpuMonitor.Id -Timeout 5 -ErrorAction SilentlyContinue
        }
    }
    $summary = Join-Path $dir "summary.json"
    $payload = Get-Content -LiteralPath $summary -Raw -Encoding UTF8 | ConvertFrom-Json
    $entries.Add([ordered]@{
        name = $name
        condition = $Condition
        app_kind = $AppKind
        run = $Run
        started_utc = $started.ToString("o")
        elapsed_seconds = [Math]::Round(([DateTimeOffset]::UtcNow - $started).TotalSeconds, 3)
        summary = $summary
        kit_log = Join-Path $dir "kit.log"
        gpu_csv = if (Test-Path -LiteralPath $gpuCsv) { $gpuCsv } else { $null }
        authority_sha256 = @{
            dry = $payload.wood.dry.authoritative_state_sha256
            wet = $payload.wood.wet.authoritative_state_sha256
            metrics_csv = $payload.metrics_csv_sha256
        }
    })
}

for ($run = 1; $run -le $Runs; $run++) {
    $order = if (($run % 2) -eq 1) { @("off_explicit", "on_default") } else { @("on_default", "off_explicit") }
    foreach ($condition in $order) { Invoke-ProductionRun -Condition $condition -Run $run }
}
Invoke-ProductionRun -Condition "on_default" -Run 1 -AppKind "normal"

$manifest = [ordered]@{
    schema = "campfire.phasev3tp.production-promotion-manifest.v1"
    phase = "V3T-P"
    runs = $Runs
    resolution = @(1280, 720)
    renderer = "Candidate Performance"
    transport = "DynamicTextureProvider.set_raw_bytes_data CPU-source"
    additional_render_product_created = $false
    milestone_capture_in_performance_population = $false
    entries = $entries
}
$json = $manifest | ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $OutputDir "manifest.json"), $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host "Phase V3T-P production matrix completed: $OutputDir"
