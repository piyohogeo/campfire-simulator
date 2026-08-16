param(
  [Parameter(Mandatory=$true)][string]$KitPath,
  [Parameter(Mandatory=$true)][string]$AppPath,
  [Parameter(Mandatory=$true)][string]$ProbePath,
  [Parameter(Mandatory=$true)][string]$MarkersPath,
  [Parameter(Mandatory=$true)][string]$ReportPath,
  [Parameter(Mandatory=$true)][string]$RunnerEvidencePath,
  [Parameter(Mandatory=$true)][string]$ContractPath,
  [Parameter(Mandatory=$true)][string]$KitLogPath,
  [Parameter(Mandatory=$true)][string]$KitStdoutPath,
  [Parameter(Mandatory=$true)][string]$KitStderrPath,
  [Parameter(Mandatory=$true)][string]$AttemptId
)
$ErrorActionPreference='Stop';Set-StrictMode -Version 3.0
$repo=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'isolated_kit_crash_safety.ps1')
. (Join-Path $PSScriptRoot 'kit_shutdown_policy.ps1')
. (Join-Path $PSScriptRoot 'phase6il_post_shutdown_monitor.ps1')
$kit=[IO.Path]::GetFullPath($KitPath);$app=[IO.Path]::GetFullPath($AppPath);$probe=[IO.Path]::GetFullPath($ProbePath)
$markers=[IO.Path]::GetFullPath($MarkersPath);$report=[IO.Path]::GetFullPath($ReportPath);$evidence=[IO.Path]::GetFullPath($RunnerEvidencePath)
$contract=[IO.Path]::GetFullPath($ContractPath);$kitLog=[IO.Path]::GetFullPath($KitLogPath);$kitStdout=[IO.Path]::GetFullPath($KitStdoutPath);$kitStderr=[IO.Path]::GetFullPath($KitStderrPath)
$attempt=Split-Path -Parent $report;$dumpDir=Join-Path $attempt 'sensitive-crash-dumps';$diagnosticDir=Join-Path $attempt 'sensitive-shutdown-diagnostics'
New-Item -ItemType Directory -Path $dumpDir,$diagnosticDir -Force|Out-Null
$source=Join-Path $attempt 'runner_evidence.source.json';$writerResult=Join-Path $attempt 'runner_evidence.writer_result.json';$writer=Join-Path $PSScriptRoot 'phase6ik_atomic_runner_evidence.py';$python='C:\Python38\python.exe'
$productionApp=Join-Path $repo '_build\windows-x86_64\release\apps\campfire.simulator.kit';$productionBefore=(Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$registryBefore=Get-CampfireCrashRegistrySnapshot
$arguments=@($app,'--no-window','--/app/file/ignoreUnsavedOnExit=true','--/app/fastShutdown=0','--/app/quitAfter=120000','--/app/settings/persistent=0','--/app/settings/loadUserConfig=0','--/app/window/hideUi=true','--/exts/campfire.app/autoCreateScene=false',"--/phase6il/markers=$markers","--/phase6il/report=$report","--/phase6il/attemptId=$AttemptId","--/log/file=$kitLog",'--/log/fileLogLevel=Info','--exec',$probe)+@(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $dumpDir)
$process=$null;$monitor=$null;$failure=$null;$forcedBoundaryCleanup=$false;$childCreation=$null
try{
  $process=Start-Process -FilePath $kit -ArgumentList $arguments -WorkingDirectory $repo -PassThru -WindowStyle Hidden -RedirectStandardOutput $kitStdout -RedirectStandardError $kitStderr
  $childCreation=Get-Phase6IlCreationEpoch -Process $process
  Write-Phase6IlMarker -OutputPath $markers -AttemptId $AttemptId -StepId 'child_wait_started' -Actor 'parent_powershell' -Details @{child_pid=$process.Id;child_creation_time_utc_epoch=$childCreation}
  $monitor=Wait-Phase6IlPostShutdown -Process $process -ExpectedExecutable $kit -AttemptId $AttemptId -MarkerPath $markers -DumpDir $dumpDir -KitLogPath $kitLog -DiagnosticDir $diagnosticDir -BoundarySeconds 180 -EnableCdb
  if(-not$monitor.native_handle_signaled){
    $live=Test-Phase6EaProcessIdentity -ProcessId $process.Id -ExpectedExecutable $kit -ExpectedStartTimeUtc $process.StartTime.ToUniversalTime()
    Stop-Process -Id $live.Id -Force;$forcedBoundaryCleanup=$true;$null=$process.WaitForExit(5000)
  }
  Write-Phase6IlMarker -OutputPath $markers -AttemptId $AttemptId -StepId 'child_wait_completed' -Actor 'parent_powershell' -Details @{child_pid=$process.Id;native_exit_code=$monitor.native_exit_code;forced_boundary_cleanup=$forcedBoundaryCleanup}
}catch{$failure="$($_.Exception.GetType().Name): $($_.Exception.Message)"}
$registryAfter=Get-CampfireCrashRegistrySnapshot;$registryUnchanged=(($registryBefore|ConvertTo-Json -Depth 12 -Compress)-eq($registryAfter|ConvertTo-Json -Depth 12 -Compress));$productionAfter=(Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$operation=if(Test-Path -LiteralPath $report){Read-CampfireBoundedJson -Path $report -MaximumBytes 1MB}else{$null}
$dumps=@(Get-CampfireCrashDumpInventory -DumpDir $dumpDir);$fatal=@(Select-String -LiteralPath $kitLog -Pattern '0xC0000005|access violation|device lost|TDR|\[crash\] A crash has occurred' -ErrorAction SilentlyContinue|ForEach-Object{$_.Line});$uploads=@(Select-String -LiteralPath $kitLog -Pattern 'upload(?:ing|ed)? (?:mini)?dump|sending crash|submit.*crash' -ErrorAction SilentlyContinue|ForEach-Object{$_.Line})
$exitCode=$null;if($null-ne$monitor){$exitCode=$monitor.native_exit_code}
$runner=[ordered]@{schema='campfire.phase6il.runner-evidence.v1';attempt_id=$AttemptId;status='collected';mode='minimal_app_ready_post_shutdown';child_identity=[ordered]@{pid=if($process){$process.Id}else{0};creation_time_utc_epoch=if($childCreation){$childCreation}else{0.0};path=$kit};process_exit_code=$exitCode;monitor=$monitor;operation_complete=($null-ne$operation-and$operation.operation_complete-eq$true);shutdown_complete=($null-ne$operation-and$operation.shutdown_complete-eq$true);forced_boundary_cleanup=$forcedBoundaryCleanup;fatal_lines=$fatal;dump_inventory=$dumps;automatic_upload_attempt_lines=$uploads;crash_registry_unchanged=$registryUnchanged;large_output_buffered_in_parent=$false;failure=$failure;production_sha256_before=$productionBefore;production_sha256_after=$productionAfter;kit_arguments=$arguments}
try{
  Write-Phase6IlMarker -OutputPath $markers -AttemptId $AttemptId -StepId 'runner_evidence_write_started' -Actor 'parent_powershell' -Details @{destination=$evidence}
  Write-CampfireBoundedJson -Path $source -Value $runner -MaximumBytes 1MB
  $writerProcess=Start-Process -FilePath $python -ArgumentList @($writer,'--source',$source,'--destination',$evidence,'--result',$writerResult) -WorkingDirectory $repo -PassThru -WindowStyle Hidden -Wait -RedirectStandardOutput (Join-Path $attempt 'writer.stdout.log') -RedirectStandardError (Join-Path $attempt 'writer.stderr.log')
  if($writerProcess.ExitCode-ne0-or-not(Test-Path -LiteralPath $evidence)){throw "phase6il_runner_evidence_writer_failed:$($writerProcess.ExitCode)"}
  Write-Phase6IlMarker -OutputPath $markers -AttemptId $AttemptId -StepId 'runner_evidence_write_completed' -Actor 'parent_powershell' -Details @{destination=$evidence;writer_exit_code=$writerProcess.ExitCode}
}catch{if($null-eq$failure){$failure="$($_.Exception.GetType().Name): $($_.Exception.Message)"}}
Write-Phase6IlMarker -OutputPath $markers -AttemptId $AttemptId -StepId 'parent_return' -Actor 'parent_powershell' -Details @{collector_exit_code=if($null-eq$failure){0}else{1}}
if($null-ne$failure){exit 1};exit 0
