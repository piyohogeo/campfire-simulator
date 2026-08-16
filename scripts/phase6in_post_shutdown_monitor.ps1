Set-StrictMode -Version 3.0

if (-not ("Phase6InNativeProcess" -as [type])) {
  Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class Phase6InNativeProcess {
  [DllImport("kernel32.dll", SetLastError=true)] public static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool GetExitCodeProcess(IntPtr handle, out uint exitCode);
}
'@
}

$script:Phase6InStarted = [Diagnostics.Stopwatch]::StartNew()
$script:Phase6InMarkerLimit = 1MB

function Get-Phase6InProcessIdentity {
  param([Parameter(Mandatory=$true)][Diagnostics.Process]$Process)
  $Process.Refresh()
  return [ordered]@{
    pid=[int]$Process.Id
    creation_time_filetime_ticks=[long]$Process.StartTime.ToUniversalTime().ToFileTimeUtc()
    executable_path=[IO.Path]::GetFullPath($Process.MainModule.FileName).ToLowerInvariant()
  }
}

function Write-Phase6InMarker {
  param(
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [Parameter(Mandatory=$true)][string]$AttemptId,
    [Parameter(Mandatory=$true)][string]$StepId,
    [Parameter(Mandatory=$true)][string]$Actor,
    [Parameter(Mandatory=$true)][System.Collections.IDictionary]$Identity,
    [hashtable]$Details=@{}
  )
  $valid=@('runner_started','kit_process_launched','kit_app_ready','operation_complete','shutdown_requested','shutdown_complete','post_shutdown_monitor_started','post_shutdown_sample','process_exit_detected','crash_reporter_detected','post_shutdown_timeout','post_shutdown_monitor_complete','cleanup_started','cleanup_complete','final_residual_confirmed')
  if($valid -notcontains $StepId){throw "phase6in_marker_step_unknown:$StepId"}
  $row=[ordered]@{
    schema='campfire.phase6in.post-shutdown-marker.v1';attempt_id=$AttemptId;step_id=$StepId;actor=$Actor
    pid=[int]$Identity.pid;creation_time_filetime_ticks=[long]$Identity.creation_time_filetime_ticks
    executable_path=[string]$Identity.executable_path
    timestamp_utc_epoch=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000.0
    monotonic_elapsed_seconds=$script:Phase6InStarted.Elapsed.TotalSeconds;details=$Details
  }
  $line=($row|ConvertTo-Json -Depth 12 -Compress)+[Environment]::NewLine
  $bytes=[Text.UTF8Encoding]::new($false).GetBytes($line)
  if($bytes.Length -gt 32768){throw 'phase6in_marker_row_oversize'}
  if((Test-Path -LiteralPath $OutputPath) -and ((Get-Item -LiteralPath $OutputPath).Length+$bytes.Length -gt $script:Phase6InMarkerLimit)){throw 'phase6in_marker_file_oversize'}
  $stream=[IO.FileStream]::new([IO.Path]::GetFullPath($OutputPath),[IO.FileMode]::Append,[IO.FileAccess]::Write,[IO.FileShare]::ReadWrite)
  try{$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
}

function Get-Phase6InLastChildStep {
  param([Parameter(Mandatory=$true)][string]$Path)
  if(-not(Test-Path -LiteralPath $Path -PathType Leaf)){return $null}
  $last=$null
  foreach($line in @(Get-Content -LiteralPath $Path -Tail 16 -Encoding UTF8)){
    try{$row=$line|ConvertFrom-Json;if($row.step_id){$last=[string]$row.step_id}}catch{}
  }
  return $last
}

function Get-Phase6InAuxiliaryProjection {
  param([Parameter(Mandatory=$true)][int]$RootPid,[int]$Maximum=64)
  $all=@(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
  $queue=[Collections.Generic.Queue[int]]::new();$queue.Enqueue($RootPid)
  $seen=[Collections.Generic.HashSet[int]]::new();$rows=[Collections.Generic.List[object]]::new()
  while($queue.Count -gt 0 -and $rows.Count -lt $Maximum){
    $parent=$queue.Dequeue()
    foreach($item in @($all|Where-Object{[int]$_.ParentProcessId -eq $parent})){
      $childPid=[int]$item.ProcessId;if(-not$seen.Add($childPid)){continue}
      $name=([string]$item.Name).ToLowerInvariant()
      $role=if($name -match 'crashreporter'){'crash_reporter'}elseif($name-eq'omni.telemetry.transmitter.exe'){'telemetry'}elseif($name-eq'nvngx_update.exe'){'ngx'}elseif($name-eq'conhost.exe'){'conhost'}else{'unknown_child'}
      $ticks=$null
      try{$ticks=[Management.ManagementDateTimeConverter]::ToDateTime([string]$item.CreationDate).ToUniversalTime().ToFileTimeUtc()}catch{}
      $rows.Add([ordered]@{pid=$childPid;parent_pid=[int]$item.ParentProcessId;creation_time_filetime_ticks=$ticks;executable_path=if($item.ExecutablePath){[IO.Path]::GetFullPath([string]$item.ExecutablePath).ToLowerInvariant()}else{$null};name=[string]$item.Name;role=$role})
      $queue.Enqueue($childPid)
    }
  }
  return @($rows)
}

function Get-Phase6InDumpInventory {
  param([Parameter(Mandatory=$true)][string]$DumpDir)
  if(-not(Test-Path -LiteralPath $DumpDir -PathType Container)){return @()}
  return @(Get-ChildItem -LiteralPath $DumpDir -File|Sort-Object Name|Select-Object -First 64|ForEach-Object{[ordered]@{name=$_.Name;bytes=[long]$_.Length;last_write_utc=$_.LastWriteTimeUtc.ToString('o')}})
}

function Get-Phase6InFileProgress {
  param([string[]]$Paths)
  $rows=[ordered]@{}
  foreach($path in $Paths){if($path){$rows[[IO.Path]::GetFileName($path)]=if(Test-Path -LiteralPath $path -PathType Leaf){[long](Get-Item -LiteralPath $path).Length}else{0}}}
  return $rows
}

function Get-Phase6InSnapshot {
  param(
    [Parameter(Mandatory=$true)][Diagnostics.Process]$Process,
    [Parameter(Mandatory=$true)][IntPtr]$NativeHandle,
    [Parameter(Mandatory=$true)][System.Collections.IDictionary]$ExpectedIdentity,
    [Parameter(Mandatory=$true)][int]$SampleIndex,
    [Parameter(Mandatory=$true)][double]$ScheduledOffset,
    [Parameter(Mandatory=$true)][double]$ObservedOffset,
    [Parameter(Mandatory=$true)][double]$PreviousCpu,
    [Parameter(Mandatory=$true)][string]$DumpDir,
    [Parameter(Mandatory=$true)][string[]]$ProgressPaths
  )
  $wait=[Phase6InNativeProcess]::WaitForSingleObject($NativeHandle,0);$code=[uint32]0;$exitCode=$null
  if([Phase6InNativeProcess]::GetExitCodeProcess($NativeHandle,[ref]$code)){$exitCode=[long]$code}
  $alive=($wait-eq258);$state=if($wait-eq0){'exact_exited'}elseif($wait-eq258){'exact_alive'}else{'query_failed'}
  $private=$null;$working=$null;$threads=$null;$cpu=$null
  if($alive){
    try{
      $current=Get-Phase6InProcessIdentity -Process $Process
      if($current.pid-ne$ExpectedIdentity.pid -or $current.creation_time_filetime_ticks-ne$ExpectedIdentity.creation_time_filetime_ticks -or $current.executable_path-ne$ExpectedIdentity.executable_path){$state='pid_reused';$alive=$false}
      else{$Process.Refresh();$private=[long]$Process.PrivateMemorySize64;$working=[long]$Process.WorkingSet64;$threads=[int]$Process.Threads.Count;$cpu=[double]$Process.TotalProcessorTime.TotalSeconds}
    }catch{$state='query_failed';$alive=$false}
  }
  $aux=@(Get-Phase6InAuxiliaryProjection -RootPid $ExpectedIdentity.pid)
  $reporters=@($aux|Where-Object{$_.role-eq'crash_reporter'})
  return [ordered]@{
    sample_index=$SampleIndex;scheduled_offset_seconds=$ScheduledOffset;observed_offset_seconds=$ObservedOffset
    pid=[int]$ExpectedIdentity.pid;creation_time_filetime_ticks=[long]$ExpectedIdentity.creation_time_filetime_ticks;executable_path=[string]$ExpectedIdentity.executable_path
    identity_state=$state;alive=[bool]$alive;exit_code=if($exitCode-eq259){$null}else{$exitCode}
    cpu_total_seconds=$cpu;cpu_delta_seconds=if($null-ne$cpu){[math]::Max(0.0,$cpu-$PreviousCpu)}else{$null}
    private_bytes=$private;working_set_bytes=$working;thread_count=$threads
    auxiliary_processes=$aux;crash_reporters=$reporters;dump_inventory=@(Get-Phase6InDumpInventory -DumpDir $DumpDir)
    file_progress=Get-Phase6InFileProgress -Paths $ProgressPaths
  }
}

function Wait-Phase6InPostShutdown {
  param(
    [Parameter(Mandatory=$true)][Diagnostics.Process]$Process,
    [Parameter(Mandatory=$true)][IntPtr]$NativeHandle,
    [Parameter(Mandatory=$true)][System.Collections.IDictionary]$ExpectedIdentity,
    [Parameter(Mandatory=$true)][string]$AttemptId,
    [Parameter(Mandatory=$true)][string]$ChildMarkerPath,
    [Parameter(Mandatory=$true)][string]$ParentMarkerPath,
    [Parameter(Mandatory=$true)][string]$DumpDir,
    [Parameter(Mandatory=$true)][string[]]$ProgressPaths,
    [double[]]$ScheduleSeconds=@(0,0.25,0.5,1,2,5,10,15,30),
    [double]$BoundarySeconds=30
  )
  $deadline=[Diagnostics.Stopwatch]::StartNew()
  while((Get-Phase6InLastChildStep -Path $ChildMarkerPath)-ne'shutdown_complete'){
    if($deadline.Elapsed.TotalSeconds-ge30){throw 'phase6in_shutdown_marker_timeout'}
    if($Process.HasExited){throw 'phase6in_exit_before_shutdown_complete'}
    Start-Sleep -Milliseconds 25
  }
  $native=$NativeHandle;$monitor=[Diagnostics.Stopwatch]::StartNew();$samples=[Collections.Generic.List[object]]::new();$priorCpu=0.0;$reporterMarked=$false
  Write-Phase6InMarker -OutputPath $ParentMarkerPath -AttemptId $AttemptId -StepId 'post_shutdown_monitor_started' -Actor 'parent_powershell' -Identity $ExpectedIdentity -Details @{schedule_seconds=$ScheduleSeconds;boundary_seconds=$BoundarySeconds;cdb_enabled=$false}
  foreach($target in $ScheduleSeconds){
    while($monitor.Elapsed.TotalSeconds-lt$target -and [Phase6InNativeProcess]::WaitForSingleObject($native,0)-ne0){Start-Sleep -Milliseconds 25}
    $sample=Get-Phase6InSnapshot -Process $Process -NativeHandle $native -ExpectedIdentity $ExpectedIdentity -SampleIndex $samples.Count -ScheduledOffset $target -ObservedOffset $monitor.Elapsed.TotalSeconds -PreviousCpu $priorCpu -DumpDir $DumpDir -ProgressPaths $ProgressPaths
    if($null-ne$sample.cpu_total_seconds){$priorCpu=[double]$sample.cpu_total_seconds};$samples.Add($sample)
    Write-Phase6InMarker -OutputPath $ParentMarkerPath -AttemptId $AttemptId -StepId 'post_shutdown_sample' -Actor 'parent_powershell' -Identity $ExpectedIdentity -Details @{sample=$sample}
    if($sample.crash_reporters.Count -gt 0 -and -not$reporterMarked){$reporterMarked=$true;Write-Phase6InMarker -OutputPath $ParentMarkerPath -AttemptId $AttemptId -StepId 'crash_reporter_detected' -Actor 'parent_powershell' -Identity $ExpectedIdentity -Details @{processes=$sample.crash_reporters}}
    if($sample.identity_state-eq'exact_exited'){
      Write-Phase6InMarker -OutputPath $ParentMarkerPath -AttemptId $AttemptId -StepId 'process_exit_detected' -Actor 'parent_powershell' -Identity $ExpectedIdentity -Details @{exit_code=$sample.exit_code;observed_offset_seconds=$sample.observed_offset_seconds}
      break
    }
    if($sample.identity_state -in @('pid_reused','query_failed')){break}
  }
  $last=$samples[$samples.Count-1]
  if($last.identity_state-ne'exact_exited'){
    Write-Phase6InMarker -OutputPath $ParentMarkerPath -AttemptId $AttemptId -StepId 'post_shutdown_timeout' -Actor 'parent_powershell' -Identity $ExpectedIdentity -Details @{boundary_seconds=$BoundarySeconds;last_identity_state=$last.identity_state}
  }
  Write-Phase6InMarker -OutputPath $ParentMarkerPath -AttemptId $AttemptId -StepId 'post_shutdown_monitor_complete' -Actor 'parent_powershell' -Identity $ExpectedIdentity -Details @{sample_count=$samples.Count;terminal_state=$last.identity_state}
  return [ordered]@{monitor_complete=$true;samples=@($samples);exit_observed=($last.identity_state-eq'exact_exited');exit_code=$last.exit_code;exit_observed_seconds=if($last.identity_state-eq'exact_exited'){$last.observed_offset_seconds}else{$null};timeout=($last.identity_state-ne'exact_exited');identity_reuse=($last.identity_state-eq'pid_reused');query_failure=($last.identity_state-eq'query_failed');crash_reporter_observed=$reporterMarked;cdb_attempted=$false;sample_schedule_seconds=$ScheduleSeconds;boundary_seconds=$BoundarySeconds}
}
