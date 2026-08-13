param([Parameter(Mandatory = $true)][string]$OutputRoot)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6FI refuses artifact root reuse: $OutputRoot" }
$contractPath = Join-Path $PSScriptRoot "phase6fi_lifecycle_replacement_contract.json"
$hashPath = Join-Path $PSScriptRoot "phase6fi_lifecycle_replacement_contract.sha256"
$expectedHash = ((Get-Content -Encoding UTF8 $hashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($actualHash -ne $expectedHash) { throw "Phase 6FI contract hash mismatch" }
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
Copy-Item -LiteralPath $hashPath -Destination (Join-Path $OutputRoot "frozen_contract.sha256")
$logs = Join-Path $OutputRoot "runner-logs"
New-Item -ItemType Directory -Path $logs | Out-Null
$guard = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
$caseRunner = Join-Path $PSScriptRoot "run_phase6ep_point_collision_case.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6fi_lifecycle_replacement.py"
$powershell = (Get-Command powershell.exe).Source
$productionApp = Join-Path $root "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$statePath = Join-Path $OutputRoot "incremental_state.json"
$reportPath = Join-Path $OutputRoot "lifecycle_replacement_report.json"
$previousExitUtc = ""
$representativeCount = 0
$prerequisiteCount = 0
$attempted = 0

function Write-State([string]$Status, [string]$Active, [string]$Classification, [string]$Reason) {
    $payload = [ordered]@{
        schema = "campfire.phase6fi.incremental-state.v1"
        phase = "phase6fi"
        status = $Status
        total_launches = $attempted
        representative_startup_count = $representativeCount
        startup_prerequisite_failure_count = $prerequisiteCount
        replacement_budget_used = [Math]::Min($prerequisiteCount, [int]$contract.population.startup_prerequisite_replacement_budget)
        active_attempt = $Active
        active_classification = $Classification
        stop_reason = $Reason
        contract_sha256 = $actualHash
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
    }
    [IO.File]::WriteAllText($statePath, ($payload | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Update-Report {
    & python $analyzer --root $OutputRoot --contract $contractPath --output $reportPath
    if ($LASTEXITCODE -ne 0) { throw "Phase 6FI analyzer failed" }
}

function Assert-ProductionUnchanged([string]$Label) {
    $productionCurrent = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
    if ($productionBefore -ne $productionCurrent) {
        Write-State "absolute_safety_stop" $Label "absolute_safety_failure" "production_app_hash_changed"
        throw "Phase 6FI production app hash changed"
    }
}

$maximumLaunches = [int]$contract.population.maximum_launches
$targetRepresentative = [int]$contract.population.target_representative_processes
$replacementBudget = [int]$contract.population.startup_prerequisite_replacement_budget

for ($attempt = 1; $attempt -le $maximumLaunches; $attempt++) {
    if ($representativeCount -ge $targetRepresentative) { break }
    $label = "run{0:D2}" -f $attempt
    $attemptId = "attempt{0:D2}" -f $attempt
    $caseDir = Join-Path $OutputRoot $label
    Write-State "running" $attemptId "" ""
    $source = $contract.startup.expected_source_sums
    $condition = $contract.condition
    $window = $contract.lifecycle
    $arguments = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $caseRunner,
        "-Scenario", $condition.scenario, "-OutputDir", $caseDir,
        "-OffsetM", "$($condition.point_offset_m)", "-SupportRadiusM", "$($condition.support_radius_m)",
        "-Filtering", "true", "-Collision", "true", "-Policy", $condition.point_policy,
        "-ReportPhase", "phase6fi", "-GeometryVariant", $condition.geometry_variant,
        "-FuelScale", "1", "-TemperatureScale", "1", "-SmokeScale", "1",
        "-SampleFrames", ($condition.sample_frames -join ','), "-ReadbackChannels", "none",
        "-ReadbackMode", "none", "-ReadbackFrames", "120", "-ReferenceDisposal", "natural",
        "-SynchronousMemoryMarkers", "true", "-PythonMemoryTelemetry", "true",
        "-SpatialCollectorsEnabled", "false", "-RunIndex", "$attempt", "-LifecycleCalibration",
        "-RendererDrainUpdates", "$($window.renderer_pre_close_drain_updates)",
        "-StageCloseTimeoutSeconds", "$($window.stage_close_timeout_seconds)",
        "-StabilityObservationStartFrame", "240", "-StabilityObservationExtraSeconds", "$($condition.running_flow_observation_seconds)",
        "-StabilityActiveBlockSampleSeconds", "0.5", "-FlowLivenessAudit", "true",
        "-StartupProbe", "true", "-StartupProbeLabel", $attemptId,
        "-StartupFlowAcquirePosition", $contract.startup.flow_acquire_position,
        "-StartupPreTimelineUpdateCount", "$($contract.startup.stopped_update_count)",
        "-StartupExtraUpdateBeforePlayCount", "$($contract.startup.extra_update_before_play_count)",
        "-StartupLivenessGate", "true", "-StartupExpectedFuelSum", "$($source.fuel)",
        "-StartupExpectedTemperatureSum", "$($source.temperature)", "-StartupExpectedSmokeSum", "$($source.smoke)",
        "-StartupSourceSumTolerance", "$($contract.startup.source_sum_absolute_tolerance)",
        "-AbsoluteTimeoutSeconds", "$($window.inner_absolute_timeout_seconds)"
    )
    if (-not [string]::IsNullOrWhiteSpace($previousExitUtc)) { $arguments += @("-PreviousProcessExitUtc", $previousExitUtc) }
    $safety = $contract.safety
    $guardArgs = @(
        $guard, "--trace", (Join-Path $logs "$label.resource.jsonl"), "--summary", (Join-Path $logs "$label.guard.json"),
        "--stdout", (Join-Path $logs "$label.stdout.log"), "--stderr", (Join-Path $logs "$label.stderr.log"),
        "--timeout-seconds", "$($window.outer_condition_timeout_seconds)", "--sample-seconds", "$($safety.resource_sampling_seconds)",
        "--runner-private-limit", "$($safety.runner_private_limit_bytes)", "--diagnostic-private-limit", "$($safety.diagnostic_private_limit_bytes)",
        "--kit-private-limit", "$($safety.kit_private_limit_bytes)", "--tree-private-limit", "$($safety.unique_tree_private_limit_bytes)",
        "--available-memory-floor", "$($safety.physical_memory_floor_bytes)", "--commit-headroom-floor", "$($safety.commit_headroom_floor_bytes)",
        "--cpu-telemetry", "--gpu-csv", (Join-Path $logs "$label.gpu.csv"), "--gpu-sample-ms", "$($safety.gpu_sampling_ms)",
        "--lifecycle-path", (Join-Path $caseDir "raw.json"), "--diagnostic-marker-path", (Join-Path $caseDir "resource_markers.jsonl"),
        "--", $powershell
    ) + $arguments
    & python @guardArgs
    $guardExit = $LASTEXITCODE
    $attempted = $attempt
    Update-Report
    Assert-ProductionUnchanged $attemptId
    $report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
    $case = @($report.attempts | Where-Object { $_.attempt_sequence -eq $attempt })[0]
    if ($null -eq $case) {
        Write-State "absolute_safety_stop" $attemptId "absolute_safety_failure" "attempt_report_missing;guard_exit=$guardExit"
        Write-Error "Phase 6FI attempt report missing at $attemptId"
        exit 2
    }
    $classification = [string]$case.classification
    $previousExitUtc = [DateTime]::UtcNow.ToString("o")
    if ($classification -eq "representative_startup") {
        $representativeCount++
        Write-State "running" $attemptId $classification ""
        continue
    }
    if ($classification -eq "startup_prerequisite_failure") {
        $prerequisiteCount++
        Write-State "running" $attemptId $classification "preserved_startup_prerequisite;guard_exit=$guardExit"
        if ($prerequisiteCount -gt $replacementBudget) {
            Write-State "prerequisite_population_incomplete" $attemptId $classification "startup_replacement_budget_exceeded"
            Write-Error "Phase 6FI exhausted the startup-prerequisite replacement budget"
            exit 2
        }
        continue
    }
    $stopStatus = switch ($classification) {
        "operation_failure" { "operation_safe_stop" }
        "native_lifecycle_failure" { "native_lifecycle_safe_stop" }
        "absolute_safety_failure" { "absolute_safety_stop" }
        default { "absolute_safety_stop" }
    }
    $stopReasons = @($case.operation_failures) + @($case.native_lifecycle_failures) + @($case.absolute_safety_failures)
    Write-State $stopStatus $attemptId $classification ($stopReasons -join ',')
    Write-Error "Phase 6FI captured nonreplaceable $classification at $attemptId; later launches were not started"
    exit 2
}

Update-Report
Assert-ProductionUnchanged "complete"
if ($representativeCount -ne $targetRepresentative) {
    Write-State "prerequisite_population_incomplete" "complete" "startup_prerequisite_failure" "maximum_launches_exhausted"
    Write-Error "Phase 6FI did not collect six representative lifecycle samples"
    exit 2
}
Write-State "lifecycle_qualification_pass" "complete" "representative_startup" ""
Write-Host "Phase 6FI completed six representative readback-free lifecycle controls; Phase 6FG remains approval-gated"
