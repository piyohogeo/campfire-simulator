param(
    [Parameter(Mandatory=$true)][ValidateSet("smoke","proxy")][string]$Mode,
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [Parameter(Mandatory=$true)][string]$MarkersPath,
    [Parameter(Mandatory=$true)][string]$RunnerEvidencePath,
    [Parameter(Mandatory=$true)][string]$KitLogPath,
    [Parameter(Mandatory=$true)][string]$KitStdoutPath,
    [Parameter(Mandatory=$true)][string]$KitStderrPath,
    [Parameter(Mandatory=$true)][string]$KitPath,
    [Parameter(Mandatory=$true)][string]$AppPath,
    [Parameter(Mandatory=$true)][string]$ProbePath,
    [Parameter(Mandatory=$true)][string]$ExpectedCampfirePath,
    [Parameter(Mandatory=$true)][string]$ExpectedAnimPath,
    [Parameter(Mandatory=$true)][int]$StageCloseTimeoutSeconds
)

$ErrorActionPreference="Stop"
Set-StrictMode -Version 3.0
$repo=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
. (Join-Path $PSScriptRoot "kit_shutdown_policy.ps1")

# GetFullPath is intentionally lexical here. Do not Resolve-Path: the build tree
# contains reparse points whose build-relative spelling controls Kit extension discovery.
$output=[IO.Path]::GetFullPath($OutputPath);$markers=[IO.Path]::GetFullPath($MarkersPath)
$runnerEvidence=[IO.Path]::GetFullPath($RunnerEvidencePath);$kitLog=[IO.Path]::GetFullPath($KitLogPath)
$kitStdout=[IO.Path]::GetFullPath($KitStdoutPath);$kitStderr=[IO.Path]::GetFullPath($KitStderrPath)
$kit=[IO.Path]::GetFullPath($KitPath);$app=[IO.Path]::GetFullPath($AppPath);$probe=[IO.Path]::GetFullPath($ProbePath)
$attempt=Split-Path -Parent $output;$dumpDir=Join-Path $attempt "sensitive-crash-dumps";$diagnosticDir=Join-Path $attempt "sensitive-shutdown-diagnostics"
$productionApp=Join-Path $repo "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore=(Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$registryBefore=Get-CampfireCrashRegistrySnapshot

$arguments=@($app,"--no-window","--/app/file/ignoreUnsavedOnExit=true","--/app/fastShutdown=0","--/app/quitAfter=300000",
 "--/app/settings/persistent=0","--/app/settings/loadUserConfig=0","--/app/window/hideUi=true","--/app/asyncRendering=false",
 "--/app/useFabricSceneDelegate=true","--/renderer/multiGpu/enabled=false","--/renderer/multiGpu/autoEnable=false",
 "--/renderer/enabled=rtx","--/renderer/active=rtx","--/exts/campfire.app/autoCreateScene=false","--/rtx/flow/enabled=true",
 "--enable","omni.usd","--enable","omni.hydra.rtx","--enable","omni.hydra.usdrt_delegate","--enable","omni.kit.viewport.utility","--enable","omni.flowusd",
 "--/phase6ho/output=$output","--/phase6ho/markers=$markers","--/phase6ho/stageCloseTimeoutSeconds=$StageCloseTimeoutSeconds",
 "--/phase6ho/expectedCampfirePath=$ExpectedCampfirePath","--/phase6ho/expectedAnimPath=$ExpectedAnimPath",
 "--/log/file=$kitLog","--/log/fileLogLevel=Info","--exec",$probe) + @(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $dumpDir)

$process=$null;$monitor=$null;$failure=$null;$exitCode=1
try {
 $process=Start-Process -FilePath $kit -ArgumentList $arguments -WorkingDirectory $repo -PassThru -WindowStyle Hidden -RedirectStandardOutput $kitStdout -RedirectStandardError $kitStderr
 $monitor=Wait-CampfireKitProcessWithShutdownPolicy -Process $process -ExpectedExecutable $kit -LifecyclePath $output -LogPath $kitLog -DiagnosticDir $diagnosticDir -ShutdownGraceSeconds 60 -AbsoluteTimeoutSeconds 360
 $exitCode=if($null -eq $monitor.exit_code){1}else{[int]$monitor.exit_code}
} catch {$failure=$_.Exception.Message}
$registryAfter=Get-CampfireCrashRegistrySnapshot
$registryUnchanged=(($registryBefore|ConvertTo-Json -Depth 12 -Compress)-eq($registryAfter|ConvertTo-Json -Depth 12 -Compress))
$productionAfter=(Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$dumps=@(Get-CampfireCrashDumpInventory -DumpDir $dumpDir)
$fatal=@(Select-String -LiteralPath $kitLog -Pattern '0xC0000005|access violation|device lost|TDR|\[crash\] A crash has occurred' -ErrorAction SilentlyContinue|ForEach-Object{$_.Line})
$uploads=@(Select-String -LiteralPath $kitLog -Pattern 'upload(?:ing|ed)? (?:mini)?dump|sending crash|submit.*crash' -ErrorAction SilentlyContinue|ForEach-Object{$_.Line})
$run=if(Test-Path -LiteralPath $output){Get-Content -Raw -Encoding UTF8 $output|ConvertFrom-Json}else{$null}
$normal = ($null -ne $monitor -and $monitor.lifecycle_candidate -eq "normal_exit" -and $monitor.exit_code -eq 0)
$qualified = ($null -eq $failure -and $null -ne $run -and $run.status -eq "qualified" -and $normal -and $fatal.Count -eq 0 -and $dumps.Count -eq 0 -and $uploads.Count -eq 0 -and $registryUnchanged -and $productionBefore -eq $productionAfter)
$evidence=[ordered]@{schema="campfire.phase6ho.kit-case-runner.v1";phase="phase6ho";mode=$Mode;status=if($qualified){"qualified"}else{"failed"};failure=$failure
 runner_pid=$PID;kit_launch_count=if($null-eq$process){0}else{1};transmitted_kit_path=$kit;transmitted_app_path=$app;transmitted_probe_path=$probe
 kit_pid=if($null-eq$process){$null}else{$process.Id};kit_start_time_utc=if($null-eq$process){$null}else{$process.StartTime.ToUniversalTime().ToString("o")}
 kit_arguments=$arguments;process_exit_code=if($null-eq$monitor){$null}else{$monitor.exit_code};shutdown_monitor=$monitor;run_status=if($null-eq$run){"missing"}else{$run.status}
 fatal_lines=@($fatal);dump_inventory=@($dumps);automatic_upload_attempt_lines=@($uploads);production_sha256_before=$productionBefore;production_sha256_after=$productionAfter
 lexical_build_paths_preserved=($kit -like "*\_build\windows-x86_64\release\kit\kit.exe" -and $app -like "*\_build\windows-x86_64\release\apps\campfire.simulator.kit");large_output_buffered_in_runner=$false}
[IO.File]::WriteAllText($runnerEvidence,($evidence|ConvertTo-Json -Depth 20)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
if (-not $qualified) { exit 1 }
exit $exitCode
