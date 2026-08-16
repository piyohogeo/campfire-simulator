param(
  [Parameter(Mandatory=$true)][string]$PythonPath,
  [Parameter(Mandatory=$true)][string]$ChildPath,
  [Parameter(Mandatory=$true)][string]$MarkersPath,
  [Parameter(Mandatory=$true)][string]$ReportPath,
  [Parameter(Mandatory=$true)][string]$ResultPath,
  [Parameter(Mandatory=$true)][string]$AttemptId,
  [double]$DelaySeconds=0.0,
  [double]$HangSeconds=0.0,
  [int]$ChildExitCode=0
)
$ErrorActionPreference="Stop"; Set-StrictMode -Version 3.0
. (Join-Path $PSScriptRoot "kit_shutdown_policy.ps1")
. (Join-Path $PSScriptRoot "phase6ik_parent_boundary.ps1")
$python=[IO.Path]::GetFullPath($PythonPath); $child=[IO.Path]::GetFullPath($ChildPath)
$markers=[IO.Path]::GetFullPath($MarkersPath); $report=[IO.Path]::GetFullPath($ReportPath); $result=[IO.Path]::GetFullPath($ResultPath)
$stdout="$ResultPath.child.stdout.log"; $stderr="$ResultPath.child.stderr.log"; $diagnostic=Join-Path (Split-Path -Parent $result) "diagnostic"
$process=Start-Process -FilePath $python -ArgumentList @($child,"--markers",$markers,"--report",$report,"--attempt-id",$AttemptId,"--delay-seconds",$DelaySeconds,"--hang-seconds",$HangSeconds,"--exit-code",$ChildExitCode) -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
$childCreation=Get-Phase6IkCreationEpoch -Process $process
Write-Phase6IkParentMarker -OutputPath $markers -AttemptId $AttemptId -StepId "child_wait_started" -Details @{child_pid=$process.Id;child_creation_time_utc_epoch=$childCreation}
$nativeHandle=$process.Handle
$exited=$process.WaitForExit(2000)
if($exited){$code=[Phase6EaFileSafety]::ReadExitCode($nativeHandle);$monitor=[ordered]@{lifecycle_candidate="normal_exit";exit_code=$code;shutdown_marker_observed=$true;absolute_timeout=$false;residual_process=$false}}
else{
  $monitor=[ordered]@{lifecycle_candidate="fixture_wait_timeout";exit_code=$null;shutdown_marker_observed=$true;absolute_timeout=$true;residual_process=$true}
  Stop-Process -Id $process.Id -Force -ErrorAction Stop
  $process.WaitForExit(5000)|Out-Null
}
if($exited){Write-Phase6IkParentMarker -OutputPath $markers -AttemptId $AttemptId -StepId "child_process_exit" -Details @{child_pid=$process.Id;exit_code=$monitor.exit_code}}
Write-Phase6IkParentMarker -OutputPath $markers -AttemptId $AttemptId -StepId "child_wait_completed" -Details @{child_pid=$process.Id;exit_code=$monitor.exit_code;lifecycle_candidate=$monitor.lifecycle_candidate}
Write-CampfireBoundedJson -Path $result -Value ([ordered]@{schema="campfire.phase6ik.wait-fixture.v1";attempt_id=$AttemptId;child_pid=$process.Id;child_creation_time_utc_epoch=$childCreation;monitor=$monitor;stdout_buffered=$false;stderr_buffered=$false}) -MaximumBytes 1MB
exit 0
