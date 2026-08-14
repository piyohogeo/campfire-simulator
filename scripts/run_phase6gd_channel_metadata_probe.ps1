param(
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [string]$DiscoveryContractPath = "",
    [ValidateSet("baseline", "divergence", "rgba", "rgb")][string]$Control = "baseline",
    [string]$ControlContractPath = "",
    [string]$DiagnosticResourceContractPath = "",
    [ValidateSet("phase6gd", "phase6ge", "phase6gf")][string]$ReportPhase = "phase6gd"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0

$repo = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6GD refuses artifact root reuse: $OutputRoot" }

$discoveryContractPath = if ([string]::IsNullOrWhiteSpace($DiscoveryContractPath)) {
    Join-Path $PSScriptRoot "phase6gd_channel_schema_discovery_contract.json"
} else { [IO.Path]::GetFullPath($DiscoveryContractPath) }
$discoveryHashPath = [IO.Path]::ChangeExtension($discoveryContractPath, ".sha256")
$expectedDiscoveryHash = ((Get-Content -Encoding UTF8 $discoveryHashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
$actualDiscoveryHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $discoveryContractPath).Hash
if ($actualDiscoveryHash -ne $expectedDiscoveryHash) { throw "Phase 6GD discovery contract hash mismatch" }
$discovery = Get-Content -Raw -Encoding UTF8 $discoveryContractPath | ConvertFrom-Json

$controlContract = $null
$controlContractHash = $null
if ($Control -ne "baseline") {
    $controlContractPath = if ([string]::IsNullOrWhiteSpace($ControlContractPath)) {
        Join-Path $PSScriptRoot "phase6gd_channel_schema_control_contract.json"
    } else { [IO.Path]::GetFullPath($ControlContractPath) }
    $controlHashPath = [IO.Path]::ChangeExtension($controlContractPath, ".sha256")
    $expectedControlHash = ((Get-Content -Encoding UTF8 $controlHashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
    $controlContractHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $controlContractPath).Hash
    if ($controlContractHash -ne $expectedControlHash) { throw "Phase 6GD control contract hash mismatch" }
    $controlContract = Get-Content -Raw -Encoding UTF8 $controlContractPath | ConvertFrom-Json
    if ($Control -notin @($controlContract.controls.order)) { throw "Phase 6GD control is not frozen by the control contract" }
}

$baseContractPath = Join-Path $repo ([string]$discovery.base_physics_contract.path)
$baseHashPath = [IO.Path]::ChangeExtension($baseContractPath, ".sha256")
$expectedBaseHash = [string]$discovery.base_physics_contract.sha256
$actualBaseHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $baseContractPath).Hash
if ($actualBaseHash -ne $expectedBaseHash) { throw "Phase 6GD frozen Phase 6GC base contract changed" }
if (((Get-Content -Encoding UTF8 $baseHashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant() -ne $actualBaseHash) {
    throw "Phase 6GD frozen Phase 6GC sidecar mismatch"
}
$base = Get-Content -Raw -Encoding UTF8 $baseContractPath | ConvertFrom-Json

$diagnosticResourceContract = $null
$diagnosticResourceContractHash = $null
$limits = $base.safety
$sampleFrames = "60,120,180,240"
$stabilityObservationStartFrame = 240
$stabilityObservationExtraSeconds = 5
if (-not [string]::IsNullOrWhiteSpace($DiagnosticResourceContractPath)) {
    $diagnosticResourceContractPath = [IO.Path]::GetFullPath($DiagnosticResourceContractPath)
    $diagnosticHashPath = [IO.Path]::ChangeExtension($diagnosticResourceContractPath, ".sha256")
    $expectedDiagnosticHash = ((Get-Content -Encoding UTF8 $diagnosticHashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
    $diagnosticResourceContractHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $diagnosticResourceContractPath).Hash
    if ($diagnosticResourceContractHash -ne $expectedDiagnosticHash) { throw "Phase 6GE diagnostic resource contract hash mismatch" }
    $diagnosticResourceContract = Get-Content -Raw -Encoding UTF8 $diagnosticResourceContractPath | ConvertFrom-Json
    $expectedDiagnosticSchema = "campfire.$ReportPhase.color-slot-diagnostic-contract.v1"
    if ($ReportPhase -notin @("phase6ge", "phase6gf") -or
        $diagnosticResourceContract.schema -ne $expectedDiagnosticSchema -or
        $diagnosticResourceContract.phase -ne $ReportPhase -or
        -not $diagnosticResourceContract.diagnostic_resource_limits.temporary_only -or
        $diagnosticResourceContract.diagnostic_resource_limits.may_replace_phase6fz_or_formal_limits) {
        throw "Phase 6GE diagnostic resource contract scope is invalid"
    }
    $resource = $diagnosticResourceContract.diagnostic_resource_limits
    $expectedResources = @{
        kit_private_limit_bytes = 21474836480
        unique_tree_private_limit_bytes = 22548578304
        runner_private_limit_bytes = 536870912
        diagnostic_private_limit_bytes = 536870912
        physical_memory_floor_bytes = 34359738368
        commit_headroom_floor_bytes = 34359738368
    }
    foreach ($name in $expectedResources.Keys) {
        if ([int64]$resource.$name -ne [int64]$expectedResources[$name]) {
            throw "Phase 6GE diagnostic resource value mismatch: $name"
        }
    }
    $limits = [pscustomobject]@{
        runner_private_limit_bytes = [int64]$resource.runner_private_limit_bytes
        diagnostic_private_limit_bytes = [int64]$resource.diagnostic_private_limit_bytes
        kit_private_limit_bytes = [int64]$resource.kit_private_limit_bytes
        unique_tree_private_limit_bytes = [int64]$resource.unique_tree_private_limit_bytes
        physical_memory_floor_bytes = [int64]$resource.physical_memory_floor_bytes
        commit_headroom_floor_bytes = [int64]$resource.commit_headroom_floor_bytes
        outer_condition_timeout_seconds = [int]$base.safety.outer_condition_timeout_seconds
        resource_sampling_seconds = [double]$base.safety.resource_sampling_seconds
        gpu_sampling_ms = [int]$base.safety.gpu_sampling_ms
        stage_close_timeout_seconds = [int]$base.safety.stage_close_timeout_seconds
        inner_absolute_timeout_seconds = [int]$base.safety.inner_absolute_timeout_seconds
    }
    $sampleFrames = "60,120,180"
    $stabilityObservationStartFrame = 180
    $stabilityObservationExtraSeconds = 0
}

New-Item -ItemType Directory -Path $OutputRoot | Out-Null
Copy-Item -LiteralPath $discoveryContractPath -Destination (Join-Path $OutputRoot "frozen_discovery_contract.json")
Copy-Item -LiteralPath $discoveryHashPath -Destination (Join-Path $OutputRoot "frozen_discovery_contract.sha256")
Copy-Item -LiteralPath $baseContractPath -Destination (Join-Path $OutputRoot "frozen_phase6gc_contract.json")
Copy-Item -LiteralPath $baseHashPath -Destination (Join-Path $OutputRoot "frozen_phase6gc_contract.sha256")
if ($null -ne $controlContract) {
    Copy-Item -LiteralPath $controlContractPath -Destination (Join-Path $OutputRoot "frozen_control_contract.json")
    Copy-Item -LiteralPath $controlHashPath -Destination (Join-Path $OutputRoot "frozen_control_contract.sha256")
}
if ($null -ne $diagnosticResourceContract) {
    Copy-Item -LiteralPath $diagnosticResourceContractPath -Destination (Join-Path $OutputRoot "frozen_diagnostic_resource_contract.json")
    Copy-Item -LiteralPath ([IO.Path]::ChangeExtension($diagnosticResourceContractPath, ".sha256")) -Destination (Join-Path $OutputRoot "frozen_diagnostic_resource_contract.sha256")
}

$productionApp = Join-Path $repo "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$attemptId = "metadata_$Control`_attempt01"
$attemptRoot = Join-Path $OutputRoot $attemptId
$caseDir = Join-Path $attemptRoot "S93_support_clear"
$logs = Join-Path $attemptRoot "runner-logs"
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$attemptMetadata = [ordered]@{
    schema = "campfire.phase6gd.attempt-metadata.v1"
    phase = $ReportPhase
    attempt_id = $attemptId
    condition = "S93"
    discovery_only = $true
    formal_population = $false
    channel_schema_control = $Control
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
}
[IO.File]::WriteAllText((Join-Path $attemptRoot "attempt_metadata.json"), ($attemptMetadata | ConvertTo-Json -Depth 6) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))

$runtimeManifest = [ordered]@{}
foreach ($name in @(
    "run_phase6fo_supply_case.ps1", "probe_phase6gd_channel_metadata.py",
    "probe_phase6gc_shared_supply_comparison.py", "phase6gc_payload_native_source.py",
    "phase6fu_resource_guard.py", "phase6fu_process_identity.py", "phase6fw_pid_reuse_policy.py",
    "phase6fz_preclose_committer.py", "phase6fz_import_contract.py", "kit_shutdown_policy.ps1"
)) {
    $path = Join-Path $PSScriptRoot $name
    $runtimeManifest[$name] = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash
}
[IO.File]::WriteAllText((Join-Path $OutputRoot "runtime_hashes.json"), ($runtimeManifest | ConvertTo-Json -Depth 4) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))

$caseRunner = Join-Path $PSScriptRoot "run_phase6fo_supply_case.ps1"
$probe = Join-Path $PSScriptRoot "probe_phase6gd_channel_metadata.py"
$guard = Join-Path $PSScriptRoot "phase6fu_resource_guard.py"
$committer = Join-Path $PSScriptRoot "phase6fz_preclose_committer.py"
$powershell = (Get-Command powershell.exe).Source
$source = $base.conditions.S93.expected_source_sums
$arguments = @(
    "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $caseRunner,
    "-Scenario", $base.fixture.scenario, "-OutputDir", $caseDir,
    "-OffsetM", "$($base.fixture.point_offset_m)", "-SupportRadiusM", "$($base.fixture.support_radius_assumption_m)",
    "-Filtering", "true", "-Collision", "true", "-Policy", $base.conditions.S93.policy,
    "-ReportPhase", $ReportPhase, "-GeometryVariant", $base.fixture.geometry.runtime_token,
    "-ExpectedGeometryConcept", $base.fixture.geometry.concept, "-ProbePath", $probe,
    "-FuelScale", "1", "-TemperatureScale", "1", "-SmokeScale", "1",
    "-SampleFrames", $sampleFrames, "-OperationFrames", "180", "-ReadbackFrames", "180",
    "-ReadbackChannels", "temperature", "-ReadbackMode", "p3_spatial_release",
    "-ReferenceDisposal", "del", "-SynchronousMemoryMarkers", "true", "-PythonMemoryTelemetry", "true",
    "-SpatialCollectorsEnabled", "true", "-SpatialColliderIndices", "2", "-SpatialAllChannels",
    "-RunIndex", "0", "-LifecycleCalibration", "-RendererDrainUpdates", "8",
    "-LifecycleReferenceReleaseOrder", "after_stage_close",
    "-StageCloseTimeoutSeconds", "$($limits.stage_close_timeout_seconds)",
    "-StabilityObservationStartFrame", "$stabilityObservationStartFrame", "-StabilityObservationExtraSeconds", "$stabilityObservationExtraSeconds",
    "-StabilityActiveBlockSampleSeconds", "0.5", "-FlowLivenessAudit", "true",
    "-StartupProbe", "true", "-StartupProbeLabel", $attemptId,
    "-StartupFlowAcquirePosition", "before_updates", "-StartupPreTimelineUpdateCount", "12",
    "-StartupExtraUpdateBeforePlayCount", "0", "-StartupLivenessGate", "true",
    "-StartupExpectedFuelSum", "$($source.fuel)", "-StartupExpectedTemperatureSum", "$($source.temperature)",
    "-StartupExpectedSmokeSum", "$($source.smoke)",
    "-StartupSourceSumTolerance", "$($base.channel_preflight.startup_source_sum_absolute_tolerance)",
    "-StartupSourceContractMode", $base.source_contract.mode,
    "-ChannelSchemaControl", $Control,
    "-AbsoluteTimeoutSeconds", "$($limits.inner_absolute_timeout_seconds)",
    "-ImportAuditPath", (Join-Path $caseDir "kit_import_audit.json"),
    "-MeasurementCommitAck", (Join-Path $caseDir "memory-measurement\measurement_commit.ack"),
    "-MeasurementCommitFailure", (Join-Path $caseDir "memory-measurement\measurement_commit.failed"),
    "-MeasurementCommitTimeoutSeconds", "$($base.artifact_commit.probe_wait_timeout_seconds)"
)
$guardArgs = @(
    $guard, "--trace", (Join-Path $logs "S93_support_clear.resource.jsonl"),
    "--summary", (Join-Path $logs "S93_support_clear.guard.json"),
    "--stdout", (Join-Path $logs "S93_support_clear.stdout.log"),
    "--stderr", (Join-Path $logs "S93_support_clear.stderr.log"),
    "--timeout-seconds", "$($limits.outer_condition_timeout_seconds)",
    "--sample-seconds", "$($limits.resource_sampling_seconds)",
    "--runner-private-limit", "$($limits.runner_private_limit_bytes)",
    "--diagnostic-private-limit", "$($limits.diagnostic_private_limit_bytes)",
    "--kit-private-limit", "$($limits.kit_private_limit_bytes)",
    "--tree-private-limit", "$($limits.unique_tree_private_limit_bytes)",
    "--available-memory-floor", "$($limits.physical_memory_floor_bytes)",
    "--commit-headroom-floor", "$($limits.commit_headroom_floor_bytes)",
    "--cpu-telemetry", "--gpu-csv", (Join-Path $logs "S93_support_clear.gpu.csv"),
    "--gpu-sample-ms", "$($limits.gpu_sampling_ms)",
    "--lifecycle-path", (Join-Path $caseDir "raw.json"),
    "--diagnostic-marker-path", (Join-Path $caseDir "resource_markers.jsonl"),
    "--attempt-id", $attemptId,
    "--cleanup-suppression-lock", ((Join-Path $caseDir "sensitive-shutdown-diagnostics") + ".ownership.json"),
    "--cleanup-suppression-deadline-seconds", "150",
    "--cleanup-marker-path", (Join-Path $logs "cleanup_markers.jsonl"),
    "--", $powershell
) + $arguments

$guardProcess = Start-Process -FilePath python -ArgumentList $guardArgs -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs "guard-launcher.stdout.log") `
    -RedirectStandardError (Join-Path $logs "guard-launcher.stderr.log")
$committerArgs = @(
    $committer, "--raw-path", (Join-Path $caseDir "raw.json"),
    "--resource-path", (Join-Path $logs "S93_support_clear.resource.jsonl"),
    "--gpu-path", (Join-Path $logs "S93_support_clear.gpu.csv"),
    "--marker-path", (Join-Path $caseDir "resource_markers.jsonl"),
    "--attempt-metadata", (Join-Path $attemptRoot "attempt_metadata.json"),
    "--contract", $discoveryContractPath,
    "--output-dir", (Join-Path $caseDir "memory-measurement"),
    "--stop-file", (Join-Path $attemptRoot "committer.stop"),
    "--timeout-seconds", "$($base.artifact_commit.helper_timeout_seconds)",
    "--private-limit-bytes", "$($base.artifact_commit.helper_private_limit_bytes)"
)
$committerProcess = Start-Process -FilePath python -ArgumentList $committerArgs -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs "committer.stdout.log") `
    -RedirectStandardError (Join-Path $logs "committer.stderr.log")
$guardProcess.WaitForExit()
[IO.File]::WriteAllText((Join-Path $attemptRoot "committer.stop"), "guard-exited`n", [Text.UTF8Encoding]::new($false))
if (-not $committerProcess.WaitForExit(15000)) {
    Stop-Process -Id $committerProcess.Id -Force -ErrorAction SilentlyContinue
    throw "Phase 6GD committer did not exit"
}

if ((Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash -ne $productionBefore) {
    throw "Phase 6GD changed production app"
}
$rawPath = Join-Path $caseDir "raw.json"
$metadataPath = Join-Path $caseDir "channel-schema-metadata\bounded_handle_metadata.json"
$runnerEvidencePath = Join-Path $caseDir "runner_evidence.json"
$guardEvidencePath = Join-Path $logs "S93_support_clear.guard.json"
if (-not (Test-Path -LiteralPath $rawPath) -or -not (Test-Path -LiteralPath $metadataPath) -or
    -not (Test-Path -LiteralPath $runnerEvidencePath) -or -not (Test-Path -LiteralPath $guardEvidencePath)) {
    throw "Phase 6GD bounded metadata artifacts are incomplete"
}
$raw = Get-Content -Raw -Encoding UTF8 $rawPath | ConvertFrom-Json
$metadata = Get-Content -Raw -Encoding UTF8 $metadataPath | ConvertFrom-Json
$runnerEvidence = Get-Content -Raw -Encoding UTF8 $runnerEvidencePath | ConvertFrom-Json
$guardEvidence = Get-Content -Raw -Encoding UTF8 $guardEvidencePath | ConvertFrom-Json
if ($raw.status -ne "ok" -or $raw.lifecycle_marker -ne "shutdown_complete") {
    throw "Phase 6GD metadata probe did not complete lifecycle"
}
if ($runnerEvidence.outcome.functional_status -ne "pass" -or
    $runnerEvidence.outcome.lifecycle_status -ne "normal_exit" -or
    -not $runnerEvidence.outcome.normal_exit_sample_accepted -or
    $null -eq $runnerEvidence.process_exit_code -or [int]$runnerEvidence.process_exit_code -ne 0) {
    throw "Phase 6GD metadata process failed the frozen functional/lifecycle/OS-exit axes"
}
if ($guardEvidence.status -ne "ok" -or [int]$guardEvidence.exit_code -ne 0 -or
    -not $guardEvidence.observed_process_cleanup.all_observed_absent -or
    $runnerEvidence.shutdown_monitor.residual_process) {
    throw "Phase 6GD metadata process failed the frozen diagnostic/cleanup axes"
}
if ($metadata.formal_channel_names_assigned -or $metadata.full_field_json_or_npz_written) {
    throw "Phase 6GD discovery probe violated bounded scope"
}
if ($metadata.returned_handle_count -lt 1 -or $metadata.returned_handle_count -gt $discovery.readback.maximum_handle_count) {
    throw "Phase 6GD returned handle count is outside the frozen discovery bound"
}

$summary = [ordered]@{
    schema = "campfire.phase6gd.channel-schema-discovery-summary.v1"
    phase = $ReportPhase
    status = "metadata_complete_mapping_pending"
    discovery_contract_sha256 = $actualDiscoveryHash
    base_contract_sha256 = $actualBaseHash
    returned_handle_count = [int]$metadata.returned_handle_count
    channel_schema_control = $Control
    control_contract_sha256 = $controlContractHash
    diagnostic_resource_contract_sha256 = $diagnosticResourceContractHash
    metadata_path = $metadataPath
    metadata_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $metadataPath).Hash
    lifecycle_marker = [string]$raw.lifecycle_marker
    functional_status = [string]$runnerEvidence.outcome.functional_status
    lifecycle_status = [string]$runnerEvidence.outcome.lifecycle_status
    os_process_normal_exit = [bool]$runnerEvidence.outcome.os_process_normal_exit
    exact_cleanup = [bool]$guardEvidence.observed_process_cleanup.all_observed_absent
    residual_process = [bool]$runnerEvidence.shutdown_monitor.residual_process
    production_sha256 = $productionBefore
    formal_population_started = $false
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
}
[IO.File]::WriteAllText((Join-Path $OutputRoot "discovery_summary.json"), ($summary | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host "Phase 6GD bounded channel metadata complete; semantic mapping remains pending."
