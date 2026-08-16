param(
  [Parameter(Mandatory=$true)][string]$KitPath,[Parameter(Mandatory=$true)][string]$ExpectedCanonicalKitPath,
  [Parameter(Mandatory=$true)][string]$AppPath,[Parameter(Mandatory=$true)][string]$ProbePath,
  [Parameter(Mandatory=$true)][string]$ChildMarkersPath,[Parameter(Mandatory=$true)][string]$ParentMarkersPath,
  [Parameter(Mandatory=$true)][string]$OperationReportPath,[Parameter(Mandatory=$true)][string]$PathIdentityReportPath,
  [Parameter(Mandatory=$true)][string]$RunnerEvidencePath,[Parameter(Mandatory=$true)][string]$KitLogPath,
  [Parameter(Mandatory=$true)][string]$KitStdoutPath,[Parameter(Mandatory=$true)][string]$KitStderrPath,
  [Parameter(Mandatory=$true)][string]$AttemptId
)
$ErrorActionPreference='Stop';Set-StrictMode -Version 3.0
$repo=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'isolated_kit_crash_safety.ps1')
. (Join-Path $PSScriptRoot 'kit_shutdown_policy.ps1')
. (Join-Path $PSScriptRoot 'phase6io_post_shutdown_monitor.ps1')
$kit=[IO.Path]::GetFullPath($KitPath);$canonical=[IO.Path]::GetFullPath($ExpectedCanonicalKitPath).ToLowerInvariant()
$app=[IO.Path]::GetFullPath($AppPath);$probe=[IO.Path]::GetFullPath($ProbePath)
$childMarkers=[IO.Path]::GetFullPath($ChildMarkersPath);$parentMarkers=[IO.Path]::GetFullPath($ParentMarkersPath)
$operationPath=[IO.Path]::GetFullPath($OperationReportPath);$pathReport=[IO.Path]::GetFullPath($PathIdentityReportPath);$evidencePath=[IO.Path]::GetFullPath($RunnerEvidencePath)
$kitLog=[IO.Path]::GetFullPath($KitLogPath);$kitStdout=[IO.Path]::GetFullPath($KitStdoutPath);$kitStderr=[IO.Path]::GetFullPath($KitStderrPath)
$attempt=Split-Path -Parent $operationPath;$dumpDir=Join-Path $attempt 'sensitive-crash-dumps';New-Item -ItemType Directory -Path $dumpDir -Force|Out-Null
$parent=Get-Phase6InProcessIdentity -Process ([Diagnostics.Process]::GetCurrentProcess())
Write-Phase6InMarker -OutputPath $parentMarkers -AttemptId $AttemptId -StepId 'runner_started' -Actor 'parent_powershell' -Identity $parent -Details @{stage_free=$true;flow_calls=0;cdb_enabled=$false;path_identity_contract='phase6io'}
$registryBefore=Get-CampfireCrashRegistrySnapshot
$arguments=@($app,'--no-window','--/app/file/ignoreUnsavedOnExit=true','--/app/fastShutdown=0','--/app/quitAfter=120000','--/app/settings/persistent=0','--/app/settings/loadUserConfig=0','--/app/window/hideUi=true','--/exts/campfire.app/autoCreateScene=false',"--/phase6io/childMarkers=$childMarkers","--/phase6io/operationReport=$operationPath","--/phase6io/attemptId=$AttemptId","--/phase6io/expectedKitPath=$kit","--/log/file=$kitLog",'--/log/fileLogLevel=Info','--exec',$probe)+@(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $dumpDir)
$process=$null;$monitor=$null;$failure=$null;$launchIdentity=$null;$operation=$null;$pathEnvelope=$null
try{
  $process=Start-Process -FilePath $kit -ArgumentList $arguments -WorkingDirectory $repo -PassThru -WindowStyle Hidden -RedirectStandardOutput $kitStdout -RedirectStandardError $kitStderr
  $native=$process.Handle;$process.Refresh()
  $launchIdentity=[ordered]@{pid=[int]$process.Id;creation_time_filetime_ticks=[long]$process.StartTime.ToUniversalTime().ToFileTimeUtc();executable_path=$canonical}
  Write-Phase6InMarker -OutputPath $parentMarkers -AttemptId $AttemptId -StepId 'kit_process_launched' -Actor 'parent_powershell' -Identity $launchIdentity -Details @{parent_pid=$PID;lexical_launch_path=$kit;expected_canonical_path=$canonical}
  $reportWait=[Diagnostics.Stopwatch]::StartNew()
  while($reportWait.Elapsed.TotalSeconds-lt60){if(Test-Path -LiteralPath $operationPath -PathType Leaf){try{$operation=Read-CampfireBoundedJson -Path $operationPath -MaximumBytes 1MB;if($operation.shutdown_complete-eq$true){break}}catch{}};if($process.HasExited){break};Start-Sleep -Milliseconds 25}
  if($null-eq$operation -or $operation.shutdown_complete-ne$true){throw 'phase6io_operation_or_shutdown_evidence_incomplete'}
  $cli=Join-Path $PSScriptRoot 'phase6io_path_identity_cli.py'
  & C:\Python38\python.exe $cli --attempt-id $AttemptId --lexical-launch-path $kit --expected-lexical-launch-path $kit --operation-report $operationPath --launch-pid $launchIdentity.pid --launch-creation-ticks $launchIdentity.creation_time_filetime_ticks --output $pathReport
  if($LASTEXITCODE-ne0){throw "phase6io_path_identity_cli_failed:$LASTEXITCODE"}
  $pathEnvelope=Read-CampfireBoundedJson -Path $pathReport -MaximumBytes 1MB
  if($pathEnvelope.validation.accepted-ne$true -or $pathEnvelope.report.accepted-ne$true){throw 'phase6io_path_identity_not_accepted'}
  $identity=$operation.process_identity
  $expected=[ordered]@{pid=[int]$identity.pid;creation_time_filetime_ticks=[long]$identity.creation_time_filetime_ticks;executable_path=[string]$pathEnvelope.report.process_executable_file.canonical_path}
  Set-Phase6IoCanonicalIdentity -Identity $expected
  $monitor=Wait-Phase6InPostShutdown -Process $process -NativeHandle $native -ExpectedIdentity $expected -AttemptId $AttemptId -ChildMarkerPath $childMarkers -ParentMarkerPath $parentMarkers -DumpDir $dumpDir -ProgressPaths @($childMarkers,$parentMarkers,$operationPath,$pathReport,$kitLog,$kitStdout,$kitStderr)
}catch{$failure="$($_.Exception.GetType().Name): $($_.Exception.Message)"}
$registryAfter=Get-CampfireCrashRegistrySnapshot;$registryUnchanged=(($registryBefore|ConvertTo-Json -Depth 12 -Compress)-eq($registryAfter|ConvertTo-Json -Depth 12 -Compress))
$dumps=@(Get-CampfireCrashDumpInventory -DumpDir $dumpDir);$fatal=@(Select-String -LiteralPath $kitLog -Pattern '0xC0000005|access violation|device lost|TDR|\[crash\] A crash has occurred' -ErrorAction SilentlyContinue|ForEach-Object{$_.Line});$uploads=@(Select-String -LiteralPath $kitLog -Pattern 'upload(?:ing|ed)? (?:mini)?dump|sending crash|submit.*crash' -ErrorAction SilentlyContinue|ForEach-Object{$_.Line})
$runner=[ordered]@{schema='campfire.phase6in.runner-evidence.v1';attempt_id=$AttemptId;mode='phase6io_stage_free_minimal_post_shutdown_monitor';operation=$operation;launch_identity=$launchIdentity;path_identity=$pathEnvelope;monitor_complete=($null-ne$monitor -and $monitor.monitor_complete-eq$true);samples=if($null-ne$monitor){$monitor.samples}else{@()};monitor=$monitor;fatal_lines=$fatal;dump_inventory=$dumps;automatic_upload_attempt_lines=$uploads;crash_registry_unchanged=$registryUnchanged;large_output_buffered_in_parent=$false;failure=$failure;kit_arguments=$arguments;cdb_attempted=$false}
Write-CampfireBoundedJson -Path $evidencePath -Value $runner -MaximumBytes 1MB
if($null-ne$failure){exit 1};if($monitor.timeout){exit 2};if($monitor.exit_code-ne0){exit 3};exit 0
