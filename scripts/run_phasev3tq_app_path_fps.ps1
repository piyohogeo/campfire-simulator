param(
    [string]$OutputDir = "",
    [ValidateSet("preflight", "formal", "focused")]
    [string]$Mode = "formal",
    [string[]]$FocusedConditions = @(),
    [ValidateRange(1, 3)][int]$FocusedRuns = 1,
    [switch]$VisibleWindow
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$release = Join-Path $root "_build\windows-x86_64\release"
$kit = Join-Path $release "kit\kit.exe"
$normalApp = Join-Path $release "apps\campfire.simulator.kit"
$benchmarkApp = Join-Path $release "apps\campfire.simulator.benchmark.kit"
$prepare = Join-Path $PSScriptRoot "prepare_phasev3tq_app_variants.py"
$phase3Runner = Join-Path $PSScriptRoot "run_phase3.ps1"
$diagnosticExtensionRoot = Join-Path $PSScriptRoot "phasev3tq_extension"
if (-not $OutputDir) { $OutputDir = Join-Path $root "artifacts\phasev3tq-$Mode" }
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath (Join-Path $OutputDir "manifest.json")) {
    throw "Phase V3T-Q refuses to reuse an existing manifest: $OutputDir"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$derivedDir = Join-Path $release "phasev3tq-apps"
$derivedManifest = Join-Path $OutputDir "derived_apps.json"
$normalHashBefore = (Get-FileHash -LiteralPath $normalApp -Algorithm SHA256).Hash
$benchmarkHashBefore = (Get-FileHash -LiteralPath $benchmarkApp -Algorithm SHA256).Hash
python $prepare --normal $normalApp --benchmark $benchmarkApp --output-dir $derivedDir --manifest $derivedManifest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$derived = Get-Content -LiteralPath $derivedManifest -Raw -Encoding UTF8 | ConvertFrom-Json
$variantPaths = @{}
foreach ($variant in $derived.variants) { $variantPaths[$variant.condition] = $variant.path }

$formalConditions = @(
    "normal_baseline",
    "normal_without_developer_bundle",
    "benchmark_with_developer_bundle",
    "benchmark_baseline"
)
$orders = @(
    @("normal_baseline", "normal_without_developer_bundle", "benchmark_with_developer_bundle", "benchmark_baseline"),
    @("benchmark_baseline", "normal_baseline", "benchmark_with_developer_bundle", "normal_without_developer_bundle"),
    @("normal_without_developer_bundle", "benchmark_with_developer_bundle", "normal_baseline", "benchmark_baseline")
)
if ($Mode -eq "preflight") {
    $orders = @($formalConditions)
}
elseif ($Mode -eq "focused") {
    if (-not $FocusedConditions.Count) { throw "Focused mode requires -FocusedConditions." }
    foreach ($condition in $FocusedConditions) {
        if (-not $variantPaths.ContainsKey($condition)) { throw "Unknown focused condition: $condition" }
    }
    $orders = @()
    for ($run = 0; $run -lt $FocusedRuns; $run++) {
        $offset = $run % $FocusedConditions.Count
        if ($offset -eq 0) { $orders += ,@($FocusedConditions) }
        else { $orders += ,@($FocusedConditions[$offset..($FocusedConditions.Count - 1)] + $FocusedConditions[0..($offset - 1)]) }
    }
}

$nvidiaSmi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
$entries = [Collections.Generic.List[object]]::new()
function Assert-NoKitProcess {
    $running = @(Get-CimInstance Win32_Process -Filter "Name='kit.exe'" -ErrorAction SilentlyContinue | Where-Object {
        $_.ExecutablePath -and ([IO.Path]::GetFullPath($_.ExecutablePath) -eq [IO.Path]::GetFullPath($kit))
    })
    if ($running.Count) { throw "Phase V3T-Q refuses overlapping Kit: $($running.ProcessId -join ',')" }
}

function Get-NumberSummary {
    param([object[]]$Values)
    $values = @($Values | Where-Object { $null -ne $_ })
    if (-not $values.Count) { return $null }
    return [ordered]@{
        count = $values.Count
        mean = [Math]::Round(($values | Measure-Object -Average).Average, 4)
        min = [Math]::Round(($values | Measure-Object -Minimum).Minimum, 4)
        max = [Math]::Round(($values | Measure-Object -Maximum).Maximum, 4)
    }
}

function Read-GpuRows {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return @() }
    return @(Get-Content -LiteralPath $Path | ForEach-Object {
        $columns = $_ -split ','
        if ($columns.Count -ge 11) {
            [pscustomobject]@{
                timestamp = [DateTimeOffset]::ParseExact($columns[0].Trim(), 'yyyy/MM/dd HH:mm:ss.fff', $null)
                utilization = [double]$columns[1].Trim()
                memory_mib = [double]$columns[2].Trim()
                power_w = [double]$columns[3].Trim()
                graphics_clock_mhz = [double]$columns[4].Trim()
                sm_clock_mhz = [double]$columns[5].Trim()
                temperature_c = [double]$columns[6].Trim()
                pstate = $columns[7].Trim()
                power_limit_w = [double]$columns[8].Trim()
                enforced_power_limit_w = [double]$columns[9].Trim()
                perf_cap_reason = $columns[10].Trim()
            }
        }
    })
}

function Invoke-Condition {
    param([string]$Condition, [int]$RunIndex, [int]$OrderIndex)
    Assert-NoKitProcess
    $name = "{0}_r{1}_o{2}" -f $Condition, ($RunIndex + 1), ($OrderIndex + 1)
    $dir = Join-Path $OutputDir $name
    if (Test-Path -LiteralPath $dir) { throw "Phase V3T-Q run already exists: $dir" }
    New-Item -ItemType Directory -Path $dir | Out-Null
    $kitLog = Join-Path $dir "kit.log"
    $diagnostic = Join-Path $dir "runtime_diagnostic.json"
    $gpuCsv = Join-Path $dir "gpu.csv"
    $monitor = $null
    if ($nvidiaSmi) {
        $monitorArgs = @(
            "--query-gpu=timestamp,utilization.gpu,memory.used,power.draw,clocks.current.graphics,clocks.current.sm,temperature.gpu,pstate,power.limit,enforced.power.limit,clocks_event_reasons.active",
            "--format=csv,noheader,nounits",
            "--loop-ms=250"
        )
        $monitor = Start-Process $nvidiaSmi.Source -ArgumentList $monitorArgs -RedirectStandardOutput $gpuCsv -PassThru -WindowStyle Hidden
    }
    $started = [DateTimeOffset]::UtcNow
    $timer = [Diagnostics.Stopwatch]::StartNew()
    try {
        $appKind = if ($Condition.StartsWith("benchmark")) { "benchmark" } else { "normal" }
        $allowDebug = $Condition -eq "benchmark_with_developer_bundle"
        $additional = @(
            "--ext-folder",
            $diagnosticExtensionRoot,
            "--/phasev3tq/output=$diagnostic",
            "--/phasev3tq/condition=$Condition"
        )
        & $phase3Runner -OutputDir $dir -AppKind $appKind -AppPath $variantPaths[$Condition] `
            -InheritProductionV3Defaults -DisableMilestoneFrames -IsolatedCrashSafety `
            -KitLog $kitLog -CrashDumpDir (Join-Path $dir "sensitive-crash-dumps") `
            -AdditionalKitArguments $additional -AllowDebugExtensions:$allowDebug `
            -VisibleWindow:$VisibleWindow.IsPresent
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    finally {
        $timer.Stop()
        if ($monitor -and -not $monitor.HasExited) {
            Stop-Process -Id $monitor.Id -Force
            Wait-Process -Id $monitor.Id -Timeout 5 -ErrorAction SilentlyContinue
        }
    }
    $summary = Get-Content -LiteralPath (Join-Path $dir "summary.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    $runtime = Get-Content -LiteralPath $diagnostic -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($runtime.status -ne "ok") { throw "Phase V3T-Q runtime diagnostic did not close cleanly: $name" }
    $startupOrder = @()
    foreach ($line in Get-Content -LiteralPath $kitLog) {
        if ($line -match '\[ext:\s*([^\]]+)\]\s+startup') { $startupOrder += $Matches[1] }
    }
    $gpu = @(Read-GpuRows -Path $gpuCsv)
    $playSnapshot = @($runtime.snapshots | Where-Object marker -eq "timeline_play" | Select-Object -First 1)
    $playUtc = if ($playSnapshot.Count) { [DateTimeOffset]::Parse($playSnapshot[0].timestamp_utc) } else { $started }
    $gpuMeasurement = @($gpu | Where-Object { $_.timestamp.ToUniversalTime() -ge $playUtc.ToUniversalTime() })
    $entry = [ordered]@{
        condition = $Condition
        run = $RunIndex + 1
        order_index = $OrderIndex + 1
        mode = $Mode
        started_utc = $started.ToString('o')
        process_wall_seconds = [Math]::Round($timer.Elapsed.TotalSeconds, 4)
        app_path = $variantPaths[$Condition]
        summary_path = Join-Path $dir "summary.json"
        diagnostic_path = $diagnostic
        kit_log = $kitLog
        startup_order = $startupOrder
        enabled_extension_ids = @($startupOrder | Sort-Object -Unique)
        developer_related_extensions = @($startupOrder | Where-Object { $_ -match '(?i)debug|developer|dev\.utilities|profiler|stats|settings|telemetry' } | Sort-Object -Unique)
        runtime_diagnostic = $runtime
        performance = [ordered]@{
            average_visible_fps = $summary.scenario.visible_viewport.average_fps
            hud_frame_time_ms = if ($summary.scenario.visible_viewport.average_fps) { [Math]::Round(1000.0 / [double]$summary.scenario.visible_viewport.average_fps, 4) } else { $null }
            simulation_wall_seconds = $summary.scenario.simulation_wall_seconds
            timeline_model_seconds = $summary.scenario.model_duration_seconds
            main_update_interval = $summary.timing.segments.frame_pacing.update_frame
            v3_publication_timing = $summary.scenario.wood_visual_v3.publication_timing
            v3_publication_count = @($summary.scenario.wood_visual_v3.publication_samples).Count
            v3_upload_count = $summary.scenario.wood_visual_v3.status_after_timeline_stop.upload_count
            v3_quantized_skip_count = $summary.scenario.wood_visual_v3.status_after_timeline_stop.quantized_skip_count
            v3_visual_commit_count = $summary.scenario.wood_visual_v3.status_after_timeline_stop.visual_commit_count
            flow_active_blocks_final = $summary.flow.active_blocks_final
            flow_active_blocks_peak = $summary.flow.active_blocks_peak
        }
        gpu = [ordered]@{
            whole_process_samples = $gpu.Count
            measurement_samples = $gpuMeasurement.Count
            utilization_percent = Get-NumberSummary $gpuMeasurement.utilization
            power_w = Get-NumberSummary $gpuMeasurement.power_w
            graphics_clock_mhz = Get-NumberSummary $gpuMeasurement.graphics_clock_mhz
            sm_clock_mhz = Get-NumberSummary $gpuMeasurement.sm_clock_mhz
            memory_used_mib = Get-NumberSummary $gpuMeasurement.memory_mib
            temperature_c = Get-NumberSummary $gpuMeasurement.temperature_c
            power_limit_w = Get-NumberSummary $gpuMeasurement.power_limit_w
            enforced_power_limit_w = Get-NumberSummary $gpuMeasurement.enforced_power_limit_w
            pstates = @($gpuMeasurement.pstate | Sort-Object -Unique)
            perf_cap_reasons = @($gpuMeasurement.perf_cap_reason | Sort-Object -Unique)
        }
        metric_contract = [ordered]@{
            visible_fps = "ViewportAPI.frame_info render counter"
            display_present_fps = $null
            gpu_render_time = $null
            raw_renderer_frame_interval = $null
            additional_render_product_created = $false
            capture_or_encode_in_population = $false
            visible_window = $VisibleWindow.IsPresent
        }
    }
    $entries.Add([pscustomobject]$entry)
}

for ($runIndex = 0; $runIndex -lt $orders.Count; $runIndex++) {
    $order = @($orders[$runIndex])
    for ($orderIndex = 0; $orderIndex -lt $order.Count; $orderIndex++) {
        Invoke-Condition -Condition $order[$orderIndex] -RunIndex $runIndex -OrderIndex $orderIndex
    }
}

$normalHashAfter = (Get-FileHash -LiteralPath $normalApp -Algorithm SHA256).Hash
$benchmarkHashAfter = (Get-FileHash -LiteralPath $benchmarkApp -Algorithm SHA256).Hash
if ($normalHashBefore -ne $normalHashAfter -or $benchmarkHashBefore -ne $benchmarkHashAfter) {
    throw "Phase V3T-Q changed a production app."
}
$manifest = [ordered]@{
    schema = "campfire.phasev3tq.app-path-fps-manifest.v1"
    status = "ok"
    mode = $Mode
    kit = "110.2"
    flow = "110.0.0"
    resolution = @(1280, 720)
    candidate_performance = $true
    v3_default_on = $true
    gpu_transport = "cpu_source"
    power_limit_changed = $false
    production_apps = [ordered]@{
        normal = [ordered]@{ path = $normalApp; sha256_before = $normalHashBefore; sha256_after = $normalHashAfter; changed = $false }
        benchmark = [ordered]@{ path = $benchmarkApp; sha256_before = $benchmarkHashBefore; sha256_after = $benchmarkHashAfter; changed = $false }
    }
    derived_apps = $derivedManifest
    order = $orders
    entries = $entries
}
$manifestPath = Join-Path $OutputDir "manifest.json"
[IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 14) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host "Phase V3T-Q $Mode complete: $($entries.Count) isolated process(es); production apps unchanged."
