param(
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [Parameter(Mandatory = $true)][string]$CalibrationReport
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
$CalibrationReport = [IO.Path]::GetFullPath($CalibrationReport)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6FG refuses artifact root reuse: $OutputRoot" }
$contractPath = Join-Path $PSScriptRoot "phase6fg_paired_readback_contract.json"
$hashPath = Join-Path $PSScriptRoot "phase6fg_paired_readback_contract.sha256"
$expectedHash = ((Get-Content -Encoding UTF8 $hashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($actualHash -ne $expectedHash) { throw "Phase 6FG contract hash mismatch" }
if (-not (Test-Path -LiteralPath $CalibrationReport)) { throw "Phase 6FG calibration report missing" }
$calibration = Get-Content -Raw -Encoding UTF8 $CalibrationReport | ConvertFrom-Json
if ($calibration.status -ne "pass" -or $calibration.contract_sha256 -ne $actualHash) { throw "Phase 6FG calibration mismatch" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
Copy-Item -LiteralPath $hashPath -Destination (Join-Path $OutputRoot "frozen_contract.sha256")
Copy-Item -LiteralPath $CalibrationReport -Destination (Join-Path $OutputRoot "synthetic_calibration.json")
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
$limits = $contract.safety
$window = $contract.observation
$startup = $contract.startup
$source = $startup.expected_source_sums
$guard = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
$caseRunner = Join-Path $PSScriptRoot "run_phase6ep_point_collision_case.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6fg_paired_readback.py"
$powershell = (Get-Command powershell.exe).Source
$productionApp = Join-Path $root "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$reportPath = Join-Path $OutputRoot "paired_readback_report.json"
$statePath = Join-Path $OutputRoot "incremental_state.json"

function Write-State([string]$Status, [int]$Completed, [string]$Active, [string]$Reason) {
    $payload = [ordered]@{
        schema="campfire.phase6fg.incremental-state.v1"; phase="phase6fg"; status=$Status
        completed_conditions=$Completed; active_condition=$Active; stop_reason=$Reason
        contract_sha256=$actualHash; timestamp_utc=[DateTime]::UtcNow.ToString("o")
    }
    [IO.File]::WriteAllText($statePath, ($payload | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Update-Report {
    & python $analyzer --root $OutputRoot --contract $contractPath --output $reportPath
    if ($LASTEXITCODE -ne 0) { throw "Phase 6FG analyzer failed" }
}

function Stop-Safely([int]$Completed, [string]$Active, [string]$Reason) {
    Write-State "safe_stop" $Completed $Active $Reason
    try { Update-Report } catch { Write-Warning $_ }
    Write-Error "Phase 6FG safe stop at ${Active}: $Reason"
    exit 2
}

function Invoke-Case([int]$Sequence, [string]$Condition) {
    $sequenceName = "sequence{0:D2}" -f $Sequence
    $groupRoot = Join-Path $OutputRoot $sequenceName
    $logs = Join-Path $groupRoot "runner-logs"
    New-Item -ItemType Directory -Force -Path $logs | Out-Null
    $label = switch ($Condition) {
        "A_control" { "R0_none" }
        "B_readback" { "C0_acquire_discard" }
        "C_fuel_alias" { "C1_fuel_alias" }
    }
    $mode = switch ($Condition) {
        "A_control" { "none" }
        "B_readback" { "acquire_discard_release" }
        "C_fuel_alias" { "fuel_convert_release" }
    }
    $caseDir = Join-Path $groupRoot $label
    $arguments = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $caseRunner,
        "-Scenario", "production_four", "-OutputDir", $caseDir,
        "-OffsetM", "-0.0125", "-SupportRadiusM", "0.05", "-Filtering", "true",
        "-Collision", "true", "-Policy", "allow_self_center", "-ReportPhase", "phase6fg",
        "-GeometryVariant", "phase6er_corrected", "-FuelScale", "1", "-TemperatureScale", "1", "-SmokeScale", "1",
        "-SampleFrames", ($contract.sample_frames -join ','), "-ReadbackChannels", "none",
        "-ReadbackMode", $mode, "-ReadbackFrames", "$($contract.readback_frame)", "-ReferenceDisposal", "natural",
        "-SynchronousMemoryMarkers", "true", "-PythonMemoryTelemetry", "true",
        "-SpatialCollectorsEnabled", "false", "-RunIndex", "$Sequence", "-LifecycleCalibration",
        "-RendererDrainUpdates", "$($contract.lifecycle.renderer_pre_close_drain_updates)",
        "-StageCloseTimeoutSeconds", "$($contract.lifecycle.stage_close_timeout_seconds)",
        "-StabilityObservationStartFrame", "$($window.start_frame)",
        "-StabilityObservationExtraSeconds", "$($window.extra_running_flow_wall_seconds)",
        "-StabilityActiveBlockSampleSeconds", "$($window.active_block_sample_seconds)",
        "-FlowLivenessAudit", "true", "-StartupProbe", "true", "-StartupProbeLabel", "${sequenceName}_${Condition}",
        "-StartupFlowAcquirePosition", "$($startup.flow_acquire_position)",
        "-StartupPreTimelineUpdateCount", "$($startup.stopped_update_count)",
        "-StartupExtraUpdateBeforePlayCount", "$($startup.extra_update_before_play_count)",
        "-StartupLivenessGate", "true", "-StartupExpectedFuelSum", "$($source.fuel)",
        "-StartupExpectedTemperatureSum", "$($source.temperature)", "-StartupExpectedSmokeSum", "$($source.smoke)",
        "-StartupSourceSumTolerance", "$($startup.source_sum_absolute_tolerance)",
        "-AbsoluteTimeoutSeconds", "$($contract.lifecycle.inner_absolute_timeout_seconds)"
    )
    $guardArgs = @(
        $guard, "--trace", (Join-Path $logs "$label.resource.jsonl"),
        "--summary", (Join-Path $logs "$label.guard.json"), "--stdout", (Join-Path $logs "$label.stdout.log"),
        "--stderr", (Join-Path $logs "$label.stderr.log"), "--timeout-seconds", "$($contract.lifecycle.outer_condition_timeout_seconds)",
        "--sample-seconds", "$($limits.resource_sampling_seconds)", "--runner-private-limit", "$($limits.runner_private_limit_bytes)",
        "--diagnostic-private-limit", "$($limits.diagnostic_private_limit_bytes)", "--kit-private-limit", "$($limits.kit_private_limit_bytes)",
        "--tree-private-limit", "$($limits.unique_tree_private_limit_bytes)", "--available-memory-floor", "$($limits.physical_memory_floor_bytes)",
        "--commit-headroom-floor", "$($limits.commit_headroom_floor_bytes)", "--cpu-telemetry",
        "--gpu-csv", (Join-Path $logs "$label.gpu.csv"), "--gpu-sample-ms", "$($limits.gpu_sampling_ms)",
        "--lifecycle-path", (Join-Path $caseDir "raw.json"), "--diagnostic-marker-path", (Join-Path $caseDir "resource_markers.jsonl"),
        "--", $powershell
    ) + $arguments
    & python @guardArgs
    $guardExit = $LASTEXITCODE
    $guardPath = Join-Path $logs "$label.guard.json"
    if (-not (Test-Path -LiteralPath $guardPath)) { return "resource_guard_summary_missing" }
    try { Update-Report } catch { return "analyzer_failure:$($_.Exception.Message)" }
    $guardResult = Get-Content -Raw -Encoding UTF8 $guardPath | ConvertFrom-Json
    if ($guardExit -ne 0 -or $guardResult.status -ne "ok" -or $guardResult.exit_code -ne 0 -or -not $guardResult.process_absent) {
        return "resource_or_lifecycle:$($guardResult.stop_reason)"
    }
    $report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
    $key = "${sequenceName}_${Condition}"
    $case = $report.cases.PSObject.Properties[$key].Value
    if (-not $case.condition_gate_pass) { return "hard_or_operation_gate:$($case.condition_gate_failures -join ',')" }
    return $null
}

$completed = 0
for ($sequence = 1; $sequence -le 3; $sequence++) {
    $order = $contract.balanced_order[$sequence - 1]
    foreach ($condition in $order) {
        $active = "sequence{0:D2}_{1}" -f $sequence, $condition
        Write-State "running" $completed $active ""
        $reason = Invoke-Case $sequence $condition
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
Write-Host "Phase 6FG completed: balanced single readback/fuel alias qualified; repeated readback remains excluded"
