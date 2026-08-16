param(
  [Parameter(Mandatory=$true)][string]$Mode,
  [Parameter(Mandatory=$true)][string]$OutputDir,
  [double]$DelaySeconds=0.15
)
$ErrorActionPreference='Stop';Set-StrictMode -Version 3.0
$repo=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'kit_shutdown_policy.ps1')
. (Join-Path $PSScriptRoot 'phase6il_post_shutdown_monitor.ps1')
$root=[IO.Path]::GetFullPath($OutputDir);New-Item -ItemType Directory -Path $root -Force|Out-Null
$marker=Join-Path $root 'markers.jsonl';$dumpDir=Join-Path $root 'dumps';New-Item -ItemType Directory -Path $dumpDir -Force|Out-Null
$stdout=Join-Path $root 'child.stdout.log';$stderr=Join-Path $root 'child.stderr.log';$python='C:\Python38\python.exe'
$attempt="fixture-$Mode";$childScript=Join-Path $PSScriptRoot 'phase6il_fixture_child.py'
$process=Start-Process -FilePath $python -ArgumentList @($childScript,'--mode',$Mode,'--artifact-root',$dumpDir,'--delay',[string]$DelaySeconds) -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
$native=$process.Handle;$created=Get-Phase6IlCreationEpoch -Process $process
foreach($step in @('process_started','kit_app_ready','operation_complete','shutdown_complete')){Write-Phase6IlMarker -OutputPath $marker -AttemptId $attempt -StepId $step -Actor 'fixture_child' -Details @{child_pid=$process.Id}}
$schedule=if($Mode-eq'hang'){@(0,0.1,0.25)}else{@(0,0.05,0.1,0.25,0.5)}
$boundary=if($Mode-eq'hang'){0.3}else{0.75}
$monitor=Wait-Phase6IlPostShutdown -Process $process -ExpectedExecutable $python -AttemptId $attempt -MarkerPath $marker -DumpDir $dumpDir -KitLogPath $stdout -DiagnosticDir (Join-Path $root 'diagnostic') -ScheduleSeconds $schedule -BoundarySeconds $boundary
if(-not$monitor.native_handle_signaled){
  $live=Test-Phase6EaProcessIdentity -ProcessId $process.Id -ExpectedExecutable $python -ExpectedStartTimeUtc $process.StartTime.ToUniversalTime()
  Stop-Process -Id $live.Id -Force;$null=$process.WaitForExit(5000)
}
$fixtureResidualCleaned=$true
$reporterPidPath=Join-Path $dumpDir 'reporter.pid'
if(Test-Path -LiteralPath $reporterPidPath -PathType Leaf){
  $reporterPid=[int](Get-Content -LiteralPath $reporterPidPath -Raw)
  try{
    $reporter=Get-Process -Id $reporterPid -ErrorAction Stop
    if([IO.Path]::GetFullPath($reporter.Path)-ne[IO.Path]::GetFullPath($python)){throw 'fixture_reporter_identity_mismatch'}
    Stop-Process -Id $reporterPid -Force;$null=$reporter.WaitForExit(5000)
  }catch [Microsoft.PowerShell.Commands.ProcessCommandException]{} catch{$fixtureResidualCleaned=$false}
}
$exitAfter=$null;try{$exitAfter=$process.ExitCode}catch{}
$report=[ordered]@{schema='campfire.phase6il.fixture-case.v1';attempt_id=$attempt;mode=$Mode;child_pid=$process.Id;child_creation_time_utc_epoch=$created;monitor=$monitor;process_object_has_exited_after=$process.HasExited;exit_code_after=$exitAfter;fixture_residual_cleaned=$fixtureResidualCleaned}
$report|ConvertTo-Json -Depth 16|Set-Content -LiteralPath (Join-Path $root 'case.json') -Encoding UTF8
exit 0
