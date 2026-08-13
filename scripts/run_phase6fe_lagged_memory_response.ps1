param([Parameter(Mandatory = $true)][string]$OutputRoot)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6FE refuses artifact root reuse: $OutputRoot" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null

$contractPath = Join-Path $PSScriptRoot "phase6fe_lagged_memory_response_contract.json"
$hashPath = Join-Path $PSScriptRoot "phase6fe_lagged_memory_response_contract.sha256"
$expectedHash = ((Get-Content -Encoding UTF8 $hashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($actualHash -ne $expectedHash) { throw "Phase 6FE contract hash mismatch" }
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
Copy-Item -LiteralPath $hashPath -Destination (Join-Path $OutputRoot "frozen_contract.sha256")
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
$limits = $contract.safety
$window = $contract.observation
$startup = $contract.startup
$source = $startup.expected_source_sums
$guard = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
$caseRunner = Join-Path $PSScriptRoot "run_phase6ep_point_collision_case.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6fe_lagged_memory_response.py"
$powershell = (Get-Command powershell.exe).Source
$productionApp = Join-Path $root "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$reportPath = Join-Path $OutputRoot "lagged_memory_response_report.json"
$statePath = Join-Path $OutputRoot "incremental_state.json"

function Write-State([string]$Status, [int]$Completed, [string]$Active, [string]$Reason) {
    $payload = [ordered]@{
        schema="campfire.phase6fe.incremental-state.v1"; phase="phase6fe"; status=$Status
        completed_conditions=$Completed; active_condition=$Active; stop_reason=$Reason
        contract_sha256=$actualHash; timestamp_utc=[DateTime]::UtcNow.ToString("o")
    }
    [IO.File]::WriteAllText($statePath, ($payload | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Update-Report {
    & python $analyzer --root $OutputRoot --contract $contractPath --output $reportPath
    if ($LASTEXITCODE -ne 0) { throw "Phase 6FE analyzer failed" }
}

function Stop-Safely([int]$Completed, [string]$Active, [string]$Reason) {
    Write-State "safe_stop" $Completed $Active $Reason
    try { Update-Report } catch { Write-Warning $_ }
    Write-Error "Phase 6FE safe stop at ${Active}: $Reason"
    exit 2
}

function Invoke-Case([int]$RunIndex, [string]$Label, [string]$Mode) {
    $runName = "run{0:D2}" -f $RunIndex
    $runRoot = Join-Path $OutputRoot $runName
    $logs = Join-Path $runRoot "runner-logs"
    New-Item -ItemType Directory -Force -Path $logs | Out-Null
    $caseDir = Join-Path $runRoot $Label
    $sampleFrames = ($contract.sample_frames -join ',')
    $arguments = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $caseRunner,
        "-Scenario", "production_four", "-OutputDir", $caseDir,
        "-OffsetM", "-0.0125", "-SupportRadiusM", "0.05", "-Filtering", "true",
        "-Collision", "true", "-Policy", "allow_self_center", "-ReportPhase", "phase6fe",
        "-GeometryVariant", "phase6er_corrected", "-FuelScale", "1", "-TemperatureScale", "1", "-SmokeScale", "1",
        "-SampleFrames", $sampleFrames, "-ReadbackChannels", "none",
        "-ReadbackMode", $Mode, "-ReadbackFrames", "$($contract.readback_frame)", "-ReferenceDisposal", "natural",
        "-SynchronousMemoryMarkers", "true", "-PythonMemoryTelemetry", "true",
        "-SpatialCollectorsEnabled", "false", "-RunIndex", "$RunIndex", "-LifecycleCalibration",
        "-RendererDrainUpdates", "$($contract.lifecycle.renderer_pre_close_drain_updates)",
        "-StageCloseTimeoutSeconds", "$($contract.lifecycle.stage_close_timeout_seconds)",
        "-StabilityObservationStartFrame", "$($window.start_frame)",
        "-StabilityObservationExtraSeconds", "$($window.extra_running_flow_wall_seconds)",
        "-StabilityActiveBlockSampleSeconds", "$($window.active_block_sample_seconds)",
        "-FlowLivenessAudit", "true", "-StartupProbe", "true", "-StartupProbeLabel", "${runName}_${Label}",
        "-StartupFlowAcquirePosition", "$($startup.flow_acquire_position)",
        "-StartupPreTimelineUpdateCount", "$($startup.stopped_update_count)",
        "-StartupExtraUpdateBeforePlayCount", "$($startup.extra_update_before_play_count)",
        "-StartupLivenessGate", "true",
        "-StartupExpectedFuelSum", "$($source.fuel)",
        "-StartupExpectedTemperatureSum", "$($source.temperature)",
        "-StartupExpectedSmokeSum", "$($source.smoke)",
        "-StartupSourceSumTolerance", "$($startup.source_sum_absolute_tolerance)",
        "-AbsoluteTimeoutSeconds", "$($contract.lifecycle.inner_absolute_timeout_seconds)"
    )
    $guardArgs = @(
        $guard, "--trace", (Join-Path $logs "$Label.resource.jsonl"),
        "--summary", (Join-Path $logs "$Label.guard.json"),
        "--stdout", (Join-Path $logs "$Label.stdout.log"),
        "--stderr", (Join-Path $logs "$Label.stderr.log"),
        "--timeout-seconds", "$($contract.lifecycle.outer_condition_timeout_seconds)",
        "--sample-seconds", "$($limits.resource_sampling_seconds)",
        "--runner-private-limit", "$($limits.runner_private_limit_bytes)",
        "--diagnostic-private-limit", "$($limits.diagnostic_private_limit_bytes)",
        "--kit-private-limit", "$($limits.kit_private_limit_bytes)",
        "--tree-private-limit", "$($limits.unique_tree_private_limit_bytes)",
        "--available-memory-floor", "$($limits.physical_memory_floor_bytes)",
        "--commit-headroom-floor", "$($limits.commit_headroom_floor_bytes)",
        "--cpu-telemetry", "--gpu-csv", (Join-Path $logs "$Label.gpu.csv"),
        "--gpu-sample-ms", "$($limits.gpu_sampling_ms)", "--lifecycle-path", (Join-Path $caseDir "raw.json"),
        "--diagnostic-marker-path", (Join-Path $caseDir "resource_markers.jsonl"), "--", $powershell
    ) + $arguments
    & python @guardArgs
    $guardExit = $LASTEXITCODE
    $guardPath = Join-Path $logs "$Label.guard.json"
    if (-not (Test-Path -LiteralPath $guardPath)) { return "resource_guard_summary_missing" }
    try { Update-Report } catch { return "analyzer_failure:$($_.Exception.Message)" }
    $guardResult = Get-Content -Raw -Encoding UTF8 $guardPath | ConvertFrom-Json
    if ($guardExit -ne 0 -or $guardResult.status -ne "ok" -or $guardResult.exit_code -ne 0 -or -not $guardResult.process_absent) {
        return "resource_or_lifecycle:$($guardResult.stop_reason)"
    }
    $report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
    $key = "${runName}_${Label}"
    $case = $report.cases.PSObject.Properties[$key].Value
    if (-not $case.condition_gate_pass) { return "condition_gate:$($case.condition_gate_failures -join ',')" }
    if ($Label -eq "C1_fuel_alias") {
        $pair = $report.pairs.PSObject.Properties[$runName].Value
        if (-not $pair.gate_pass) { return "pair_gate:$($pair.failures -join ',')" }
    }
    return $null
}

$completed = 0
foreach ($runIndex in 1..3) {
    foreach ($spec in @(
        @{ Label="C0_acquire_discard"; Mode="acquire_discard_release" },
        @{ Label="C1_fuel_alias"; Mode="fuel_convert_release" }
    )) {
        $active = "run{0:D2}_{1}" -f $runIndex, $spec.Label
        Write-State "running" $completed $active ""
        $reason = Invoke-Case $runIndex $spec.Label $spec.Mode
        if ($reason) { Stop-Safely $completed $active $reason }
        $completed++
    }
}

$productionAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
if ($productionBefore -ne $productionAfter) { Stop-Safely $completed "final" "production_app_hash_changed" }
Update-Report
$report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
if (-not $report.qualified) { Stop-Safely $completed "final" "qualification_report_failed" }
Write-State "qualified" $completed "complete" ""
Write-Host "Phase 6FE completed: 3/3 C0/C1 pairs qualified under lag-aware memory response"
