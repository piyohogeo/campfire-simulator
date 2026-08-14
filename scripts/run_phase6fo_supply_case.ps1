param(
    [Parameter(Mandatory = $true)][ValidateSet("single", "near_two", "lower_upper", "production_four")][string]$Scenario,
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [double]$OffsetM = 0.075,
    [double]$SupportRadiusM = 0.05,
    [ValidateSet("true", "false")][string]$Filtering = "true",
    [ValidateSet("true", "false")][string]$Collision = "true",
    [ValidateSet("strict_all", "allow_self_support", "allow_self_center", "allow_other_support")][string]$Policy = "strict_all",
    [ValidateSet("phase6ep", "phase6eq", "phase6er", "phase6es", "phase6et", "phase6eu", "phase6ev", "phase6ew", "phase6ex", "phase6ey", "phase6ez", "phase6fa", "phase6fb", "phase6fc", "phase6fd", "phase6fe", "phase6ff", "phase6fg", "phase6fh", "phase6fi", "phase6fj", "phase6fk", "phase6fn", "phase6fo", "phase6fp", "phase6fq", "phase6fr", "phase6fs", "phase6ft", "phase6fv", "phase6ga", "phase6gb", "phase6gc")][string]$ReportPhase = "phase6ep",
    [string]$SampleFrames = "60,120,180,200",
    [string]$ReadbackChannels = "temperature,fuel,burn,smoke,velocity",
    [ValidateSet("legacy", "none", "acquire_discard", "acquire_discard_release", "fuel_convert", "fuel_convert_release", "fuel_scalar", "fuel_jsonl", "fuel_spatial", "p3_spatial_release")][string]$ReadbackMode = "legacy",
    [string]$ReadbackFrames = "",
    [string]$OperationFrames = "",
    [string]$SettlingEndFrames = "",
    [ValidateSet("natural", "del", "gc")][string]$ReferenceDisposal = "natural",
    [ValidateSet("true", "false")][string]$SynchronousMemoryMarkers = "false",
    [ValidateSet("true", "false")][string]$PythonMemoryTelemetry = "false",
    [string]$BoundedJsonlPath = "",
    [ValidateSet("true", "false")][string]$SpatialCollectorsEnabled = "true",
    [string]$SpatialColliderIndices = "",
    [switch]$SpatialAllChannels,
    [string]$SpatialScalarColliderIndices = "",
    [int]$RunIndex = 1,
    [ValidateRange(0, 7)][int]$AllocationCalibrationLevel = 0,
    [switch]$Capture,
    [int]$CaptureStart = 21,
    [int]$CaptureEnd = 200,
    [ValidateSet("legacy_phase6ep", "phase6er_corrected")][string]$GeometryVariant = "legacy_phase6ep",
    [double]$FuelScale = 1.0,
    [double]$TemperatureScale = 1.0,
    [double]$SmokeScale = 1.0,
    [switch]$LifecycleCalibration,
    [ValidateRange(0, 64)][int]$RendererDrainUpdates = 8,
    [ValidateSet("before_stage_close", "after_stage_close")][string]$LifecycleReferenceReleaseOrder = "before_stage_close",
    [ValidateSet("none", "manifest", "provider_alias")][string]$CapturePreparationMode = "none",
    [double]$StageCloseTimeoutSeconds = 0.0,
    [int]$StabilityObservationStartFrame = 0,
    [double]$StabilityObservationExtraSeconds = 0.0,
    [double]$StabilityActiveBlockSampleSeconds = 0.5,
    [ValidateSet("true", "false")][string]$FlowLivenessAudit = "false",
    [ValidateSet("true", "false")][string]$FuelLivenessDecode = "false",
    [ValidateSet("true", "false")][string]$StartupProbe = "false",
    [string]$StartupProbeLabel = "",
    [ValidateSet("before_updates", "after_updates")][string]$StartupFlowAcquirePosition = "before_updates",
    [ValidateRange(0, 120)][int]$StartupPreTimelineUpdateCount = 12,
    [ValidateRange(0, 120)][int]$StartupExtraUpdateBeforePlayCount = 0,
    [ValidateSet("true", "false")][string]$StartupLivenessGate = "false",
    [double]$StartupExpectedFuelSum = 0.0,
    [double]$StartupExpectedTemperatureSum = 0.0,
    [double]$StartupExpectedSmokeSum = 0.0,
    [double]$StartupSourceSumTolerance = 0.000001,
    [ValidateSet("decimal_legacy", "payload_native_float32_v1")][string]$StartupSourceContractMode = "decimal_legacy",
    [string]$PreviousProcessExitUtc = "",
    [int]$AbsoluteTimeoutSeconds = 330,
    [string]$ProbePath = "",
    [string]$ImportAuditPath = "",
    [string]$MeasurementCommitAck = "",
    [string]$MeasurementCommitFailure = "",
    [double]$MeasurementCommitTimeoutSeconds = 60.0,
    [string]$ExpectedGeometryConcept = "",
    [switch]$ValidateArgumentsOnly,
    [string]$ArgumentAuditPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
. (Join-Path $PSScriptRoot "kit_shutdown_policy.ps1")
$release = Join-Path $root "_build\windows-x86_64\release"
$kit = Join-Path $release "kit\kit.exe"
$output = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $output) { throw "Phase 6EP refuses output reuse: $output" }
New-Item -ItemType Directory -Path $output | Out-Null
$raw = Join-Path $output "raw.json"
$log = Join-Path $output "kit.log"
$dumpDir = Join-Path $output "sensitive-crash-dumps"
$diagnosticDir = Join-Path $output "sensitive-shutdown-diagnostics"
$evidencePath = Join-Path $output "runner_evidence.json"
$resourceMarkerPath = Join-Path $output "resource_markers.jsonl"
$extensionMarkerPath = Join-Path $output "extension_lifecycle_markers.jsonl"
$runnerMarkerPath = Join-Path $output "runner_lifecycle_markers.jsonl"
$productionApp = Join-Path $release "apps\campfire.simulator.kit"
$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$app = Join-Path $release "kit\apps\omni.app.editor.base.kit"
$probe = if ([string]::IsNullOrWhiteSpace($ProbePath)) { Join-Path $PSScriptRoot "probe_phase6fo_supply_comparison.py" } else { [IO.Path]::GetFullPath($ProbePath) }
$filterValue = $Filtering
$collisionValue = $Collision
$captureValue = $Capture.IsPresent.ToString().ToLowerInvariant()
$arguments = @(
    $app,
    "--no-window",
    "--/app/file/ignoreUnsavedOnExit=true",
    "--/app/fastShutdown=0",
    "--/app/quitAfter=300000",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/app/window/hideUi=true",
    "--/app/asyncRendering=false",
    "--/renderer/enabled=rtx",
    "--/renderer/active=rtx",
    "--/persistent/rtx/modes/rt/enabled=false",
    "--/persistent/rtx/modes/pt/enabled=true",
    "--/persistent/rtx/modes/rt2/enabled=true",
    "--/phase6ep/output=$raw",
    "--/phase6ep/scenario=$Scenario",
    "--/phase6ep/offsetM=$OffsetM",
    "--/phase6ep/supportRadiusM=$SupportRadiusM",
    "--/phase6ep/filtering=$filterValue",
    "--/phase6ep/collision=$collisionValue",
    "--/phase6ep/policy=$Policy",
    "--/phase6ep/reportPhase=$ReportPhase",
    "--/phase6ep/sampleFrames=$SampleFrames",
    "--/phase6ep/readbackChannels=$ReadbackChannels",
    "--/phase6ep/readbackMode=$ReadbackMode",
    "--/phase6ep/readbackFrames=$ReadbackFrames",
    "--/phase6ep/operationFrames=$OperationFrames",
    "--/phase6ep/settlingEndFrames=$SettlingEndFrames",
    "--/phase6ep/referenceDisposal=$ReferenceDisposal",
    "--/phase6ep/synchronousMemoryMarkers=$SynchronousMemoryMarkers",
    "--/phase6ep/pythonMemoryTelemetry=$PythonMemoryTelemetry",
    "--/phase6ep/boundedJsonlPath=$BoundedJsonlPath",
    "--/phase6ep/spatialCollectorsEnabled=$SpatialCollectorsEnabled",
    "--/phase6ep/spatialColliderIndices=$SpatialColliderIndices",
    "--/phase6ep/spatialAllChannels=$($SpatialAllChannels.IsPresent.ToString().ToLowerInvariant())",
    "--/phase6ep/spatialScalarColliderIndices=$SpatialScalarColliderIndices",
    "--/phase6ep/runIndex=$RunIndex",
    "--/phase6ep/allocationCalibrationLevel=$AllocationCalibrationLevel",
    "--/phase6ep/capture=$captureValue",
    "--/phase6ep/captureStart=$CaptureStart",
    "--/phase6ep/captureEnd=$CaptureEnd",
    "--/phase6ep/geometryVariant=$GeometryVariant",
    "--/phase6ep/fuelScale=$FuelScale",
    "--/phase6ep/temperatureScale=$TemperatureScale",
    "--/phase6ep/smokeScale=$SmokeScale",
    "--/phase6ep/resourceMarkerPath=$resourceMarkerPath",
    "--/phase6ep/lifecycleCalibration=$($LifecycleCalibration.IsPresent.ToString().ToLowerInvariant())",
    "--/phase6ep/rendererDrainUpdates=$RendererDrainUpdates",
    "--/phase6ep/lifecycleReferenceReleaseOrder=$LifecycleReferenceReleaseOrder",
    "--/phase6ep/capturePreparationMode=$CapturePreparationMode",
    "--/phase6ep/stageCloseTimeoutSeconds=$StageCloseTimeoutSeconds",
    "--/phase6ep/stabilityObservationStartFrame=$StabilityObservationStartFrame",
    "--/phase6ep/stabilityObservationExtraSeconds=$StabilityObservationExtraSeconds",
    "--/phase6ep/stabilityActiveBlockSampleSeconds=$StabilityActiveBlockSampleSeconds",
    "--/phase6ep/flowLivenessAudit=$FlowLivenessAudit",
    "--/phase6ep/fuelLivenessDecode=$FuelLivenessDecode",
    "--/phase6ep/startupProbe=$StartupProbe",
    "--/phase6ep/startupProbeLabel=$StartupProbeLabel",
    "--/phase6ep/startupFlowAcquirePosition=$StartupFlowAcquirePosition",
    "--/phase6ep/startupPreTimelineUpdateCount=$StartupPreTimelineUpdateCount",
    "--/phase6ep/startupExtraUpdateBeforePlayCount=$StartupExtraUpdateBeforePlayCount",
    "--/phase6ep/startupLivenessGate=$StartupLivenessGate",
    "--/phase6ep/startupExpectedFuelSum=$StartupExpectedFuelSum",
    "--/phase6ep/startupExpectedTemperatureSum=$StartupExpectedTemperatureSum",
    "--/phase6ep/startupExpectedSmokeSum=$StartupExpectedSmokeSum",
    "--/phase6ep/startupSourceSumTolerance=$StartupSourceSumTolerance",
    "--/phase6ep/startupSourceContractMode=$StartupSourceContractMode",
    "--/phase6fz/importAuditPath=$ImportAuditPath",
    "--/phase6fz/measurementCommitAck=$MeasurementCommitAck",
    "--/phase6fz/measurementCommitFailure=$MeasurementCommitFailure",
    "--/phase6fz/measurementCommitTimeoutSeconds=$MeasurementCommitTimeoutSeconds",
    "--ext-folder", (Join-Path $PSScriptRoot "phasev3tg_extension"),
    "--enable", "omni.campfire.phasev3tg_shutdown",
    "--/phasev3tg/markers=$extensionMarkerPath",
    "--/rtx/flow/enabled=true",
    "--/log/file=$log",
    "--/log/fileLogLevel=Info",
    "--enable", "omni.flowusd",
    "--enable", "omni.volume",
    "--enable", "omni.hydra.rtx",
    "--enable", "omni.kit.viewport.window",
    "--enable", "omni.kit.renderer.capture",
    "--enable", "omni.physx.cooking",
    "--enable", "omni.physx.stageupdate",
    "--exec", $probe
) + @(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $dumpDir)

if (-not [string]::IsNullOrWhiteSpace($ExpectedGeometryConcept)) {
    if ($ExpectedGeometryConcept -ne "corrected") {
        throw "Unsupported geometry concept: $ExpectedGeometryConcept"
    }
    if ($GeometryVariant -ne "phase6er_corrected") {
        throw "Geometry concept '$ExpectedGeometryConcept' must map to runtime token 'phase6er_corrected'; received '$GeometryVariant'."
    }
}

if ($ValidateArgumentsOnly.IsPresent) {
    if ([string]::IsNullOrWhiteSpace($ArgumentAuditPath)) {
        throw "-ArgumentAuditPath is required with -ValidateArgumentsOnly."
    }
    $argumentAudit = [ordered]@{
        schema = "campfire.phase6gb.parameter-binding-audit.v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        kit_started = $false
        runner_path = [IO.Path]::GetFullPath($PSCommandPath)
        kit_path = [IO.Path]::GetFullPath($kit)
        app_path = [IO.Path]::GetFullPath($app)
        probe_path = [IO.Path]::GetFullPath($probe)
        geometry_concept = $ExpectedGeometryConcept
        geometry_runtime_token = $GeometryVariant
        report_phase = $ReportPhase
        argument_count = $arguments.Count
        arguments = @($arguments)
        final_command_line = (@($kit) + @($arguments)) -join " "
    }
    $auditFullPath = [IO.Path]::GetFullPath($ArgumentAuditPath)
    $auditParent = Split-Path -Parent $auditFullPath
    if (-not (Test-Path -LiteralPath $auditParent)) { New-Item -ItemType Directory -Path $auditParent | Out-Null }
    $auditText = $argumentAudit | ConvertTo-Json -Depth 8
    if ([Text.Encoding]::UTF8.GetByteCount($auditText) -gt 1048576) {
        throw "Parameter-binding audit exceeded the 1 MiB bound."
    }
    $auditPartial = "$auditFullPath.partial"
    [IO.File]::WriteAllText($auditPartial, $auditText + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $auditPartial -Destination $auditFullPath
    Write-Host "Phase 6GB argument validation completed without starting Kit: $auditFullPath"
    return
}

$registryBefore = Get-CampfireCrashRegistrySnapshot
$process = Start-Process -FilePath $kit -ArgumentList $arguments -PassThru -WindowStyle Hidden
$processStartUtc = $process.StartTime.ToUniversalTime()
$previousProcessExitGapSeconds = $null
if (-not [string]::IsNullOrWhiteSpace($PreviousProcessExitUtc)) {
    $previousExit = [DateTimeOffset]::Parse($PreviousProcessExitUtc, [Globalization.CultureInfo]::InvariantCulture)
    $previousProcessExitGapSeconds = ($processStartUtc - $previousExit.UtcDateTime).TotalSeconds
}
$monitor = Wait-CampfireKitProcessWithShutdownPolicy -Process $process -ExpectedExecutable $kit -LifecyclePath $raw -LogPath $log -DiagnosticDir $diagnosticDir -ShutdownGraceSeconds 60 -AbsoluteTimeoutSeconds $AbsoluteTimeoutSeconds
$osExitMarker = [ordered]@{
    schema = "campfire.phase6ev.runner-lifecycle-marker.v1"
    marker = "os_process_exit_observed"
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
    pid = $process.Id
    expected_executable = $kit
    process_exit_code = $monitor.exit_code
    lifecycle_candidate = $monitor.lifecycle_candidate
    residual_process = $monitor.residual_process
}
[IO.File]::WriteAllText($runnerMarkerPath, ($osExitMarker | ConvertTo-Json -Depth 8 -Compress) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
$logEvidenceReadiness = [ordered]@{ available=$false; attempts=0; waited_seconds=0.0; last_error=$null; maximum_wait_seconds=15 }
$logReadyStopwatch = [Diagnostics.Stopwatch]::StartNew()
do {
    $logEvidenceReadiness.attempts += 1
    $readinessProbe = Get-CampfireWindowsExceptionEvidence -Path $log
    $logEvidenceReadiness.available = [bool]$readinessProbe.available
    $logEvidenceReadiness.last_error = $readinessProbe.error
    if ($logEvidenceReadiness.available -or $logReadyStopwatch.Elapsed.TotalSeconds -ge $logEvidenceReadiness.maximum_wait_seconds) { break }
    Start-Sleep -Milliseconds 100
} while ($true)
$logReadyStopwatch.Stop()
$logEvidenceReadiness.waited_seconds = $logReadyStopwatch.Elapsed.TotalSeconds
$registryAfter = Get-CampfireCrashRegistrySnapshot
$registryUnchanged = (($registryBefore | ConvertTo-Json -Depth 12 -Compress) -eq ($registryAfter | ConvertTo-Json -Depth 12 -Compress))
$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$dumps = @(Get-CampfireCrashDumpInventory -DumpDir $dumpDir)
$fatalPatterns = @(
    "[crash] A crash has occurred", "Traceback (most recent call last)",
    "CUDA illegal address", "0xC0000005", "access violation", "device lost",
    "invalid pointer", "TDR", "IRenderSettings::getRenderSettings failed getting a stage-id"
)
$fatalLines = @()
foreach ($pattern in $fatalPatterns) {
    $fatalLines += @(Select-String -LiteralPath $log -SimpleMatch $pattern -ErrorAction SilentlyContinue | ForEach-Object { $_.Line })
}
$uploadAttemptLines = @(Select-String -LiteralPath $log -Pattern "upload(?:ing|ed)? (?:mini)?dump|sending crash|submit.*crash" -CaseSensitive:$false -ErrorAction SilentlyContinue | ForEach-Object { $_.Line })
$probeReport = $null
if (Test-Path -LiteralPath $raw) { $probeReport = Get-Content -Raw -Encoding UTF8 $raw | ConvertFrom-Json }
$outcome = $null
if ($null -ne $probeReport) {
    $outcome = Invoke-CampfireShutdownOutcomeClassification -Monitor $monitor -ProbeReport $probeReport -LogPath $log -FatalLines $fatalLines -DumpCount $dumps.Count -UploadAttemptCount $uploadAttemptLines.Count -ProductionHashBefore $productionHashBefore -ProductionHashAfter $productionHashAfter -OutputDir $output
}
$evidence = [ordered]@{
    schema = "campfire.$ReportPhase.point-collision-runner.v1"
    phase = $ReportPhase
    scenario = $Scenario
    offset_m = $OffsetM
    filtering = ($Filtering -eq "true")
    collision = ($Collision -eq "true")
    policy = $Policy
    sample_frames = $SampleFrames
    readback_channels = $ReadbackChannels
    readback_mode = $ReadbackMode
    readback_frames = $ReadbackFrames
    reference_disposal = $ReferenceDisposal
    synchronous_memory_markers = ($SynchronousMemoryMarkers -eq "true")
    python_memory_telemetry = ($PythonMemoryTelemetry -eq "true")
    lifecycle_calibration = $LifecycleCalibration.IsPresent
    renderer_drain_updates = $RendererDrainUpdates
    lifecycle_reference_release_order = $LifecycleReferenceReleaseOrder
    capture_preparation_mode = $CapturePreparationMode
    stage_close_timeout_seconds = $StageCloseTimeoutSeconds
    stability_observation_start_frame = $StabilityObservationStartFrame
    stability_observation_extra_seconds = $StabilityObservationExtraSeconds
    stability_active_block_sample_seconds = $StabilityActiveBlockSampleSeconds
    flow_liveness_audit = ($FlowLivenessAudit -eq "true")
    fuel_liveness_decode = ($FuelLivenessDecode -eq "true")
    startup_probe = ($StartupProbe -eq "true")
    startup_probe_label = $StartupProbeLabel
    startup_flow_acquire_position = $StartupFlowAcquirePosition
    startup_pre_timeline_update_count = $StartupPreTimelineUpdateCount
    startup_extra_update_before_play_count = $StartupExtraUpdateBeforePlayCount
    startup_liveness_gate = ($StartupLivenessGate -eq "true")
    process_start_utc = $processStartUtc.ToString("o")
    previous_process_exit_utc = if ([string]::IsNullOrWhiteSpace($PreviousProcessExitUtc)) { $null } else { $PreviousProcessExitUtc }
    previous_process_exit_to_process_start_seconds = $previousProcessExitGapSeconds
    extension_marker_path = $extensionMarkerPath
    runner_marker_path = $runnerMarkerPath
    spatial_collectors_enabled = ($SpatialCollectorsEnabled -eq "true")
    spatial_collider_indices = $SpatialColliderIndices
    spatial_all_channels = $SpatialAllChannels.IsPresent
    spatial_scalar_collider_indices = $SpatialScalarColliderIndices
    run_index = $RunIndex
    allocation_calibration_level = $AllocationCalibrationLevel
    geometry_variant = $GeometryVariant
    source_scales = [ordered]@{ fuel=$FuelScale; temperature=$TemperatureScale; smoke=$SmokeScale }
    process_exit_code = $monitor.exit_code
    shutdown_monitor = $monitor
    log_evidence_readiness = $logEvidenceReadiness
    outcome = $outcome
    fatal_lines = @($fatalLines)
    dump_inventory = $dumps
    automatic_upload_attempt_lines = @($uploadAttemptLines)
    relevant_crash_registry_unchanged = $registryUnchanged
    production_app_sha256_before = $productionHashBefore
    production_app_sha256_after = $productionHashAfter
    production_changed = ($productionHashBefore -ne $productionHashAfter)
    kit_import_audit = if (-not [string]::IsNullOrWhiteSpace($ImportAuditPath) -and (Test-Path -LiteralPath $ImportAuditPath)) { Get-Content -Raw -Encoding UTF8 $ImportAuditPath | ConvertFrom-Json } else { $null }
    measurement_commit_ack_present = (-not [string]::IsNullOrWhiteSpace($MeasurementCommitAck) -and (Test-Path -LiteralPath $MeasurementCommitAck))
    measurement_commit_failure_present = (-not [string]::IsNullOrWhiteSpace($MeasurementCommitFailure) -and (Test-Path -LiteralPath $MeasurementCommitFailure))
    lifecycle_marker = if ($null -ne $probeReport) { $probeReport.lifecycle_marker } else { $null }
    probe_status = if ($null -ne $probeReport) { $probeReport.status } else { "missing" }
}
[IO.File]::WriteAllText($evidencePath, ($evidence | ConvertTo-Json -Depth 12) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))

if (-not $registryUnchanged) { throw "Phase 6EP changed crash registry" }
if ($productionHashBefore -ne $productionHashAfter) { throw "Phase 6EP changed production app" }
if ($dumps.Count -gt 0 -or $fatalLines.Count -gt 0 -or $uploadAttemptLines.Count -gt 0) { throw "Phase 6EP safety evidence failed" }
if ($null -eq $probeReport -or $probeReport.status -ne "ok" -or $probeReport.lifecycle_marker -ne "shutdown_complete") { throw "Phase 6EP probe failed" }
if ($null -eq $outcome -or $outcome.functional_status -ne "pass" -or $outcome.lifecycle_status -ne "normal_exit") { throw "Phase 6EP normal exit required" }
if ($ReportPhase -in @("phase6ga", "phase6gb", "phase6gc")) {
    if (-not (Test-Path -LiteralPath $ImportAuditPath)) { throw "Phase 6GA import audit missing" }
    $importAudit = Get-Content -Raw -Encoding UTF8 $ImportAuditPath | ConvertFrom-Json
    if ($importAudit.status -ne "pass") { throw "Phase 6GA deterministic import failed" }
    if (-not (Test-Path -LiteralPath $MeasurementCommitAck) -or (Test-Path -LiteralPath $MeasurementCommitFailure)) { throw "Phase 6GA durable pre-close commit failed" }
}
Write-Host "$ReportPhase passed: $Scenario offset=$OffsetM policy=$Policy filtering=$Filtering collision=$Collision run=$RunIndex"
