param(
    [string]$OutputDir="",
    [int]$Runs=3,
    [double]$WarmupSeconds=30,
    [double]$MeasureSeconds=60,
    [double]$OverheadWarmupSeconds=30,
    [double]$OverheadMeasureSeconds=30,
    [string]$SmokeCondition="",
    [switch]$SkipOverhead,
    [string]$StatsInventory=""
)
$ErrorActionPreference="Stop"
$processPath=$env:Path
$pathKeys=@([Environment]::GetEnvironmentVariables().Keys|Where-Object{$_ -ieq "path"})
if($pathKeys.Count -gt 1){[Environment]::SetEnvironmentVariable("Path",$null,[EnvironmentVariableTarget]::Process);[Environment]::SetEnvironmentVariable("Path",$processPath,[EnvironmentVariableTarget]::Process)}
$root=Split-Path -Parent $PSScriptRoot
$release=Join-Path $root "_build\windows-x86_64\release"
$kit=Join-Path $release "kit\kit.exe";$app=Join-Path $release "apps\campfire.simulator.kit"
$python=Join-Path $release "kit\python\python.exe";$probe=Join-Path $PSScriptRoot "probe_phasev3th_render_fps.py";$analyzer=Join-Path $PSScriptRoot "analyze_phasev3th_render_fps.py"
$native=Join-Path $root "artifacts\phasev2\native-build\campfire_wood_native.dll"
if(-not(Test-Path $native)){throw "Phase V3T-H requires qualified native library: $native"}
if(-not$OutputDir){$OutputDir=Join-Path $root "artifacts\phasev3th"};$OutputDir=[IO.Path]::GetFullPath($OutputDir)
if(-not$StatsInventory){$StatsInventory=Join-Path $root "artifacts\phasev3th-stats-inventory-smoke\stats_inventory.json"};$StatsInventory=[IO.Path]::GetFullPath($StatsInventory)
if(-not(Test-Path $StatsInventory)){throw "Phase V3T-H requires completed omni.stats inventory: $StatsInventory"}
$inventory=Get-Content -Raw -Encoding UTF8 $StatsInventory|ConvertFrom-Json
if($inventory.status-ne"ok"-or$inventory.analysis.exact_numeric_matches.Count-ne0){throw "Phase V3T-H stats inventory gate failed"}
if(Test-Path (Join-Path $OutputDir "manifest.json")){throw "Phase V3T-H refuses to reuse an existing manifest: $OutputDir"}
New-Item -ItemType Directory -Force $OutputDir|Out-Null
$nvidiaSmi=Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
$stageIdError="IRenderSettings::getRenderSettings failed getting a stage-id"
$fatalTokens=@($stageIdError,"Traceback (most recent call last)","CUDA_ERROR_ILLEGAL_ADDRESS","device lost","invalid pointer","Invoked with: <omni.ui._ui.ImageProvider")

function Assert-NoKit {
    $old=@(Get-CimInstance Win32_Process -Filter "Name='kit.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.ExecutablePath-and([IO.Path]::GetFullPath($_.ExecutablePath)-eq[IO.Path]::GetFullPath($kit))})
    if($old.Count){throw "Phase V3T-H refuses to overlap isolated Kit: $($old.ProcessId -join ',')"}
}

function Invoke-Run {
    param([string]$Condition,[string]$ReadMode,[int]$Run,[string]$Group,[double]$Warmup,[double]$Measure)
    Assert-NoKit
    $name="{0}_{1}_{2}_r{3}" -f $Group,$Condition,$ReadMode,($Run+1);$dir=Join-Path $OutputDir $name
    if(Test-Path $dir){throw "Phase V3T-H refuses to reuse run directory: $dir"};New-Item -ItemType Directory $dir|Out-Null
    $raw=Join-Path $dir "samples.json";$kitLog=Join-Path $dir "kit.log";$gpuCsv=Join-Path $dir "gpu.csv";$processJson=Join-Path $dir "process.json"
    $monitor=$null;$reader=$null;$classification=$null;$exit=$null
    if($nvidiaSmi){$monitor=Start-Process $nvidiaSmi.Source -ArgumentList @("--query-gpu=timestamp,utilization.gpu,memory.used","--format=csv,noheader,nounits","--loop-ms=250") -RedirectStandardOutput $gpuCsv -PassThru -WindowStyle Hidden}
    $started=[DateTimeOffset]::UtcNow
    try{
        $flow=$Condition-ne"flow_off_v3_off";$quitAfterMs=[int][Math]::Ceiling(($Warmup+$Measure+180)*1000)
        $arguments=@($app,"--/app/file/ignoreUnsavedOnExit=true","--/app/quitAfter=$quitAfterMs","--/app/settings/persistent=0","--/app/settings/loadUserConfig=0","--/app/window/hideUi=false","--/app/window/width=1280","--/app/window/height=720","--/app/viewport/defaults/fillViewport=false","--/renderer/multiGpu/enabled=false","--/rtx/flow/enabled=$($flow.ToString().ToLowerInvariant())","--/exts/campfire.app/autoCreateScene=false","--/exts/campfire.app/residentPointApplicationEnabled=false","--/exts/campfire.app/residentPointRigidLayoutEnabled=false","--/exts/campfire.app/woodVisualV3Enabled=false","--/log/file=$kitLog","--/phasev3th/output=$raw","--/phasev3th/condition=$Condition","--/phasev3th/readMode=$ReadMode","--/phasev3th/warmupSeconds=$Warmup","--/phasev3th/measureSeconds=$Measure","--/phasev3th/run=$Run","--/phasev3th/nativeLibrary=$native","--exec",$probe)
        $process=Start-Process $kit -ArgumentList $arguments -PassThru;$deadline=[DateTimeOffset]::UtcNow.AddSeconds($Warmup+$Measure+180)
        while(-not$process.WaitForExit(250)){
            if(-not$reader-and(Test-Path $kitLog)){$stream=[IO.File]::Open($kitLog,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite);$reader=[IO.StreamReader]::new($stream)}
            if($reader){while(-not$reader.EndOfStream){if(($reader.ReadLine()).Contains($stageIdError)){$classification="rtx_stage_id_error";Stop-Process $process.Id -Force;break}}}
            if($classification){break}
            if([DateTimeOffset]::UtcNow-gt$deadline){$classification="timeout";Stop-Process $process.Id -Force;break}
        }
        if(-not$classification){$process.WaitForExit();$process.Refresh();$exit=$process.ExitCode;$classification=if($exit-eq0){"normal"}else{"nonzero_exit"}}
    }finally{if($reader){$reader.Dispose()};if($monitor-and-not$monitor.HasExited){Stop-Process $monitor.Id -Force;Wait-Process $monitor.Id -Timeout 5 -ErrorAction SilentlyContinue}}
    $fatalCounts=[ordered]@{};foreach($token in $fatalTokens){$fatalCounts[$token]=if(Test-Path $kitLog){(Select-String -LiteralPath $kitLog -SimpleMatch $token).Count}else{0}}
    if($fatalCounts[$stageIdError]-gt0){$classification="rtx_stage_id_error"}
    if($classification-ne"normal"){throw "Phase V3T-H process rejected: $name ($classification); stage-id errors=$($fatalCounts[$stageIdError])"}
    if(($fatalCounts.Values|Measure-Object -Sum).Sum-ne0){throw "Phase V3T-H process rejected by fatal-log gate: $name"}
    $payload=Get-Content -Raw -Encoding UTF8 $raw|ConvertFrom-Json;if($payload.status-ne"ok"){throw "Phase V3T-H probe error: $($payload.error)"}
    $gpu=@();if(Test-Path $gpuCsv){$gpu=@(Get-Content $gpuCsv|ForEach-Object{$columns=$_-split',';if($columns.Count-ge3){[pscustomobject]@{time=[DateTimeOffset]::ParseExact($columns[0].Trim(),'yyyy/MM/dd HH:mm:ss.fff',$null);util=[double]$columns[1].Trim();mem=[double]$columns[2].Trim()}}})}
    $measureStart=[DateTimeOffset]::FromUnixTimeMilliseconds([Math]::Floor($payload.measurement.started_wall_ns/1000000));$measureEnd=[DateTimeOffset]::FromUnixTimeMilliseconds([Math]::Ceiling($payload.measurement.ended_wall_ns/1000000));$gpuMeasured=@($gpu|Where-Object{$_.time.ToUniversalTime() -ge $measureStart -and $_.time.ToUniversalTime() -le $measureEnd})
    $record=[ordered]@{name=$name;group=$Group;condition=$Condition;read_mode=$ReadMode;run=$Run+1;classification=$classification;exit_code=$exit;started_utc=$started.ToString('o');elapsed_ms=[Math]::Round(([DateTimeOffset]::UtcNow-$started).TotalMilliseconds,3);samples=$raw;kit_log=$kitLog;fatal_log_counts=$fatalCounts;gpu_csv=if(Test-Path $gpuCsv){$gpuCsv}else{$null};gpu=@{scope="whole process at 250 ms cadence";samples=$gpu.Count;util_mean=if($gpu.Count){[Math]::Round(($gpu.util|Measure-Object -Average).Average,3)}else{$null};util_max=if($gpu.Count){($gpu.util|Measure-Object -Maximum).Maximum}else{$null};memory_min_mib=if($gpu.Count){($gpu.mem|Measure-Object -Minimum).Minimum}else{$null};memory_max_mib=if($gpu.Count){($gpu.mem|Measure-Object -Maximum).Maximum}else{$null};measurement_only=@{samples=$gpuMeasured.Count;util_mean=if($gpuMeasured.Count){[Math]::Round(($gpuMeasured.util|Measure-Object -Average).Average,3)}else{$null};util_max=if($gpuMeasured.Count){($gpuMeasured.util|Measure-Object -Maximum).Maximum}else{$null};memory_min_mib=if($gpuMeasured.Count){($gpuMeasured.mem|Measure-Object -Minimum).Minimum}else{$null};memory_max_mib=if($gpuMeasured.Count){($gpuMeasured.mem|Measure-Object -Maximum).Maximum}else{$null}}}}
    [IO.File]::WriteAllText($processJson,($record|ConvertTo-Json -Depth 8)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false));return [pscustomobject]$record
}

$allConditions=@("flow_off_v3_off","flow_on_v3_off","flow_on_v3_cpu")
if($SmokeCondition){if($SmokeCondition -notin $allConditions){throw "invalid smoke condition: $SmokeCondition"};$conditions=@($SmokeCondition);$Runs=1;$SkipOverhead=$true}else{$conditions=$allConditions}
$entries=[Collections.Generic.List[object]]::new()
for($run=0;$run-lt$Runs;$run++){$offset=$run%$conditions.Count;$ordered=if($offset-eq0){$conditions}else{@($conditions[$offset..($conditions.Count-1)]+$conditions[0..($offset-1)])};foreach($condition in $ordered){$entries.Add((Invoke-Run $condition "on" $run "formal" $WarmupSeconds $MeasureSeconds))}}
if(-not$SkipOverhead){for($run=0;$run-lt$Runs;$run++){$modes=if(($run%2)-eq0){@("off","on")}else{@("on","off")};foreach($mode in $modes){$entries.Add((Invoke-Run "flow_on_v3_off" $mode $run "overhead" $OverheadWarmupSeconds $OverheadMeasureSeconds))}}}
$manifest=[ordered]@{schema="campfire.phasev3th.visible-viewport-manifest.v2";kit="110.2";flow="110.0.0";resolution=@(1280,720);logs=20;runs=$Runs;conditions=$conditions;warmup_seconds=$WarmupSeconds;measure_seconds=$MeasureSeconds;overhead_warmup_seconds=$OverheadWarmupSeconds;overhead_measure_seconds=$OverheadMeasureSeconds;stats_inventory=@{path=$StatsInventory;scope_count=$inventory.analysis.scope_count;total_node_count=$inventory.analysis.total_node_count;exact_numeric_matches=$inventory.analysis.exact_numeric_matches.Count;conclusion=$inventory.analysis.conclusion};gpu_condition_skipped=$true;gpu_skip_reason="Phase V3T-G did not establish repeated final lifecycle safety";additional_render_product_created=$false;production_changed=$false;entries=$entries}
$manifestPath=Join-Path $OutputDir "manifest.json";[IO.File]::WriteAllText($manifestPath,($manifest|ConvertTo-Json -Depth 10)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false));&$python $analyzer --manifest $manifestPath;if($LASTEXITCODE-ne0){exit $LASTEXITCODE}
