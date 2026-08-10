param(
    [string]$OutputDir="",
    [double]$WarmupSeconds=15,
    [double]$SampleSeconds=5
)
$ErrorActionPreference="Stop"
$root=Split-Path -Parent $PSScriptRoot
$release=Join-Path $root "_build\windows-x86_64\release"
$kit=Join-Path $release "kit\kit.exe";$app=Join-Path $release "apps\campfire.simulator.kit"
$python=Join-Path $release "kit\python\python.exe";$probe=Join-Path $PSScriptRoot "probe_phasev3th_stats_inventory.py";$analyzer=Join-Path $PSScriptRoot "analyze_phasev3th_stats_inventory.py"
if(-not$OutputDir){$OutputDir=Join-Path $root "artifacts\phasev3th-stats-inventory"};$OutputDir=[IO.Path]::GetFullPath($OutputDir);New-Item -ItemType Directory -Force $OutputDir|Out-Null
$raw=Join-Path $OutputDir "stats_inventory.json";$log=Join-Path $OutputDir "kit.log";Remove-Item $raw,$log -Force -ErrorAction SilentlyContinue
$quitAfter=[int][Math]::Ceiling(($WarmupSeconds+$SampleSeconds+180)*1000)
$arguments=@($app,"--/app/file/ignoreUnsavedOnExit=true","--/app/quitAfter=$quitAfter","--/app/settings/persistent=0","--/app/settings/loadUserConfig=0","--/app/window/hideUi=false","--/app/window/width=1280","--/app/window/height=720","--/app/viewport/defaults/fillViewport=false","--/renderer/multiGpu/enabled=false","--/rtx/flow/enabled=true","--/exts/campfire.app/autoCreateScene=false","--/exts/campfire.app/woodVisualV3Enabled=false","--/log/file=$log","--/phasev3th/output=$raw","--/phasev3th/warmupSeconds=$WarmupSeconds","--/phasev3th/sampleSeconds=$SampleSeconds","--exec",$probe)
$process=Start-Process $kit -ArgumentList $arguments -PassThru
$stageIdError="IRenderSettings::getRenderSettings failed getting a stage-id";$reader=$null;$failed=$false;$deadline=[DateTimeOffset]::UtcNow.AddSeconds($WarmupSeconds+$SampleSeconds+180)
try{
    while(-not$process.WaitForExit(250)){
        if(-not$reader-and(Test-Path $log)){$stream=[IO.File]::Open($log,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite);$reader=[IO.StreamReader]::new($stream)}
        if($reader){while(-not$reader.EndOfStream){if(($reader.ReadLine()).Contains($stageIdError)){$failed=$true;break}}}
        if($failed){Stop-Process $process.Id -Force;break}
        if([DateTimeOffset]::UtcNow-gt$deadline){Stop-Process $process.Id -Force;throw "Phase V3T-H stats inventory timed out"}
    }
}finally{if($reader){$reader.Dispose()}}
if($failed){throw "Phase V3T-H fail-fast: $stageIdError"}
$process.WaitForExit();$process.Refresh();if($process.ExitCode-ne0){throw "Phase V3T-H stats inventory exit $($process.ExitCode)"}
if((Select-String -LiteralPath $log -SimpleMatch $stageIdError).Count){throw "Phase V3T-H rejected after exit: $stageIdError"}
&$python $analyzer --input $raw;if($LASTEXITCODE-ne0){exit $LASTEXITCODE}
