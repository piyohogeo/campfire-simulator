param(
    [string]$OutputDir="",
    [ValidateSet("Preflight","Formal")][string]$Mode="Preflight",
    [int]$Runs=1,
    [double]$WarmupSeconds=12,
    [double]$MeasureSeconds=12,
    [string[]]$Conditions=@()
)
$ErrorActionPreference="Stop"
$processPath=$env:Path
$pathKeys=@([Environment]::GetEnvironmentVariables().Keys|Where-Object{$_ -ieq "path"})
if($pathKeys.Count -gt 1){[Environment]::SetEnvironmentVariable("Path",$null,[EnvironmentVariableTarget]::Process);[Environment]::SetEnvironmentVariable("Path",$processPath,[EnvironmentVariableTarget]::Process)}
$root=Split-Path -Parent $PSScriptRoot
$release=Join-Path $root "_build\windows-x86_64\release"
$kit=Join-Path $release "kit\kit.exe"
$app=Join-Path $release "apps\campfire.simulator.kit"
$probe=Join-Path $PSScriptRoot "probe_phasev3ti_fps_isolation.py"
if(-not$OutputDir){$OutputDir=Join-Path $root ("artifacts\phasev3ti-"+$Mode.ToLowerInvariant())}
$OutputDir=[IO.Path]::GetFullPath($OutputDir)
if(Test-Path $OutputDir){throw "Phase V3T-I refuses to reuse output: $OutputDir"}
New-Item -ItemType Directory -Path $OutputDir|Out-Null
$nvidiaSmi=Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
$stageIdError="IRenderSettings::getRenderSettings failed getting a stage-id"
$fatalTokens=@($stageIdError,"Traceback (most recent call last)","CUDA_ERROR_ILLEGAL_ADDRESS","device lost","invalid pointer")
$allConditions=@(
    "empty_rtx","current_flow_off","reflection_off","indirect_off","denoiser_on",
    "resolution_640x360","resolution_1920x1080","ui_hidden",
    "flow_simulation_only","flow_volume"
)
if(-not$Conditions.Count){$Conditions=$allConditions}
foreach($condition in $Conditions){if($condition -notin $allConditions){throw "Invalid Phase V3T-I condition: $condition"}}
if($Mode-eq"Preflight"){$Runs=1}

function Assert-NoKit {
    $old=@(Get-CimInstance Win32_Process -Filter "Name='kit.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.ExecutablePath-and([IO.Path]::GetFullPath($_.ExecutablePath)-eq[IO.Path]::GetFullPath($kit))})
    if($old.Count){throw "Phase V3T-I refuses to overlap isolated Kit: $($old.ProcessId -join ',')"}
}

function Get-ConditionConfig([string]$Condition) {
    $width=1280;$height=720;$flow=$false;$hideUi=$false;$extra=@()
    switch($Condition){
        "reflection_off"{$extra+=@("--/rtx/reflections/enabled=false")}
        "indirect_off"{$extra+=@("--/rtx/indirectDiffuse/enabled=false")}
        "denoiser_on"{$extra+=@("--/rtx/realtime/optixDenoiser/enabled=true")}
        "resolution_640x360"{$width=640;$height=360}
        "resolution_1920x1080"{$width=1920;$height=1080}
        "ui_hidden"{$hideUi=$true}
        "flow_simulation_only"{$flow=$true}
        "flow_volume"{$flow=$true}
    }
    return [pscustomobject]@{width=$width;height=$height;flow=$flow;hide_ui=$hideUi;extra=$extra}
}

function Read-GpuCsv([string]$Path,[DateTimeOffset]$Start,[DateTimeOffset]$End) {
    $rows=@()
    if(Test-Path $Path){
        $rows=@(Get-Content $Path|ForEach-Object{
            $columns=$_ -split ','
            if($columns.Count-ge12){
                [pscustomobject]@{
                    time=[DateTimeOffset]::ParseExact($columns[0].Trim(),'yyyy/MM/dd HH:mm:ss.fff',$null)
                    util=[double]$columns[1].Trim();memory=[double]$columns[2].Trim()
                    graphics_clock=[double]$columns[3].Trim();sm_clock=[double]$columns[4].Trim();memory_clock=[double]$columns[5].Trim()
                    pstate=$columns[6].Trim();power=[double]$columns[7].Trim();temperature=[double]$columns[8].Trim()
                    power_limit=[double]$columns[9].Trim();enforced_power_limit=[double]$columns[10].Trim();perfcap=$columns[11].Trim()
                }
            }
        })
    }
    $measured=@($rows|Where-Object{$_.time.ToUniversalTime() -ge $Start -and $_.time.ToUniversalTime() -le $End})
    function Summary($items,[string]$name){if($items.Count){return [Math]::Round(($items.$name|Measure-Object -Average).Average,3)}return $null}
    function Maximum($items,[string]$name){if($items.Count){return ($items.$name|Measure-Object -Maximum).Maximum}return $null}
    function Minimum($items,[string]$name){if($items.Count){return ($items.$name|Measure-Object -Minimum).Minimum}return $null}
    return [ordered]@{
        scope="measurement interval at 250 ms cadence";samples=$measured.Count
        utilization_mean_percent=(Summary $measured "util");utilization_max_percent=(Maximum $measured "util")
        graphics_clock_mean_mhz=(Summary $measured "graphics_clock");sm_clock_mean_mhz=(Summary $measured "sm_clock");memory_clock_mean_mhz=(Summary $measured "memory_clock")
        memory_min_mib=(Minimum $measured "memory");memory_max_mib=(Maximum $measured "memory")
        power_mean_w=(Summary $measured "power");power_max_w=(Maximum $measured "power");temperature_mean_c=(Summary $measured "temperature");temperature_max_c=(Maximum $measured "temperature")
        power_limit_w=$(if($measured.Count){$measured[0].power_limit}else{$null});enforced_power_limit_w=$(if($measured.Count){$measured[0].enforced_power_limit}else{$null})
        perfcap_active_values=@($measured.perfcap|Sort-Object -Unique);pstates=@($measured.pstate|Sort-Object -Unique)
    }
}

function Invoke-IsolatedRun([string]$Condition,[int]$Run) {
    Assert-NoKit
    $config=Get-ConditionConfig $Condition
    $name="{0}_r{1}" -f $Condition,($Run+1)
    $dir=Join-Path $OutputDir $name
    New-Item -ItemType Directory -Path $dir|Out-Null
    $raw=Join-Path $dir "samples.json";$log=Join-Path $dir "kit.log";$gpuCsv=Join-Path $dir "gpu.csv";$processJson=Join-Path $dir "process.json"
    $monitor=$null;$reader=$null;$classification=$null;$exitCode=$null
    if($nvidiaSmi){
        $query="--query-gpu=timestamp,utilization.gpu,memory.used,clocks.gr,clocks.sm,clocks.mem,pstate,power.draw,temperature.gpu,power.limit,enforced.power.limit,clocks_throttle_reasons.active"
        $monitor=Start-Process $nvidiaSmi.Source -ArgumentList @($query,"--format=csv,noheader,nounits","--loop-ms=250") -RedirectStandardOutput $gpuCsv -PassThru -WindowStyle Hidden
    }
    $started=[DateTimeOffset]::UtcNow
    try{
        $quitAfterMs=[int][Math]::Ceiling(($WarmupSeconds+$MeasureSeconds+180)*1000)
        $arguments=@(
            $app,"--/app/file/ignoreUnsavedOnExit=true","--/app/quitAfter=$quitAfterMs",
            "--/app/settings/persistent=0","--/app/settings/loadUserConfig=0",
            "--/app/window/hideUi=$($config.hide_ui.ToString().ToLowerInvariant())",
            "--/app/window/width=$($config.width)","--/app/window/height=$($config.height)",
            "--/app/viewport/defaults/fillViewport=false","--/renderer/multiGpu/enabled=false",
            "--/rtx/flow/enabled=$($config.flow.ToString().ToLowerInvariant())",
            "--/exts/campfire.app/autoCreateScene=false",
            "--/exts/campfire.app/residentPointApplicationEnabled=false",
            "--/exts/campfire.app/residentPointRigidLayoutEnabled=false",
            "--/exts/campfire.app/woodVisualV3Enabled=false",
            "--/log/file=$log","--/phasev3ti/output=$raw","--/phasev3ti/condition=$Condition",
            "--/phasev3ti/width=$($config.width)","--/phasev3ti/height=$($config.height)",
            "--/phasev3ti/warmupSeconds=$WarmupSeconds","--/phasev3ti/measureSeconds=$MeasureSeconds",
            "--/phasev3ti/run=$Run"
        )+$config.extra+@("--exec",$probe)
        $process=Start-Process $kit -ArgumentList $arguments -PassThru
        $deadline=[DateTimeOffset]::UtcNow.AddSeconds($WarmupSeconds+$MeasureSeconds+180)
        while(-not$process.WaitForExit(250)){
            if(-not$reader-and(Test-Path $log)){$stream=[IO.File]::Open($log,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite);$reader=[IO.StreamReader]::new($stream)}
            if($reader){while(-not$reader.EndOfStream){if(($reader.ReadLine()).Contains($stageIdError)){$classification="rtx_stage_id_error";Stop-Process $process.Id -Force;break}}}
            if($classification){break}
            if([DateTimeOffset]::UtcNow-gt$deadline){$classification="timeout";Stop-Process $process.Id -Force;break}
        }
        if(-not$classification){$process.WaitForExit();$process.Refresh();$exitCode=$process.ExitCode;$classification=if($exitCode-eq0){"normal"}else{"nonzero_exit"}}
    } finally {
        if($reader){$reader.Dispose()}
        if($monitor-and-not$monitor.HasExited){Stop-Process $monitor.Id -Force;Wait-Process $monitor.Id -Timeout 5 -ErrorAction SilentlyContinue}
    }
    $fatal=[ordered]@{};foreach($token in $fatalTokens){$fatal[$token]=if(Test-Path $log){(Select-String -LiteralPath $log -SimpleMatch $token).Count}else{0}}
    if($fatal[$stageIdError]-gt0){$classification="rtx_stage_id_error"}
    if($classification-ne"normal"){throw "Phase V3T-I rejected $name ($classification); stage-ID errors=$($fatal[$stageIdError])"}
    if(($fatal.Values|Measure-Object -Sum).Sum-ne0){throw "Phase V3T-I fatal-log gate rejected $name"}
    $payload=Get-Content -Raw -Encoding UTF8 $raw|ConvertFrom-Json
    if($payload.status-ne"ok"){throw "Phase V3T-I probe failed: $($payload.error)"}
    $expectedFlow=$config.flow
    if([bool]$payload.settings_before.'/rtx/flow/enabled' -ne $expectedFlow-or[bool]$payload.settings_after.'/rtx/flow/enabled' -ne $expectedFlow){
        throw "Phase V3T-I Flow setting gate failed: $name expected=$expectedFlow"
    }
    $measurement=$payload.measurement
    $measureStart=[DateTimeOffset]::FromUnixTimeMilliseconds([Math]::Floor($measurement.started_wall_ns/1000000))
    $measureEnd=[DateTimeOffset]::FromUnixTimeMilliseconds([Math]::Ceiling($measurement.ended_wall_ns/1000000))
    $gpu=Read-GpuCsv $gpuCsv $measureStart $measureEnd
    $frameDelta=[double]$measurement.final_frame_info.frame_number-[double]$measurement.initial_frame_info.frame_number
    $hud=@($measurement.hud_fps_values|Where-Object{$_-gt0})
    $timelineDelta=[double]$measurement.timeline_seconds_end-[double]$measurement.timeline_seconds_start
    $visibleFramesAvailable=($measurement.initial_frame_info.frame_number-ge0-and$measurement.final_frame_info.frame_number-ge0-and$frameDelta-gt0)
    if(-not$visibleFramesAvailable-and$Condition-ne"ui_hidden"){
        throw "Phase V3T-I visible viewport did not produce measurable frames: $name"
    }
    $metrics=[ordered]@{
        measurement_status=$(if($visibleFramesAvailable){"measured"}else{"no_visible_frames"})
        average_visible_fps=$(if($visibleFramesAvailable){[Math]::Round($frameDelta/[double]$measurement.wall_seconds,3)}else{$null})
        hud_fps_mean=$(if($hud.Count){[Math]::Round(($hud|Measure-Object -Average).Average,3)}else{$null})
        kit_updates_per_second=[Math]::Round([double]$measurement.kit_update_count/[double]$measurement.wall_seconds,3)
        timeline_sim_per_wall=[Math]::Round($timelineDelta/[double]$measurement.wall_seconds,5)
        raw_frame_p95_ms=$null;raw_frame_p99_ms=$null;display_present_fps=$null
    }
    $record=[ordered]@{name=$name;condition=$Condition;run=$Run+1;classification=$classification;exit_code=$exitCode;started_utc=$started.ToString('o');samples=$raw;kit_log=$log;gpu_csv=$gpuCsv;fatal_log_counts=$fatal;metrics=$metrics;gpu=$gpu}
    [IO.File]::WriteAllText($processJson,($record|ConvertTo-Json -Depth 10)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
    Write-Host ("{0}: visible={1} HUD={2} updates={3} GPU={4}% power={5}W" -f $name,$metrics.average_visible_fps,$metrics.hud_fps_mean,$metrics.kit_updates_per_second,$gpu.utilization_mean_percent,$gpu.power_mean_w)
    return [pscustomobject]$record
}

$entries=[Collections.Generic.List[object]]::new()
for($run=0;$run-lt$Runs;$run++){
    $offset=$run%$Conditions.Count
    $ordered=if($offset-eq0){$Conditions}else{@($Conditions[$offset..($Conditions.Count-1)]+$Conditions[0..($offset-1)])}
    foreach($condition in $ordered){$entries.Add((Invoke-IsolatedRun $condition $run))}
}
$manifest=[ordered]@{
    schema="campfire.phasev3ti.visible-viewport-manifest.v1";phase="V3T-I";mode=$Mode;runs=$Runs
    warmup_seconds=$WarmupSeconds;measure_seconds=$MeasureSeconds;conditions=$Conditions
    hard_fail_stage_id_error=$true;additional_render_product_created=$false;hydra_texture_created=$false;capture_or_encode_used=$false
    power_limit_changed=$false;production_changed=$false;entries=$entries
}
$manifestPath=Join-Path $OutputDir "manifest.json"
[IO.File]::WriteAllText($manifestPath,($manifest|ConvertTo-Json -Depth 12)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
Write-Host "Phase V3T-I $Mode complete: $manifestPath"
