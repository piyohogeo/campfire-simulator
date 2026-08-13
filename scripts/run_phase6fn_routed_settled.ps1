param(
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [string]$ContractPath = "",
    [Parameter(Mandatory = $true)][string]$PreflightManifest
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6FN refuses artifact root reuse: $OutputRoot" }
$contractPath = if ([string]::IsNullOrWhiteSpace($ContractPath)) {
    Join-Path $PSScriptRoot "phase6fn_routed_settled_contract.json"
} else { [IO.Path]::GetFullPath($ContractPath) }
$hashPath = [IO.Path]::ChangeExtension($contractPath, ".sha256")
$expectedHash = ((Get-Content -Encoding UTF8 $hashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($actualHash -ne $expectedHash) { throw "Phase 6FN contract hash mismatch" }
$preflightPath = [IO.Path]::GetFullPath($PreflightManifest)
$preflight = Get-Content -Raw -Encoding UTF8 $preflightPath | ConvertFrom-Json
if ($preflight.schema -ne "campfire.phase6fn.e2e-preflight.v1" -or -not $preflight.all_pass) {
    throw "Phase 6FN end-to-end preflight did not pass"
}
if ([string]$preflight.contract_sha256 -ne $actualHash) { throw "Phase 6FN preflight contract hash mismatch" }
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
foreach ($item in $contract.runtime_implementation) {
    $path = Join-Path $root ([string]$item.path)
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash -ne [string]$item.sha256) {
        throw "Phase 6FN runtime implementation hash changed: $($item.path)"
    }
}
$basePath = Join-Path $root $contract.base_operation_contract.path
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $basePath).Hash -ne $contract.base_operation_contract.sha256) {
    throw "Phase 6FN base operation contract changed"
}
$base = Get-Content -Raw -Encoding UTF8 $basePath | ConvertFrom-Json

New-Item -ItemType Directory -Path $OutputRoot | Out-Null
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
Copy-Item -LiteralPath $hashPath -Destination (Join-Path $OutputRoot "frozen_contract.sha256")
Copy-Item -LiteralPath $basePath -Destination (Join-Path $OutputRoot "frozen_phase6fg_contract.json")
Copy-Item -LiteralPath $preflightPath -Destination (Join-Path $OutputRoot "verified_preflight_manifest.json")
$guard = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
$caseRunner = Join-Path $PSScriptRoot "run_phase6ep_point_collision_case.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6fn_routed_settled.py"
$powershell = (Get-Command powershell.exe).Source
$productionApp = Join-Path $root "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$reportPath = Join-Path $OutputRoot "settled_three_iteration_report.json"
$statePath = Join-Path $OutputRoot "incremental_state.json"
$attempted = 0; $representative = 0; $prerequisite = 0; $slotIndex = 0; $previousExitUtc = ""
$slots = @()
for ($sequence = 1; $sequence -le 3; $sequence++) {
    $position = 0
    foreach ($condition in $contract.balanced_order[$sequence - 1]) {
        $position++
        $slots += [pscustomobject]@{
            slot_id = "sequence{0:D2}_position{1:D2}_{2}" -f $sequence, $position, $condition
            sequence = $sequence; position = $position; condition = [string]$condition
        }
    }
}

function Write-State([string]$Status, [string]$ActiveAttempt, [string]$ActiveSlot, [string]$Classification, [string]$Reason) {
    $payload = [ordered]@{
        schema = "campfire.phase6fn.incremental-state.v1"; phase = "phase6fn"; status = $Status
        total_launches = $attempted; representative_processes = $representative
        startup_prerequisite_failures = $prerequisite; replacement_budget_used = $prerequisite
        completed_balanced_slots = $slotIndex; active_attempt = $ActiveAttempt; active_slot = $ActiveSlot
        active_classification = $Classification; stop_reason = $Reason; contract_sha256 = $actualHash
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
    }
    [IO.File]::WriteAllText($statePath, ($payload | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}
function Update-Report {
    & python $analyzer --root $OutputRoot --contract $contractPath --base-contract $basePath --output $reportPath
    if ($LASTEXITCODE -ne 0) { throw "Phase 6FN analyzer failed" }
}
function Assert-Production([string]$Boundary) {
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash -ne $productionBefore) {
        Write-State "absolute_safety_stop" $Boundary "" "absolute_safety_failure" "production_app_hash_changed"
        throw "Phase 6FN production app changed"
    }
}

while ($slotIndex -lt $slots.Count -and $attempted -lt [int]$contract.population.maximum_launches) {
    $slot = $slots[$slotIndex]; $attempted++; $attemptId = "attempt{0:D2}" -f $attempted
    $attemptRoot = Join-Path $OutputRoot $attemptId; $logs = Join-Path $attemptRoot "runner-logs"
    New-Item -ItemType Directory -Path $logs | Out-Null
    $condition = [string]$slot.condition; $spec = $contract.conditions.$condition
    $label = [string]$spec.label; $mode = [string]$spec.readback_mode; $caseDir = Join-Path $attemptRoot $label
    $metadata = [ordered]@{
        schema = "campfire.phase6fn.attempt-metadata.v1"; phase = "phase6fn"; attempt_id = $attemptId
        attempt_sequence = $attempted; slot_id = $slot.slot_id; sequence = $slot.sequence
        position = $slot.position; condition = $condition; label = $label; readback_mode = $mode
        operation_frames = @($contract.operation_frames); settling_end_frames = @($contract.settling_end_frames)
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
    }
    [IO.File]::WriteAllText((Join-Path $attemptRoot "attempt_metadata.json"), ($metadata | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Write-State "running" $attemptId $slot.slot_id "" ""
    $source = $base.startup.expected_source_sums
    $frameCsv = $contract.sample_frames -join ','; $operationFrameCsv = $contract.operation_frames -join ','
    $settlingEndCsv = $contract.settling_end_frames -join ','
    $readbackCsv = if ($mode -eq "none") { "" } else { $operationFrameCsv }
    $arguments = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $caseRunner,
        "-Scenario", $base.scenario, "-OutputDir", $caseDir, "-OffsetM", "$($base.point_offset_m)",
        "-SupportRadiusM", "$($base.support_radius_m)", "-Filtering", "true", "-Collision", "true",
        "-Policy", $base.point_policy, "-ReportPhase", $contract.embedded_probe_report_phase, "-GeometryVariant", $base.geometry_variant,
        "-FuelScale", "1", "-TemperatureScale", "1", "-SmokeScale", "1",
        "-SampleFrames", $frameCsv, "-OperationFrames", $operationFrameCsv, "-SettlingEndFrames", $settlingEndCsv,
        "-ReadbackChannels", "none", "-ReadbackMode", $mode, "-ReferenceDisposal", "natural",
        "-SynchronousMemoryMarkers", "true", "-PythonMemoryTelemetry", "true", "-SpatialCollectorsEnabled", "false",
        "-RunIndex", "$($slot.sequence)", "-LifecycleCalibration",
        "-RendererDrainUpdates", "$($base.lifecycle.renderer_pre_close_drain_updates)",
        "-StageCloseTimeoutSeconds", "$($base.lifecycle.stage_close_timeout_seconds)",
        "-StabilityObservationStartFrame", "$($contract.sample_frames[-1])",
        "-StabilityObservationExtraSeconds", "$($contract.settling.final_extra_running_flow_seconds)",
        "-StabilityActiveBlockSampleSeconds", "$($contract.settling.active_block_sample_seconds)",
        "-FlowLivenessAudit", "true", "-StartupProbe", "true", "-StartupProbeLabel", $attemptId,
        "-StartupFlowAcquirePosition", $base.startup.flow_acquire_position,
        "-StartupPreTimelineUpdateCount", "$($base.startup.stopped_update_count)",
        "-StartupExtraUpdateBeforePlayCount", "$($base.startup.extra_update_before_play_count)",
        "-StartupLivenessGate", "true", "-StartupExpectedFuelSum", "$($source.fuel)",
        "-StartupExpectedTemperatureSum", "$($source.temperature)", "-StartupExpectedSmokeSum", "$($source.smoke)",
        "-StartupSourceSumTolerance", "$($base.startup.source_sum_absolute_tolerance)",
        "-AbsoluteTimeoutSeconds", "$($base.lifecycle.inner_absolute_timeout_seconds)"
    )
    if (-not [string]::IsNullOrWhiteSpace($readbackCsv)) { $arguments += @("-ReadbackFrames", $readbackCsv) }
    if (-not [string]::IsNullOrWhiteSpace($previousExitUtc)) { $arguments += @("-PreviousProcessExitUtc", $previousExitUtc) }
    $limits = $base.safety
    $guardArgs = @(
        $guard, "--trace", (Join-Path $logs "$label.resource.jsonl"), "--summary", (Join-Path $logs "$label.guard.json"),
        "--stdout", (Join-Path $logs "$label.stdout.log"), "--stderr", (Join-Path $logs "$label.stderr.log"),
        "--timeout-seconds", "$($base.lifecycle.outer_condition_timeout_seconds)", "--sample-seconds", "$($limits.resource_sampling_seconds)",
        "--runner-private-limit", "$($limits.runner_private_limit_bytes)", "--diagnostic-private-limit", "$($limits.diagnostic_private_limit_bytes)",
        "--kit-private-limit", "$($limits.kit_private_limit_bytes)", "--tree-private-limit", "$($limits.unique_tree_private_limit_bytes)",
        "--available-memory-floor", "$($limits.physical_memory_floor_bytes)", "--commit-headroom-floor", "$($limits.commit_headroom_floor_bytes)",
        "--cpu-telemetry", "--gpu-csv", (Join-Path $logs "$label.gpu.csv"), "--gpu-sample-ms", "$($limits.gpu_sampling_ms)",
        "--lifecycle-path", (Join-Path $caseDir "raw.json"), "--diagnostic-marker-path", (Join-Path $caseDir "resource_markers.jsonl"),
        "--", $powershell
    ) + $arguments
    & python @guardArgs
    $guardExit = $LASTEXITCODE; $previousExitUtc = [DateTime]::UtcNow.ToString("o")
    try { Update-Report } catch {
        Write-State "absolute_safety_stop" $attemptId $slot.slot_id "absolute_safety_failure" "analyzer_failure:$($_.Exception.Message)"
        Write-Error "Phase 6FN analyzer failed after $attemptId"; exit 2
    }
    Assert-Production $attemptId
    $report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
    $case = @($report.attempts | Where-Object { $_.attempt_id -eq $attemptId })[0]
    if ($null -eq $case) { Write-State "absolute_safety_stop" $attemptId $slot.slot_id "absolute_safety_failure" "attempt_report_missing"; exit 2 }
    $classification = [string]$case.classification
    if ($classification -eq "representative_pass") {
        if (@($report.replicated_settled_failures).Count -gt 0) {
            $reason = [string]$report.replicated_settled_failures[0].failure
            Write-State "operation_safe_stop" $attemptId $slot.slot_id "operation_failure" $reason
            Write-Error "Phase 6FN captured replicated settled accumulation failure; later slots were not started"; exit 2
        }
        $representative++; $slotIndex++; Write-State "running" $attemptId $slot.slot_id $classification ""; continue
    }
    if ($classification -eq "startup_prerequisite_failure") {
        $prerequisite++; Write-State "running" $attemptId $slot.slot_id $classification "preserved_startup_prerequisite;guard_exit=$guardExit"
        if ($prerequisite -gt [int]$contract.population.startup_prerequisite_replacement_budget) {
            Write-State "prerequisite_population_incomplete" $attemptId $slot.slot_id $classification "startup_replacement_budget_exhausted"; exit 2
        }
        continue
    }
    $status = if ($classification -eq "operation_failure") { "operation_safe_stop" } elseif ($classification -eq "native_lifecycle_failure") { "native_lifecycle_safe_stop" } elseif ($classification -eq "cleanup_failure") { "cleanup_safe_stop" } else { "absolute_safety_stop" }
    $reasons = @($case.layers.PSObject.Properties.Value | ForEach-Object { @($_.failures) })
    Write-State $status $attemptId $slot.slot_id $classification ($reasons -join ',')
    Write-Error "Phase 6FN captured nonreplaceable $classification at $attemptId; later slots were not started"; exit 2
}

Update-Report; Assert-Production "complete"
if ($slotIndex -ne $slots.Count) { Write-State "prerequisite_population_incomplete" "complete" "" "population_incomplete"; exit 2 }
$final = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
if (-not $final.qualified) { Write-State "operation_safe_stop" "complete" "" "final_qualification_report_failed"; exit 2 }
Write-State "qualified" "complete" "complete" "representative_pass" ""
Write-Host "Phase 6FN completed nine representative settled-baseline processes; iteration count above three remains excluded"
