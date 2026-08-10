param(
    [string]$OutputDir="",
    [ValidateSet("Preflight","Formal")][string]$Mode="Preflight",
    [int]$Runs=1,
    [double]$WarmupSeconds=6,
    [double]$MeasureSeconds=8,
    [double]$SettleSeconds=12,
    [ValidateSet("Performance","AutoBaseline")][string]$RendererPreset="Performance",
    [string[]]$Conditions=@(),
    [string]$ConditionCsv="",
    [string]$SettledTransformsPath=""
)
$ErrorActionPreference="Stop"
$processPath=$env:Path
$pathKeys=@([Environment]::GetEnvironmentVariables().Keys|Where-Object{$_ -ieq "path"})
if($pathKeys.Count-gt1){[Environment]::SetEnvironmentVariable("Path",$null,[EnvironmentVariableTarget]::Process);[Environment]::SetEnvironmentVariable("Path",$processPath,[EnvironmentVariableTarget]::Process)}
$root=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
$release=Join-Path $root "_build\windows-x86_64\release"
$kit=Join-Path $release "kit\kit.exe"
$app=Join-Path $release "apps\campfire.simulator.kit"
$app=New-CampfireIsolatedKitApp -SourceApp $app
$probe=Join-Path $PSScriptRoot "probe_phasev3tm_physx_flow_cost.py"
$dumpAnalyzer=Join-Path $PSScriptRoot "analyze_phasev3tl_native_dump.py"
if(-not$OutputDir){$OutputDir=Join-Path $root ("artifacts\phasev3tm-"+$Mode.ToLowerInvariant())}
$OutputDir=[IO.Path]::GetFullPath($OutputDir)
if(Test-Path $OutputDir){throw "Phase V3T-M refuses to reuse output: $OutputDir"}
New-Item -ItemType Directory -Path $OutputDir|Out-Null

$physxConditions=@(
    "physx_none_stop","physx_none_play","physx_scene_only","physx_kinematic20",
    "physx_dynamic20_sleep","physx_dynamic20_move_no_collision",
    "physx_dynamic20_collision","physx_collapse20"
)
$flowConditions=@(
    "flow_no_prims","flow_empty_xform","flow_all_inactive","flow_simulate_only_no_emitter",
    "flow_offscreen_only","flow_render_only","flow_shadow_raymarch_only",
    "flow_relationship_none","flow_relationship_incremental_unavailable",
    "flow_layer_enabled_only","flow_layer_pathtracing_only","flow_layer_reflections_only",
    "flow_global_off_active","flow_global_on_emitter_off",
    "flow_simulation_active_blocks","flow_volume"
)
$safeFlowConditions=@("flow_no_prims","flow_empty_xform")
$heldConditions=@("flow_layer_translucency_only") + @($flowConditions|Where-Object{$_-notin$safeFlowConditions})
$allConditions=@($physxConditions+$flowConditions|Where-Object{$_-notin$heldConditions})
if($ConditionCsv){$Conditions=@($ConditionCsv.Split(',')|ForEach-Object{$_.Trim()}|Where-Object{$_})}
if(-not$Conditions.Count){$Conditions=$allConditions}
foreach($condition in $Conditions){
    if($condition-in$heldConditions){throw "Phase V3T-M condition is held after a native crash and must not be rerun: $condition"}
    if($condition-notin$physxConditions-and$condition-notin$flowConditions){throw "Invalid Phase V3T-M condition: $condition"}
}
if($Mode-eq"Preflight"){$Runs=1}
$nvidiaSmi=Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
$fatalTokens=@(
    "IRenderSettings::getRenderSettings failed getting a stage-id",
    "Traceback (most recent call last)","CUDA_ERROR_ILLEGAL_ADDRESS","device lost","invalid pointer",
    "[crash] A crash has occurred"
)

function Assert-NoKit {
    $old=@(Get-CimInstance Win32_Process -Filter "Name='kit.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.ExecutablePath-and([IO.Path]::GetFullPath($_.ExecutablePath)-eq[IO.Path]::GetFullPath($kit))})
    if($old.Count){throw "Phase V3T-M refuses to overlap isolated Kit: $($old.ProcessId -join ',')"}
}

function Read-GpuCsv([string]$Path,[DateTimeOffset]$Start,[DateTimeOffset]$End) {
    $rows=@()
    if(Test-Path $Path){$rows=@(Get-Content $Path|ForEach-Object{
        $c=$_ -split ','
        if($c.Count-ge12){[pscustomobject]@{
            time=[DateTimeOffset]::ParseExact($c[0].Trim(),'yyyy/MM/dd HH:mm:ss.fff',$null)
            util=[double]$c[1].Trim();memory=[double]$c[2].Trim();graphics_clock=[double]$c[3].Trim()
            sm_clock=[double]$c[4].Trim();memory_clock=[double]$c[5].Trim();pstate=$c[6].Trim()
            power=[double]$c[7].Trim();temperature=[double]$c[8].Trim();power_limit=[double]$c[9].Trim()
            enforced_power_limit=[double]$c[10].Trim();perfcap=$c[11].Trim()
        }}
    })}
    $measured=@($rows|Where-Object{$_.time.ToUniversalTime()-ge$Start-and$_.time.ToUniversalTime()-le$End})
    function Avg($items,$name){if($items.Count){[Math]::Round(($items.$name|Measure-Object -Average).Average,3)}else{$null}}
    function Max($items,$name){if($items.Count){($items.$name|Measure-Object -Maximum).Maximum}else{$null}}
    function Min($items,$name){if($items.Count){($items.$name|Measure-Object -Minimum).Minimum}else{$null}}
    return [ordered]@{
        scope="whole-GPU nvidia-smi samples within the measurement interval";sample_count=$measured.Count;interval_ms=250
        utilization_mean_percent=(Avg $measured util);utilization_max_percent=(Max $measured util)
        graphics_clock_mean_mhz=(Avg $measured graphics_clock);sm_clock_mean_mhz=(Avg $measured sm_clock);memory_clock_mean_mhz=(Avg $measured memory_clock)
        memory_min_mib=(Min $measured memory);memory_max_mib=(Max $measured memory);memory_span_mib=$(if($measured.Count){(Max $measured memory)-(Min $measured memory)}else{$null})
        power_mean_w=(Avg $measured power);power_max_w=(Max $measured power)
        temperature_mean_c=(Avg $measured temperature);temperature_max_c=(Max $measured temperature)
        power_limit_w=$(if($measured.Count){$measured[0].power_limit}else{$null})
        enforced_power_limit_w=$(if($measured.Count){$measured[0].enforced_power_limit}else{$null})
        perfcap_active_values=@($measured.perfcap|Sort-Object -Unique);pstates=@($measured.pstate|Sort-Object -Unique)
        provider_scoped=$false
    }
}

function Invoke-IsolatedRun([string]$Condition,[int]$Run,[string]$SettledPath) {
    Assert-NoKit
    $name="{0}_preset-{1}_r{2}" -f $Condition,$RendererPreset.ToLowerInvariant(),($Run+1)
    $dir=Join-Path $OutputDir $name;New-Item -ItemType Directory -Path $dir|Out-Null
    $raw=Join-Path $dir "samples.json";$log=Join-Path $dir "kit.log";$gpuCsv=Join-Path $dir "gpu.csv";$processJson=Join-Path $dir "process.json"
    $dumpDir=Join-Path $dir "sensitive-crash-dumps";$lifecycle=Join-Path $dir "lifecycle.jsonl"
    $monitor=$null;$reader=$null;$classification=$null;$exitCode=$null
    if($nvidiaSmi){
        $query="--query-gpu=timestamp,utilization.gpu,memory.used,clocks.gr,clocks.sm,clocks.mem,pstate,power.draw,temperature.gpu,power.limit,enforced.power.limit,clocks_throttle_reasons.active"
        $monitor=Start-Process $nvidiaSmi.Source -ArgumentList @($query,"--format=csv,noheader,nounits","--loop-ms=250") -RedirectStandardOutput $gpuCsv -PassThru -WindowStyle Hidden
    }
    $started=[DateTimeOffset]::UtcNow
    $runWarmup=if($Condition-eq"settle_capture"){$SettleSeconds}else{$WarmupSeconds}
    $runMeasure=if($Condition-eq"settle_capture"){1.0}else{$MeasureSeconds}
    try{
        $quitAfterMs=[int][Math]::Ceiling(($runWarmup+$runMeasure+300)*1000)
        $flowEnabled=$Condition-in@("flow_simulate_only_no_emitter","flow_offscreen_only","flow_render_only","flow_shadow_raymarch_only","flow_layer_enabled_only","flow_global_on_emitter_off","flow_simulation_active_blocks","flow_volume")
        $dlss=if($RendererPreset-eq"Performance"){0}else{3}
        $bounces=if($RendererPreset-eq"Performance"){2}else{4}
        $physicsArgs=if($Condition-in$physxConditions-or$Condition-eq"settle_capture"){@("--/physics/updateToUsd=true","--/physics/fabricEnabled=false")}else{@()}
        $args=@(
            $app,"--/app/file/ignoreUnsavedOnExit=true","--/app/quitAfter=$quitAfterMs",
            "--/app/settings/persistent=0","--/app/settings/loadUserConfig=0",
            "--/app/window/hideUi=false","--/app/window/width=1280","--/app/window/height=720",
            "--/app/viewport/defaults/fillViewport=false","--/renderer/multiGpu/enabled=false",
            "--/rtx/ecoMode/enabled=false","--/rtx/rendermode=RealTimePathTracing",
            "--/rtx/post/aa/op=3","--/rtx/post/dlss/execMode=$dlss","--/rtx/rtpt/maxBounces=$bounces",
            "--/rtx/flow/enabled=$($flowEnabled.ToString().ToLowerInvariant())",
            "--/exts/campfire.app/autoCreateScene=false","--/exts/campfire.app/woodVisualV3Enabled=false",
            "--/exts/campfire.app/residentPointApplicationEnabled=false","--/exts/campfire.app/residentPointRigidLayoutEnabled=false",
            "--/log/file=$log","--/phasev3tm/output=$raw","--/phasev3tm/condition=$Condition",
            "--/phasev3tm/warmupSeconds=$runWarmup","--/phasev3tm/measureSeconds=$runMeasure",
            "--/phasev3tm/run=$Run","--/phasev3tm/settledTransformsPath=$SettledPath",
            "--/phasev3tm/preset=$RendererPreset","--/phasev3tm/lifecycleMarker=$lifecycle","--exec",$probe
        ) + $physicsArgs + @(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $dumpDir)
        $process=Start-Process $kit -ArgumentList $args -PassThru
        $deadline=[DateTimeOffset]::UtcNow.AddSeconds($runWarmup+$runMeasure+300)
        while(-not$process.WaitForExit(250)){
            if(-not$reader-and(Test-Path $log)){$stream=[IO.File]::Open($log,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite);$reader=[IO.StreamReader]::new($stream)}
            if($reader){while(-not$reader.EndOfStream){
                $line=$reader.ReadLine()
                foreach($token in $fatalTokens){if($line.Contains($token)){
                    $classification=if($token-eq"[crash] A crash has occurred"){"native_crash_log"}else{"fatal_log:$token"}
                    if($classification-eq"native_crash_log"){
                        $dumpDeadline=[DateTimeOffset]::UtcNow.AddSeconds(30)
                        do{Start-Sleep -Milliseconds 250;$preserved=@(Get-CampfireCrashDumpInventory -DumpDir $dumpDir);$verified=@($preserved|Where-Object{$_.readable-and$_.sha256})}while(-not$verified.Count-and[DateTimeOffset]::UtcNow-lt$dumpDeadline)
                        if($verified.Count){Start-Sleep -Seconds 2}
                    }
                    if(-not$process.HasExited){Stop-Process $process.Id -Force}
                    break
                }}
                if($classification){break}
            }}
            if($classification){break}
            if([DateTimeOffset]::UtcNow-gt$deadline){$classification="timeout";Stop-Process $process.Id -Force;break}
        }
        if(-not$classification){
            $process.WaitForExit();$process.Refresh();$exitCode=$process.ExitCode
            if($exitCode-eq0){$classification="normal"}
            elseif(Test-Path $raw){
                try{$probeExit=Get-Content -Raw -Encoding UTF8 $raw|ConvertFrom-Json;$classification=if($probeExit.status-eq"error"){"probe_error_exit"}else{"native_crash_nonzero_exit"}}catch{$classification="native_crash_nonzero_exit"}
            }else{$classification="native_crash_nonzero_exit"}
        }
        elseif($process.HasExited){$process.Refresh();$exitCode=$process.ExitCode}
    } finally {
        if($reader){$reader.Dispose()}
        if($monitor-and-not$monitor.HasExited){Stop-Process $monitor.Id -Force;Wait-Process $monitor.Id -Timeout 5 -ErrorAction SilentlyContinue}
    }
    $fatal=[ordered]@{};foreach($token in $fatalTokens){$fatal[$token]=if(Test-Path $log){@(Select-String -LiteralPath $log -SimpleMatch $token).Count}else{0}}
    $crashSafety=Get-CampfireCrashSafetyEvidence -LogPath $log -DumpDir $dumpDir
    $uploadAttempts=if(Test-Path $log){@(Select-String -LiteralPath $log -SimpleMatch "Uploading minidump:").Count}else{0}
    $uploadEnabledTrue=if(Test-Path $log){@(Select-String -LiteralPath $log -SimpleMatch "upload enabled:"|Where-Object{$_.Line-match"upload enabled:\s*true"}).Count}else{0}
    $crashAnalysis=$null
    if(@($crashSafety.dump_inventory).Count){
        $archive=@($crashSafety.dump_inventory|Where-Object{$_.name-match'\.dmp\.zip$'}|Select-Object -First 1)
        if($archive.Count){
            $analysisPath=Join-Path $dir "native_crash_analysis.json"
            & (Join-Path $release "kit\python\python.exe") $dumpAnalyzer $archive[0].path --output $analysisPath
            if($LASTEXITCODE-eq0-and(Test-Path $analysisPath)){$crashAnalysis=Get-Content -Raw -Encoding UTF8 $analysisPath|ConvertFrom-Json}
        }
    }
    $crashEvidence=[ordered]@{upload_attempt_count=$uploadAttempts;upload_enabled_true_count=$uploadEnabledTrue;crash_reporter=$crashSafety;lifecycle_marker=$lifecycle;analysis=$crashAnalysis}
    if($fatal["[crash] A crash has occurred"]-gt0){$classification="native_crash_log"}
    elseif(@($crashSafety.dump_inventory).Count-gt0){$classification="native_crash_reporter_dump"}
    if($classification-ne"normal"-or($fatal.Values|Measure-Object -Sum).Sum-ne0-or$uploadAttempts-ne0-or$uploadEnabledTrue-ne0){
        $rejected=[ordered]@{name=$name;condition=$Condition;preset=$RendererPreset;classification=$classification;exit_code=$exitCode;fatal_log_counts=$fatal;crash_evidence=$crashEvidence}
        [IO.File]::WriteAllText($processJson,($rejected|ConvertTo-Json -Depth 24)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
        throw "Phase V3T-M rejected $name ($classification); dump preserved before matrix stop: $processJson"
    }
    $payload=Get-Content -Raw -Encoding UTF8 $raw|ConvertFrom-Json
    if($payload.status-ne"ok"){throw "Phase V3T-M probe failed: $($payload.error)"}
    $m=$payload.measurement
    $measureStart=[DateTimeOffset]::FromUnixTimeMilliseconds([Math]::Floor($m.started_wall_ns/1000000))
    $measureEnd=[DateTimeOffset]::FromUnixTimeMilliseconds([Math]::Ceiling($m.ended_wall_ns/1000000))
    $gpu=Read-GpuCsv $gpuCsv $measureStart $measureEnd
    if($gpu.enforced_power_limit_w-ne$null-and[double]$gpu.enforced_power_limit_w-ne210.0){throw "Phase V3T-M power limit changed: $($gpu.enforced_power_limit_w) W"}
    $frameDelta=[double]$m.final_frame_info.frame_number-[double]$m.initial_frame_info.frame_number
    if($frameDelta-le0){throw "Phase V3T-M visible viewport produced no frames: $name"}
    $fps=[Math]::Round($frameDelta/[double]$m.wall_seconds,3)
    $hud=@($m.hud_fps_values|Where-Object{$_-gt0})
    $timelineDelta=[double]$m.timeline_seconds_end-[double]$m.timeline_seconds_start
    $metrics=[ordered]@{
        average_visible_fps=$fps;frame_time_ms=[Math]::Round(1000.0/$fps,4)
        hud_fps_mean=$(if($hud.Count){[Math]::Round(($hud|Measure-Object -Average).Average,3)}else{$null})
        kit_updates_per_second=[Math]::Round([double]$m.kit_update_count/[double]$m.wall_seconds,3)
        timeline_sim_per_wall=[Math]::Round($timelineDelta/[double]$m.wall_seconds,5)
        display_present_fps=$null;raw_frame_p95_ms=$null;raw_frame_p99_ms=$null
    }
    $record=[ordered]@{
        name=$name;condition=$Condition;preset=$RendererPreset;run=$Run+1;classification=$classification;exit_code=$exitCode
        started_utc=$started.ToString('o');samples=$raw;kit_log=$log;gpu_csv=$gpuCsv;fatal_log_counts=$fatal
        crash_evidence=$crashEvidence;metrics=$metrics;gpu=$gpu;stage=$payload.stage;physx_observation=$payload.physx_observation
        effective_settings=$payload.effective_settings;metric_contract=$payload.metric_contract
    }
    [IO.File]::WriteAllText($processJson,($record|ConvertTo-Json -Depth 24)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
    Write-Host ("{0}: {1} FPS / {2} ms, blocks={3}, changed={4}, contacts={5}" -f $name,$fps,$metrics.frame_time_ms,$payload.stage.flow_active_blocks_peak,$payload.physx_observation.changed_transform_count,$payload.physx_observation.contact_point_count)
    return [pscustomobject]$record
}

$settledPath=$SettledTransformsPath
$settleRecord=$null
if(-not$settledPath){
    $settleRecord=Invoke-IsolatedRun "settle_capture" 0 ""
    $settlePayload=Get-Content -Raw -Encoding UTF8 $settleRecord.samples|ConvertFrom-Json
    $settledPath=Join-Path $OutputDir "settled_transforms.json"
    $settled=[ordered]@{schema="campfire.phasev3tm.settled-transforms.v1";source=$settleRecord.samples;transforms=$settlePayload.settled_transforms.transforms}
    [IO.File]::WriteAllText($settledPath,($settled|ConvertTo-Json -Depth 12)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
} else {$settledPath=[IO.Path]::GetFullPath($settledPath)}

$jobs=@($Conditions)
$entries=[Collections.Generic.List[object]]::new()
for($run=0;$run-lt$Runs;$run++){
    $offset=$run%$jobs.Count
    $ordered=if($offset-eq0){$jobs}else{@($jobs[$offset..($jobs.Count-1)]+$jobs[0..($offset-1)])}
    foreach($condition in $ordered){$entries.Add((Invoke-IsolatedRun $condition $run $settledPath))}
}
$gpuInventory=$null
if($nvidiaSmi){
    $line=&$nvidiaSmi.Source --query-gpu=name,driver_version,power.limit,enforced.power.limit,temperature.gpu --format=csv,noheader,nounits
    $parts=$line -split ','
    if($parts.Count-ge5){$gpuInventory=[ordered]@{name=$parts[0].Trim();driver=$parts[1].Trim();power_limit_w=[double]$parts[2].Trim();enforced_power_limit_w=[double]$parts[3].Trim();temperature_c=[double]$parts[4].Trim()}}
}
$manifest=[ordered]@{
    schema="campfire.phasev3tm.physx-flow-cost-manifest.v1";phase="V3T-M";mode=$Mode;runs=$Runs
    warmup_seconds=$WarmupSeconds;measure_seconds=$MeasureSeconds;settle_seconds=$SettleSeconds
    conditions=$Conditions;physx_conditions=$physxConditions;flow_conditions=$flowConditions;held_conditions=$heldConditions
    settled_transforms=$settledPath;settle_record=$settleRecord;gpu_inventory=$gpuInventory
    preset=[ordered]@{name=$RendererPreset;renderer="RTX Real-Time 2.0";aa_op=3;dlss_exec_mode=$(if($RendererPreset-eq"Performance"){0}else{3});rt2_max_bounces=$(if($RendererPreset-eq"Performance"){2}else{4});ao="unchanged"}
    power_limit_changed=$false;additional_render_product_created=$false;hydra_texture_created=$false
    capture_or_encode_used=$false;production_changed=$false;entries=$entries
}
$manifestPath=Join-Path $OutputDir "manifest.json"
[IO.File]::WriteAllText($manifestPath,($manifest|ConvertTo-Json -Depth 26)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
Write-Host "Phase V3T-M $Mode complete: $manifestPath"
