param([Parameter(Mandatory=$true)][string]$Mode,[Parameter(Mandatory=$true)][string]$OutputDir)
$ErrorActionPreference='Stop';Set-StrictMode -Version 3.0
$repo=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'isolated_kit_crash_safety.ps1')
. (Join-Path $PSScriptRoot 'kit_shutdown_policy.ps1')
. (Join-Path $PSScriptRoot 'phase6in_post_shutdown_monitor.ps1')
$root=[IO.Path]::GetFullPath($OutputDir);New-Item -ItemType Directory -Path $root -Force|Out-Null
$attempt="phase6in-fixture-$Mode";$parentMarkers=Join-Path $root 'parent.jsonl';$childMarkers=Join-Path $root 'child.jsonl';$reportPath=Join-Path $root 'operation.json';$dumpDir=Join-Path $root 'dumps';New-Item -ItemType Directory -Path $dumpDir -Force|Out-Null
$python='C:\Python38\python.exe';$script=Join-Path $PSScriptRoot 'phase6in_fixture_child.py';$stdout=Join-Path $root 'child.stdout.log';$stderr=Join-Path $root 'child.stderr.log'
$parent=Get-Phase6InProcessIdentity -Process ([Diagnostics.Process]::GetCurrentProcess())
Write-Phase6InMarker -OutputPath $parentMarkers -AttemptId $attempt -StepId 'runner_started' -Actor 'fixture_parent' -Identity $parent
$process=Start-Process -FilePath $python -ArgumentList @($script,'--mode',$Mode,'--attempt-id',$attempt,'--markers',$childMarkers,'--report',$reportPath) -WorkingDirectory $repo -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
$native=$process.Handle
$launch=Get-Phase6InProcessIdentity -Process $process
Write-Phase6InMarker -OutputPath $parentMarkers -AttemptId $attempt -StepId 'kit_process_launched' -Actor 'fixture_parent' -Identity $launch
$wait=[Diagnostics.Stopwatch]::StartNew();while(-not(Test-Path -LiteralPath $reportPath -PathType Leaf) -and $wait.Elapsed.TotalSeconds-lt5){Start-Sleep -Milliseconds 10}
$operation=Read-CampfireBoundedJson -Path $reportPath -MaximumBytes 1MB;$identity=[ordered]@{pid=[int]$operation.process_identity.pid;creation_time_filetime_ticks=[long]$operation.process_identity.creation_time_filetime_ticks;executable_path=([string]$operation.process_identity.executable_path).ToLowerInvariant()}
if($identity.pid-ne$launch.pid -or $identity.creation_time_filetime_ticks-ne$launch.creation_time_filetime_ticks -or $identity.executable_path-ne$launch.executable_path){throw 'fixture_identity_mismatch'}
$monitor=Wait-Phase6InPostShutdown -Process $process -NativeHandle $native -ExpectedIdentity $identity -AttemptId $attempt -ChildMarkerPath $childMarkers -ParentMarkerPath $parentMarkers -DumpDir $dumpDir -ProgressPaths @($childMarkers,$parentMarkers,$reportPath,$stdout,$stderr) -ScheduleSeconds @(0,0.05,0.1,0.25,0.5) -BoundarySeconds 0.5
Write-Phase6InMarker -OutputPath $parentMarkers -AttemptId $attempt -StepId 'cleanup_started' -Actor 'fixture_parent' -Identity $parent -Details @{exact_target=$identity}
$assisted=$false
if(-not$process.HasExited){$current=Get-Phase6InProcessIdentity -Process $process;if($current.pid-eq$identity.pid -and $current.creation_time_filetime_ticks-eq$identity.creation_time_filetime_ticks -and $current.executable_path-eq$identity.executable_path){Stop-Process -Id $process.Id -Force;$null=$process.WaitForExit(5000);$assisted=$true}}
$residual=if($process.HasExited){0}else{1}
Write-Phase6InMarker -OutputPath $parentMarkers -AttemptId $attempt -StepId 'cleanup_complete' -Actor 'fixture_parent' -Identity $parent -Details @{assisted=$assisted;residual_count=$residual}
Write-Phase6InMarker -OutputPath $parentMarkers -AttemptId $attempt -StepId 'final_residual_confirmed' -Actor 'fixture_parent' -Identity $parent -Details @{residual_count=$residual}
$value=[ordered]@{schema='campfire.phase6in.runner-evidence.v1';attempt_id=$attempt;mode=$Mode;operation=$operation;launch_identity=$launch;monitor_complete=$monitor.monitor_complete;samples=$monitor.samples;monitor=$monitor;assisted_cleanup=$assisted;residual_process_count=$residual;fatal_lines=@();dump_inventory=@();automatic_upload_attempt_lines=@();large_output_buffered_in_parent=$false;failure=$null;cdb_attempted=$false}
Write-CampfireBoundedJson -Path (Join-Path $root 'case.json') -Value $value -MaximumBytes 1MB
exit 0
