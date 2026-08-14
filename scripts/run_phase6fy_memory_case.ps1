param(
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [Parameter(Mandatory = $true)][ValidateSet("M0_baseline", "M1_phase6fo_equivalent", "M2_pre_readback_frame")][string]$Condition,
    [Parameter(Mandatory = $true)][int]$RunIndex,
    [Parameter(Mandatory = $true)][string]$AttemptId,
    [Parameter(Mandatory = $true)][int]$AllocationLevel,
    [Parameter(Mandatory = $true)][ValidateSet("true", "false")][string]$SpatialCollectorsEnabled,
    [Parameter(Mandatory = $true)][string]$SampleFrames,
    [Parameter(Mandatory = $true)][int]$TerminalFrame,
    [Parameter(Mandatory = $true)][double]$StageCloseTimeoutSeconds,
    [Parameter(Mandatory = $true)][int]$AbsoluteTimeoutSeconds,
    [string]$PreviousProcessExitUtc = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
. (Join-Path $PSScriptRoot "kit_shutdown_policy.ps1")
$release = Join-Path $root "_build\windows-x86_64\release"
$kit = Join-Path $release "kit\kit.exe"
$app = Join-Path $release "kit\apps\omni.app.editor.base.kit"
$productionApp = Join-Path $release "apps\campfire.simulator.kit"
$output = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $output) { throw "Phase 6FY refuses case output reuse: $output" }
New-Item -ItemType Directory -Path $output | Out-Null
$raw = Join-Path $output "raw.json"
$log = Join-Path $output "kit.log"
$dumpDir = Join-Path $output "sensitive-crash-dumps"
$diagnosticDir = Join-Path $output "sensitive-shutdown-diagnostics"
$evidencePath = Join-Path $output "runner_evidence.json"
$resourceMarkerPath = Join-Path $output "resource_markers.jsonl"
$extensionMarkerPath = Join-Path $output "extension_lifecycle_markers.jsonl"
$runnerMarkerPath = Join-Path $output "runner_lifecycle_markers.jsonl"
$measurementDir = Join-Path $output "memory-measurement"
$measurementAck = Join-Path $measurementDir "measurement_commit.ack"
$measurementFailure = Join-Path $measurementDir "measurement_commit.failed"
$probe = Join-Path $PSScriptRoot "probe_phase6fy_three_axis_memory.py"
$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$registryBefore = Get-CampfireCrashRegistrySnapshot
$spatialAllChannels = if ($SpatialCollectorsEnabled -eq "true") { "true" } else { "false" }
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
    "--/phase6ep/scenario=production_four",
    "--/phase6ep/offsetM=-0.0125",
    "--/phase6ep/supportRadiusM=0.05",
    "--/phase6ep/filtering=true",
    "--/phase6ep/collision=true",
    "--/phase6ep/policy=allow_self_center",
    "--/phase6ep/reportPhase=phase6fv",
    "--/phase6ep/sampleFrames=$SampleFrames",
    "--/phase6ep/readbackChannels=none",
    "--/phase6ep/readbackMode=none",
    "--/phase6ep/readbackFrames=",
    "--/phase6ep/operationFrames=$TerminalFrame",
    "--/phase6ep/referenceDisposal=del",
    "--/phase6ep/synchronousMemoryMarkers=true",
    "--/phase6ep/pythonMemoryTelemetry=true",
    "--/phase6ep/spatialCollectorsEnabled=$SpatialCollectorsEnabled",
    "--/phase6ep/spatialColliderIndices=2",
    "--/phase6ep/spatialAllChannels=$spatialAllChannels",
    "--/phase6ep/runIndex=$RunIndex",
    "--/phase6ep/allocationCalibrationLevel=$AllocationLevel",
    "--/phase6ep/capture=false",
    "--/phase6ep/geometryVariant=phase6er_corrected",
    "--/phase6ep/fuelScale=1",
    "--/phase6ep/temperatureScale=1",
    "--/phase6ep/smokeScale=1",
    "--/phase6ep/resourceMarkerPath=$resourceMarkerPath",
    "--/phase6ep/lifecycleCalibration=true",
    "--/phase6ep/rendererDrainUpdates=8",
    "--/phase6ep/lifecycleReferenceReleaseOrder=after_stage_close",
    "--/phase6ep/capturePreparationMode=none",
    "--/phase6ep/stageCloseTimeoutSeconds=$StageCloseTimeoutSeconds",
    "--/phase6ep/flowLivenessAudit=true",
    "--/phase6ep/startupProbe=true",
    "--/phase6ep/startupProbeLabel=$AttemptId",
    "--/phase6ep/startupFlowAcquirePosition=before_updates",
    "--/phase6ep/startupPreTimelineUpdateCount=12",
    "--/phase6ep/startupExtraUpdateBeforePlayCount=0",
    "--/phase6ep/startupLivenessGate=true",
    "--/phase6ep/startupExpectedFuelSum=1075.2000160217285",
    "--/phase6ep/startupExpectedTemperatureSum=2688.0",
    "--/phase6ep/startupExpectedSmokeSum=107.51999759674072",
    "--/phase6ep/startupSourceSumTolerance=0.0001",
    "--/phase6fy/measurementCommitAck=$measurementAck",
    "--/phase6fy/measurementCommitFailure=$measurementFailure",
    "--/phase6fy/measurementCommitTimeoutSeconds=60",
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

$process = Start-Process -FilePath $kit -ArgumentList $arguments -PassThru -WindowStyle Hidden
$processStartUtc = $process.StartTime.ToUniversalTime()
$previousGap = $null
if (-not [string]::IsNullOrWhiteSpace($PreviousProcessExitUtc)) {
    $previous = [DateTimeOffset]::Parse($PreviousProcessExitUtc, [Globalization.CultureInfo]::InvariantCulture)
    $previousGap = ($processStartUtc - $previous.UtcDateTime).TotalSeconds
}
$monitor = Wait-CampfireKitProcessWithShutdownPolicy -Process $process -ExpectedExecutable $kit -LifecyclePath $raw -LogPath $log -DiagnosticDir $diagnosticDir -ShutdownGraceSeconds 60 -AbsoluteTimeoutSeconds $AbsoluteTimeoutSeconds
$exitMarker = [ordered]@{
    schema="campfire.phase6fy.runner-lifecycle-marker.v1"; marker="os_process_exit_observed"
    timestamp_utc=[DateTime]::UtcNow.ToString("o"); pid=$process.Id
    expected_executable=$kit; process_exit_code=$monitor.exit_code
    lifecycle_candidate=$monitor.lifecycle_candidate; residual_process=$monitor.residual_process
}
[IO.File]::WriteAllText($runnerMarkerPath, ($exitMarker | ConvertTo-Json -Depth 8 -Compress) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
$registryAfter = Get-CampfireCrashRegistrySnapshot
$registryUnchanged = (($registryBefore | ConvertTo-Json -Depth 12 -Compress) -eq ($registryAfter | ConvertTo-Json -Depth 12 -Compress))
$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$dumps = @(Get-CampfireCrashDumpInventory -DumpDir $dumpDir)
$fatalPatterns = @(
    "[crash] A crash has occurred", "Traceback (most recent call last)", "CUDA illegal address",
    "0xC0000005", "access violation", "device lost", "invalid pointer", "TDR",
    "IRenderSettings::getRenderSettings failed getting a stage-id"
)
$fatalLines = @()
foreach ($pattern in $fatalPatterns) {
    $fatalLines += @(Select-String -LiteralPath $log -SimpleMatch $pattern -ErrorAction SilentlyContinue | ForEach-Object { $_.Line })
}
$uploadLines = @(Select-String -LiteralPath $log -Pattern "upload(?:ing|ed)? (?:mini)?dump|sending crash|submit.*crash" -CaseSensitive:$false -ErrorAction SilentlyContinue | ForEach-Object { $_.Line })
$probeReport = if (Test-Path -LiteralPath $raw) { Get-Content -Raw -Encoding UTF8 $raw | ConvertFrom-Json } else { $null }
$evidence = [ordered]@{
    schema="campfire.phase6fy.memory-case-runner.v1"; phase="phase6fy"; condition=$Condition
    run_index=$RunIndex; attempt_id=$AttemptId; process_start_utc=$processStartUtc.ToString("o")
    previous_process_exit_utc=$PreviousProcessExitUtc; previous_process_exit_to_process_start_seconds=$previousGap
    process_exit_code=$monitor.exit_code; shutdown_monitor=$monitor
    fatal_lines=@($fatalLines); dump_inventory=$dumps; automatic_upload_attempt_lines=@($uploadLines)
    relevant_crash_registry_unchanged=$registryUnchanged
    production_app_sha256_before=$productionHashBefore; production_app_sha256_after=$productionHashAfter
    production_changed=($productionHashBefore -ne $productionHashAfter)
    lifecycle_marker=if($null -ne $probeReport){$probeReport.lifecycle_marker}else{$null}
    probe_status=if($null -ne $probeReport){$probeReport.status}else{"missing"}
    memory_measurement_ack_present=(Test-Path -LiteralPath $measurementAck)
    memory_measurement_failure_present=(Test-Path -LiteralPath $measurementFailure)
}
[IO.File]::WriteAllText($evidencePath, ($evidence | ConvertTo-Json -Depth 12) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
if (-not $registryUnchanged) { throw "Phase 6FY changed crash registry" }
if ($productionHashBefore -ne $productionHashAfter) { throw "Phase 6FY changed production app" }
if ($dumps.Count -gt 0 -or $fatalLines.Count -gt 0 -or $uploadLines.Count -gt 0) { throw "Phase 6FY safety evidence failed" }
if (-not (Test-Path -LiteralPath $measurementAck)) { throw "Phase 6FY pre-close memory artifact was not committed" }
if ($null -eq $probeReport) { throw "Phase 6FY probe report missing" }
if ($probeReport.lifecycle_marker -ne "shutdown_complete" -or $monitor.exit_code -ne 0) {
    throw "Phase 6FY lifecycle did not exit normally"
}
Write-Host "Phase 6FY case completed: $AttemptId $Condition"
