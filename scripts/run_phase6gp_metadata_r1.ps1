param(
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [string]$ContractPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$repo = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6GP refuses artifact root reuse: $OutputRoot" }
$contractPath = if ($ContractPath) { [IO.Path]::GetFullPath($ContractPath) } else { Join-Path $PSScriptRoot "phase6gp_metadata_r1_contract.json" }
$hashPath = [IO.Path]::ChangeExtension($contractPath, ".sha256")
$expectedHash = ((Get-Content -Encoding UTF8 $hashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($actualHash -ne $expectedHash) { throw "Phase 6GP contract hash mismatch" }
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json

New-Item -ItemType Directory -Path $OutputRoot | Out-Null
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
Copy-Item -LiteralPath $hashPath -Destination (Join-Path $OutputRoot "frozen_contract.sha256")
$preflight = Join-Path $OutputRoot "offline-preflight"
New-Item -ItemType Directory -Path $preflight | Out-Null
& python (Join-Path $PSScriptRoot "test_phase6gp_metadata_r1.py") *> (Join-Path $preflight "fixture.log")
if ($LASTEXITCODE -ne 0) { throw "Phase 6GP offline fixture failed before Kit launch" }
[IO.File]::WriteAllText((Join-Path $preflight "result.json"),'{"schema":"campfire.phase6gp.offline-fixture.v1","passed":true,"case_count":15}'+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))

$production = Join-Path $repo "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$latestDemo = Join-Path $repo "docs\devlog\assets\latest_demo.json"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $production).Hash
$demoBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $latestDemo).Hash
$attemptRoot = Join-Path $OutputRoot "formal\R1"
$caseRoot = Join-Path $attemptRoot "S93_support_clear"
$logs = Join-Path $attemptRoot "runner-logs"
New-Item -ItemType Directory -Path $logs | Out-Null
$statePath = Join-Path $OutputRoot "incremental_state.json"
$state = [ordered]@{
    schema="campfire.phase6gp.incremental-state.v1";status="running";active_condition="R1";
    launches=1;maximum_launches=1;phase6go_r0_reclassified=$false;formal_population_started=$false;
    contract_sha256=$actualHash;timestamp_utc=[DateTime]::UtcNow.ToString("o")
}
[IO.File]::WriteAllText($statePath,($state|ConvertTo-Json -Depth 8)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))

$caseRunner = Join-Path $PSScriptRoot "run_phase6fo_supply_case.ps1"
$guard = Join-Path $PSScriptRoot "phase6fu_resource_guard.py"
$probe = Join-Path $PSScriptRoot "probe_phase6gp_metadata_r1.py"
$powershell = (Get-Command powershell.exe).Source
$arguments = @(
    "-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",$caseRunner,
    "-Scenario","production_four","-OutputDir",$caseRoot,"-OffsetM","-0.0125","-SupportRadiusM","0.05",
    "-Filtering","true","-Collision","true","-Policy","allow_self_center","-ReportPhase","phase6gp",
    "-GeometryVariant","phase6er_corrected","-ExpectedGeometryConcept","corrected","-ProbePath",$probe,
    "-SampleFrames","60,120,180,240","-OperationFrames","180","-ReadbackFrames","180",
    "-ReadbackChannels","velocity,temperature,smoke,fuel","-ReadbackMode","p3_spatial_release",
    "-ReferenceDisposal","del","-SynchronousMemoryMarkers","true","-PythonMemoryTelemetry","true",
    "-SpatialCollectorsEnabled","true","-SpatialColliderIndices","0,1,2,3","-SpatialAllChannels",
    "-RunIndex","1","-LifecycleCalibration","-RendererDrainUpdates","8",
    "-LifecycleReferenceReleaseOrder","after_stage_close","-StageCloseTimeoutSeconds","180",
    "-StabilityObservationStartFrame","240","-StabilityObservationExtraSeconds","5",
    "-StabilityActiveBlockSampleSeconds","0.5","-FlowLivenessAudit","true","-StartupProbe","true",
    "-StartupProbeLabel","R1","-StartupFlowAcquirePosition","before_updates",
    "-StartupPreTimelineUpdateCount","12","-StartupExtraUpdateBeforePlayCount","0",
    "-StartupLivenessGate","true","-StartupExpectedFuelSum","1075.2",
    "-StartupExpectedTemperatureSum","2688.0","-StartupExpectedSmokeSum","107.52",
    "-StartupSourceSumTolerance","0.00001","-StartupSourceContractMode","payload_native_float32_v1",
    "-AbsoluteTimeoutSeconds","900","-ImportAuditPath",(Join-Path $caseRoot "kit_import_audit.json"),
    "-PostReadbackIsolationMode","R1","-PostReadbackIsolationChannel","temperature",
    "-PostReadbackIsolationReportPath",(Join-Path $caseRoot "post_readback_isolation.json"),
    "-SkipLowLevelShutdownDiagnostic"
)
$limits = $contract.safety
$guardArgs = @(
    $guard,"--trace",(Join-Path $logs "R1.resource.jsonl"),"--summary",(Join-Path $logs "R1.guard.json"),
    "--stdout",(Join-Path $logs "R1.stdout.log"),"--stderr",(Join-Path $logs "R1.stderr.log"),
    "--timeout-seconds","$($limits.outer_condition_timeout_seconds)","--sample-seconds","$($limits.resource_sampling_seconds)",
    "--runner-private-limit","$($limits.runner_private_limit_bytes)","--diagnostic-private-limit","$($limits.diagnostic_private_limit_bytes)",
    "--kit-private-limit","$($limits.kit_private_limit_bytes)","--tree-private-limit","$($limits.unique_tree_private_limit_bytes)",
    "--available-memory-floor","$($limits.physical_memory_floor_bytes)","--commit-headroom-floor","$($limits.commit_headroom_floor_bytes)",
    "--cpu-telemetry","--gpu-csv",(Join-Path $logs "R1.gpu.csv"),"--gpu-sample-ms","$($limits.gpu_sampling_ms)",
    "--lifecycle-path",(Join-Path $caseRoot "raw.json"),"--diagnostic-marker-path",(Join-Path $caseRoot "resource_markers.jsonl"),
    "--attempt-id","R1","--cleanup-suppression-lock",((Join-Path $caseRoot "sensitive-shutdown-diagnostics")+".ownership.json"),
    "--cleanup-suppression-deadline-seconds","150","--cleanup-marker-path",(Join-Path $logs "cleanup_markers.jsonl"),
    "--",$powershell
) + $arguments
& python @guardArgs
$guardExit = $LASTEXITCODE

$runnerPath = Join-Path $caseRoot "runner_evidence.json"
$guardPath = Join-Path $logs "R1.guard.json"
$operationPath = Join-Path $caseRoot "post_readback_isolation.json"
$runner = if(Test-Path $runnerPath){Get-Content -Raw -Encoding UTF8 $runnerPath|ConvertFrom-Json}else{$null}
$guardReport = if(Test-Path $guardPath){Get-Content -Raw -Encoding UTF8 $guardPath|ConvertFrom-Json}else{$null}
$operation = if(Test-Path $operationPath){Get-Content -Raw -Encoding UTF8 $operationPath|ConvertFrom-Json}else{$null}
$operationComplete = ($null -ne $operation -and $operation.status -eq "pass" -and
    $operation.operation_result -eq "pass" -and $operation.slots.Count -eq 7 -and
    $operation.last_operation_marker -eq "phase6gp_reference_release_after" -and
    $operation.weak_reference_alive_after_release_count -eq 0)
$lifecycleNormal = ($guardExit -eq 0 -and $null -ne $runner -and
    $runner.process_exit_code -eq 0 -and $runner.outcome.lifecycle_status -eq "normal_exit" -and
    $runner.outcome.normal_exit_sample_accepted -and $runner.lifecycle_marker -eq "shutdown_complete")
$cleanupAbsent = ($null -ne $guardReport -and $guardReport.observed_process_cleanup.all_observed_absent)
$resourcePass = ($null -ne $guardReport -and
    $guardReport.peaks.kit -le $limits.kit_private_limit_bytes -and
    $guardReport.peaks.tree -le $limits.unique_tree_private_limit_bytes -and
    $guardReport.peaks.runner -le $limits.runner_private_limit_bytes -and
    $guardReport.peaks.diagnostic -le $limits.diagnostic_private_limit_bytes -and
    $guardReport.machine_minima.available_physical_bytes -ge $limits.physical_memory_floor_bytes -and
    $guardReport.machine_minima.estimated_commit_headroom_bytes -ge $limits.commit_headroom_floor_bytes)
$qualified = $operationComplete -and $lifecycleNormal -and $cleanupAbsent -and $resourcePass
$operationResult = if($operationComplete -and $lifecycleNormal){"pass"}elseif($operationComplete){"partial_operation_evidence"}else{"failure"}
$lifecycleResult = if($lifecycleNormal){"normal_exit"}else{"failure"}
$summary = [ordered]@{
    schema="campfire.phase6gp.metadata-r1-summary.v1";qualified=[bool]$qualified;
    status=if($qualified){"qualified_no_r2_started"}else{"safe_stop"};contract_sha256=$actualHash;
    launches=1;R2_started=$false;formal_nine_process_population_started=$false;
    operation_result=$operationResult;lifecycle_result=$lifecycleResult;
    operation=$operation;process_exit_code=if($runner){$runner.process_exit_code}else{$null};
    lifecycle_marker=if($runner){$runner.lifecycle_marker}else{$null};
    runner_outcome=if($runner){$runner.outcome}else{$null};guard_exit=$guardExit;
    cleanup_all_observed_absent=[bool]$cleanupAbsent;resource_pass=[bool]$resourcePass;
    peaks=if($guardReport){$guardReport.peaks}else{$null};machine_minima=if($guardReport){$guardReport.machine_minima}else{$null};
    low_level_diagnostic_allowed=$false;
    production_sha256_before=$productionBefore;production_sha256_after=(Get-FileHash -Algorithm SHA256 -LiteralPath $production).Hash;
    latest_demo_sha256_before=$demoBefore;latest_demo_sha256_after=(Get-FileHash -Algorithm SHA256 -LiteralPath $latestDemo).Hash
}
[IO.File]::WriteAllText((Join-Path $OutputRoot "phase6gp_summary.json"),($summary|ConvertTo-Json -Depth 16)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$state.status=if($qualified){"qualified_no_r2_started"}else{"safe_stop"}
$state.operation_result=$operationResult;$state.lifecycle_result=$lifecycleResult
$state.last_operation_marker=if($operation){$operation.last_operation_marker}else{$null}
[IO.File]::WriteAllText($statePath,($state|ConvertTo-Json -Depth 8)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
if (-not $qualified) { throw "Phase 6GP safe stop: operation=$operationResult lifecycle=$lifecycleResult" }
