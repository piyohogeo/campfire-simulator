param(
    [string]$OutputDir="",
    [ValidateSet("Preflight","Formal")][string]$Mode="Preflight",
    [int]$Runs=1,
    [double]$WarmupSeconds=10,
    [double]$MeasureSeconds=10,
    [string[]]$StageConditions=@(),
    [string[]]$AaModes=@(),
    [string]$AaSceneCondition="flow_prims_global_off_active",
    [switch]$AaOnly
)
$ErrorActionPreference="Stop"
$processPath=$env:Path
$pathKeys=@([Environment]::GetEnvironmentVariables().Keys|Where-Object{$_ -ieq "path"})
if($pathKeys.Count-gt1){[Environment]::SetEnvironmentVariable("Path",$null,[EnvironmentVariableTarget]::Process);[Environment]::SetEnvironmentVariable("Path",$processPath,[EnvironmentVariableTarget]::Process)}
$root=Split-Path -Parent $PSScriptRoot
$release=Join-Path $root "_build\windows-x86_64\release"
$kit=Join-Path $release "kit\kit.exe"
$app=Join-Path $release "apps\campfire.simulator.kit"
$probe=Join-Path $PSScriptRoot "probe_phasev3tk_rtx_stage_cost.py"
if(-not$OutputDir){$OutputDir=Join-Path $root ("artifacts\phasev3tk-"+$Mode.ToLowerInvariant())}
$OutputDir=[IO.Path]::GetFullPath($OutputDir)
if(Test-Path $OutputDir){throw "Phase V3T-K refuses to reuse output: $OutputDir"}
New-Item -ItemType Directory -Path $OutputDir|Out-Null
$allStages=@(
    "empty_rtx","ground_stones_no_lights","ground_stones_lit","ground_stones_shadows_off",
    "cylinder1_solid","cylinder20_solid","v3mesh20_solid","v3mesh20_static_texture",
    "v3mesh20_dynamic_unprovided","v3mesh20_dynamic_rigid_stopped","v3mesh20_dynamic_rigid_play",
    "flow_prims_disabled","flow_prims_global_off_active","flow_simulation_only","flow_volume"
)
$allAa=@("performance","balanced","quality","auto","dlaa")
if(-not$StageConditions.Count){$StageConditions=$allStages}
foreach($condition in $StageConditions){if($condition-notin$allStages){throw "Invalid Phase V3T-K stage condition: $condition"}}
foreach($aa in $AaModes){if($aa-notin$allAa){throw "Invalid Phase V3T-K AA mode: $aa"}}
if($AaSceneCondition-notin$allStages){throw "Invalid Phase V3T-K AA scene: $AaSceneCondition"}
if($Mode-eq"Preflight"){$Runs=1}
$nvidiaSmi=Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
$fatalTokens=@(
    "IRenderSettings::getRenderSettings failed getting a stage-id",
    "Traceback (most recent call last)","CUDA_ERROR_ILLEGAL_ADDRESS","device lost","invalid pointer"
)

function Assert-NoKit {
    $old=@(Get-CimInstance Win32_Process -Filter "Name='kit.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.ExecutablePath-and([IO.Path]::GetFullPath($_.ExecutablePath)-eq[IO.Path]::GetFullPath($kit))})
    if($old.Count){throw "Phase V3T-K refuses to overlap isolated Kit: $($old.ProcessId -join ',')"}
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
        memory_min_mib=(Min $measured memory);memory_max_mib=(Max $measured memory)
        power_mean_w=(Avg $measured power);power_max_w=(Max $measured power)
        temperature_mean_c=(Avg $measured temperature);temperature_max_c=(Max $measured temperature)
        power_limit_w=$(if($measured.Count){$measured[0].power_limit}else{$null})
        enforced_power_limit_w=$(if($measured.Count){$measured[0].enforced_power_limit}else{$null})
        perfcap_active_values=@($measured.perfcap|Sort-Object -Unique);pstates=@($measured.pstate|Sort-Object -Unique)
        provider_scoped=$false
    }
}

function Invoke-IsolatedRun([string]$Condition,[string]$AaMode,[int]$Run) {
    Assert-NoKit
    $name="{0}_aa-{1}_r{2}" -f $Condition,$AaMode,($Run+1)
    $dir=Join-Path $OutputDir $name;New-Item -ItemType Directory -Path $dir|Out-Null
    $raw=Join-Path $dir "samples.json";$log=Join-Path $dir "kit.log";$gpuCsv=Join-Path $dir "gpu.csv";$processJson=Join-Path $dir "process.json"
    $monitor=$null;$reader=$null;$classification=$null;$exitCode=$null
    if($nvidiaSmi){
        $query="--query-gpu=timestamp,utilization.gpu,memory.used,clocks.gr,clocks.sm,clocks.mem,pstate,power.draw,temperature.gpu,power.limit,enforced.power.limit,clocks_throttle_reasons.active"
        $monitor=Start-Process $nvidiaSmi.Source -ArgumentList @($query,"--format=csv,noheader,nounits","--loop-ms=250") -RedirectStandardOutput $gpuCsv -PassThru -WindowStyle Hidden
    }
    $started=[DateTimeOffset]::UtcNow
    try{
        $quitAfterMs=[int][Math]::Ceiling(($WarmupSeconds+$MeasureSeconds+180)*1000)
        $args=@(
            $app,"--/app/file/ignoreUnsavedOnExit=true","--/app/quitAfter=$quitAfterMs",
            "--/app/settings/persistent=0","--/app/settings/loadUserConfig=0",
            "--/app/window/hideUi=false","--/app/window/width=1280","--/app/window/height=720",
            "--/app/viewport/defaults/fillViewport=false","--/renderer/multiGpu/enabled=false",
            "--/rtx/ecoMode/enabled=false",
            "--/rtx/flow/enabled=false","--/exts/campfire.app/autoCreateScene=false",
            "--/exts/campfire.app/residentPointApplicationEnabled=false",
            "--/exts/campfire.app/residentPointRigidLayoutEnabled=false",
            "--/exts/campfire.app/woodVisualV3Enabled=false",
            "--/log/file=$log","--/phasev3tk/output=$raw","--/phasev3tk/condition=$Condition",
            "--/phasev3tk/aaMode=$AaMode","--/phasev3tk/warmupSeconds=$WarmupSeconds",
            "--/phasev3tk/measureSeconds=$MeasureSeconds","--/phasev3tk/run=$Run","--exec",$probe
        )
        $process=Start-Process $kit -ArgumentList $args -PassThru
        $deadline=[DateTimeOffset]::UtcNow.AddSeconds($WarmupSeconds+$MeasureSeconds+180)
        while(-not$process.WaitForExit(250)){
            if(-not$reader-and(Test-Path $log)){$stream=[IO.File]::Open($log,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite);$reader=[IO.StreamReader]::new($stream)}
            if($reader){while(-not$reader.EndOfStream){$line=$reader.ReadLine();foreach($token in $fatalTokens){if($line.Contains($token)){$classification="fatal_log:$token";Stop-Process $process.Id -Force;break}}if($classification){break}}}
            if($classification){break}
            if([DateTimeOffset]::UtcNow-gt$deadline){$classification="timeout";Stop-Process $process.Id -Force;break}
        }
        if(-not$classification){$process.WaitForExit();$process.Refresh();$exitCode=$process.ExitCode;$classification=if($exitCode-eq0){"normal"}else{"nonzero_exit"}}
    } finally {
        if($reader){$reader.Dispose()}
        if($monitor-and-not$monitor.HasExited){Stop-Process $monitor.Id -Force;Wait-Process $monitor.Id -Timeout 5 -ErrorAction SilentlyContinue}
    }
    $fatal=[ordered]@{};foreach($token in $fatalTokens){$fatal[$token]=if(Test-Path $log){(Select-String -LiteralPath $log -SimpleMatch $token).Count}else{0}}
    if($classification-ne"normal"-or($fatal.Values|Measure-Object -Sum).Sum-ne0){throw "Phase V3T-K rejected $name ($classification): $($fatal|ConvertTo-Json -Compress)"}
    $payload=Get-Content -Raw -Encoding UTF8 $raw|ConvertFrom-Json
    if($payload.status-ne"ok"){throw "Phase V3T-K probe failed: $($payload.error)"}
    $m=$payload.measurement
    $measureStart=[DateTimeOffset]::FromUnixTimeMilliseconds([Math]::Floor($m.started_wall_ns/1000000))
    $measureEnd=[DateTimeOffset]::FromUnixTimeMilliseconds([Math]::Ceiling($m.ended_wall_ns/1000000))
    $gpu=Read-GpuCsv $gpuCsv $measureStart $measureEnd
    $frameDelta=[double]$m.final_frame_info.frame_number-[double]$m.initial_frame_info.frame_number
    if($frameDelta-le0){throw "Phase V3T-K visible viewport produced no frames: $name"}
    $hud=@($m.hud_fps_values|Where-Object{$_-gt0})
    $timelineDelta=[double]$m.timeline_seconds_end-[double]$m.timeline_seconds_start
    $metrics=[ordered]@{
        average_visible_fps=[Math]::Round($frameDelta/[double]$m.wall_seconds,3)
        hud_fps_mean=$(if($hud.Count){[Math]::Round(($hud|Measure-Object -Average).Average,3)}else{$null})
        kit_updates_per_second=[Math]::Round([double]$m.kit_update_count/[double]$m.wall_seconds,3)
        timeline_sim_per_wall=[Math]::Round($timelineDelta/[double]$m.wall_seconds,5)
        display_present_fps=$null;raw_frame_p95_ms=$null;raw_frame_p99_ms=$null;one_percent_low_fps=$null
    }
    $dynamicLines=@(if(Test-Path $log){Select-String -LiteralPath $log -SimpleMatch "campfire_wood_visual_v3"}else{@()})
    $lookupWarnings=@($dynamicLines|Where-Object{$_.Line-match'Warning|Error|fail|missing|resolve|open'})
    $record=[ordered]@{
        name=$name;condition=$Condition;aa_mode=$AaMode;run=$Run+1;classification=$classification;exit_code=$exitCode
        started_utc=$started.ToString('o');samples=$raw;kit_log=$log;gpu_csv=$gpuCsv;fatal_log_counts=$fatal
        dynamic_uri_log_mentions=$dynamicLines.Count;dynamic_uri_warning_or_error_count=$lookupWarnings.Count
        dynamic_uri_warning_lines=@($lookupWarnings|Select-Object -First 20|ForEach-Object{$_.Line})
        metrics=$metrics;gpu=$gpu;stage=$payload.stage;settings_before=$payload.settings_before;settings_after=$payload.settings_after
    }
    [IO.File]::WriteAllText($processJson,($record|ConvertTo-Json -Depth 20)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
    Write-Host ("{0}: FPS={1} HUD={2} GPU={3}% {4}W clock={5}MHz" -f $name,$metrics.average_visible_fps,$metrics.hud_fps_mean,$gpu.utilization_mean_percent,$gpu.power_mean_w,$gpu.graphics_clock_mean_mhz)
    return [pscustomobject]$record
}

$jobs=[Collections.Generic.List[object]]::new()
if(-not$AaOnly){foreach($condition in $StageConditions){$jobs.Add([pscustomobject]@{condition=$condition;aa="inherit"})}}
foreach($aa in $AaModes){$jobs.Add([pscustomobject]@{condition=$AaSceneCondition;aa=$aa})}
if(-not$jobs.Count){throw "Phase V3T-K has no jobs"}
$entries=[Collections.Generic.List[object]]::new()
for($run=0;$run-lt$Runs;$run++){
    $jobArray=@($jobs)
    $offset=$run%$jobArray.Count
    $ordered=if($offset-eq0){$jobArray}else{@($jobArray[$offset..($jobArray.Count-1)]+$jobArray[0..($offset-1)])}
    foreach($job in $ordered){$entries.Add((Invoke-IsolatedRun $job.condition $job.aa $run))}
}
$gpuInventory=$null
if($nvidiaSmi){
    $line=&$nvidiaSmi.Source --query-gpu=name,driver_version,power.limit,enforced.power.limit,temperature.gpu --format=csv,noheader,nounits
    $parts=$line -split ','
    if($parts.Count-ge5){$gpuInventory=[ordered]@{name=$parts[0].Trim();driver=$parts[1].Trim();power_limit_w=[double]$parts[2].Trim();enforced_power_limit_w=[double]$parts[3].Trim();temperature_c=[double]$parts[4].Trim()}}
}
$manifest=[ordered]@{
    schema="campfire.phasev3tk.rtx-stage-cost-manifest.v1";phase="V3T-K";mode=$Mode;runs=$Runs
    warmup_seconds=$WarmupSeconds;measure_seconds=$MeasureSeconds;stage_conditions=$StageConditions
    aa_modes=$AaModes;aa_scene_condition=$AaSceneCondition;gpu_inventory=$gpuInventory
    local_sdk_aa_enum=[ordered]@{performance=0;balanced=1;quality=2;auto=3;dlaa=4;aa_op=3;source="Kit 110.2 omni.rtx.settings.core rt_widgets.py"}
    aa_none_skipped_reason="not exposed as a valid choice by the fixed Kit 110.2 RTX Real-Time DLSS UI"
    power_limit_changed=$false;additional_render_product_created=$false;hydra_texture_created=$false
    capture_or_encode_used=$false;production_changed=$false
    measurement_only_overrides=[ordered]@{"/rtx/ecoMode/enabled"=$false};entries=$entries
}
$manifestPath=Join-Path $OutputDir "manifest.json"
[IO.File]::WriteAllText($manifestPath,($manifest|ConvertTo-Json -Depth 22)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
Write-Host "Phase V3T-K $Mode complete: $manifestPath"
