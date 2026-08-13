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
$phase6fnReport = Join-Path $repo "artifacts\phase6fn-routed-settled-1\settled_three_iteration_report.json"
if (-not (Test-Path -LiteralPath $phase6fnReport)) { throw "Phase 6FO requires frozen Phase 6FN report" }
$phase6fn = Get-Content -Raw -Encoding UTF8 $phase6fnReport | ConvertFrom-Json
if (-not $phase6fn.qualified) { throw "Phase 6FN is not qualified" }

New-Item -ItemType Directory -Path $OutputRoot | Out-Null
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
Copy-Item -LiteralPath $hashPath -Destination (Join-Path $OutputRoot "frozen_contract.sha256")
Copy-Item -LiteralPath $phase6fnReport -Destination (Join-Path $OutputRoot "frozen_phase6fn_report.json")
$offlineDir = Join-Path $OutputRoot "offline"
New-Item -ItemType Directory -Path $offlineDir | Out-Null
$offlinePath = Join-Path $offlineDir "comparison.json"
$recordsPath = Join-Path $offlineDir "point_records.jsonl"
& python (Join-Path $PSScriptRoot "prepare_phase6fo_supply_comparison.py") --output $offlinePath --records $recordsPath
if ($LASTEXITCODE -ne 0) { throw "Phase 6FO offline preparation failed" }
$offline = Get-Content -Raw -Encoding UTF8 $offlinePath | ConvertFrom-Json
if (-not $offline.all_pass) { throw "Phase 6FO offline gate failed" }

$guard = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
$caseRunner = Join-Path $PSScriptRoot "run_phase6fo_supply_case.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6fo_supply_comparison.py"
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
        schema="campfire.phase6fo.incremental-state.v1"; phase="phase6fo"; status=$Status
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
        "-Filtering", "true", "-Collision", "true", "-Policy", $spec.policy,
        "-ReportPhase", "phase6fo", "-GeometryVariant", $contract.fixture.geometry_variant,
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
        "-StartupExpectedSmokeSum", "$($source.smoke)", "-StartupSourceSumTolerance", "$($contract.hard_gates.source_sum_relative_tolerance)",
        "-AbsoluteTimeoutSeconds", "$($contract.safety.inner_absolute_timeout_seconds)"
    )
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
    & python @guardArgs
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
    $metadata = [ordered]@{schema="campfire.phase6fo.attempt-metadata.v1";phase="phase6fo";attempt_id=$attemptId;condition="S93";label=$contract.conditions.S93.label;preflight=$true;timestamp_utc=[DateTime]::UtcNow.ToString("o")}
    [IO.File]::WriteAllText((Join-Path $attemptRoot "attempt_metadata.json"), ($metadata | ConvertTo-Json -Depth 6)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
    Write-State "channel_preflight_running" $attemptId "channel_preflight" "" ""
    Invoke-GuardedCase $attemptRoot $attemptId "S93" 0 $true
    Update-Report; Assert-Production $attemptId
    $report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
    $case = @($report.channel_preflight | Where-Object { $_.attempt_id -eq $attemptId })[0]
    if ($case.classification -eq "representative_pass") { $preflightComplete = $true; break }
    if ($case.classification -eq "startup_prerequisite_failure") { $startupFailures++; continue }
    Write-State "channel_preflight_safe_stop" $attemptId "channel_preflight" $case.classification ($case.failures -join ',')
    throw "Phase 6FO channel preflight failed"
}

$slots = @()
for ($sequence=1; $sequence -le 3; $sequence++) {
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
    $metadata=[ordered]@{schema="campfire.phase6fo.attempt-metadata.v1";phase="phase6fo";attempt_id=$attemptId;slot_id=$slot.slot_id;sequence=$slot.sequence;position=$slot.position;condition=$slot.condition;label=$spec.label;preflight=$false;timestamp_utc=[DateTime]::UtcNow.ToString("o")}
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
