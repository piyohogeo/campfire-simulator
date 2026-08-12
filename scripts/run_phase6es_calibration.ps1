param([Parameter(Mandatory=$true)][string]$OutputRoot)
$ErrorActionPreference="Stop";Set-StrictMode -Version 3.0
$root=Split-Path -Parent $PSScriptRoot;$OutputRoot=[IO.Path]::GetFullPath($OutputRoot)
if(Test-Path -LiteralPath $OutputRoot){throw "Phase 6ES refuses calibration root reuse: $OutputRoot"}
New-Item -ItemType Directory -Path $OutputRoot|Out-Null
$contractPath=Join-Path $PSScriptRoot "phase6es_calibration_contract.json"
$expected=((Get-Content -Raw -Encoding ASCII (Join-Path $PSScriptRoot "phase6es_calibration_contract.sha256")).Trim().Split(' ')[0]).ToUpperInvariant()
$actual=(Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash;if($expected -ne $actual){throw "Phase 6ES calibration contract hash mismatch"}
$contract=Get-Content -Raw -Encoding UTF8 $contractPath|ConvertFrom-Json
$caseRunner=Join-Path $PSScriptRoot "run_phase6ep_point_collision_case.ps1";$guardTool=Join-Path $PSScriptRoot "phase6eg_resource_guard.py";$transport=Join-Path $PSScriptRoot "phase6es_directional_transport.py"
$productionApp=Join-Path $root "_build\windows-x86_64\release\apps\campfire.simulator.kit";$productionBefore=(Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$powershell=(Get-Process -Id $PID).Path;$logs=Join-Path $OutputRoot "runner-logs";New-Item -ItemType Directory -Path $logs|Out-Null
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "predeclared_calibration_contract.json")
foreach($condition in $contract.conditions){
 $name=[string]$condition.name;$case=Join-Path $OutputRoot "calibration\$name";$stdout=Join-Path $logs "$name.stdout.log";$stderr=Join-Path $logs "$name.stderr.log";$trace=Join-Path $logs "$name.memory.jsonl";$summary=Join-Path $logs "$name.guard.json"
 $scalarCollider=if($condition.scenario -eq "production_four"){"2"}else{"1"}
 $arguments=@("-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",$caseRunner,"-Scenario",$condition.scenario,"-OutputDir",$case,"-OffsetM","$($condition.offset_m)","-SupportRadiusM","0.05","-Filtering",([bool]$condition.filtering).ToString().ToLowerInvariant(),"-Collision",([bool]$condition.collision).ToString().ToLowerInvariant(),"-Policy",$condition.policy,"-ReportPhase","phase6es","-GeometryVariant","phase6er_corrected","-FuelScale","$($condition.fuel_scale)","-TemperatureScale","$($condition.temperature_scale)","-SmokeScale","$($condition.smoke_scale)","-SampleFrames","30,60,90,120,150,180,200","-SpatialAllChannels","-SpatialScalarColliderIndices",$scalarCollider,"-RunIndex","1")
 $limits=$contract.safety;$guardArgs=@($guardTool,"--trace",$trace,"--summary",$summary,"--stdout",$stdout,"--stderr",$stderr,"--timeout-seconds","1200","--runner-private-limit","$($limits.runner_private_limit_bytes)","--diagnostic-private-limit","$($limits.diagnostic_private_limit_bytes)","--kit-private-limit","$($limits.kit_private_limit_bytes)","--tree-private-limit","$($limits.unique_tree_private_limit_bytes)","--available-memory-floor","$($limits.physical_memory_floor_bytes)","--commit-headroom-floor","$($limits.commit_headroom_floor_bytes)","--cpu-telemetry","--lifecycle-path",(Join-Path $case "raw.json"),"--diagnostic-marker-path",((Join-Path $case "sensitive-shutdown-diagnostics")+".markers.jsonl"),"--",$powershell)+$arguments
 & python @guardArgs | Out-Host;if($LASTEXITCODE -ne 0){throw "Phase 6ES calibration runner failed: $name"}
 $guard=Get-Content -Raw -Encoding UTF8 $summary|ConvertFrom-Json;$raw=Get-Content -Raw -Encoding UTF8 (Join-Path $case "raw.json")|ConvertFrom-Json;$evidence=Get-Content -Raw -Encoding UTF8 (Join-Path $case "runner_evidence.json")|ConvertFrom-Json
 if($guard.status -ne "ok" -or -not $guard.process_absent -or $guard.exit_code -ne 0){throw "Phase 6ES calibration resource gate failed: $name"}
 if($raw.status -ne "ok" -or $raw.lifecycle_marker -ne "shutdown_complete" -or $evidence.outcome.lifecycle_status -ne "normal_exit"){throw "Phase 6ES calibration lifecycle gate failed: $name"}
 if(@($evidence.fatal_lines).Count -or @($evidence.dump_inventory).Count -or @($evidence.automatic_upload_attempt_lines).Count -or [bool]$evidence.production_changed){throw "Phase 6ES calibration safety gate failed: $name"}
 & python $transport --condition $case --output (Join-Path $case "directional_transport.json") --plane-offset-m 0.05 | Out-Host;if($LASTEXITCODE -ne 0){throw "Phase 6ES transport analysis failed: $name"}
}
$productionAfter=(Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash;if($productionBefore -ne $productionAfter){throw "Phase 6ES changed production app"}
[IO.File]::WriteAllText((Join-Path $OutputRoot "calibration_complete.json"),([ordered]@{schema="campfire.phase6es.calibration-complete.v1";process_count=5;contract_sha256=$actual;production_app_sha256_before=$productionBefore;production_app_sha256_after=$productionAfter;production_changed=$false}|ConvertTo-Json -Depth 6)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
Write-Host "Phase 6ES calibration complete: 5 independent processes"
