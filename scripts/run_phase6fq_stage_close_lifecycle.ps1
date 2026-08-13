param(
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [string]$ContractPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$repo = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6FQ refuses artifact root reuse: $OutputRoot" }
$contractPath = if ([string]::IsNullOrWhiteSpace($ContractPath)) { Join-Path $PSScriptRoot "phase6fq_stage_close_lifecycle_contract.json" } else { [IO.Path]::GetFullPath($ContractPath) }
$hashPath = [IO.Path]::ChangeExtension($contractPath, ".sha256")
$expectedHash = ((Get-Content -Encoding UTF8 $hashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($actualHash -ne $expectedHash) { throw "Phase 6FQ contract hash mismatch" }
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json

New-Item -ItemType Directory -Path $OutputRoot | Out-Null
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
Copy-Item -LiteralPath $hashPath -Destination (Join-Path $OutputRoot "frozen_contract.sha256")
$productionApp = Join-Path $repo "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$guard = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
$caseRunner = Join-Path $PSScriptRoot "run_phase6fo_supply_case.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6fq_stage_close_lifecycle.py"
$powershell = (Get-Command powershell.exe).Source
$reportPath = Join-Path $OutputRoot "stage_close_lifecycle_report.json"
$statePath = Join-Path $OutputRoot "incremental_state.json"
$attempted = 0
$completedSlots = 0
$startupFailures = 0
$previousExitUtc = ""

function Write-State([string]$Status, [string]$AttemptId, [string]$SlotId, [string]$Classification, [string]$Reason) {
    $state = [ordered]@{
        schema="campfire.phase6fq.incremental-state.v1"; phase="phase6fq"; status=$Status
        launches=$attempted; completed_slots=$completedSlots; startup_prerequisite_failures=$startupFailures
        active_attempt=$AttemptId; active_slot=$SlotId; active_classification=$Classification; stop_reason=$Reason
        contract_sha256=$actualHash; production_sha256=$productionBefore; timestamp_utc=[DateTime]::UtcNow.ToString("o")
    }
    [IO.File]::WriteAllText($statePath, ($state | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Update-Report {
    & python $analyzer --root $OutputRoot --contract $contractPath --output $reportPath
    if ($LASTEXITCODE -ne 0) { throw "Phase 6FQ analyzer failed" }
}

function Assert-Production([string]$Boundary) {
    $after = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
    if ($after -ne $productionBefore) {
        Write-State "absolute_safety_stop" $Boundary "" "nonreplaceable_failure" "production_app_hash_changed"
        throw "Phase 6FQ production app hash changed"
    }
}

function Invoke-LifecycleCase([string]$AttemptRoot, [object]$Condition, [int]$RunIndex, [string]$AttemptId) {
    $caseDir = Join-Path $AttemptRoot "case"
    $logs = Join-Path $AttemptRoot "runner-logs"
    New-Item -ItemType Directory -Path $logs | Out-Null
    $collectors = if ([int]$Condition.allocation_level -ge 1) { "true" } else { "false" }
    $arguments = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $caseRunner,
        "-Scenario", $contract.physical_fixture.scenario, "-OutputDir", $caseDir,
        "-OffsetM", "$($contract.physical_fixture.point_offset_m)", "-SupportRadiusM", "$($contract.physical_fixture.support_radius_m)",
        "-Filtering", "true", "-Collision", "true", "-Policy", $contract.physical_fixture.point_policy,
        "-ReportPhase", "phase6fq", "-GeometryVariant", $contract.physical_fixture.geometry_variant,
        "-FuelScale", "1", "-TemperatureScale", "1", "-SmokeScale", "1",
        "-SampleFrames", "60,96", "-OperationFrames", "96", "-ReadbackFrames", "",
        "-ReadbackChannels", "none", "-ReadbackMode", "none", "-ReferenceDisposal", "del",
        "-SynchronousMemoryMarkers", "true", "-PythonMemoryTelemetry", "true",
        "-SpatialCollectorsEnabled", $collectors, "-SpatialColliderIndices", "2",
        "-RunIndex", "$RunIndex", "-AllocationCalibrationLevel", "$($Condition.allocation_level)",
        "-CapturePreparationMode", "$($Condition.capture_preparation_mode)",
        "-LifecycleCalibration", "-RendererDrainUpdates", "$($Condition.renderer_drain_updates)",
        "-LifecycleReferenceReleaseOrder", "$($Condition.reference_release_order)",
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
    if ([int]$Condition.allocation_level -ge 3) { $arguments += "-SpatialAllChannels" }
    if (-not [string]::IsNullOrWhiteSpace($previousExitUtc)) { $arguments += @("-PreviousProcessExitUtc", $previousExitUtc) }
    $guardArgs = @(
        $guard, "--trace", (Join-Path $logs "resource.jsonl"), "--summary", (Join-Path $logs "guard.json"),
        "--stdout", (Join-Path $logs "stdout.log"), "--stderr", (Join-Path $logs "stderr.log"),
        "--timeout-seconds", "$($contract.safety.outer_condition_timeout_seconds)",
        "--sample-seconds", "$($contract.recording.resource_sample_seconds)",
        "--runner-private-limit", "$($contract.safety.runner_private_limit_bytes)",
        "--diagnostic-private-limit", "$($contract.safety.diagnostic_private_limit_bytes)",
        "--kit-private-limit", "$($contract.safety.kit_private_limit_bytes)",
        "--tree-private-limit", "$($contract.safety.unique_tree_private_limit_bytes)",
        "--available-memory-floor", "$($contract.safety.physical_memory_floor_bytes)",
        "--commit-headroom-floor", "$($contract.safety.commit_headroom_floor_bytes)",
        "--cpu-telemetry", "--gpu-csv", (Join-Path $logs "gpu.csv"),
        "--gpu-sample-ms", "$($contract.recording.gpu_sample_ms)",
        "--lifecycle-path", (Join-Path $caseDir "raw.json"),
        "--diagnostic-marker-path", (Join-Path $caseDir "resource_markers.jsonl"),
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

while ($completedSlots -lt $slots.Count) {
    $slot = $slots[$completedSlots]
    $attempted++
    $attemptId = "attempt{0:D2}" -f $attempted
    $attemptRoot = Join-Path $OutputRoot "attempts\$attemptId"
    New-Item -ItemType Directory -Path $attemptRoot | Out-Null
    $condition = @($contract.conditions | Where-Object { $_.id -eq $slot.condition })[0]
    $metadata = [ordered]@{
        schema="campfire.phase6fq.attempt-metadata.v1"; phase="phase6fq"; attempt_id=$attemptId
        slot_id=$slot.slot_id; sequence=$slot.sequence; position=$slot.position; condition=$slot.condition
        settings=[ordered]@{
            allocation_level=[int]$condition.allocation_level
            capture_preparation_mode=[string]$condition.capture_preparation_mode
            renderer_drain_updates=[int]$condition.renderer_drain_updates
            reference_release_order=[string]$condition.reference_release_order
        }
        timestamp_utc=[DateTime]::UtcNow.ToString("o")
    }
    [IO.File]::WriteAllText((Join-Path $attemptRoot "attempt_metadata.json"), ($metadata | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Write-State "running" $attemptId $slot.slot_id "" ""
    Invoke-LifecycleCase $attemptRoot $condition $slot.sequence $attemptId
    Update-Report
    Assert-Production $attemptId
    $report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
    $case = @($report.attempts | Where-Object { $_.attempt_id -eq $attemptId })[0]
    if ($case.classification -eq "representative_pass") {
        $completedSlots++
        continue
    }
    if ($case.classification -eq "startup_prerequisite_failure") {
        $startupFailures++
        if ($startupFailures -le [int]$contract.population.startup_replacement_budget) { continue }
        Write-State "startup_safe_stop" $attemptId $slot.slot_id $case.classification "startup_replacement_budget_exhausted"
        throw "Phase 6FQ startup replacement budget exhausted"
    }
    Write-State "safe_stop" $attemptId $slot.slot_id $case.classification ($case.failures -join ',')
    throw "Phase 6FQ nonreplaceable failure: $($case.failures -join ',')"
}

Update-Report
Assert-Production "complete"
$final = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
if (-not $final.qualification_complete) {
    Write-State "safe_stop" "complete" "" "nonreplaceable_failure" "final_report_not_qualified"
    throw "Phase 6FQ lifecycle qualification did not qualify"
}
Write-State "qualified" "complete" "complete" "representative_pass" ""
Write-Host "Phase 6FQ stage-close lifecycle qualification qualified"
