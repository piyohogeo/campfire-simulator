param(
  [Parameter(Mandatory=$true)][string]$KitPath,
  [Parameter(Mandatory=$true)][string]$AppPath,
  [Parameter(Mandatory=$true)][string]$ProbePath,
  [Parameter(Mandatory=$true)][string]$MarkersPath,
  [Parameter(Mandatory=$true)][string]$ReportPath,
  [Parameter(Mandatory=$true)][string]$IdentityPath,
  [Parameter(Mandatory=$true)][string]$StageRoot,
  [Parameter(Mandatory=$true)][string]$RunnerEvidencePath,
  [Parameter(Mandatory=$true)][string]$ContractPath,
  [Parameter(Mandatory=$true)][string]$KitLogPath,
  [Parameter(Mandatory=$true)][string]$KitStdoutPath,
  [Parameter(Mandatory=$true)][string]$KitStderrPath,
  [Parameter(Mandatory=$true)][ValidateSet("A","B","C")][string]$Condition,
  [Parameter(Mandatory=$true)][string]$AttemptId
)
$ErrorActionPreference="Stop"; Set-StrictMode -Version 3.0
$repo=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
. (Join-Path $PSScriptRoot "kit_shutdown_policy.ps1")
$kit=[IO.Path]::GetFullPath($KitPath); $app=[IO.Path]::GetFullPath($AppPath); $probe=[IO.Path]::GetFullPath($ProbePath)
$markers=[IO.Path]::GetFullPath($MarkersPath); $report=[IO.Path]::GetFullPath($ReportPath); $identity=[IO.Path]::GetFullPath($IdentityPath); $stages=[IO.Path]::GetFullPath($StageRoot)
$evidence=[IO.Path]::GetFullPath($RunnerEvidencePath); $contract=[IO.Path]::GetFullPath($ContractPath); $kitLog=[IO.Path]::GetFullPath($KitLogPath); $kitStdout=[IO.Path]::GetFullPath($KitStdoutPath); $kitStderr=[IO.Path]::GetFullPath($KitStderrPath)
$attempt=Split-Path -Parent $report; $dumpDir=Join-Path $attempt "sensitive-crash-dumps"; $diagnosticDir=Join-Path $attempt "sensitive-shutdown-diagnostics"
$productionApp=Join-Path $repo "_build\windows-x86_64\release\apps\campfire.simulator.kit"; $productionBefore=(Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash; $registryBefore=Get-CampfireCrashRegistrySnapshot
$arguments=@($app,"--no-window","--/app/file/ignoreUnsavedOnExit=true","--/app/fastShutdown=0","--/app/quitAfter=120000","--/app/settings/persistent=0","--/app/settings/loadUserConfig=0","--/app/window/hideUi=true","--/exts/campfire.app/autoCreateScene=false","--/rtx/flow/enabled=true","--enable","omni.usd","--enable","omni.flowusd","--enable","omni.physx","--/phase6ii/markers=$markers","--/phase6ii/report=$report","--/phase6ii/identity=$identity","--/phase6ii/stageRoot=$stages","--/phase6ii/attemptId=$AttemptId","--/phase6ii/condition=$Condition","--/log/file=$kitLog","--/log/fileLogLevel=Info","--exec",$probe)+@(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $dumpDir)
$process=$null; $monitor=$null; $failure=$null; $exitCode=1
try {
  $process=Start-Process -FilePath $kit -ArgumentList $arguments -WorkingDirectory $repo -PassThru -WindowStyle Hidden -RedirectStandardOutput $kitStdout -RedirectStandardError $kitStderr
  $monitor=Wait-CampfireKitProcessWithShutdownPolicy -Process $process -ExpectedExecutable $kit -LifecyclePath $report -LogPath $kitLog -DiagnosticDir $diagnosticDir -ShutdownGraceSeconds 30 -AbsoluteTimeoutSeconds 180
  $exitCode=if($null-eq$monitor.exit_code){1}else{[int]$monitor.exit_code}
} catch { $failure=$_.Exception.Message }
$registryAfter=Get-CampfireCrashRegistrySnapshot; $registryUnchanged=(($registryBefore|ConvertTo-Json -Depth 12 -Compress)-eq($registryAfter|ConvertTo-Json -Depth 12 -Compress)); $productionAfter=(Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$markerNames=@(); if(Test-Path $markers){$markerNames=@(Get-Content $markers|ForEach-Object{try{($_|ConvertFrom-Json).marker}catch{$null}}|Where-Object{$_})}
$policy=Get-Content -Raw $contract|ConvertFrom-Json; $missing=@($policy.operation_contract.required_markers|Where-Object{$markerNames -notcontains $_}); $reportObject=if(Test-Path $report){Get-Content -Raw $report|ConvertFrom-Json}else{$null}
$dumps=@(Get-CampfireCrashDumpInventory -DumpDir $dumpDir); $fatal=@(Select-String -LiteralPath $kitLog -Pattern '0xC0000005|access violation|device lost|TDR|\[crash\] A crash has occurred' -ErrorAction SilentlyContinue|ForEach-Object{$_.Line}); $uploads=@(Select-String -LiteralPath $kitLog -Pattern 'upload(?:ing|ed)? (?:mini)?dump|sending crash|submit.*crash' -ErrorAction SilentlyContinue|ForEach-Object{$_.Line})
$qualified=($null-eq$failure -and $exitCode-eq 0 -and $null-ne$reportObject -and $reportObject.status-eq"stage_open_close_qualified" -and $reportObject.operation_complete-eq$true -and $reportObject.shutdown_complete-eq$true -and $missing.Count-eq 0 -and $fatal.Count-eq 0 -and $dumps.Count-eq 0 -and $uploads.Count-eq 0 -and $registryUnchanged -and $productionBefore-eq$productionAfter)
$out=[ordered]@{schema="campfire.phase6ii.runner.v1";phase="phase6ii";condition=$Condition;status=if($qualified){"qualified"}else{"failed"};attempt_id=$AttemptId;runner_pid=$PID;kit_launch_count=if($null-eq$process){0}else{1};kit_pid=if($null-eq$process){$null}else{$process.Id};kit_start_time_utc=if($null-eq$process){$null}else{$process.StartTime.ToUniversalTime().ToString("o")};process_exit_code=if($null-eq$monitor){$null}else{$monitor.exit_code};shutdown_monitor=$monitor;failure=$failure;missing_markers=$missing;marker_names=$markerNames;fatal_lines=$fatal;dump_inventory=$dumps;automatic_upload_attempt_lines=$uploads;crash_registry_unchanged=$registryUnchanged;production_sha256_before=$productionBefore;production_sha256_after=$productionAfter;kit_arguments=$arguments;large_output_buffered_in_runner=$false}
[IO.File]::WriteAllText($evidence,($out|ConvertTo-Json -Depth 20)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false)); if(-not$qualified){exit 1}; exit 0
