param(
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [string]$ContractPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$repo = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6FO refuses artifact root reuse: $OutputRoot" }
$contractPath = if ([string]::IsNullOrWhiteSpace($ContractPath)) { Join-Path $PSScriptRoot "phase6fo_supply_comparison_contract.json" } else { [IO.Path]::GetFullPath($ContractPath) }
$hashPath = [IO.Path]::ChangeExtension($contractPath, ".sha256")
$expectedHash = ((Get-Content -Encoding UTF8 $hashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($actualHash -ne $expectedHash) { throw "Phase 6FO contract hash mismatch" }
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
$phase = if ($contract.phase) { [string]$contract.phase } else { "phase6fo" }
if ($phase -notin @("phase6fo", "phase6ga", "phase6gb", "phase6gc")) { throw "Unsupported supply comparison phase: $phase" }
$isGuardedPhase = $phase -in @("phase6ga", "phase6gb", "phase6gc")
$geometryConcept = ""
$geometryRuntimeToken = ""
if ($phase -in @("phase6gb", "phase6gc")) {
    $geometryConcept = [string]$contract.fixture.geometry.concept
    $geometryRuntimeToken = [string]$contract.fixture.geometry.runtime_token
    if ($geometryConcept -ne "corrected" -or $geometryRuntimeToken -ne "phase6er_corrected") {
        throw "Phase 6GB corrected geometry mapping is invalid."
    }
    if ($geometryRuntimeToken -eq [string]$contract.fixture.geometry.legacy_runtime_token) {
        throw "Phase 6GB corrected geometry was misrouted to legacy_phase6ep."
    }
} else {
    $geometryRuntimeToken = [string]$contract.fixture.geometry_variant
}
$phase6fnReport = Join-Path $repo "artifacts\phase6fn-routed-settled-1\settled_three_iteration_report.json"
if (-not (Test-Path -LiteralPath $phase6fnReport)) { throw "Phase 6FO requires frozen Phase 6FN report" }
$phase6fn = Get-Content -Raw -Encoding UTF8 $phase6fnReport | ConvertFrom-Json
if (-not $phase6fn.qualified) { throw "Phase 6FN is not qualified" }

New-Item -ItemType Directory -Path $OutputRoot | Out-Null
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
Copy-Item -LiteralPath $hashPath -Destination (Join-Path $OutputRoot "frozen_contract.sha256")
Copy-Item -LiteralPath $phase6fnReport -Destination (Join-Path $OutputRoot "frozen_phase6fn_report.json")
$runtimeManifest = [ordered]@{}
foreach ($name in @("run_phase6fo_supply_case.ps1","run_phase6gb_parameter_binding_fixtures.ps1","run_phase6gc_source_contract_fixtures.py","phase6gc_payload_native_source.py","probe_phase6fo_supply_comparison.py","probe_phase6ga_supply_comparison.py","probe_phase6gb_supply_comparison.py","probe_phase6gc_supply_comparison.py","probe_phase6gc_shared_supply_comparison.py","phase6fu_resource_guard.py","phase6fu_process_identity.py","phase6fw_pid_reuse_policy.py","phase6fz_preclose_committer.py","phase6fz_import_contract.py","kit_shutdown_policy.ps1")) {
    $path = Join-Path $PSScriptRoot $name
    if (Test-Path -LiteralPath $path) { $runtimeManifest[$name] = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash }
}
[IO.File]::WriteAllText((Join-Path $OutputRoot "runtime_hashes.json"), ($runtimeManifest | ConvertTo-Json -Depth 4) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
if($isGuardedPhase) {
    $preflightRoot = Join-Path $OutputRoot "safety-preflight"
    if ($phase -eq "phase6gc") {
        & python (Join-Path $PSScriptRoot "run_phase6gc_source_contract_fixtures.py") --output (Join-Path $preflightRoot "source-contract-fixtures")
        if ($LASTEXITCODE -ne 0) { throw "Phase 6GC source-contract fixture failed" }
        $sourceFixture = Get-Content -Raw -Encoding UTF8 (Join-Path $preflightRoot "source-contract-fixtures\source_contract_fixture_report.json") | ConvertFrom-Json
        if (-not $sourceFixture.passed -or $sourceFixture.case_count -ne 16) { throw "Phase 6GC source-contract fixture did not pass 16/16" }
    }
    if ($phase -in @("phase6gb", "phase6gc")) {
        & (Join-Path $PSScriptRoot "run_phase6gb_parameter_binding_fixtures.ps1") -OutputRoot (Join-Path $preflightRoot "parameter-binding-fixtures") -ContractPath $contractPath -ProbePath (Join-Path $PSScriptRoot "probe_phase6gb_supply_comparison.py")
        $binding = Get-Content -Raw -Encoding UTF8 (Join-Path $preflightRoot "parameter-binding-fixtures\parameter_binding_fixture_report.json") | ConvertFrom-Json
        if (-not $binding.passed -or -not $binding.no_kit_launch -or $binding.results.Count -ne 4) { throw "Phase 6GB parameter-binding fixture failed" }
    }
    & (Join-Path $PSScriptRoot "run_phase6fz_import_smoke.ps1") -OutputRoot (Join-Path $preflightRoot "app-ready-import-smoke")
    $smoke = Get-Content -Raw -Encoding UTF8 (Join-Path $preflightRoot "app-ready-import-smoke\import_smoke_suite.json") | ConvertFrom-Json
    if(-not $smoke.passed -or $smoke.completed_count -ne 3){throw "Phase 6GA app-ready import smoke failed"}
    & (Join-Path $PSScriptRoot "run_phase6fz_cdb_progress_fixtures.ps1") -OutputRoot (Join-Path $preflightRoot "cdb-progress-fixtures")
    $cdb = Get-Content -Raw -Encoding UTF8 (Join-Path $preflightRoot "cdb-progress-fixtures\cdb_progress_fixture_report.json") | ConvertFrom-Json
    if(-not $cdb.passed -or $cdb.residual.cdb -ne 0){throw "Phase 6GA CDB progress fixture failed"}
}
$offlineDir = Join-Path $OutputRoot "offline"
New-Item -ItemType Directory -Path $offlineDir | Out-Null
$offlinePath = Join-Path $offlineDir "comparison.json"
$recordsPath = Join-Path $offlineDir "point_records.jsonl"
& python (Join-Path $PSScriptRoot "prepare_phase6fo_supply_comparison.py") --output $offlinePath --records $recordsPath
if ($LASTEXITCODE -ne 0) { throw "Phase 6FO offline preparation failed" }
$offline = Get-Content -Raw -Encoding UTF8 $offlinePath | ConvertFrom-Json
if (-not $offline.all_pass) { throw "Phase 6FO offline gate failed" }

$guard = Join-Path $PSScriptRoot $(if($isGuardedPhase){"phase6fu_resource_guard.py"}else{"phase6eg_resource_guard.py"})
$caseRunner = Join-Path $PSScriptRoot "run_phase6fo_supply_case.ps1"
$analyzer = Join-Path $PSScriptRoot $(if($isGuardedPhase){"analyze_phase6ga_supply_comparison.py"}else{"analyze_phase6fo_supply_comparison.py"})
$probe = Join-Path $PSScriptRoot $(if($phase -eq "phase6gc"){"probe_phase6gc_supply_comparison.py"}elseif($phase -eq "phase6gb"){"probe_phase6gb_supply_comparison.py"}elseif($phase -eq "phase6ga"){"probe_phase6ga_supply_comparison.py"}else{"probe_phase6fo_supply_comparison.py"})
$committer = Join-Path $PSScriptRoot "phase6fz_preclose_committer.py"
$powershell = (Get-Command powershell.exe).Source
$productionApp = Join-Path $repo "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$reportPath = Join-Path $OutputRoot "supply_comparison_report.json"
$statePath = Join-Path $OutputRoot "incremental_state.json"
$attempted = 0
$formalAttempted = 0
$representative = 0
$startupFailures = 0
$completedSlots = 0
$previousExitUtc = ""

function Write-State([string]$Status, [string]$ActiveAttempt, [string]$ActiveSlot, [string]$Classification, [string]$Reason) {
    $value = [ordered]@{
        schema="campfire.$phase.incremental-state.v1"; phase=$phase; status=$Status
        total_launches=$attempted; formal_launches=$formalAttempted; representative_processes=$representative
        startup_prerequisite_failures=$startupFailures; completed_formal_slots=$completedSlots
        active_attempt=$ActiveAttempt; active_slot=$ActiveSlot; active_classification=$Classification
        stop_reason=$Reason; contract_sha256=$actualHash; production_sha256=$productionBefore
        timestamp_utc=[DateTime]::UtcNow.ToString("o")
    }
    [IO.File]::WriteAllText($statePath, ($value | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}
function Update-Report {
    & python $analyzer --root $OutputRoot --contract $contractPath --offline $offlinePath --output $reportPath
    if ($LASTEXITCODE -ne 0) { throw "Phase 6FO analyzer failed" }
}
function Assert-Production([string]$Boundary) {
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash -ne $productionBefore) {
        Write-State "absolute_safety_stop" $Boundary "" "absolute_safety_failure" "production_app_hash_changed"
        throw "Phase 6FO production app changed"
    }
}
function Invoke-GuardedCase([string]$AttemptRoot, [string]$AttemptId, [string]$Condition, [int]$RunIndex, [bool]$Preflight) {
    $spec = $contract.conditions.$Condition
    $label = [string]$spec.label
    $caseDir = Join-Path $AttemptRoot $label
    $logs = Join-Path $AttemptRoot "runner-logs"
    New-Item -ItemType Directory -Path $logs | Out-Null
    $sampleFrames = if ($Preflight) { "60,120,180,240" } else { $contract.sample_frames -join ',' }
    $operationFrames = if ($Preflight) { "180" } else { $contract.readback_frames -join ',' }
    $readbackFrames = $operationFrames
    $colliders = if ($Preflight) { $contract.channel_preflight.representative_collider_indices -join ',' } else { $contract.spatial.all_collider_indices -join ',' }
    $source = $spec.expected_source_sums
    $arguments = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $caseRunner,
        "-Scenario", $contract.fixture.scenario, "-OutputDir", $caseDir,
        "-OffsetM", "$($contract.fixture.point_offset_m)", "-SupportRadiusM", "$($contract.fixture.support_radius_assumption_m)",
        "-Filtering", "true", "-Collision", $(if($spec.collision_enabled -eq $false){"false"}else{"true"}), "-Policy", $spec.policy,
        "-ReportPhase", $phase, "-GeometryVariant", $geometryRuntimeToken,
        "-ProbePath", $probe,
        "-FuelScale", "1", "-TemperatureScale", "1", "-SmokeScale", "1",
        "-SampleFrames", $sampleFrames, "-OperationFrames", $operationFrames, "-ReadbackFrames", $readbackFrames,
        "-ReadbackChannels", ($contract.spatial.required_channels -join ','), "-ReadbackMode", "p3_spatial_release",
        "-ReferenceDisposal", "del", "-SynchronousMemoryMarkers", "true", "-PythonMemoryTelemetry", "true",
        "-SpatialCollectorsEnabled", "true", "-SpatialColliderIndices", $colliders, "-SpatialAllChannels",
        "-RunIndex", "$RunIndex", "-LifecycleCalibration", "-RendererDrainUpdates", "8",
        "-StageCloseTimeoutSeconds", "$($contract.safety.stage_close_timeout_seconds)",
        "-StabilityObservationStartFrame", $(if($Preflight){"240"}else{"600"}),
        "-StabilityObservationExtraSeconds", "5", "-StabilityActiveBlockSampleSeconds", "0.5",
        "-FlowLivenessAudit", "true", "-StartupProbe", "true", "-StartupProbeLabel", $AttemptId,
        "-StartupFlowAcquirePosition", "before_updates", "-StartupPreTimelineUpdateCount", "12",
        "-StartupExtraUpdateBeforePlayCount", "0", "-StartupLivenessGate", "true",
        "-StartupExpectedFuelSum", "$($source.fuel)", "-StartupExpectedTemperatureSum", "$($source.temperature)",
        "-StartupExpectedSmokeSum", "$($source.smoke)", "-StartupSourceSumTolerance", "$($contract.channel_preflight.startup_source_sum_absolute_tolerance)",
        "-StartupSourceContractMode", $(if($phase -eq "phase6gc"){[string]$contract.source_contract.mode}else{"decimal_legacy"}),
        "-AbsoluteTimeoutSeconds", "$($contract.safety.inner_absolute_timeout_seconds)"
    )
    if($phase -in @("phase6gb", "phase6gc")) { $arguments += @("-ExpectedGeometryConcept", $geometryConcept) }
    if($isGuardedPhase) {
        $arguments += @(
            "-ImportAuditPath", (Join-Path $caseDir "kit_import_audit.json"),
            "-MeasurementCommitAck", (Join-Path $caseDir "memory-measurement\measurement_commit.ack"),
            "-MeasurementCommitFailure", (Join-Path $caseDir "memory-measurement\measurement_commit.failed"),
            "-MeasurementCommitTimeoutSeconds", "$($contract.artifact_commit.probe_wait_timeout_seconds)"
        )
    }
    if (-not [string]::IsNullOrWhiteSpace($previousExitUtc)) { $arguments += @("-PreviousProcessExitUtc", $previousExitUtc) }
    $limits = $contract.safety
    $guardArgs = @(
        $guard, "--trace", (Join-Path $logs "$label.resource.jsonl"), "--summary", (Join-Path $logs "$label.guard.json"),
        "--stdout", (Join-Path $logs "$label.stdout.log"), "--stderr", (Join-Path $logs "$label.stderr.log"),
        "--timeout-seconds", "$($limits.outer_condition_timeout_seconds)", "--sample-seconds", "$($limits.resource_sampling_seconds)",
        "--runner-private-limit", "$($limits.runner_private_limit_bytes)", "--diagnostic-private-limit", "$($limits.diagnostic_private_limit_bytes)",
        "--kit-private-limit", "$($limits.kit_private_limit_bytes)", "--tree-private-limit", "$($limits.unique_tree_private_limit_bytes)",
        "--available-memory-floor", "$($limits.physical_memory_floor_bytes)", "--commit-headroom-floor", "$($limits.commit_headroom_floor_bytes)",
        "--cpu-telemetry", "--gpu-csv", (Join-Path $logs "$label.gpu.csv"), "--gpu-sample-ms", "$($limits.gpu_sampling_ms)",
        "--lifecycle-path", (Join-Path $caseDir "raw.json"), "--diagnostic-marker-path", (Join-Path $caseDir "resource_markers.jsonl"),
        "--", $powershell
    ) + $arguments
    if($isGuardedPhase) {
        $separator = [Array]::IndexOf($guardArgs, "--")
        $prefix = @($guardArgs[0..($separator-1)]) + @(
            "--attempt-id", $AttemptId,
            "--cleanup-suppression-lock", ((Join-Path $caseDir "sensitive-shutdown-diagnostics") + ".ownership.json"),
            "--cleanup-suppression-deadline-seconds", "150",
            "--cleanup-marker-path", (Join-Path $logs "cleanup_markers.jsonl")
        )
        $guardArgs = $prefix + @($guardArgs[$separator..($guardArgs.Count-1)])
        $guardProcess = Start-Process -FilePath python -ArgumentList $guardArgs -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs "$label.guard-launcher.stdout.log") -RedirectStandardError (Join-Path $logs "$label.guard-launcher.stderr.log")
        $committerArgs = @(
            $committer, "--raw-path", (Join-Path $caseDir "raw.json"), "--resource-path", (Join-Path $logs "$label.resource.jsonl"),
            "--gpu-path", (Join-Path $logs "$label.gpu.csv"), "--marker-path", (Join-Path $caseDir "resource_markers.jsonl"),
            "--attempt-metadata", (Join-Path $AttemptRoot "attempt_metadata.json"), "--contract", $contractPath,
            "--output-dir", (Join-Path $caseDir "memory-measurement"), "--stop-file", (Join-Path $AttemptRoot "committer.stop"),
            "--timeout-seconds", "$($contract.artifact_commit.helper_timeout_seconds)", "--private-limit-bytes", "$($contract.artifact_commit.helper_private_limit_bytes)"
        )
        $committerProcess = Start-Process -FilePath python -ArgumentList $committerArgs -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs "$label.committer.stdout.log") -RedirectStandardError (Join-Path $logs "$label.committer.stderr.log")
        $guardProcess.WaitForExit()
        [IO.File]::WriteAllText((Join-Path $AttemptRoot "committer.stop"), "guard-exited`n", [Text.UTF8Encoding]::new($false))
        if(-not $committerProcess.WaitForExit(15000)){Stop-Process -Id $committerProcess.Id -Force -ErrorAction SilentlyContinue;throw "Phase 6GA committer did not exit"}
    } else { & python @guardArgs }
    $script:previousExitUtc = [DateTime]::UtcNow.ToString("o")
}

# Channel qualification is evidence-only and is never reused as a formal S93 sample.
$preflightComplete = $false
while (-not $preflightComplete) {
    if ($startupFailures -gt [int]$contract.formal_population.startup_prerequisite_replacement_budget) { throw "Phase 6FO startup replacement budget exhausted in channel preflight" }
    $attempted++
    $attemptId = "channel_attempt{0:D2}" -f $attempted
    $attemptRoot = Join-Path $OutputRoot "channel-preflight\$attemptId"
    New-Item -ItemType Directory -Path $attemptRoot | Out-Null
    $metadata = [ordered]@{schema="campfire.$phase.attempt-metadata.v1";phase=$phase;attempt_id=$attemptId;condition="S93";label=$contract.conditions.S93.label;preflight=$true;timestamp_utc=[DateTime]::UtcNow.ToString("o")}
    [IO.File]::WriteAllText((Join-Path $attemptRoot "attempt_metadata.json"), ($metadata | ConvertTo-Json -Depth 6)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
    Write-State "channel_preflight_running" $attemptId "channel_preflight" "" ""
    Invoke-GuardedCase $attemptRoot $attemptId "S93" 0 $true
    Update-Report; Assert-Production $attemptId
    $report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
    $matchingCases = @($report.channel_preflight | Where-Object { $_.attempt_id -eq $attemptId })
    if ($matchingCases.Count -ne 1) {
        Write-State "channel_preflight_safe_stop" $attemptId "channel_preflight" "harness_failure" "preflight_report_missing_or_ambiguous"
        throw "Phase 6FO channel preflight report is missing or ambiguous"
    }
    $case = $matchingCases[0]
    if ($case.classification -eq "representative_pass") { $preflightComplete = $true; break }
    if ($case.classification -eq "startup_prerequisite_failure") { $startupFailures++; continue }
    Write-State "channel_preflight_safe_stop" $attemptId "channel_preflight" $case.classification ($case.failures -join ',')
    throw "Phase 6FO channel preflight failed"
}

$slots = @()
for ($sequence=1; $sequence -le $contract.formal_population.balanced_order.Count; $sequence++) {
    $position=0
    foreach($condition in $contract.formal_population.balanced_order[$sequence-1]) {
        $position++
        $slots += [pscustomobject]@{sequence=$sequence;position=$position;condition=[string]$condition;slot_id=("sequence{0:D2}_position{1:D2}_{2}" -f $sequence,$position,$condition)}
    }
}
while ($completedSlots -lt $slots.Count -and $formalAttempted -lt [int]$contract.formal_population.maximum_formal_launches) {
    $slot=$slots[$completedSlots]; $attempted++; $formalAttempted++
    $attemptId="attempt{0:D2}" -f $formalAttempted
    $attemptRoot=Join-Path $OutputRoot "formal\$attemptId"
    New-Item -ItemType Directory -Path $attemptRoot | Out-Null
    $spec=$contract.conditions.($slot.condition)
    $metadata=[ordered]@{schema="campfire.$phase.attempt-metadata.v1";phase=$phase;attempt_id=$attemptId;slot_id=$slot.slot_id;sequence=$slot.sequence;position=$slot.position;condition=$slot.condition;label=$spec.label;preflight=$false;timestamp_utc=[DateTime]::UtcNow.ToString("o")}
    [IO.File]::WriteAllText((Join-Path $attemptRoot "attempt_metadata.json"),($metadata|ConvertTo-Json -Depth 6)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
    Write-State "formal_running" $attemptId $slot.slot_id "" ""
    Invoke-GuardedCase $attemptRoot $attemptId $slot.condition $slot.sequence $false
    Update-Report; Assert-Production $attemptId
    $report=Get-Content -Raw -Encoding UTF8 $reportPath|ConvertFrom-Json
    $case=@($report.attempts|Where-Object{$_.attempt_id -eq $attemptId})[0]
    if($case.classification -eq "representative_pass") {
        $representative++;$completedSlots++
        $failedPair=@($report.pairs|Where-Object{$_.sequence -eq $slot.sequence -and -not $_.pass})
        if($failedPair.Count -gt 0){Write-State "numeric_safe_stop" $attemptId $slot.slot_id "operation_failure" ($failedPair[0].failures -join ',');throw "Phase 6FO pair gate failed"}
        continue
    }
    if($case.classification -eq "startup_prerequisite_failure") {
        $startupFailures++
        if($startupFailures -gt [int]$contract.formal_population.startup_prerequisite_replacement_budget){Write-State "startup_population_incomplete" $attemptId $slot.slot_id $case.classification "replacement_budget_exhausted";throw "Phase 6FO startup budget exhausted"}
        continue
    }
    Write-State "numeric_safe_stop" $attemptId $slot.slot_id $case.classification ($case.failures -join ',')
    throw "Phase 6FO captured nonreplaceable failure"
}

Update-Report; Assert-Production "numeric_complete"
$final=Get-Content -Raw -Encoding UTF8 $reportPath|ConvertFrom-Json
if(-not $final.numeric_qualified){Write-State "numeric_safe_stop" "complete" "" "operation_failure" "final_numeric_report_failed";throw "Phase 6FO numeric comparison did not qualify"}
Write-State "numeric_qualified" "complete" "complete" "representative_pass" ""
Write-Host "Phase 6FO numeric comparison qualified; visual capture is a separate post-gate step"
