param(
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [string]$ContractPath = "",
    [ValidateSet("phase6fv", "phase6fx")][string]$Phase = "phase6fv",
    [string]$AnalyzerPath = "",
    [ValidateSet("phase6fv")][string]$CaseReportPhase = "phase6fv"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$repo = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "$Phase refuses artifact root reuse: $OutputRoot" }
$contractPath = if ([string]::IsNullOrWhiteSpace($ContractPath)) { Join-Path $PSScriptRoot "phase6fv_memory_ceiling_qualification_contract.json" } else { [IO.Path]::GetFullPath($ContractPath) }
$hashPath = [IO.Path]::ChangeExtension($contractPath, ".sha256")
$expectedHash = ((Get-Content -Encoding UTF8 $hashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($actualHash -ne $expectedHash) { throw "$Phase contract hash mismatch" }
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
if ($contract.phase -ne $Phase) { throw "$Phase contract phase mismatch" }

$runtimeFiles = [ordered]@{
    phase6fu_resource_guard_sha256 = Join-Path $PSScriptRoot "phase6fu_resource_guard.py"
    phase6fu_process_identity_sha256 = Join-Path $PSScriptRoot "phase6fu_process_identity.py"
    frozen_phase6eg_resource_guard_sha256 = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
    kit_shutdown_policy_sha256 = Join-Path $PSScriptRoot "kit_shutdown_policy.ps1"
    shared_case_runner_sha256 = Join-Path $PSScriptRoot "run_phase6fo_supply_case.ps1"
    shared_probe_sha256 = Join-Path $PSScriptRoot "probe_phase6fo_supply_comparison.py"
}
$optionalRuntimeFiles = [ordered]@{
    qualification_runner_sha256 = $PSCommandPath
    phase6fw_policy_sha256 = Join-Path $PSScriptRoot "phase6fw_pid_reuse_policy.py"
}
foreach ($entry in $optionalRuntimeFiles.GetEnumerator()) {
    if ($contract.runtime_hashes.PSObject.Properties.Name -contains $entry.Key) {
        $runtimeFiles[$entry.Key] = $entry.Value
    }
}
foreach ($entry in $runtimeFiles.GetEnumerator()) {
    $observed = (Get-FileHash -Algorithm SHA256 -LiteralPath $entry.Value).Hash
    $required = [string]$contract.runtime_hashes.($entry.Key)
    if ($observed -ne $required) { throw "$Phase runtime hash mismatch: $($entry.Key)" }
}

New-Item -ItemType Directory -Path $OutputRoot | Out-Null
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
Copy-Item -LiteralPath $hashPath -Destination (Join-Path $OutputRoot "frozen_contract.sha256")
$productionApp = Join-Path $repo "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$guard = Join-Path $PSScriptRoot "phase6fu_resource_guard.py"
$caseRunner = Join-Path $PSScriptRoot "run_phase6fo_supply_case.ps1"
$analyzer = if ([string]::IsNullOrWhiteSpace($AnalyzerPath)) { Join-Path $PSScriptRoot "analyze_phase6fv_memory_ceiling_qualification.py" } else { [IO.Path]::GetFullPath($AnalyzerPath) }
$powershell = (Get-Command powershell.exe).Source
$reportPath = Join-Path $OutputRoot "memory_ceiling_qualification_report.json"
$statePath = Join-Path $OutputRoot "incremental_state.json"
$attempted = 0
$completed = 0
$startupFailures = 0
$previousExitUtc = ""

function Write-State([string]$Status, [string]$AttemptId, [string]$SlotId, [string]$Classification, [string]$Reason) {
    $state = [ordered]@{
        schema="campfire.$Phase.incremental-state.v1"; phase=$Phase; status=$Status
        launches=$attempted; completed_representative_slots=$completed; startup_prerequisite_failures=$startupFailures
        active_attempt=$AttemptId; active_slot=$SlotId; active_classification=$Classification; stop_reason=$Reason
        legacy_14_gib_is_soft_evaluation_threshold=$true
        kit_hard_limit_bytes=[long]$contract.safety.kit_absolute_stop_bytes
        unique_tree_hard_limit_bytes=[long]$contract.safety.unique_tree_absolute_stop_bytes
        phase6ft_reclassified=$false; phase6fo_restarted=$false; production_shutdown_order_changed=$false
        contract_sha256=$actualHash; production_sha256=$productionBefore; timestamp_utc=[DateTime]::UtcNow.ToString("o")
    }
    [IO.File]::WriteAllText($statePath, ($state | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Update-Report {
    & python $analyzer --root $OutputRoot --contract $contractPath --output $reportPath
    if ($LASTEXITCODE -ne 0) { throw "Phase 6FV analyzer failed" }
}

function Assert-Production([string]$Boundary) {
    $after = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
    if ($after -ne $productionBefore) {
        Write-State "absolute_safety_stop" $Boundary "" "nonreplaceable_failure" "production_app_hash_changed"
        throw "Phase 6FV production app hash changed"
    }
}

function Invoke-MemoryCase([string]$AttemptRoot, [object]$Condition, [int]$RunIndex, [string]$AttemptId) {
    $caseDir = Join-Path $AttemptRoot "case"
    $logs = Join-Path $AttemptRoot "runner-logs"
    New-Item -ItemType Directory -Path $logs | Out-Null
    $collectors = if ($Condition.spatial_collectors_enabled) { "true" } else { "false" }
    $sampleFrames = ($Condition.sample_frames -join ',')
    $arguments = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $caseRunner,
        "-Scenario", $contract.physical_fixture.scenario, "-OutputDir", $caseDir,
        "-OffsetM", "$($contract.physical_fixture.point_offset_m)", "-SupportRadiusM", "$($contract.physical_fixture.support_radius_m)",
        "-Filtering", "true", "-Collision", "true", "-Policy", $contract.physical_fixture.point_policy,
        "-ReportPhase", $CaseReportPhase, "-GeometryVariant", $contract.physical_fixture.geometry_variant,
        "-FuelScale", "1", "-TemperatureScale", "1", "-SmokeScale", "1",
        "-SampleFrames", $sampleFrames, "-OperationFrames", "$($Condition.terminal_frame)",
        "-ReadbackChannels", "none", "-ReadbackMode", "none", "-ReferenceDisposal", "del",
        "-SynchronousMemoryMarkers", "true", "-PythonMemoryTelemetry", "true",
        "-SpatialCollectorsEnabled", $collectors, "-SpatialColliderIndices", "2",
        "-RunIndex", "$RunIndex", "-AllocationCalibrationLevel", "$($Condition.allocation_level)",
        "-CapturePreparationMode", "none",
        "-LifecycleCalibration", "-RendererDrainUpdates", "$($contract.lifecycle.renderer_drain_updates)",
        "-LifecycleReferenceReleaseOrder", $contract.lifecycle.reference_release_order,
        "-StageCloseTimeoutSeconds", "$($contract.safety.stage_close_timeout_seconds)",
        "-FlowLivenessAudit", "true", "-StartupProbe", "true", "-StartupProbeLabel", $AttemptId,
        "-StartupFlowAcquirePosition", $contract.startup.flow_acquire_position,
        "-StartupPreTimelineUpdateCount", "$($contract.startup.stopped_update_count)",
        "-StartupExtraUpdateBeforePlayCount", "$($contract.startup.extra_update_before_play_count)",
        "-StartupLivenessGate", "true",
        "-StartupExpectedFuelSum", "$($contract.physical_fixture.expected_source_sums.fuel)",
        "-StartupExpectedTemperatureSum", "$($contract.physical_fixture.expected_source_sums.temperature)",
        "-StartupExpectedSmokeSum", "$($contract.physical_fixture.expected_source_sums.smoke)",
        "-StartupSourceSumTolerance", "$($contract.physical_fixture.source_sum_absolute_tolerance)",
        "-AbsoluteTimeoutSeconds", "$($contract.safety.inner_absolute_timeout_seconds)"
    )
    if ($Condition.spatial_collectors_enabled) { $arguments += "-SpatialAllChannels" }
    if (-not [string]::IsNullOrWhiteSpace($previousExitUtc)) { $arguments += @("-PreviousProcessExitUtc", $previousExitUtc) }
    $guardArgs = @(
        $guard, "--trace", (Join-Path $logs "resource.jsonl"), "--summary", (Join-Path $logs "guard.json"),
        "--stdout", (Join-Path $logs "stdout.log"), "--stderr", (Join-Path $logs "stderr.log"),
        "--timeout-seconds", "$($contract.safety.outer_condition_timeout_seconds)",
        "--sample-seconds", "$($contract.recording.resource_sample_seconds)",
        "--runner-private-limit", "$($contract.safety.runner_private_limit_bytes)",
        "--diagnostic-private-limit", "$($contract.safety.diagnostic_private_limit_bytes)",
        "--kit-private-limit", "$($contract.safety.kit_absolute_stop_bytes)",
        "--tree-private-limit", "$($contract.safety.unique_tree_absolute_stop_bytes)",
        "--available-memory-floor", "$($contract.safety.physical_memory_floor_bytes)",
        "--commit-headroom-floor", "$($contract.safety.commit_headroom_floor_bytes)",
        "--cpu-telemetry", "--gpu-csv", (Join-Path $logs "gpu.csv"),
        "--gpu-sample-ms", "$($contract.recording.gpu_sample_ms)",
        "--lifecycle-path", (Join-Path $caseDir "raw.json"),
        "--diagnostic-marker-path", (Join-Path $caseDir "resource_markers.jsonl"),
        "--attempt-id", $AttemptId,
        "--cleanup-suppression-lock", ((Join-Path $caseDir "sensitive-shutdown-diagnostics") + ".ownership.json"),
        "--cleanup-suppression-deadline-seconds", "$($contract.identity_cleanup.cleanup_suppression_deadline_seconds)",
        "--cleanup-marker-path", (Join-Path $logs "cleanup_markers.jsonl"),
        "--", $powershell
    ) + $arguments
    & python @guardArgs
    $script:previousExitUtc = [DateTime]::UtcNow.ToString("o")
}

$slots = @()
for ($sequence = 1; $sequence -le $contract.population.orders.Count; $sequence++) {
    $position = 0
    foreach ($conditionId in $contract.population.orders[$sequence - 1]) {
        $position++
        $slots += [pscustomobject]@{
            sequence=$sequence; position=$position; condition=[string]$conditionId
            slot_id=("sequence{0:D2}_position{1:D2}_{2}" -f $sequence, $position, $conditionId)
        }
    }
}

while ($completed -lt $slots.Count) {
    $slot = $slots[$completed]
    $attempted++
    $attemptId = "attempt{0:D2}" -f $attempted
    $attemptRoot = Join-Path $OutputRoot "attempts\$attemptId"
    New-Item -ItemType Directory -Path $attemptRoot | Out-Null
    $condition = @($contract.conditions | Where-Object { $_.id -eq $slot.condition })[0]
    $metadata = [ordered]@{
        schema="campfire.$Phase.attempt-metadata.v1"; phase=$Phase; attempt_id=$attemptId
        slot_id=$slot.slot_id; sequence=$slot.sequence; position=$slot.position; condition=$slot.condition
        run_index=$slot.sequence
        settings=[ordered]@{
            allocation_level=[int]$condition.allocation_level; terminal_frame=[int]$condition.terminal_frame
            reference_release_order="after_stage_close"; readback_calls=0; capture_calls=0
        }
        previous_process_exit_utc=$previousExitUtc; timestamp_utc=[DateTime]::UtcNow.ToString("o")
    }
    [IO.File]::WriteAllText((Join-Path $attemptRoot "attempt_metadata.json"), ($metadata | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Write-State "running" $attemptId $slot.slot_id "" ""
    Invoke-MemoryCase $attemptRoot $condition $slot.sequence $attemptId
    Update-Report
    Assert-Production $attemptId
    $report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
    $case = @($report.attempts | Where-Object { $_.attempt_id -eq $attemptId })[0]
    if ($case.classification -eq "representative_pass") {
        $completed++
        continue
    }
    if ($case.classification -eq "startup_prerequisite_failure") {
        $startupFailures++
        if ($startupFailures -le [int]$contract.startup.startup_replacement_budget) { continue }
        Write-State "startup_safe_stop" $attemptId $slot.slot_id $case.classification "startup_replacement_budget_exhausted"
        throw "$Phase startup replacement budget exhausted"
    }
    Write-State "safe_stop" $attemptId $slot.slot_id $case.classification ($case.failures -join ',')
    throw "$Phase nonreplaceable failure: $($case.failures -join ',')"
}

Update-Report
Assert-Production "complete"
$final = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
if (-not $final.qualification_complete -or -not $final.candidate_16_gib_qualified -or -not $final.candidate_17_gib_tree_qualified) {
    Write-State "safe_stop" "complete" "" "nonreplaceable_failure" "final_report_not_qualified"
    throw "$Phase memory ceiling qualification did not qualify"
}
Write-State "qualified" "complete" "complete" "representative_pass" ""
Write-Host "$Phase memory ceiling qualification completed; Phase 6FO remains stopped"
