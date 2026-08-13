param([Parameter(Mandatory = $true)][string]$OutputRoot)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6FJ refuses artifact root reuse: $OutputRoot" }
$contractPath = Join-Path $PSScriptRoot "phase6fj_balanced_single_readback_contract.json"
$hashPath = Join-Path $PSScriptRoot "phase6fj_balanced_single_readback_contract.sha256"
$expectedHash = ((Get-Content -Encoding UTF8 $hashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($actualHash -ne $expectedHash) { throw "Phase 6FJ contract hash mismatch" }
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
$basePath = Join-Path $root $contract.base_operation_contract.path
$baseHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $basePath).Hash
if ($baseHash -ne $contract.base_operation_contract.sha256) { throw "Phase 6FJ base operation contract changed" }
$replacementPath = Join-Path $root $contract.base_replacement_contract.path
$replacementHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $replacementPath).Hash
if ($replacementHash -ne $contract.base_replacement_contract.sha256) { throw "Phase 6FJ replacement contract changed" }
$base = Get-Content -Raw -Encoding UTF8 $basePath | ConvertFrom-Json

New-Item -ItemType Directory -Path $OutputRoot | Out-Null
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
Copy-Item -LiteralPath $hashPath -Destination (Join-Path $OutputRoot "frozen_contract.sha256")
Copy-Item -LiteralPath $basePath -Destination (Join-Path $OutputRoot "frozen_phase6fg_contract.json")
Copy-Item -LiteralPath $replacementPath -Destination (Join-Path $OutputRoot "frozen_phase6fi_contract.json")

$guard = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
$caseRunner = Join-Path $PSScriptRoot "run_phase6ep_point_collision_case.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6fj_balanced_single_readback.py"
$powershell = (Get-Command powershell.exe).Source
$productionApp = Join-Path $root "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$reportPath = Join-Path $OutputRoot "balanced_single_readback_report.json"
$statePath = Join-Path $OutputRoot "incremental_state.json"
$attempted = 0
$representative = 0
$prerequisite = 0
$slotIndex = 0
$previousExitUtc = ""

$slots = @()
for ($sequence = 1; $sequence -le 3; $sequence++) {
    $position = 0
    foreach ($condition in $contract.balanced_order[$sequence - 1]) {
        $position++
        $slots += [pscustomobject]@{
            slot_id = "sequence{0:D2}_position{1:D2}_{2}" -f $sequence, $position, $condition
            sequence = $sequence
            position = $position
            condition = [string]$condition
        }
    }
}

function Write-State([string]$Status, [string]$ActiveAttempt, [string]$ActiveSlot, [string]$Classification, [string]$Reason) {
    $payload = [ordered]@{
        schema = "campfire.phase6fj.incremental-state.v1"
        phase = "phase6fj"
        status = $Status
        total_launches = $attempted
        representative_processes = $representative
        startup_prerequisite_failures = $prerequisite
        replacement_budget_used = $prerequisite
        completed_balanced_slots = $slotIndex
        active_attempt = $ActiveAttempt
        active_slot = $ActiveSlot
        active_classification = $Classification
        stop_reason = $Reason
        contract_sha256 = $actualHash
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
    }
    [IO.File]::WriteAllText($statePath, ($payload | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Update-Report {
    & python $analyzer --root $OutputRoot --contract $contractPath --base-contract $basePath --output $reportPath
    if ($LASTEXITCODE -ne 0) { throw "Phase 6FJ analyzer failed" }
}

function Assert-Production([string]$Boundary) {
    $current = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
    if ($current -ne $productionBefore) {
        Write-State "absolute_safety_stop" $Boundary "" "absolute_safety_failure" "production_app_hash_changed"
        throw "Phase 6FJ production app changed"
    }
}

while ($slotIndex -lt $slots.Count -and $attempted -lt [int]$contract.population.maximum_launches) {
    $slot = $slots[$slotIndex]
    $attempted++
    $attemptId = "attempt{0:D2}" -f $attempted
    $attemptRoot = Join-Path $OutputRoot $attemptId
    $logs = Join-Path $attemptRoot "runner-logs"
    New-Item -ItemType Directory -Path $logs | Out-Null
    $condition = [string]$slot.condition
    $conditionSpec = $contract.conditions.$condition
    $label = [string]$conditionSpec.label
    $mode = [string]$conditionSpec.readback_mode
    $caseDir = Join-Path $attemptRoot $label
    $metadata = [ordered]@{
        schema = "campfire.phase6fj.attempt-metadata.v1"
        attempt_id = $attemptId
        attempt_sequence = $attempted
        slot_id = $slot.slot_id
        sequence = $slot.sequence
        position = $slot.position
        condition = $condition
        label = $label
        readback_mode = $mode
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
    }
    [IO.File]::WriteAllText((Join-Path $attemptRoot "attempt_metadata.json"), ($metadata | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Write-State "running" $attemptId $slot.slot_id "" ""

    $source = $base.startup.expected_source_sums
    $arguments = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $caseRunner,
        "-Scenario", $base.scenario, "-OutputDir", $caseDir,
        "-OffsetM", "$($base.point_offset_m)", "-SupportRadiusM", "$($base.support_radius_m)",
        "-Filtering", "true", "-Collision", "true", "-Policy", $base.point_policy,
        "-ReportPhase", "phase6fj", "-GeometryVariant", $base.geometry_variant,
        "-FuelScale", "1", "-TemperatureScale", "1", "-SmokeScale", "1",
        "-SampleFrames", ($base.sample_frames -join ','), "-ReadbackChannels", "none",
        "-ReadbackMode", $mode, "-ReadbackFrames", "$($base.readback_frame)", "-ReferenceDisposal", "natural",
        "-SynchronousMemoryMarkers", "true", "-PythonMemoryTelemetry", "true",
        "-SpatialCollectorsEnabled", "false", "-RunIndex", "$($slot.sequence)", "-LifecycleCalibration",
        "-RendererDrainUpdates", "$($base.lifecycle.renderer_pre_close_drain_updates)",
        "-StageCloseTimeoutSeconds", "$($base.lifecycle.stage_close_timeout_seconds)",
        "-StabilityObservationStartFrame", "$($base.observation.start_frame)",
        "-StabilityObservationExtraSeconds", "$($base.observation.extra_running_flow_wall_seconds)",
        "-StabilityActiveBlockSampleSeconds", "$($base.observation.active_block_sample_seconds)",
        "-FlowLivenessAudit", "true", "-StartupProbe", "true", "-StartupProbeLabel", $attemptId,
        "-StartupFlowAcquirePosition", $base.startup.flow_acquire_position,
        "-StartupPreTimelineUpdateCount", "$($base.startup.stopped_update_count)",
        "-StartupExtraUpdateBeforePlayCount", "$($base.startup.extra_update_before_play_count)",
        "-StartupLivenessGate", "true", "-StartupExpectedFuelSum", "$($source.fuel)",
        "-StartupExpectedTemperatureSum", "$($source.temperature)", "-StartupExpectedSmokeSum", "$($source.smoke)",
        "-StartupSourceSumTolerance", "$($base.startup.source_sum_absolute_tolerance)",
        "-AbsoluteTimeoutSeconds", "$($base.lifecycle.inner_absolute_timeout_seconds)"
    )
    if (-not [string]::IsNullOrWhiteSpace($previousExitUtc)) { $arguments += @("-PreviousProcessExitUtc", $previousExitUtc) }
    $limits = $base.safety
    $guardArgs = @(
        $guard, "--trace", (Join-Path $logs "$label.resource.jsonl"),
        "--summary", (Join-Path $logs "$label.guard.json"), "--stdout", (Join-Path $logs "$label.stdout.log"),
        "--stderr", (Join-Path $logs "$label.stderr.log"), "--timeout-seconds", "$($base.lifecycle.outer_condition_timeout_seconds)",
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
    $previousExitUtc = [DateTime]::UtcNow.ToString("o")
    try { Update-Report } catch {
        Write-State "absolute_safety_stop" $attemptId $slot.slot_id "absolute_safety_failure" "analyzer_failure:$($_.Exception.Message)"
        Write-Error "Phase 6FJ analyzer failed after $attemptId"
        exit 2
    }
    Assert-Production $attemptId
    $report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
    $case = @($report.attempts | Where-Object { $_.attempt_id -eq $attemptId })[0]
    if ($null -eq $case) {
        Write-State "absolute_safety_stop" $attemptId $slot.slot_id "absolute_safety_failure" "attempt_report_missing;guard_exit=$guardExit"
        Write-Error "Phase 6FJ attempt report missing"
        exit 2
    }
    $classification = [string]$case.classification
    if ($classification -eq "representative_pass") {
        $representative++
        $slotIndex++
        Write-State "running" $attemptId $slot.slot_id $classification ""
        continue
    }
    if ($classification -eq "startup_prerequisite_failure") {
        $prerequisite++
        Write-State "running" $attemptId $slot.slot_id $classification "preserved_startup_prerequisite;guard_exit=$guardExit"
        if ($prerequisite -gt [int]$contract.population.startup_prerequisite_replacement_budget) {
            Write-State "prerequisite_population_incomplete" $attemptId $slot.slot_id $classification "startup_replacement_budget_exhausted"
            Write-Error "Phase 6FJ exhausted startup replacement budget"
            exit 2
        }
        continue
    }
    $status = switch ($classification) {
        "operation_failure" { "operation_safe_stop" }
        "native_lifecycle_failure" { "native_lifecycle_safe_stop" }
        default { "absolute_safety_stop" }
    }
    $reasons = @($case.operation_failures) + @($case.native_lifecycle_failures) + @($case.absolute_safety_failures)
    Write-State $status $attemptId $slot.slot_id $classification ($reasons -join ',')
    Write-Error "Phase 6FJ captured nonreplaceable $classification at $attemptId; later slots were not started"
    exit 2
}

Update-Report
Assert-Production "complete"
if ($slotIndex -ne $slots.Count) {
    Write-State "prerequisite_population_incomplete" "complete" "" "startup_replacement_budget_or_launch_limit_exhausted"
    Write-Error "Phase 6FJ did not complete nine representative slots"
    exit 2
}
$final = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
if (-not $final.qualified) {
    Write-State "operation_safe_stop" "complete" "" "final_qualification_report_failed"
    Write-Error "Phase 6FJ final qualification report failed"
    exit 2
}
Write-State "qualified" "complete" "complete" "representative_pass" ""
Write-Host "Phase 6FJ completed nine balanced representative processes; repeated readback remains excluded"
