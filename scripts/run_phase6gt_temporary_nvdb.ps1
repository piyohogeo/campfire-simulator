param(
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [string]$ContractPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
. (Join-Path $PSScriptRoot "phase6gs_reporting_contract.ps1")
. (Join-Path $PSScriptRoot "phase6gt_temporary_file_cleanup.ps1")
$repo = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6GT refuses artifact root reuse: $OutputRoot" }
$contractPath = if ($ContractPath) { [IO.Path]::GetFullPath($ContractPath) } else { Join-Path $PSScriptRoot "phase6gt_temporary_nvdb_contract.json" }
$hashPath = [IO.Path]::ChangeExtension($contractPath, ".sha256")
$expectedHash = ((Get-Content -Encoding UTF8 $hashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($actualHash -ne $expectedHash) { throw "Phase 6GT contract hash mismatch" }
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json

New-Item -ItemType Directory -Path $OutputRoot | Out-Null
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
Copy-Item -LiteralPath $hashPath -Destination (Join-Path $OutputRoot "frozen_contract.sha256")
$preflight = Join-Path $OutputRoot "offline-preflight"
New-Item -ItemType Directory -Path $preflight | Out-Null
$fixtureReport = Join-Path $preflight "result.json"
$env:PHASE6GT_FIXTURE_REPORT = $fixtureReport
try {
    & python (Join-Path $PSScriptRoot "test_phase6gt_temporary_nvdb.py") *> (Join-Path $preflight "fixture.log")
    if ($LASTEXITCODE -ne 0) { throw "Phase 6GT no-Kit fixture failed before Kit launch" }
} finally {
    Remove-Item Env:PHASE6GT_FIXTURE_REPORT -ErrorAction SilentlyContinue
}
$fixture = Get-Content -Raw -Encoding UTF8 $fixtureReport | ConvertFrom-Json
if (-not $fixture.passed -or $fixture.case_count -ne 23 -or $fixture.kit_started) {
    throw "Phase 6GT fixture contract mismatch"
}
$e2eRoot = Join-Path $preflight "parent-e2e"
& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "test_phase6gt_temporary_nvdb_e2e.ps1") -OutputDir $e2eRoot *> (Join-Path $preflight "parent_e2e.log")
if ($LASTEXITCODE -ne 0) { throw "Phase 6GT parent end-to-end fixture failed before Kit launch" }
$e2e = Get-Content -Raw -Encoding UTF8 (Join-Path $e2eRoot "result.json") | ConvertFrom-Json
if (-not $e2e.passed -or $e2e.case_count -ne 5 -or $e2e.kit_started) { throw "Phase 6GT parent E2E fixture contract mismatch" }

$production = Join-Path $repo "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$latestDemo = Join-Path $repo "docs\devlog\assets\latest_demo.json"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $production).Hash
$demoBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $latestDemo).Hash
$attemptRoot = Join-Path $OutputRoot "formal\temperature_temporary_nvdb_once"
$caseRoot = Join-Path $attemptRoot "S93_support_clear"
$logs = Join-Path $attemptRoot "runner-logs"
New-Item -ItemType Directory -Path $logs | Out-Null
$statePath = Join-Path $OutputRoot "incremental_state.json"
$state = [ordered]@{
    schema="campfire.phase6gt.incremental-state.v1";status="running";terminal=$false;
    active_condition="temperature_temporary_nvdb_once";launches=1;maximum_launches=1;
    prior_phases_reclassified=$false;prior_runtime_sample_reused=$false;formal_population_started=$false;
    contract_sha256=$actualHash;timestamp_utc=[DateTime]::UtcNow.ToString("o")
}
[IO.File]::WriteAllText($statePath,($state|ConvertTo-Json -Depth 8)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))

$caseRunner = Join-Path $PSScriptRoot "run_phase6fo_supply_case.ps1"
$guard = Join-Path $PSScriptRoot "phase6fu_resource_guard.py"
$probe = Join-Path $PSScriptRoot "probe_phase6gt_temporary_nvdb.py"
$powershell = (Get-Command powershell.exe).Source
$arguments = @(
    "-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",$caseRunner,
    "-Scenario","production_four","-OutputDir",$caseRoot,"-OffsetM","-0.0125","-SupportRadiusM","0.05",
    "-Filtering","true","-Collision","true","-Policy","allow_self_center","-ReportPhase","phase6gt",
    "-GeometryVariant","phase6er_corrected","-ExpectedGeometryConcept","corrected","-ProbePath",$probe,
    "-SampleFrames","60,120,180,240","-OperationFrames","180","-ReadbackFrames","180",
    "-ReadbackChannels","velocity,temperature,smoke,fuel","-ReadbackMode","p3_spatial_release",
    "-ReferenceDisposal","del","-SynchronousMemoryMarkers","true","-PythonMemoryTelemetry","true",
    "-SpatialCollectorsEnabled","true","-SpatialColliderIndices","0,1,2,3","-SpatialAllChannels",
    "-RunIndex","1","-LifecycleCalibration","-RendererDrainUpdates","8",
    "-LifecycleReferenceReleaseOrder","after_stage_close","-StageCloseTimeoutSeconds","180",
    "-StabilityObservationStartFrame","240","-StabilityObservationExtraSeconds","5",
    "-StabilityActiveBlockSampleSeconds","0.5","-FlowLivenessAudit","true","-StartupProbe","true",
    "-StartupProbeLabel","temperature_temporary_nvdb_once","-StartupFlowAcquirePosition","before_updates",
    "-StartupPreTimelineUpdateCount","12","-StartupExtraUpdateBeforePlayCount","0",
    "-StartupLivenessGate","true","-StartupExpectedFuelSum","1075.2",
    "-StartupExpectedTemperatureSum","2688.0","-StartupExpectedSmokeSum","107.52",
    "-StartupSourceSumTolerance","0.00001","-StartupSourceContractMode","payload_native_float32_v1",
    "-AbsoluteTimeoutSeconds","900","-ImportAuditPath",(Join-Path $caseRoot "kit_import_audit.json"),
    "-PostReadbackIsolationMode","R3","-PostReadbackIsolationChannel","temperature",
    "-PostReadbackIsolationReportPath",(Join-Path $caseRoot "post_readback_isolation.json"),
    "-SkipLowLevelShutdownDiagnostic"
)
$limits = $contract.safety
$guardArgs = @(
    $guard,"--trace",(Join-Path $logs "temperature_temporary_nvdb_once.resource.jsonl"),"--summary",(Join-Path $logs "temperature_temporary_nvdb_once.guard.json"),
    "--stdout",(Join-Path $logs "temperature_temporary_nvdb_once.stdout.log"),"--stderr",(Join-Path $logs "temperature_temporary_nvdb_once.stderr.log"),
    "--timeout-seconds","$($limits.outer_condition_timeout_seconds)","--sample-seconds","$($limits.resource_sampling_seconds)",
    "--runner-private-limit","$($limits.runner_private_limit_bytes)","--diagnostic-private-limit","$($limits.diagnostic_private_limit_bytes)",
    "--kit-private-limit","$($limits.kit_private_limit_bytes)","--tree-private-limit","$($limits.unique_tree_private_limit_bytes)",
    "--available-memory-floor","$($limits.physical_memory_floor_bytes)","--commit-headroom-floor","$($limits.commit_headroom_floor_bytes)",
    "--cpu-telemetry","--gpu-csv",(Join-Path $logs "temperature_temporary_nvdb_once.gpu.csv"),"--gpu-sample-ms","$($limits.gpu_sampling_ms)",
    "--lifecycle-path",(Join-Path $caseRoot "raw.json"),"--diagnostic-marker-path",(Join-Path $caseRoot "resource_markers.jsonl"),
    "--attempt-id","temperature_temporary_nvdb_once","--cleanup-suppression-lock",((Join-Path $caseRoot "sensitive-shutdown-diagnostics")+".ownership.json"),
    "--cleanup-suppression-deadline-seconds","150","--cleanup-marker-path",(Join-Path $logs "cleanup_markers.jsonl"),
    "--",$powershell
) + $arguments
& python @guardArgs
$guardExit = $LASTEXITCODE

$runnerPath = Join-Path $caseRoot "runner_evidence.json"
$guardPath = Join-Path $logs "temperature_temporary_nvdb_once.guard.json"
$operationPath = Join-Path $caseRoot "post_readback_isolation.json"
$temporaryPath = [IO.Path]::GetFullPath((Join-Path $caseRoot $contract.temporary_file.filename))
if ([IO.Path]::GetDirectoryName($temporaryPath) -ne [IO.Path]::GetFullPath($caseRoot)) {
    throw "Phase 6GT parent cleanup path escaped the case artifact directory"
}
$parentCleanup = Invoke-Phase6gtExactTemporaryCleanup -TemporaryPath $temporaryPath -CaseRoot $caseRoot -ExpectedFilename $contract.temporary_file.filename
[IO.File]::WriteAllText((Join-Path $caseRoot "temporary_file_parent_cleanup.json"),($parentCleanup|ConvertTo-Json -Depth 6)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))

$runner = if(Test-Path $runnerPath){Get-Content -Raw -Encoding UTF8 $runnerPath|ConvertFrom-Json}else{$null}
$guardReport = if(Test-Path $guardPath){Get-Content -Raw -Encoding UTF8 $guardPath|ConvertFrom-Json}else{$null}
$operation = if(Test-Path $operationPath){Get-Content -Raw -Encoding UTF8 $operationPath|ConvertFrom-Json}else{$null}

$lastSuccessfulAccessor = $null
$lastOperationMarker = $null
$normalizationStatus = "pass"
$normalizationError = $null
try {
    $lastSuccessfulAccessor = Get-Phase6gsOptionalString -InputObject $operation -PropertyName "last_successful_accessor"
    $lastOperationMarker = Get-Phase6gsOptionalString -InputObject $operation -PropertyName "last_operation_marker"
} catch {
    $normalizationStatus = "fail_closed"
    $normalizationError = $_.Exception.Message
}
$accessorsComplete = ($null -ne $operation -and $null -ne $operation.accessor_calls -and
    $operation.accessor_calls.get_num_grids -eq 1 -and
    $operation.accessor_calls.get_grid_type -eq 1 -and
    $operation.accessor_calls.get_short_grid_name -eq 1 -and
    $operation.accessor_calls.get_grid_class -eq 1 -and
    $operation.accessor_calls.get_index_bounding_box -eq 1 -and
    $operation.accessor_calls.get_world_bounding_box -eq 1)
$fileEvidence = ($null -ne $operation -and $null -ne $operation.temporary_file -and
    $operation.save_volume_calls -eq 1 -and $operation.save_volume_return -eq $true -and
    $operation.temporary_file.file_exists -eq $true -and
    $operation.temporary_file.file_size_bytes -gt 0 -and
    $operation.temporary_file.file_size_bytes -le $contract.temporary_file.maximum_file_bytes -and
    $operation.temporary_file.within_limit -eq $true -and
    $operation.temporary_file.deleted -eq $true -and
    $operation.temporary_file.file_exists_after_delete -eq $false -and
    $parentCleanup.existed_after_process -eq $false -and $parentCleanup.exists_after_cleanup -eq $false)
$operationComplete = ($normalizationStatus -eq "pass" -and $null -ne $operation -and
    $operation.status -eq "pass" -and $operation.operation_result -eq "pass" -and
    $operation.public_readback_calls -eq 1 -and $operation.volume_conversion_calls -eq 1 -and
    $operation.bounded_metadata_complete -and $accessorsComplete -and $fileEvidence -and
    $lastSuccessfulAccessor -eq "get_world_bounding_box" -and
    $lastOperationMarker -eq "phase6gt_source_release_after" -and
    $operation.weak_reference_alive_after_release_count -eq 0 -and
    $operation.file_content_read_calls -eq 0 -and $operation.file_hash_calls -eq 0 -and
    $operation.nanovdb_reload_calls -eq 0 -and $operation.numpy_asarray_calls -eq 0 -and
    $operation.sampling_calls -eq 0 -and $operation.collector_calls -eq 0 -and $operation.flux_calls -eq 0)
$lifecycleNormal = ($guardExit -eq 0 -and $null -ne $runner -and
    $runner.process_exit_code -eq 0 -and $runner.outcome.lifecycle_status -eq "normal_exit" -and
    $runner.outcome.normal_exit_sample_accepted -and $runner.lifecycle_marker -eq "shutdown_complete")
$cleanupAbsent = ($null -ne $guardReport -and $guardReport.observed_process_cleanup.all_observed_absent -and -not $parentCleanup.exists_after_cleanup)
$resourcePass = ($null -ne $guardReport -and
    $guardReport.peaks.kit -le $limits.kit_private_limit_bytes -and
    $guardReport.peaks.tree -le $limits.unique_tree_private_limit_bytes -and
    $guardReport.peaks.runner -le $limits.runner_private_limit_bytes -and
    $guardReport.peaks.diagnostic -le $limits.diagnostic_private_limit_bytes -and
    $guardReport.machine_minima.available_physical_bytes -ge $limits.physical_memory_floor_bytes -and
    $guardReport.machine_minima.estimated_commit_headroom_bytes -ge $limits.commit_headroom_floor_bytes)
$qualified = $operationComplete -and $lifecycleNormal -and $cleanupAbsent -and $resourcePass
$operationResult = if($operationComplete -and $lifecycleNormal){"pass"}elseif($operationComplete){"partial_operation_evidence"}else{"temporary_nvdb_save_boundary_failure"}
$lifecycleResult = if($lifecycleNormal){"normal_exit"}else{"failure"}
$summary = [ordered]@{
    schema="campfire.phase6gt.temporary-nvdb-summary.v1";qualified=[bool]$qualified;
    status=if($qualified){"qualified_no_later_operation_started"}else{"safe_stop"};contract_sha256=$actualHash;
    launches=1;retries=0;replacements=0;later_operations_started=$false;formal_nine_process_population_started=$false;
    prior_runtime_sample_reused=$false;operation_result=$operationResult;lifecycle_result=$lifecycleResult;operation=$operation;
    normalized_last_successful_accessor=$lastSuccessfulAccessor;normalized_last_operation_marker=$lastOperationMarker;
    reporting_normalization=[ordered]@{status=$normalizationStatus;error=$normalizationError};
    temporary_file_parent_cleanup=$parentCleanup;
    process_exit_code=if($runner){$runner.process_exit_code}else{$null};lifecycle_marker=if($runner){$runner.lifecycle_marker}else{$null};
    runner_outcome=if($runner){$runner.outcome}else{$null};guard_exit=$guardExit;
    cleanup_all_observed_absent=[bool]$cleanupAbsent;resource_pass=[bool]$resourcePass;
    peaks=if($guardReport){$guardReport.peaks}else{$null};machine_minima=if($guardReport){$guardReport.machine_minima}else{$null};
    production_sha256_before=$productionBefore;production_sha256_after=(Get-FileHash -Algorithm SHA256 -LiteralPath $production).Hash;
    latest_demo_sha256_before=$demoBefore;latest_demo_sha256_after=(Get-FileHash -Algorithm SHA256 -LiteralPath $latestDemo).Hash
}
[IO.File]::WriteAllText((Join-Path $OutputRoot "phase6gt_summary.json"),($summary|ConvertTo-Json -Depth 16)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$state.last_operation_marker = $lastOperationMarker
Write-Phase6gsTerminalState -Path $statePath -State $state -Status $(if($qualified){"qualified_no_later_operation_started"}else{"safe_stop"}) -OperationResult $operationResult -LifecycleResult $lifecycleResult -LastSuccessfulAccessor $lastSuccessfulAccessor
if ($normalizationStatus -ne "pass") { throw "Phase 6GT reporting normalization safe stop: $normalizationError" }
if (-not $qualified) { throw "Phase 6GT safe stop: operation=$operationResult lifecycle=$lifecycleResult" }
