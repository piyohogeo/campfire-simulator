param(
    [string]$OutputDir="",
    [int]$Runs=3,
    [int]$Warmup=6,
    [int]$Updates=30,
    [int]$TimeoutSeconds=240,
    [switch]$Quick
)
$ErrorActionPreference="Stop"
$processPath=$env:Path
$pathKeys=@([Environment]::GetEnvironmentVariables().Keys|Where-Object{$_ -ieq "path"})
if($pathKeys.Count-gt1){[Environment]::SetEnvironmentVariable("Path",$null,[EnvironmentVariableTarget]::Process);[Environment]::SetEnvironmentVariable("Path",$processPath,[EnvironmentVariableTarget]::Process)}
$root=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
if(-not$OutputDir){$OutputDir=Join-Path $root "artifacts\phasev3tj-gpu-revalidation"}
$OutputDir=[IO.Path]::GetFullPath($OutputDir)
if(Test-Path $OutputDir){throw "Phase V3T-J refuses to reuse output: $OutputDir"}
New-Item -ItemType Directory -Path $OutputDir|Out-Null
$release=Join-Path $root "_build\windows-x86_64\release"
$kit=Join-Path $release "kit\kit.exe";$app=Join-Path $release "apps\campfire.simulator.kit"
$app=New-CampfireIsolatedKitApp -SourceApp $app
$probe=Join-Path $PSScriptRoot "probe_phasev3tj_gpu_transport.py"
$extension=Join-Path $PSScriptRoot "phasev3tg_extension"
$tools=Join-Path $root "artifacts\phasev3tj-tools"
& (Join-Path $PSScriptRoot "build_phasev3tj_dump_collector.ps1") -OutputDir $tools
if($LASTEXITCODE-ne0){exit $LASTEXITCODE}
$handler=Join-Path $tools "build\Release\phasev3tj_crash_handler.dll"
$helper=Join-Path $tools "build\Release\phasev3tj_dump_helper.exe"
$kitPython=Join-Path $release "kit\python\python.exe"
$dumpAnalyzer=Join-Path $PSScriptRoot "analyze_phasev3tj_minidump.py"
$nvidiaSmi=Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
$stageIdError="IRenderSettings::getRenderSettings failed getting a stage-id"
$fatalTokens=@($stageIdError,"Traceback (most recent call last)","CUDA_ERROR_ILLEGAL_ADDRESS","device lost","invalid pointer","[crash] A crash has occurred")
if($Quick){$Runs=1;$Warmup=2;$Updates=8}

$commit=(& git -c "safe.directory=$($root.Replace('\','/'))" rev-parse --short HEAD).Trim()
$kitHash=(Get-FileHash -Algorithm SHA256 $kit).Hash.ToLowerInvariant()
$kitVersion=(Get-Item $kit).VersionInfo.FileVersion
$gpuInventory=$null
if($nvidiaSmi){
    $gpuLine=&$nvidiaSmi.Source --query-gpu=name,driver_version,power.limit,enforced.power.limit --format=csv,noheader,nounits
    $parts=$gpuLine -split ','
    if($parts.Count-ge4){$gpuInventory=[ordered]@{name=$parts[0].Trim();driver=$parts[1].Trim();power_limit_w=[double]$parts[2].Trim();enforced_power_limit_w=[double]$parts[3].Trim()}}
}

function Assert-NoKit {
    $existing=@(Get-CimInstance Win32_Process -Filter "Name='kit.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.ExecutablePath-and([IO.Path]::GetFullPath($_.ExecutablePath)-eq[IO.Path]::GetFullPath($kit))})
    if($existing.Count){throw "Phase V3T-J refuses to overlap Kit: $($existing.ProcessId -join ',')"}
}

function Invoke-IsolatedRun([string]$Transport,[string]$Scenario,[int]$Run) {
    Assert-NoKit
    $name="{0}_{1}_r{2}" -f $Transport,$Scenario,($Run+1)
    $dir=Join-Path $OutputDir $name;New-Item -ItemType Directory -Path $dir|Out-Null
    $probeJson=Join-Path $dir "probe.json";$markersPath=Join-Path $dir "markers.jsonl";$kitLog=Join-Path $dir "kit.log"
    $crashJson=Join-Path $dir "crash_handler.json";$processJson=Join-Path $dir "process.json";$dump=Join-Path $dir "kit_access_violation_full.dmp"
    $arguments=@(
        $app,"--no-window","--/app/file/ignoreUnsavedOnExit=true","--/app/quitAfter=180000",
        "--/app/settings/persistent=0","--/app/settings/loadUserConfig=0","--/app/window/hideUi=true",
        "--/app/viewport/defaults/fillViewport=false","--/renderer/multiGpu/enabled=false","--/rtx/flow/enabled=true",
        "--/exts/campfire.app/autoCreateScene=false","--/exts/campfire.app/residentPointApplicationEnabled=false",
        "--/exts/campfire.app/residentPointRigidLayoutEnabled=false","--/exts/campfire.app/woodVisualV3Enabled=false",
        "--ext-folder",$extension,"--enable","omni.campfire.phasev3tg_shutdown","--/log/file=$kitLog",
        "--/phasev3tj/output=$probeJson","--/phasev3tj/markers=$markersPath","--/phasev3tj/transport=$Transport",
        "--/phasev3tj/scenario=$Scenario","--/phasev3tj/warmup=$Warmup","--/phasev3tj/updates=$Updates","--/phasev3tj/run=$Run",
        "--/phasev3tj/crashHandler=$handler","--/phasev3tj/dumpHelper=$helper","--/phasev3tj/crashDump=$dump","--/phasev3tj/crashMetadata=$crashJson",
        "--exec",$probe
    ) + @(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir (Join-Path $dir "sensitive-crash-dumps"))
    $started=[DateTimeOffset]::UtcNow
    $process=Start-Process -FilePath $kit -ArgumentList $arguments -PassThru -WindowStyle Hidden
    if(-not$process.WaitForExit($TimeoutSeconds*1000)){
        Stop-Process -Id $process.Id -Force
        throw "Phase V3T-J Kit timeout: $name"
    }
    $process.WaitForExit();$process.Refresh()
    $exitCode=$process.ExitCode;$exitHex='0x{0:X8}' -f ([int32]$exitCode)
    $markers=@();if(Test-Path $markersPath){$markers=@(Get-Content -Encoding UTF8 $markersPath|Where-Object{$_}|ForEach-Object{$_|ConvertFrom-Json})}
    $last=@($markers|Select-Object -Last 1)
    $publication=@($markers|Where-Object{$_.name-eq"publication_end"}|Select-Object -Last 1)
    $fatal=[ordered]@{};foreach($token in $fatalTokens){$fatal[$token]=$(if(Test-Path $kitLog){(Select-String -LiteralPath $kitLog -SimpleMatch $token).Count}else{0})}
    $dumpRecord=$null
    $crashResult=if(Test-Path $crashJson){Get-Content -Raw -Encoding UTF8 $crashJson|ConvertFrom-Json}else{$null}
    if(Test-Path $dump){
        $dumpValidation=Join-Path $dir "dump_validation.json"
        &$kitPython $dumpAnalyzer --dump $dump --metadata $crashJson --output $dumpValidation
        if($LASTEXITCODE-ne0){throw "Phase V3T-J dump validation failed: $name"}
        $dumpResult=Get-Content -Raw -Encoding UTF8 $dumpValidation|ConvertFrom-Json
        $dumpRecord=[ordered]@{path=$dumpResult.path;sha256=$dumpResult.sha256;size_bytes=$dumpResult.size_bytes;memory64_list_stream_present=$dumpResult.memory64_list_stream_present;git_managed=$false}
    }
    $probeResult=if(Test-Path $probeJson){Get-Content -Raw -Encoding UTF8 $probeJson|ConvertFrom-Json}else{$null}
    $expectedOrder=@("teardown_publication_gate_closed","teardown_publication_rejected","timeline_stop","source_generation_sync_begin","source_generation_sync_end","stage_close_begin","stage_close_end","provider_destroy_begin","provider_destroy_end","gpu_allocation_release_begin","gpu_allocation_release_end","extension_disable_begin","extension_disable_end","normal_quit_posted")
    $markerNames=@($markers.name);$cursor=-1;$orderOk=$true
    foreach($marker in $expectedOrder){$next=[Array]::IndexOf($markerNames,$marker,$cursor+1);if($next-lt0){$orderOk=$false;break};$cursor=$next}
    $classification=if($exitHex-eq"0xC0000005"){"access_violation_0xC0000005"}elseif($exitCode-eq0){"normal"}else{"nonzero_exit"}
    $record=[ordered]@{
        schema="campfire.phasev3tj.process-result.v1";name=$name;transport=$Transport;scenario=$Scenario;run=$Run+1
        started_utc=$started.ToString('o');ended_utc=[DateTimeOffset]::UtcNow.ToString('o');classification=$classification
        simulator_commit=$commit;kit_build_id=$kitHash;kit_file_version=$kitVersion;kit="110.2";flow="110.0.0";rtx="omni.hydra.rtx 1.0.4"
        gpu=$gpuInventory;settings=@{flow_enabled=$true;wood_visual_v3_enabled=$false;gpu_transport_production_enabled=$false;point_enabled=$false;rigid_layout_enabled=$false}
        crash_handler=@{installed=[bool]($markerNames -contains "crash_handler_installed");metadata=$crashResult;scope="isolated target process only";machine_wide_configuration_changed=$false};windows_exit_code=$exitCode;windows_exit_hex=$exitHex
        dump=$dumpRecord;fatal_log_counts=$fatal;marker_count=$markers.Count;last_marker=$(if($last.Count){$last[0].name}else{$null})
        teardown_order_ok=$orderOk;publication=@{revision=$(if($publication.Count){$publication[0].detail.revision}else{$null});slot=$(if($publication.Count){$publication[0].detail.slot}else{$null});fallback_count=$(if($publication.Count){$publication[0].detail.fallback_count}else{$null})}
        probe_status=$(if($probeResult){$probeResult.status}else{$null});probe_json=$(if($probeResult){$probeJson}else{$null});markers=$markersPath;kit_log=$kitLog
    }
    [IO.File]::WriteAllText($processJson,($record|ConvertTo-Json -Depth 12)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
    if($classification-eq"access_violation_0xC0000005"){
        throw "Phase V3T-J captured access violation in $name. Dump retained at $dump; stop for WinDbg analysis."
    }
    if($classification-ne"normal"-or$probeResult.status-ne"ok"-or-not$orderOk){throw "Phase V3T-J lifecycle gate failed: $name ($classification)"}
    if(($fatal.Values|Measure-Object -Sum).Sum-ne0){throw "Phase V3T-J fatal log gate failed: $name"}
    Write-Host "$name normal; markers=$($markers.Count); last=$($record.last_marker)"
    return [pscustomobject]$record
}

$entries=[Collections.Generic.List[object]]::new()
$scenarios=@("normal_exit","timeline_restart","stage_replacement","provider_regeneration","extension_disable","gpu_initialization_failure","publication_failure")
for($run=0;$run-lt$Runs;$run++){
    $entries.Add((Invoke-IsolatedRun "cpu" "normal_exit" $run))
    $offset=$run%$scenarios.Count
    $ordered=if($offset-eq0){$scenarios}else{@($scenarios[$offset..($scenarios.Count-1)]+$scenarios[0..($offset-1)])}
    foreach($scenario in $ordered){$entries.Add((Invoke-IsolatedRun "gpu_ring3" $scenario $run))}
}
$manifest=[ordered]@{
    schema="campfire.phasev3tj.manifest.v1";baseline_commit="a014058";phase1_commit=$commit;kit_build_id=$kitHash
    kit="110.2";flow="110.0.0";rtx="omni.hydra.rtx 1.0.4";gpu=$gpuInventory
    atlas=@{width=120;height=60;textures=2;bytes=57600};logs=20;runs=$Runs;warmup=$Warmup;updates=$Updates
    dump_collection=@{scope="SetUnhandledExceptionFilter installed only by isolated probe in target kit.exe";exception="unhandled 0xC0000005 only";full_memory=$true;machine_wide_configuration_changed=$false;dump_git_managed=$false;external_debugger_attached=$false}
    production_changed=$false;entries=$entries
}
$manifestPath=Join-Path $OutputDir "manifest.json"
[IO.File]::WriteAllText($manifestPath,($manifest|ConvertTo-Json -Depth 14)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
Write-Host "Phase V3T-J GPU revalidation complete: $manifestPath"
