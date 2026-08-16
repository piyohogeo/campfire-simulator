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
$ErrorActionPreference="Stop"; Set-StrictMode -Version 3.0
$repo=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
. (Join-Path $PSScriptRoot "kit_shutdown_policy.ps1")
. (Join-Path $PSScriptRoot "phase6ik_parent_boundary.ps1")
$kit=[IO.Path]::GetFullPath($KitPath); $app=[IO.Path]::GetFullPath($AppPath); $probe=[IO.Path]::GetFullPath($ProbePath)
$markers=[IO.Path]::GetFullPath($MarkersPath); $report=[IO.Path]::GetFullPath($ReportPath); $evidence=[IO.Path]::GetFullPath($RunnerEvidencePath)
$contract=[IO.Path]::GetFullPath($ContractPath); $kitLog=[IO.Path]::GetFullPath($KitLogPath); $kitStdout=[IO.Path]::GetFullPath($KitStdoutPath); $kitStderr=[IO.Path]::GetFullPath($KitStderrPath)
$attempt=Split-Path -Parent $report; $dumpDir=Join-Path $attempt "sensitive-crash-dumps"; $diagnosticDir=Join-Path $attempt "sensitive-shutdown-diagnostics"
$source=Join-Path $attempt "runner_evidence.source.json"; $writerResult=Join-Path $attempt "runner_evidence.writer_result.json"
$writer=Join-Path $PSScriptRoot "phase6ik_atomic_runner_evidence.py"; $python="C:\Python38\python.exe"
$productionApp=Join-Path $repo "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore=(Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash; $registryBefore=Get-CampfireCrashRegistrySnapshot
$arguments=@($app,"--no-window","--/app/file/ignoreUnsavedOnExit=true","--/app/fastShutdown=0","--/app/quitAfter=120000","--/app/settings/persistent=0","--/app/settings/loadUserConfig=0","--/app/window/hideUi=true","--/exts/campfire.app/autoCreateScene=false","--/phase6ik/markers=$markers","--/phase6ik/report=$report","--/phase6ik/attemptId=$AttemptId","--/log/file=$kitLog","--/log/fileLogLevel=Info","--exec",$probe)+@(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $dumpDir)
$process=$null; $monitor=$null; $failure=$null; $exitCode=$null; $parent=[Diagnostics.Process]::GetCurrentProcess()
try {
  $process=Start-Process -FilePath $kit -ArgumentList $arguments -WorkingDirectory $repo -PassThru -WindowStyle Hidden -RedirectStandardOutput $kitStdout -RedirectStandardError $kitStderr
  $childCreation=Get-Phase6IkCreationEpoch -Process $process
  Write-Phase6IkParentMarker -OutputPath $markers -AttemptId $AttemptId -StepId "child_wait_started" -Details @{child_pid=$process.Id;child_creation_time_utc_epoch=$childCreation}
  $monitor=Wait-CampfireKitProcessWithShutdownPolicy -Process $process -ExpectedExecutable $kit -LifecyclePath $report -LogPath $kitLog -DiagnosticDir $diagnosticDir -ShutdownGraceSeconds 30 -AbsoluteTimeoutSeconds 180
  $exitCode=$monitor.exit_code
  if ($null-ne$exitCode) { Write-Phase6IkParentMarker -OutputPath $markers -AttemptId $AttemptId -StepId "child_process_exit" -Details @{child_pid=$process.Id;exit_code=[int]$exitCode} }
  Write-Phase6IkParentMarker -OutputPath $markers -AttemptId $AttemptId -StepId "child_wait_completed" -Details @{child_pid=$process.Id;exit_code=$exitCode;lifecycle_candidate=$monitor.lifecycle_candidate}
} catch { $failure=$_.Exception.Message }
$registryAfter=Get-CampfireCrashRegistrySnapshot; $registryUnchanged=(($registryBefore|ConvertTo-Json -Depth 12 -Compress)-eq($registryAfter|ConvertTo-Json -Depth 12 -Compress)); $productionAfter=(Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$operation=if(Test-Path -LiteralPath $report){Read-CampfireBoundedJson -Path $report -MaximumBytes 1MB}else{$null}
$dumps=@(Get-CampfireCrashDumpInventory -DumpDir $dumpDir); $fatal=@(Select-String -LiteralPath $kitLog -Pattern '0xC0000005|access violation|device lost|TDR|\[crash\] A crash has occurred' -ErrorAction SilentlyContinue|ForEach-Object{$_.Line}); $uploads=@(Select-String -LiteralPath $kitLog -Pattern 'upload(?:ing|ed)? (?:mini)?dump|sending crash|submit.*crash' -ErrorAction SilentlyContinue|ForEach-Object{$_.Line})
$qualified=($null-eq$failure -and $exitCode-eq 0 -and $null-ne$operation -and $operation.status-eq"qualified" -and $operation.operation_complete-eq$true -and $operation.shutdown_complete-eq$true -and $fatal.Count-eq 0 -and $dumps.Count-eq 0 -and $uploads.Count-eq 0 -and $registryUnchanged -and $productionBefore-eq$productionAfter)
$parentIdentity=[ordered]@{pid=$PID;creation_time_utc_epoch=(Get-Phase6IkCreationEpoch -Process $parent);path=$parent.MainModule.FileName}
$childIdentity=if($null-eq$process){[ordered]@{pid=0;creation_time_utc_epoch=0.0;path=$kit}}else{[ordered]@{pid=$process.Id;creation_time_utc_epoch=$childCreation;path=$kit}}
$runner=[ordered]@{schema="campfire.phase6ik.runner-evidence.v1";attempt_id=$AttemptId;status=if($qualified){"qualified"}else{"failed"};mode="smoke";parent_identity=$parentIdentity;child_identity=$childIdentity;process_exit_code=$exitCode;shutdown_monitor=$monitor;fatal_lines=$fatal;dump_inventory=$dumps;automatic_upload_attempt_lines=$uploads;large_output_buffered_in_parent=$false;failure=$failure;production_sha256_before=$productionBefore;production_sha256_after=$productionAfter;kit_arguments=$arguments}
try {
  Write-Phase6IkParentMarker -OutputPath $markers -AttemptId $AttemptId -StepId "runner_evidence_write_started" -Details @{destination=$evidence}
  Write-CampfireBoundedJson -Path $source -Value $runner -MaximumBytes 1MB
  $writerStdout=Join-Path $attempt "runner-evidence-writer.stdout.log"; $writerStderr=Join-Path $attempt "runner-evidence-writer.stderr.log"
  $writerProcess=Start-Process -FilePath $python -ArgumentList @($writer,"--source",$source,"--destination",$evidence,"--result",$writerResult) -WorkingDirectory $repo -PassThru -WindowStyle Hidden -Wait -RedirectStandardOutput $writerStdout -RedirectStandardError $writerStderr
  if($writerProcess.ExitCode-ne 0 -or -not(Test-Path -LiteralPath $evidence)){throw "phase6ik_runner_evidence_writer_failed:$($writerProcess.ExitCode)"}
  Write-Phase6IkParentMarker -OutputPath $markers -AttemptId $AttemptId -StepId "runner_evidence_write_completed" -Details @{destination=$evidence;writer_exit_code=$writerProcess.ExitCode}
} catch { if($null-eq$failure){$failure=$_.Exception.Message}; $qualified=$false }
Write-Phase6IkParentMarker -OutputPath $markers -AttemptId $AttemptId -StepId "parent_return" -Details @{exit_code=if($qualified){0}else{1}}
if(-not$qualified){exit 1}; exit 0
