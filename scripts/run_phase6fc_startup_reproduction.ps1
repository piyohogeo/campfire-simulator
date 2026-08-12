param([Parameter(Mandatory = $true)][string]$OutputRoot)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6FC refuses artifact root reuse: $OutputRoot" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
$logs = Join-Path $OutputRoot "runner-logs"
New-Item -ItemType Directory -Path $logs | Out-Null

$contractPath = Join-Path $PSScriptRoot "phase6fc_startup_reproduction_contract.json"
$hashPath = Join-Path $PSScriptRoot "phase6fc_startup_reproduction_contract.sha256"
$expectedHash = ((Get-Content -Encoding UTF8 $hashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($actualHash -ne $expectedHash) { throw "Phase 6FC contract hash mismatch" }
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
Copy-Item -LiteralPath $hashPath -Destination (Join-Path $OutputRoot "frozen_contract.sha256")
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
$limits = $contract.safety
$guard = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
$caseRunner = Join-Path $PSScriptRoot "run_phase6ep_point_collision_case.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6fc_startup_reproduction.py"
$powershell = (Get-Command powershell.exe).Source
$productionApp = Join-Path $root "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$reportPath = Join-Path $OutputRoot "startup_reproduction_report.json"
$statePath = Join-Path $OutputRoot "incremental_state.json"
$timingPath = Join-Path $OutputRoot "process_timing.jsonl"
$previousExitUtc = ""

function Write-State([string]$Status, [int]$Completed, [string]$Active, [string]$Reason) {
    $payload = [ordered]@{
        schema="campfire.phase6fc.incremental-state.v1"; phase="phase6fc"; status=$Status
        completed_conditions=$Completed; active_condition=$Active; stop_reason=$Reason
        contract_sha256=$actualHash; timestamp_utc=[DateTime]::UtcNow.ToString("o")
    }
    [IO.File]::WriteAllText($statePath, ($payload | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Write-Timing([string]$Label, [string]$Marker) {
    $payload = [ordered]@{schema="campfire.phase6fc.process-timing.v1"; label=$Label; marker=$Marker; timestamp_utc=[DateTime]::UtcNow.ToString("o")}
    [IO.File]::AppendAllText($timingPath, ($payload | ConvertTo-Json -Compress) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Update-Report {
    & python $analyzer --root $OutputRoot --contract $contractPath --output $reportPath
    if ($LASTEXITCODE -ne 0) { throw "Phase 6FC analyzer failed" }
}

function Stop-Safely([int]$Completed, [string]$Active, [string]$Reason) {
    Write-State "safe_stop" $Completed $Active $Reason
    Update-Report
    Write-Error "Phase 6FC safe stop at ${Active}: $Reason"
    exit 2
}

function Get-LastOsExitUtc([string]$Label) {
    $path = Join-Path (Join-Path $OutputRoot $Label) "runner_lifecycle_markers.jsonl"
    if (-not (Test-Path -LiteralPath $path)) { return "" }
    $last = Get-Content -Encoding UTF8 $path | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object { $_.marker -eq "os_process_exit_observed" } | Select-Object -Last 1
    if ($null -eq $last) { return "" }
    return [string]$last.timestamp_utc
}

function Invoke-StartupCase($Condition) {
    $label = [string]$Condition.id
    $caseDir = Join-Path $OutputRoot $label
    $arguments = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $caseRunner,
        "-Scenario", "production_four", "-OutputDir", $caseDir,
        "-OffsetM", "-0.0125", "-SupportRadiusM", "0.05", "-Filtering", "true",
        "-Collision", "true", "-Policy", "allow_self_center", "-ReportPhase", "phase6fc",
        "-GeometryVariant", "phase6er_corrected", "-FuelScale", "1", "-TemperatureScale", "1", "-SmokeScale", "1",
        "-SampleFrames", "30,60,90,120", "-ReadbackChannels", "none", "-ReadbackMode", "none",
        "-ReadbackFrames", "30", "-ReferenceDisposal", "natural",
        "-SynchronousMemoryMarkers", "true", "-PythonMemoryTelemetry", "false",
        "-SpatialCollectorsEnabled", "false", "-RunIndex", "1", "-LifecycleCalibration",
        "-FlowLivenessAudit", "true", "-FuelLivenessDecode", "false",
        "-StartupProbe", "true", "-StartupProbeLabel", $label,
        "-StartupFlowAcquirePosition", ([string]$Condition.flow_acquire_position),
        "-StartupPreTimelineUpdateCount", ([string]$Condition.pre_timeline_update_count),
        "-StartupExtraUpdateBeforePlayCount", ([string]$Condition.extra_update_before_play_count),
        "-PreviousProcessExitUtc", $previousExitUtc,
        "-RendererDrainUpdates", "$($contract.lifecycle.renderer_pre_close_drain_updates)",
        "-StageCloseTimeoutSeconds", "$($contract.lifecycle.stage_close_timeout_seconds)",
        "-AbsoluteTimeoutSeconds", "$($contract.lifecycle.inner_absolute_timeout_seconds)"
    )
    $guardArgs = @(
        $guard, "--trace", (Join-Path $logs "$label.resource.jsonl"),
        "--summary", (Join-Path $logs "$label.guard.json"),
        "--stdout", (Join-Path $logs "$label.stdout.log"),
        "--stderr", (Join-Path $logs "$label.stderr.log"),
        "--timeout-seconds", "$($contract.lifecycle.outer_condition_timeout_seconds)",
        "--sample-seconds", "$($limits.resource_sampling_seconds)",
        "--runner-private-limit", "$($limits.runner_private_limit_bytes)",
        "--diagnostic-private-limit", "$($limits.diagnostic_private_limit_bytes)",
        "--kit-private-limit", "$($limits.kit_private_limit_bytes)",
        "--tree-private-limit", "$($limits.unique_tree_private_limit_bytes)",
        "--available-memory-floor", "$($limits.physical_memory_floor_bytes)",
        "--commit-headroom-floor", "$($limits.commit_headroom_floor_bytes)",
        "--cpu-telemetry", "--gpu-csv", (Join-Path $logs "$label.gpu.csv"),
        "--gpu-sample-ms", "$($limits.gpu_sampling_ms)",
        "--lifecycle-path", (Join-Path $caseDir "raw.json"),
        "--diagnostic-marker-path", (Join-Path $caseDir "resource_markers.jsonl"), "--", $powershell
    ) + $arguments
    Write-Timing $label "process_launch_started"
    & python @guardArgs
    $guardExit = $LASTEXITCODE
    Write-Timing $label "guard_returned"
    Update-Report
    if ($guardExit -ne 0) { return "lifecycle_failure" }
    $report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
    $case = $report.cases.PSObject.Properties[$label].Value
    return [string]$case.classification
}

$completed = 0
$baselineClasses = @()
foreach ($condition in $contract.baseline_conditions) {
    $label = [string]$condition.id
    Write-State "running" $completed $label ""
    $classification = Invoke-StartupCase $condition
    $previousExitUtc = Get-LastOsExitUtc $label
    if ($classification -in @("lifecycle_failure", "stale_telemetry", "no_source", "indeterminate_startup")) {
        Stop-Safely $completed $label "baseline classification=$classification"
    }
    $baselineClasses += $classification
    $completed++
}

$allRepresentative = (@($baselineClasses | Where-Object { $_ -eq "representative_ingestion" }).Count -eq 6)
if ($allRepresentative) {
    foreach ($condition in $contract.ablation_conditions) {
        $label = [string]$condition.id
        Write-State "running" $completed $label ""
        $classification = Invoke-StartupCase $condition
        $previousExitUtc = Get-LastOsExitUtc $label
        if ($classification -ne "representative_ingestion") {
            Stop-Safely $completed $label "ablation classification=$classification; later ablations prohibited"
        }
        $completed++
    }
}

$productionAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
if ($productionBefore -ne $productionAfter) { Stop-Safely $completed "final" "production_app_hash_changed" }
Update-Report
$final = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
$reason = if ($allRepresentative) { "six representative baselines and four bounded ablations completed" } else { "baseline reproduction measured; ablations not eligible" }
Write-State "completed" $completed "complete" $reason
Write-Host "Phase 6FC completed: $reason"
