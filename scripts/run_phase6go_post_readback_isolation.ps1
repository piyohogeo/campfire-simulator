param(
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [string]$ContractPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$repo = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6GO refuses artifact root reuse: $OutputRoot" }
$contractPath = if ($ContractPath) { [IO.Path]::GetFullPath($ContractPath) } else { Join-Path $PSScriptRoot "phase6go_post_readback_isolation_contract.json" }
$hashPath = [IO.Path]::ChangeExtension($contractPath, ".sha256")
$expectedHash = ((Get-Content -Encoding UTF8 $hashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($actualHash -ne $expectedHash) { throw "Phase 6GO contract hash mismatch" }
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
Copy-Item -LiteralPath $hashPath -Destination (Join-Path $OutputRoot "frozen_contract.sha256")

$production = Join-Path $repo "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$latestDemo = Join-Path $repo "docs\devlog\assets\latest_demo.json"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $production).Hash
$demoBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $latestDemo).Hash

# Preserve the original Phase 6GN minidump package as immutable input plus a bounded inventory.
$dumpSource = Join-Path $repo $contract.dump_preservation.source
$dumpCopy = Join-Path $OutputRoot "phase6gn-dump-preservation"
New-Item -ItemType Directory -Path $dumpCopy | Out-Null
$dumpInventory = @()
foreach ($file in Get-ChildItem -LiteralPath $dumpSource -File | Sort-Object Name) {
    Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $dumpCopy $file.Name)
    $dumpInventory += [ordered]@{name=$file.Name;bytes=$file.Length;sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash}
}
[IO.File]::WriteAllText((Join-Path $dumpCopy "inventory.json"), ([ordered]@{schema="campfire.phase6go.dump-preservation.v1";source=$dumpSource;original_modified=$false;files=$dumpInventory}|ConvertTo-Json -Depth 6)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))

$preflight = Join-Path $OutputRoot "offline-preflight"
New-Item -ItemType Directory -Path $preflight | Out-Null
& python (Join-Path $PSScriptRoot "test_phase6go_post_readback_isolation.py") *> (Join-Path $preflight "fixture.log")
if ($LASTEXITCODE -ne 0) { throw "Phase 6GO offline fixture failed before Kit launch" }
[IO.File]::WriteAllText((Join-Path $preflight "result.json"),'{"schema":"campfire.phase6go.offline-fixture.v1","passed":true,"case_count":18}'+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))

$guard = Join-Path $PSScriptRoot "phase6fu_resource_guard.py"
$caseRunner = Join-Path $PSScriptRoot "run_phase6fo_supply_case.ps1"
$probe = Join-Path $PSScriptRoot "probe_phase6go_post_readback_isolation.py"
$powershell = (Get-Command powershell.exe).Source
$results = @()
$statePath = Join-Path $OutputRoot "incremental_state.json"

foreach ($spec in $contract.ladder) {
    $attemptId = [string]$spec.id
    $attemptRoot = Join-Path $OutputRoot ("formal\" + $attemptId)
    $caseRoot = Join-Path $attemptRoot "S93_support_clear"
    $logs = Join-Path $attemptRoot "runner-logs"
    New-Item -ItemType Directory -Path $logs | Out-Null
    $state = [ordered]@{schema="campfire.phase6go.incremental-state.v1";status="running";active_condition=$attemptId;completed=@($results|ForEach-Object{$_.condition});contract_sha256=$actualHash;timestamp_utc=[DateTime]::UtcNow.ToString("o")}
    [IO.File]::WriteAllText($statePath,($state|ConvertTo-Json -Depth 8)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
    $arguments = @(
        "-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",$caseRunner,
        "-Scenario","production_four","-OutputDir",$caseRoot,"-OffsetM","-0.0125","-SupportRadiusM","0.05",
        "-Filtering","true","-Collision","true","-Policy","allow_self_center","-ReportPhase","phase6go",
        "-GeometryVariant","phase6er_corrected","-ExpectedGeometryConcept","corrected","-ProbePath",$probe,
        "-SampleFrames","60,120,180,240","-OperationFrames","180","-ReadbackFrames","180",
        "-ReadbackChannels","velocity,temperature,smoke,fuel","-ReadbackMode","p3_spatial_release",
        "-ReferenceDisposal","del","-SynchronousMemoryMarkers","true","-PythonMemoryTelemetry","true",
        "-SpatialCollectorsEnabled","true","-SpatialColliderIndices","0,1,2,3","-SpatialAllChannels",
        "-RunIndex","1","-LifecycleCalibration","-RendererDrainUpdates","8",
        "-LifecycleReferenceReleaseOrder","after_stage_close","-StageCloseTimeoutSeconds","180",
        "-StabilityObservationStartFrame","240","-StabilityObservationExtraSeconds","5",
        "-StabilityActiveBlockSampleSeconds","0.5","-FlowLivenessAudit","true","-StartupProbe","true",
        "-StartupProbeLabel",$attemptId,"-StartupFlowAcquirePosition","before_updates",
        "-StartupPreTimelineUpdateCount","12","-StartupExtraUpdateBeforePlayCount","0",
        "-StartupLivenessGate","true","-StartupExpectedFuelSum","1075.2",
        "-StartupExpectedTemperatureSum","2688.0","-StartupExpectedSmokeSum","107.52",
        "-StartupSourceSumTolerance","0.00001","-StartupSourceContractMode","payload_native_float32_v1",
        "-AbsoluteTimeoutSeconds","900","-ImportAuditPath",(Join-Path $caseRoot "kit_import_audit.json"),
        "-PostReadbackIsolationMode",([string]$spec.mode),"-PostReadbackIsolationChannel",([string]$spec.channel),
        "-PostReadbackIsolationReportPath",(Join-Path $caseRoot "post_readback_isolation.json")
    )
    $limits = $contract.safety
    $guardArgs = @(
        $guard,"--trace",(Join-Path $logs "$attemptId.resource.jsonl"),"--summary",(Join-Path $logs "$attemptId.guard.json"),
        "--stdout",(Join-Path $logs "$attemptId.stdout.log"),"--stderr",(Join-Path $logs "$attemptId.stderr.log"),
        "--timeout-seconds","$($limits.outer_condition_timeout_seconds)","--sample-seconds","$($limits.resource_sampling_seconds)",
        "--runner-private-limit","$($limits.runner_private_limit_bytes)","--diagnostic-private-limit","$($limits.diagnostic_private_limit_bytes)",
        "--kit-private-limit","$($limits.kit_private_limit_bytes)","--tree-private-limit","$($limits.unique_tree_private_limit_bytes)",
        "--available-memory-floor","$($limits.physical_memory_floor_bytes)","--commit-headroom-floor","$($limits.commit_headroom_floor_bytes)",
        "--cpu-telemetry","--gpu-csv",(Join-Path $logs "$attemptId.gpu.csv"),"--gpu-sample-ms","$($limits.gpu_sampling_ms)",
        "--lifecycle-path",(Join-Path $caseRoot "raw.json"),"--diagnostic-marker-path",(Join-Path $caseRoot "resource_markers.jsonl"),
        "--attempt-id",$attemptId,"--cleanup-suppression-lock",((Join-Path $caseRoot "sensitive-shutdown-diagnostics")+".ownership.json"),
        "--cleanup-suppression-deadline-seconds","150","--cleanup-marker-path",(Join-Path $logs "cleanup_markers.jsonl"),
        "--",$powershell
    ) + $arguments
    & python @guardArgs
    $guardExit = $LASTEXITCODE
    $runnerEvidencePath = Join-Path $caseRoot "runner_evidence.json"
    $guardPath = Join-Path $logs "$attemptId.guard.json"
    $isolationPath = Join-Path $caseRoot "post_readback_isolation.json"
    $runner = if(Test-Path $runnerEvidencePath){Get-Content -Raw -Encoding UTF8 $runnerEvidencePath|ConvertFrom-Json}else{$null}
    $guardReport = if(Test-Path $guardPath){Get-Content -Raw -Encoding UTF8 $guardPath|ConvertFrom-Json}else{$null}
    $isolation = if(Test-Path $isolationPath){Get-Content -Raw -Encoding UTF8 $isolationPath|ConvertFrom-Json}else{$null}
    $passed = ($guardExit -eq 0 -and $null -ne $runner -and $null -ne $guardReport -and $null -ne $isolation -and
        $runner.process_exit_code -eq 0 -and $runner.outcome.functional_status -eq "pass" -and
        $runner.outcome.lifecycle_status -eq "normal_exit" -and $runner.outcome.normal_exit_sample_accepted -and
        $runner.dump_inventory.Count -eq 0 -and $isolation.status -eq "pass" -and
        $guardReport.observed_process_cleanup.all_observed_absent)
    $result = [ordered]@{
        condition=$attemptId;mode=[string]$spec.mode;channel=[string]$spec.channel;passed=[bool]$passed;
        guard_exit=$guardExit;process_exit_code=if($runner){$runner.process_exit_code}else{$null};
        functional=if($runner){$runner.outcome.functional_status}else{"missing"};
        lifecycle=if($runner){$runner.outcome.lifecycle_status}else{"missing"};
        last_checkpoint=if($isolation){$isolation.last_checkpoint}else{$null};
        dump_count=if($runner){$runner.dump_inventory.Count}else{$null};
        cleanup_absent=if($guardReport){$guardReport.observed_process_cleanup.all_observed_absent}else{$false};
        peaks=if($guardReport){$guardReport.peaks}else{$null};
        machine_minima=if($guardReport){$guardReport.machine_minima}else{$null}
    }
    $results += [pscustomobject]$result
    [IO.File]::WriteAllText((Join-Path $attemptRoot "condition_summary.json"),($result|ConvertTo-Json -Depth 10)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
    if (-not $passed) {
        $state.status="safe_stop";$state.stop_reason="first_nonreplaceable_failure";$state.last_checkpoint=$result.last_checkpoint
        [IO.File]::WriteAllText($statePath,($state|ConvertTo-Json -Depth 8)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
        break
    }
}

$allPassed = $results.Count -eq $contract.ladder.Count -and @($results|Where-Object{-not $_.passed}).Count -eq 0
$summary = [ordered]@{
    schema="campfire.phase6go.post-readback-isolation-summary.v1";qualified=$allPassed;
    status=if($allPassed){"qualified_no_formal_population_started"}else{"safe_stop"};
    contract_sha256=$actualHash;conditions_planned=$contract.ladder.Count;conditions_launched=$results.Count;
    results=$results;formal_nine_process_population_started=$false;
    production_sha256_before=$productionBefore;production_sha256_after=(Get-FileHash -Algorithm SHA256 -LiteralPath $production).Hash;
    latest_demo_sha256_before=$demoBefore;latest_demo_sha256_after=(Get-FileHash -Algorithm SHA256 -LiteralPath $latestDemo).Hash
}
[IO.File]::WriteAllText((Join-Path $OutputRoot "phase6go_summary.json"),($summary|ConvertTo-Json -Depth 14)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
if (-not $allPassed) { throw "Phase 6GO safe stop: first failed isolation condition" }
