param([Parameter(Mandatory=$true)][string]$OutputRoot)

$ErrorActionPreference="Stop"
Set-StrictMode -Version 3.0
$root=Split-Path -Parent $PSScriptRoot
$OutputRoot=[IO.Path]::GetFullPath($OutputRoot)
if(Test-Path -LiteralPath $OutputRoot){throw "Phase 6ER refuses formal root reuse: $OutputRoot"}
New-Item -ItemType Directory -Path $OutputRoot|Out-Null
$contractPath=Join-Path $PSScriptRoot "phase6er_formal_contract.json"
$hashPath=Join-Path $PSScriptRoot "phase6er_formal_contract.sha256"
$expectedHash=((Get-Content -Raw -Encoding ASCII $hashPath).Trim().Split(' ')[0]).ToUpperInvariant()
$contractHash=(Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if($expectedHash -ne $contractHash){throw "Phase 6ER formal contract hash mismatch"}
$contract=Get-Content -Raw -Encoding UTF8 $contractPath|ConvertFrom-Json
if(-not [bool]$contract.declared_before_formal_runtime){throw "Phase 6ER formal contract is not frozen"}
$caseRunner=Join-Path $PSScriptRoot "run_phase6ep_point_collision_case.ps1"
$guardTool=Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
$conditionGate=Join-Path $PSScriptRoot "gate_phase6er_condition.py"
$pairGate=Join-Path $PSScriptRoot "gate_phase6er_pair.py"
$analyzer=Join-Path $PSScriptRoot "analyze_phase6er_formal.py"
$productionApp=Join-Path $root "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionHashBefore=(Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$powershell=(Get-Process -Id $PID).Path
$runnerLogs=Join-Path $OutputRoot "runner-logs";New-Item -ItemType Directory -Path $runnerLogs|Out-Null
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "predeclared_formal_contract.json")

function Invoke-Phase6ErCase{
    param([string]$Group,[string]$Name,[string]$Scenario,[string]$Policy,[double]$Offset,[string]$Filtering,[string]$Collision,[int]$RunIndex)
    $caseOutput=Join-Path $OutputRoot "$Group\$Name";$stem=(($Group+"_"+$Name)-replace '[\\/]','_')
    $stdout=Join-Path $runnerLogs "$stem.stdout.log";$stderr=Join-Path $runnerLogs "$stem.stderr.log"
    $trace=Join-Path $runnerLogs "$stem.memory.jsonl";$summary=Join-Path $runnerLogs "$stem.guard.json"
    $arguments=@("-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",$caseRunner,
      "-Scenario",$Scenario,"-OutputDir",$caseOutput,"-OffsetM","$Offset","-SupportRadiusM","0.05",
      "-Filtering",$Filtering,"-Collision",$Collision,"-Policy",$Policy,"-ReportPhase","phase6er",
      "-GeometryVariant","phase6er_corrected","-FuelScale","1","-TemperatureScale","1","-SmokeScale","1",
      "-SampleFrames","30,60,90,120,150,180,200","-SpatialAllChannels","-RunIndex","$RunIndex")
    $limits=$contract.safety
    $guardArgs=@($guardTool,"--trace",$trace,"--summary",$summary,"--stdout",$stdout,"--stderr",$stderr,
      "--timeout-seconds","1200","--runner-private-limit","$($limits.runner_private_limit_bytes)",
      "--diagnostic-private-limit","$($limits.diagnostic_private_limit_bytes)","--kit-private-limit","$($limits.kit_private_limit_bytes)",
      "--tree-private-limit","$($limits.unique_tree_private_limit_bytes)","--available-memory-floor","$($limits.physical_memory_floor_bytes)",
      "--commit-headroom-floor","$($limits.commit_headroom_floor_bytes)","--cpu-telemetry","--lifecycle-path",(Join-Path $caseOutput "raw.json"),
      "--diagnostic-marker-path",((Join-Path $caseOutput "sensitive-shutdown-diagnostics")+".markers.jsonl"),"--",$powershell)+$arguments
    & python @guardArgs | Out-Host
    if($LASTEXITCODE -ne 0){throw "Phase 6ER guard/runner failed for $Group/$Name"}
    $guard=Get-Content -Raw -Encoding UTF8 $summary|ConvertFrom-Json
    $raw=Get-Content -Raw -Encoding UTF8 (Join-Path $caseOutput "raw.json")|ConvertFrom-Json
    $evidence=Get-Content -Raw -Encoding UTF8 (Join-Path $caseOutput "runner_evidence.json")|ConvertFrom-Json
    if($guard.status -ne "ok" -or -not $guard.process_absent -or $guard.exit_code -ne 0){throw "Phase 6ER resource gate failed for $Group/$Name"}
    if($raw.status -ne "ok" -or $raw.lifecycle_marker -ne "shutdown_complete"){throw "Phase 6ER functional gate failed for $Group/$Name"}
    if($evidence.outcome.lifecycle_status -ne "normal_exit" -or $evidence.outcome.functional_status -ne "pass"){throw "Phase 6ER lifecycle gate failed for $Group/$Name"}
    if(@($evidence.fatal_lines).Count -or @($evidence.dump_inventory).Count -or @($evidence.automatic_upload_attempt_lines).Count -or [bool]$evidence.production_changed){throw "Phase 6ER safety gate failed for $Group/$Name"}
    & python $conditionGate --condition $caseOutput --contract $contractPath --output (Join-Path $caseOutput "incremental_gate.json") | Out-Host
    if($LASTEXITCODE -ne 0){throw "Phase 6ER incremental gate failed for $Group/$Name"}
    return $caseOutput
}

for($run=1;$run -le 3;$run++){
  foreach($scenario in @($contract.formal_scenarios)){
    $conditions=@{}
    foreach($name in @($contract.formal_orders[$run-1])){
      $definition=$contract.policies.$name;$collision=if($name -eq "collision_off"){"false"}else{"true"}
      $filtering=if($name -eq "collision_off"){"false"}else{"true"};$policy=if($name -eq "collision_off"){"strict_all"}else{$name}
      $group="formal\run_$run\$scenario"
      $conditions[$name]=Invoke-Phase6ErCase -Group $group -Name $name -Scenario $scenario -Policy $policy -Offset ([double]$definition.selected_offset_m) -Filtering $filtering -Collision $collision -RunIndex $run
    }
    foreach($name in @("strict_all","allow_self_support","allow_self_center")){
      & python $pairGate --off $conditions["collision_off"] --candidate $conditions[$name] --contract $contractPath --output (Join-Path $conditions[$name] "pair_gate.json") | Out-Host
      if($LASTEXITCODE -ne 0){throw "Phase 6ER pair gate failed for run $run/$scenario/$name"}
    }
  }
}

$report=Join-Path $OutputRoot "report.json";$svg=Join-Path $OutputRoot "qualification.svg"
& python $analyzer --root $OutputRoot --contract $contractPath --output $report --svg $svg
if($LASTEXITCODE -ne 0){throw "Phase 6ER formal aggregate failed"}
$productionHashAfter=(Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
if($productionHashBefore -ne $productionHashAfter){throw "Phase 6ER changed production app"}
if((Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash -ne $contractHash){throw "Phase 6ER contract changed during run"}
[IO.File]::WriteAllText((Join-Path $OutputRoot "matrix_complete.json"),([ordered]@{schema="campfire.phase6er.matrix-complete.v1";phase="phase6er";qualified=$true;formal_process_count=24;contract_sha256=$contractHash;production_app_sha256_before=$productionHashBefore;production_app_sha256_after=$productionHashAfter;production_changed=$false}|ConvertTo-Json -Depth 8)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
Write-Host "Phase 6ER formal matrix complete: 24 independent processes"
