param(
    [string]$OutputDir="",
    [ValidateSet("Preflight","Formal")][string]$Mode="Preflight",
    [int]$Runs=1,
    [double]$WarmupSeconds=10,
    [double]$MeasureSeconds=10,
    [string[]]$Conditions=@(),
    [ValidateSet("ProductionCapped","Uncapped240")][string]$RateMode="Uncapped240"
)
$ErrorActionPreference="Stop"
$processPath=$env:Path
$pathKeys=@([Environment]::GetEnvironmentVariables().Keys|Where-Object{$_ -ieq "path"})
if($pathKeys.Count-gt1){[Environment]::SetEnvironmentVariable("Path",$null,[EnvironmentVariableTarget]::Process);[Environment]::SetEnvironmentVariable("Path",$processPath,[EnvironmentVariableTarget]::Process)}
$root=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
$release=Join-Path $root "_build\windows-x86_64\release"
$kit=Join-Path $release "kit\kit.exe"
$app=New-CampfireIsolatedKitApp -SourceApp (Join-Path $release "apps\campfire.simulator.kit")
$probe=Join-Path $PSScriptRoot "probe_phasev3to_uncapped_budget.py"
$dumpAnalyzer=Join-Path $PSScriptRoot "analyze_phasev3tl_native_dump.py"
if(-not$OutputDir){$OutputDir=Join-Path $root ("artifacts\phasev3to-"+$Mode.ToLowerInvariant()+"-"+$RateMode.ToLowerInvariant())}
$OutputDir=[IO.Path]::GetFullPath($OutputDir)
if(Test-Path $OutputDir){throw "Phase V3T-O refuses to reuse output: $OutputDir"}
New-Item -ItemType Directory -Path $OutputDir|Out-Null
$allowedConditions=@("ground_stones_lit","cylinder20_solid","v3mesh20_static_texture","flow_volume")
if(-not$Conditions.Count){$Conditions=$allowedConditions}
foreach($condition in $Conditions){if($condition-notin$allowedConditions){throw "Invalid Phase V3T-O condition: $condition"}}
if($Mode-eq"Preflight"){$Runs=1}
$nvidiaSmi=Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
$fatalTokens=@(
    "IRenderSettings::getRenderSettings failed getting a stage-id",
    "Traceback (most recent call last)","ModuleNotFoundError:","SyntaxError:",
    "CUDA_ERROR_ILLEGAL_ADDRESS","device lost","invalid pointer",
    "[crash] A crash has occurred"
)

function Assert-NoKit {
    $old=@(Get-CimInstance Win32_Process -Filter "Name='kit.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.ExecutablePath-and([IO.Path]::GetFullPath($_.ExecutablePath)-eq[IO.Path]::GetFullPath($kit))})
    if($old.Count){throw "Phase V3T-O refuses to overlap isolated Kit: $($old.ProcessId -join ',')"}
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

function Invoke-IsolatedRun([string]$Condition,[int]$Run) {
    Assert-NoKit
    $name="{0}_rate-{1}_r{2}" -f $Condition,$RateMode.ToLowerInvariant(),($Run+1)
    $dir=Join-Path $OutputDir $name;New-Item -ItemType Directory -Path $dir|Out-Null
    $raw=Join-Path $dir "samples.json";$log=Join-Path $dir "kit.log";$gpuCsv=Join-Path $dir "gpu.csv";$processJson=Join-Path $dir "process.json"
    $dumpDir=Join-Path $dir "sensitive-crash-dumps";$lifecycle=Join-Path $dir "lifecycle.jsonl"
    $monitor=$null;$reader=$null;$classification=$null;$exitCode=$null
    if($nvidiaSmi){
        $query="--query-gpu=timestamp,utilization.gpu,memory.used,clocks.gr,clocks.sm,clocks.mem,pstate,power.draw,temperature.gpu,power.limit,enforced.power.limit,clocks_throttle_reasons.active"
        $monitor=Start-Process $nvidiaSmi.Source -ArgumentList @($query,"--format=csv,noheader,nounits","--loop-ms=250") -RedirectStandardOutput $gpuCsv -PassThru -WindowStyle Hidden
    }
    $started=[DateTimeOffset]::UtcNow
    try{
        $quitAfterMs=[int][Math]::Ceiling(($WarmupSeconds+$MeasureSeconds+300)*1000)
        $flowEnabled=$Condition-eq"flow_volume"
        $rateArgs=if($RateMode-eq"Uncapped240"){@(
            "--/app/runLoops/main/rateLimitEnabled=true","--/app/runLoops/main/rateLimitFrequency=240",
            "--/app/runLoops/rendering_0/rateLimitEnabled=true","--/app/runLoops/rendering_0/rateLimitFrequency=240",
            "--/persistent/app/viewport/defaults/tickRate=240"
        )}else{@()}
        $args=@(
            $app,"--/app/file/ignoreUnsavedOnExit=true","--/app/quitAfter=$quitAfterMs",
            "--/app/settings/persistent=0","--/app/settings/loadUserConfig=0",
            "--/app/window/hideUi=false","--/app/window/width=1280","--/app/window/height=720",
            "--/app/viewport/defaults/fillViewport=false","--/renderer/multiGpu/enabled=false",
            "--/rtx/ecoMode/enabled=false","--/rtx/rendermode=RealTimePathTracing",
            "--/rtx/post/aa/op=3","--/rtx/post/dlss/execMode=0","--/rtx/rtpt/maxBounces=2",
            "--/rtx/flow/enabled=$($flowEnabled.ToString().ToLowerInvariant())",
            "--/exts/campfire.app/autoCreateScene=false","--/exts/campfire.app/woodVisualV3Enabled=false",
            "--/exts/campfire.app/residentPointApplicationEnabled=false","--/exts/campfire.app/residentPointRigidLayoutEnabled=false",
            "--/log/file=$log","--/phasev3tk/output=$raw","--/phasev3tk/condition=$Condition",
            "--/phasev3tk/aaMode=inherit","--/phasev3tk/warmupSeconds=$WarmupSeconds",
            "--/phasev3tk/measureSeconds=$MeasureSeconds","--/phasev3tk/run=$Run","--exec",$probe
        )+$rateArgs+@(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $dumpDir)
        [IO.File]::WriteAllText($lifecycle,(ConvertTo-Json ([ordered]@{marker="before_kit_start";time=[DateTimeOffset]::UtcNow.ToString('o');condition=$Condition;rate_mode=$RateMode}) -Compress)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
        $process=Start-Process $kit -ArgumentList $args -PassThru
        $deadline=[DateTimeOffset]::UtcNow.AddSeconds($WarmupSeconds+$MeasureSeconds+300)
        while(-not$process.WaitForExit(250)){
            if(-not$reader-and(Test-Path $log)){$stream=[IO.File]::Open($log,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite);$reader=[IO.StreamReader]::new($stream)}
            if($reader){while(-not$reader.EndOfStream){
                $line=$reader.ReadLine()
                foreach($token in $fatalTokens){if($line.Contains($token)){
                    $classification=if($token-eq"[crash] A crash has occurred"){"native_crash_log"}else{"fatal_log:$token"}
                    if($classification-eq"native_crash_log"){
                        $dumpDeadline=[DateTimeOffset]::UtcNow.AddSeconds(30)
                        do{Start-Sleep -Milliseconds 250;$verified=@(Get-CampfireCrashDumpInventory -DumpDir $dumpDir|Where-Object{$_.readable-and$_.sha256})}while(-not$verified.Count-and[DateTimeOffset]::UtcNow-lt$dumpDeadline)
                    }
                    if(-not$process.HasExited){Stop-Process $process.Id -Force};break
                }}
                if($classification){break}
            }}
            if($classification){break}
            if([DateTimeOffset]::UtcNow-gt$deadline){$classification="timeout";Stop-Process $process.Id -Force;break}
        }
        if(-not$classification){$process.WaitForExit();$process.Refresh();$exitCode=$process.ExitCode;$classification=if($exitCode-eq0){"normal"}else{"native_crash_nonzero_exit"}}
        elseif($process.HasExited){$process.Refresh();$exitCode=$process.ExitCode}
    } finally {
        if($reader){$reader.Dispose()}
        if($monitor-and-not$monitor.HasExited){Stop-Process $monitor.Id -Force;Wait-Process $monitor.Id -Timeout 5 -ErrorAction SilentlyContinue}
    }
    $fatal=[ordered]@{};foreach($token in $fatalTokens){$fatal[$token]=if(Test-Path $log){@(Select-String -LiteralPath $log -SimpleMatch $token).Count}else{0}}
    $crashSafety=Get-CampfireCrashSafetyEvidence -LogPath $log -DumpDir $dumpDir
    $uploadAttempts=if(Test-Path $log){@(Select-String -LiteralPath $log -SimpleMatch "Uploading minidump:").Count}else{0}
    $uploadEnabledTrue=if(Test-Path $log){@(Select-String -LiteralPath $log -SimpleMatch "upload enabled:"|Where-Object{$_.Line-match"upload enabled:\s*true"}).Count}else{0}
    if($fatal["[crash] A crash has occurred"]-gt0){$classification="native_crash_log"}
    elseif(@($crashSafety.dump_inventory).Count){$classification="native_crash_reporter_dump"}
    if($classification-ne"normal"-or($fatal.Values|Measure-Object -Sum).Sum-ne0-or$uploadAttempts-ne0-or$uploadEnabledTrue-ne0){
        $rejected=[ordered]@{name=$name;condition=$Condition;rate_mode=$RateMode;classification=$classification;exit_code=$exitCode;fatal_log_counts=$fatal;automatic_upload_attempt_count=$uploadAttempts;crash_reporter=$crashSafety;lifecycle_marker=$lifecycle}
        [IO.File]::WriteAllText($processJson,($rejected|ConvertTo-Json -Depth 20)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
        throw "Phase V3T-O rejected $name ($classification); matrix stopped without retry: $processJson"
    }
    $payload=Get-Content -Raw -Encoding UTF8 $raw|ConvertFrom-Json
    if($payload.status-ne"ok"){throw "Phase V3T-O probe failed: $($payload.error)"}
    $paths=$payload.settings_before.requested_paths
    $expectedRate=if($RateMode-eq"Uncapped240"){240.0}else{120.0}
    $expectedMainRate=if($Condition-eq"flow_volume"){60.0}else{$expectedRate}
    if(-not[bool]$paths.'/app/runLoops/main/rateLimitEnabled'-or[double]$paths.'/app/runLoops/main/rateLimitFrequency'-ne$expectedMainRate){throw "Phase V3T-O main rate mismatch: $($paths|ConvertTo-Json -Compress)"}
    if(-not[bool]$paths.'/app/runLoops/rendering_0/rateLimitEnabled'-or[double]$paths.'/app/runLoops/rendering_0/rateLimitFrequency'-ne$expectedRate){throw "Phase V3T-O rendering rate mismatch"}
    if([double]$paths.'/persistent/app/viewport/defaults/tickRate'-ne$expectedRate){throw "Phase V3T-O viewport tick-rate mismatch"}
    if([int]$paths.'/rtx/post/aa/op'-ne3-or[int]$paths.'/rtx/post/dlss/execMode'-ne0-or[int]$paths.'/rtx/rtpt/maxBounces'-ne2){throw "Phase V3T-O Candidate Performance mismatch"}
    $m=$payload.measurement
    $measureStart=[DateTimeOffset]::FromUnixTimeMilliseconds([Math]::Floor($m.started_wall_ns/1000000));$measureEnd=[DateTimeOffset]::FromUnixTimeMilliseconds([Math]::Ceiling($m.ended_wall_ns/1000000))
    $gpu=Read-GpuCsv $gpuCsv $measureStart $measureEnd
    if($gpu.enforced_power_limit_w-ne$null-and[double]$gpu.enforced_power_limit_w-ne210.0){throw "Phase V3T-O power limit changed: $($gpu.enforced_power_limit_w) W"}
    $frameDelta=[double]$m.final_frame_info.frame_number-[double]$m.initial_frame_info.frame_number
    if($frameDelta-le0){throw "Phase V3T-O visible viewport produced no frames: $name"}
    $hud=@($m.hud_fps_values|Where-Object{$_-gt0});$timelineDelta=[double]$m.timeline_seconds_end-[double]$m.timeline_seconds_start
    $fps=[Math]::Round($frameDelta/[double]$m.wall_seconds,3)
    $metrics=[ordered]@{average_visible_fps=$fps;frame_time_ms=[Math]::Round(1000.0/$fps,4);hud_fps_mean=$(if($hud.Count){[Math]::Round(($hud|Measure-Object -Average).Average,3)}else{$null});kit_updates_per_second=[Math]::Round([double]$m.kit_update_count/[double]$m.wall_seconds,3);timeline_sim_per_wall=[Math]::Round($timelineDelta/[double]$m.wall_seconds,5);display_present_fps=$null;raw_frame_p95_ms=$null;raw_frame_p99_ms=$null;gpu_render_time_ms=$null;gpu_render_time_status="unavailable through confirmed public Kit 110.2 viewport/stats boundary"}
    $record=[ordered]@{name=$name;condition=$Condition;rate_mode=$RateMode;run=$Run+1;classification=$classification;exit_code=$exitCode;started_utc=$started.ToString('o');samples=$raw;kit_log=$log;gpu_csv=$gpuCsv;fatal_log_counts=$fatal;automatic_upload_attempt_count=$uploadAttempts;crash_reporter=$crashSafety;metrics=$metrics;gpu=$gpu;stage=$payload.stage;effective_settings=$payload.settings_before;flow_main_rate_override_observed=($Condition-eq"flow_volume"-and$expectedRate-ne$expectedMainRate);metric_contract=$payload.metric_contract;production_changed=$false}
    [IO.File]::WriteAllText($processJson,($record|ConvertTo-Json -Depth 24)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
    Write-Host ("{0}: {1} FPS / {2} ms, updates={3}, GPU={4}% {5}W" -f $name,$fps,$metrics.frame_time_ms,$metrics.kit_updates_per_second,$gpu.utilization_mean_percent,$gpu.power_mean_w)
    return [pscustomobject]$record
}

$entries=[Collections.Generic.List[object]]::new();$jobs=@($Conditions)
for($run=0;$run-lt$Runs;$run++){$offset=$run%$jobs.Count;$ordered=if($offset-eq0){$jobs}else{@($jobs[$offset..($jobs.Count-1)]+$jobs[0..($offset-1)])};foreach($condition in $ordered){$entries.Add((Invoke-IsolatedRun $condition $run))}}
    $manifest=[ordered]@{schema="campfire.phasev3to.uncapped-budget-manifest.v1";phase="V3T-O";mode=$Mode;runs=$Runs;rate_mode=$RateMode;warmup_seconds=$WarmupSeconds;measure_seconds=$MeasureSeconds;conditions=$Conditions;candidate_performance=[ordered]@{renderer="RTX Real-Time 2.0";aa_op=3;dlss_exec_mode=0;rtpt_max_bounces=2;ao="unchanged"};rate_contract=[ordered]@{requested_main_hz=if($RateMode-eq"Uncapped240"){240}else{120};flow_effective_main_hz=60;rendering_hz=if($RateMode-eq"Uncapped240"){240}else{120};viewport_tick_hz=if($RateMode-eq"Uncapped240"){240}else{120};present="inherited production setting and not overridden"};power_limit_w=210;resolution=@(1280,720);additional_render_product_created=$false;hydra_texture_created=$false;capture_or_encode_used=$false;production_changed=$false;entries=$entries}
$manifestPath=Join-Path $OutputDir "manifest.json";[IO.File]::WriteAllText($manifestPath,($manifest|ConvertTo-Json -Depth 26)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false));Write-Host "Phase V3T-O complete: $manifestPath"
