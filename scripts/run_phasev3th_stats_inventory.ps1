param(
    [string]$OutputDir="",
    [double]$WarmupSeconds=15,
    [double]$SampleSeconds=5
)
$ErrorActionPreference="Stop"
$root=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
$release=Join-Path $root "_build\windows-x86_64\release"
$kit=Join-Path $release "kit\kit.exe";$app=Join-Path $release "apps\campfire.simulator.kit"
$app=New-CampfireIsolatedKitApp -SourceApp $app
$python=Join-Path $release "kit\python\python.exe";$probe=Join-Path $PSScriptRoot "probe_phasev3th_stats_inventory.py";$analyzer=Join-Path $PSScriptRoot "analyze_phasev3th_stats_inventory.py"
if(-not$OutputDir){$OutputDir=Join-Path $root "artifacts\phasev3th-stats-inventory"};$OutputDir=[IO.Path]::GetFullPath($OutputDir);New-Item -ItemType Directory -Force $OutputDir|Out-Null
$raw=Join-Path $OutputDir "stats_inventory.json";$log=Join-Path $OutputDir "kit.log";Remove-Item $raw,$log -Force -ErrorAction SilentlyContinue
$quitAfter=[int][Math]::Ceiling(($WarmupSeconds+$SampleSeconds+180)*1000)
$crashDumpDir=Join-Path $OutputDir "sensitive-crash-dumps"
$arguments=@($app,"--/app/file/ignoreUnsavedOnExit=true","--/app/quitAfter=$quitAfter","--/app/settings/persistent=0","--/app/settings/loadUserConfig=0","--/app/window/hideUi=false","--/app/window/width=1280","--/app/window/height=720","--/app/viewport/defaults/fillViewport=false","--/renderer/multiGpu/enabled=false","--/rtx/flow/enabled=true","--/exts/campfire.app/autoCreateScene=false","--/exts/campfire.app/woodVisualV3Enabled=false","--/log/file=$log","--/phasev3th/output=$raw","--/phasev3th/warmupSeconds=$WarmupSeconds","--/phasev3th/sampleSeconds=$SampleSeconds","--exec",$probe)+@(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $crashDumpDir)
$process=Start-Process $kit -ArgumentList $arguments -PassThru
$fatalTokens=@("IRenderSettings::getRenderSettings failed getting a stage-id","Traceback (most recent call last)","CUDA_ERROR_ILLEGAL_ADDRESS","device lost","invalid pointer","[crash] A crash has occurred")
$reader=$null;$failed=$null;$deadline=[DateTimeOffset]::UtcNow.AddSeconds($WarmupSeconds+$SampleSeconds+180)
try{
    while(-not$process.WaitForExit(250)){
        if(-not$reader-and(Test-Path $log)){$stream=[IO.File]::Open($log,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite);$reader=[IO.StreamReader]::new($stream)}
        if($reader){while(-not$reader.EndOfStream){$line=$reader.ReadLine();foreach($token in $fatalTokens){if($line.Contains($token)){$failed=$token;break}};if($failed){break}}}
        if($failed){if($failed-eq"[crash] A crash has occurred"){Start-Sleep -Seconds 5};if(-not$process.HasExited){Stop-Process $process.Id -Force};break}
        if([DateTimeOffset]::UtcNow-gt$deadline){Stop-Process $process.Id -Force;throw "Phase V3T-H stats inventory timed out"}
    }
}finally{if($reader){$reader.Dispose()}}
if($failed){throw "Phase V3T-H fail-fast: $failed; isolated dump directory preserved at $crashDumpDir"}
$process.WaitForExit();$process.Refresh();if($process.ExitCode-ne0){throw "Phase V3T-H stats inventory exit $($process.ExitCode)"}
foreach($token in $fatalTokens){if((Select-String -LiteralPath $log -SimpleMatch $token).Count){throw "Phase V3T-H rejected after exit: $token"}}
&$python $analyzer --input $raw;if($LASTEXITCODE-ne0){exit $LASTEXITCODE}
