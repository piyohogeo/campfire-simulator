param(
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [string]$ContractPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$repo = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6FR refuses artifact root reuse: $OutputRoot" }
$contractPath = if ([string]::IsNullOrWhiteSpace($ContractPath)) { Join-Path $PSScriptRoot "phase6fr_stage_close_native_lifecycle_contract.json" } else { [IO.Path]::GetFullPath($ContractPath) }
$hashPath = [IO.Path]::ChangeExtension($contractPath, ".sha256")
$expectedHash = ((Get-Content -Encoding UTF8 $hashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($actualHash -ne $expectedHash) { throw "Phase 6FR contract hash mismatch" }
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json

New-Item -ItemType Directory -Path $OutputRoot | Out-Null
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
Copy-Item -LiteralPath $hashPath -Destination (Join-Path $OutputRoot "frozen_contract.sha256")
$productionApp = Join-Path $repo "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$powershell = (Get-Command powershell.exe).Source
$policy = Join-Path $PSScriptRoot "kit_shutdown_policy.ps1"
. $policy

# No Kit process may start until the stoppable CDB fixtures have proved stack,
# timeout, detach, target survival, and cleanup behavior end-to-end.
$fixtureScript = Join-Path $PSScriptRoot "run_phase6fr_cdb_stack_first_fixtures.ps1"
$fixtureRoot = Join-Path $OutputRoot "cdb-fixture"
$fixtureGuard = Invoke-Phase6EaGuardedHelper -FilePath $powershell -ArgumentList @(
    "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
    "-File", $fixtureScript, "-OutputRoot", $fixtureRoot
) -StdoutPath (Join-Path $OutputRoot "cdb-fixture.stdout.log") -StderrPath (Join-Path $OutputRoot "cdb-fixture.stderr.log") -TimeoutSeconds 300 -PrivateBytesLimit 512MB -MaximumStdoutBytes 2MB -MaximumStderrBytes 2MB
$fixtureReport = if (Test-Path -LiteralPath (Join-Path $fixtureRoot "report.json")) { Read-CampfireBoundedJson -Path (Join-Path $fixtureRoot "report.json") } else { $null }
$fixturePassed = $fixtureGuard.exit_code -eq 0 -and -not $fixtureGuard.timed_out -and -not $fixtureGuard.private_bytes_exceeded -and -not $fixtureGuard.output_bytes_exceeded -and $fixtureGuard.process_absent -and $null -ne $fixtureReport -and $fixtureReport.status -eq "pass" -and $fixtureReport.process_remainder.cdb -eq 0
[IO.File]::WriteAllText((Join-Path $OutputRoot "cdb_fixture_gate.json"), (([ordered]@{ schema="campfire.phase6fr.cdb-fixture-gate.v1"; passed=$fixturePassed; guard=$fixtureGuard; report=$fixtureReport } | ConvertTo-Json -Depth 40) + [Environment]::NewLine), [Text.UTF8Encoding]::new($false))
if (-not $fixturePassed) { throw "Phase 6FR CDB fixture gate failed; Kit was not started" }

$guard = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
$caseRunner = Join-Path $PSScriptRoot "run_phase6fo_supply_case.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6fr_stage_close_native_lifecycle.py"
$reportPath = Join-Path $OutputRoot "stage_close_native_lifecycle_report.json"
$statePath = Join-Path $OutputRoot "incremental_state.json"
$attempted = 0
$completedSlots = 0
$startupFailures = 0
$previousExitUtc = ""
$runCounts = @{ A_release_before_close=0; B_release_after_close=0 }

function Write-State([string]$Status, [string]$AttemptId, [string]$SlotId, [string]$Classification, [string]$Reason) {
    $state = [ordered]@{
        schema="campfire.phase6fr.incremental-state.v1"; phase="phase6fr"; status=$Status
        launches=$attempted; completed_slots=$completedSlots; startup_prerequisite_failures=$startupFailures
        active_attempt=$AttemptId; active_slot=$SlotId; active_classification=$Classification; stop_reason=$Reason
        cdb_fixture_passed=$fixturePassed; phase6fo_restarted=$false
        contract_sha256=$actualHash; production_sha256=$productionBefore; timestamp_utc=[DateTime]::UtcNow.ToString("o")
    }
    [IO.File]::WriteAllText($statePath, ($state | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Update-Report {
    & python $analyzer --root $OutputRoot --contract $contractPath --output $reportPath
    if ($LASTEXITCODE -ne 0) { throw "Phase 6FR analyzer failed" }
}

function Assert-Production([string]$Boundary) {
    $after = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
    if ($after -ne $productionBefore) {
        Write-State "absolute_safety_stop" $Boundary "" "nonreplaceable_failure" "production_app_hash_changed"
        throw "Phase 6FR production app hash changed"
    }
}

function Invoke-LifecycleCase([string]$AttemptRoot, [object]$Condition, [int]$RunIndex, [string]$AttemptId) {
    $caseDir = Join-Path $AttemptRoot "case"
    $logs = Join-Path $AttemptRoot "runner-logs"
    New-Item -ItemType Directory -Path $logs | Out-Null
    $arguments = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $caseRunner,
        "-Scenario", $contract.physical_fixture.scenario, "-OutputDir", $caseDir,
        "-OffsetM", "$($contract.physical_fixture.point_offset_m)", "-SupportRadiusM", "$($contract.physical_fixture.support_radius_m)",
        "-Filtering", "true", "-Collision", "true", "-Policy", $contract.physical_fixture.point_policy,
        "-ReportPhase", "phase6fr", "-GeometryVariant", $contract.physical_fixture.geometry_variant,
        "-FuelScale", "1", "-TemperatureScale", "1", "-SmokeScale", "1",
        "-SampleFrames", "60,96", "-OperationFrames", "96",
        "-ReadbackChannels", "none", "-ReadbackMode", "none", "-ReferenceDisposal", "del",
        "-SynchronousMemoryMarkers", "true", "-PythonMemoryTelemetry", "true",
        "-SpatialCollectorsEnabled", "true", "-SpatialColliderIndices", "2", "-SpatialAllChannels",
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
    if (-not [string]::IsNullOrWhiteSpace($previousExitUtc)) { $arguments += @("-PreviousProcessExitUtc", $previousExitUtc) }
    $guardArgs = @(
        $guard, "--trace", (Join-Path $logs "resource.jsonl"), "--summary", (Join-Path $logs "guard.json"),
        "--stdout", (Join-Path $logs "stdout.log"), "--stderr", (Join-Path $logs "stderr.log"),
        "--timeout-seconds", "$($contract.safety.outer_condition_timeout_seconds)",
        "--sample-seconds", "0.2", "--runner-private-limit", "$($contract.safety.runner_private_limit_bytes)",
        "--diagnostic-private-limit", "$($contract.safety.diagnostic_private_limit_bytes)",
        "--kit-private-limit", "$($contract.safety.kit_private_limit_bytes)",
        "--tree-private-limit", "$($contract.safety.unique_tree_private_limit_bytes)",
        "--available-memory-floor", "$($contract.safety.physical_memory_floor_bytes)",
        "--commit-headroom-floor", "$($contract.safety.commit_headroom_floor_bytes)",
        "--cpu-telemetry", "--gpu-csv", (Join-Path $logs "gpu.csv"), "--gpu-sample-ms", "1000",
        "--lifecycle-path", (Join-Path $caseDir "raw.json"), "--diagnostic-marker-path", (Join-Path $caseDir "resource_markers.jsonl"),
        "--", $powershell
    ) + $arguments
    & python @guardArgs
    $script:previousExitUtc = [DateTime]::UtcNow.ToString("o")
}

$slots = @($contract.population.order)
while ($completedSlots -lt $slots.Count) {
    $conditionId = [string]$slots[$completedSlots]
    $attempted++
    $attemptId = "attempt{0:D2}" -f $attempted
    $runCounts[$conditionId] = 1 + [int]$runCounts[$conditionId]
    $runIndex = [int]$runCounts[$conditionId]
    $slotId = "slot{0:D2}_{1}_run{2:D2}" -f ($completedSlots + 1), $conditionId, $runIndex
    $attemptRoot = Join-Path $OutputRoot "attempts\$attemptId"
    New-Item -ItemType Directory -Path $attemptRoot | Out-Null
    $condition = @($contract.conditions | Where-Object { $_.id -eq $conditionId })[0]
    $metadata = [ordered]@{
        schema="campfire.phase6fr.attempt-metadata.v1"; phase="phase6fr"; attempt_id=$attemptId
        slot_id=$slotId; sequence=($completedSlots + 1); position=($completedSlots + 1); condition=$conditionId; run_index=$runIndex
        settings=[ordered]@{ allocation_level=[int]$condition.allocation_level; capture_preparation_mode=[string]$condition.capture_preparation_mode; renderer_drain_updates=[int]$condition.renderer_drain_updates; reference_release_order=[string]$condition.reference_release_order }
        timestamp_utc=[DateTime]::UtcNow.ToString("o")
    }
    [IO.File]::WriteAllText((Join-Path $attemptRoot "attempt_metadata.json"), ($metadata | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Write-State "running" $attemptId $slotId "" ""
    Invoke-LifecycleCase $attemptRoot $condition $runIndex $attemptId
    Update-Report
    Assert-Production $attemptId
    $report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
    $case = @($report.attempts | Where-Object { $_.attempt_id -eq $attemptId })[0]
    if ($case.classification -eq "representative_pass") { $completedSlots++; continue }
    if ($case.classification -eq "startup_prerequisite_failure") {
        $startupFailures++
        if ($startupFailures -le [int]$contract.population.startup_replacement_budget) { continue }
        Write-State "startup_safe_stop" $attemptId $slotId $case.classification "startup_replacement_budget_exhausted"
        throw "Phase 6FR startup replacement budget exhausted"
    }
    Write-State "safe_stop" $attemptId $slotId $case.classification ($case.failures -join ',')
    throw "Phase 6FR nonreplaceable failure: $($case.failures -join ',')"
}

Update-Report
Assert-Production "complete"
$final = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
if (-not $final.qualification_complete) {
    Write-State "safe_stop" "complete" "" "nonreplaceable_failure" "final_report_not_qualified"
    throw "Phase 6FR lifecycle qualification did not qualify"
}
Write-State "qualified" "complete" "complete" "representative_pass" ""
Write-Host "Phase 6FR stage-close native lifecycle qualification completed; Phase 6FO remains stopped"
