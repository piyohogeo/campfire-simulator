Set-StrictMode -Version 3.0

if (-not ("Phase6IlNativeWait" -as [type])) {
  Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class Phase6IlNativeWait {
  [DllImport("kernel32.dll", SetLastError=true)]
  private static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);
  public static uint Poll(IntPtr handle) { return WaitForSingleObject(handle, 0); }
}
'@
}

$script:Phase6IlStarted = [Diagnostics.Stopwatch]::StartNew()
$script:Phase6IlMarkerLimit = 1MB

function Get-Phase6IlCreationEpoch {
  param([Parameter(Mandatory=$true)][Diagnostics.Process]$Process)
  return [DateTimeOffset]::new($Process.StartTime.ToUniversalTime()).ToUnixTimeMilliseconds() / 1000.0
}

function Write-Phase6IlMarker {
  param(
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [Parameter(Mandatory=$true)][string]$AttemptId,
    [Parameter(Mandatory=$true)][string]$StepId,
    [Parameter(Mandatory=$true)][string]$Actor,
    [hashtable]$Details = @{}
  )
  $self=[Diagnostics.Process]::GetCurrentProcess()
  $record=[ordered]@{
    schema="campfire.phase6il.post-shutdown-marker.v1"; attempt_id=$AttemptId
    marker=$StepId; step_id=$StepId; actor=$Actor; pid=$PID
    creation_time_utc_epoch=Get-Phase6IlCreationEpoch -Process $self
    timestamp_utc_epoch=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000.0
    monotonic_elapsed_seconds=$script:Phase6IlStarted.Elapsed.TotalSeconds
    details=$Details
  }
  $line=($record|ConvertTo-Json -Depth 12 -Compress)+[Environment]::NewLine
  $bytes=[Text.UTF8Encoding]::new($false).GetBytes($line)
  if($bytes.Length -gt 32768){throw "phase6il_marker_row_oversize"}
  if((Test-Path -LiteralPath $OutputPath) -and ((Get-Item -LiteralPath $OutputPath).Length+$bytes.Length -gt $script:Phase6IlMarkerLimit)){throw "phase6il_marker_file_oversize"}
  $stream=[IO.FileStream]::new([IO.Path]::GetFullPath($OutputPath),[IO.FileMode]::Append,[IO.FileAccess]::Write,[IO.FileShare]::ReadWrite)
  try{$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
}

function Get-Phase6IlLifecycleMarker {
  param([Parameter(Mandatory=$true)][string]$Path)
  if(-not(Test-Path -LiteralPath $Path -PathType Leaf)){return $null}
  foreach($line in @(Get-Content -LiteralPath $Path -Tail 32 -Encoding UTF8)){
    try{$row=$line|ConvertFrom-Json;if($row.step_id){$last=[string]$row.step_id}}catch{}
  }
  return $last
}

function Get-Phase6IlTreeProjection {
  param([Parameter(Mandatory=$true)][int]$RootPid,[int]$Maximum=64)
  $all=@(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
  $queue=[Collections.Generic.Queue[int]]::new();$queue.Enqueue($RootPid)
  $seen=[Collections.Generic.HashSet[int]]::new();$rows=[Collections.Generic.List[object]]::new()
  while($queue.Count -gt 0 -and $rows.Count -lt $Maximum){
    $parent=$queue.Dequeue()
    foreach($item in @($all|Where-Object{[int]$_.ParentProcessId -eq $parent})){
      $pidValue=[int]$item.ProcessId;if(-not$seen.Add($pidValue)){continue}
      $role=if(([string]$item.Name).ToLowerInvariant() -match 'crashreporter'){"crash_reporter"}elseif(([string]$item.Name).ToLowerInvariant() -eq 'conhost.exe'){"conhost"}elseif(([string]$item.Name).ToLowerInvariant() -eq 'omni.telemetry.transmitter.exe'){"telemetry"}elseif(([string]$item.Name).ToLowerInvariant() -eq 'nvngx_update.exe'){"ngx"}else{"unknown_child"}
      $rows.Add([ordered]@{pid=$pidValue;parent_pid=[int]$item.ParentProcessId;name=[string]$item.Name;path=if($item.ExecutablePath){[IO.Path]::GetFullPath([string]$item.ExecutablePath)}else{$null};creation_date=if($item.CreationDate){([datetime]$item.CreationDate).ToUniversalTime().ToString('o')}else{$null};role=$role})
      $queue.Enqueue($pidValue)
    }
  }
  return [ordered]@{count=$rows.Count;truncated=($rows.Count -ge $Maximum);processes=@($rows)}
}

function Get-Phase6IlDumpState {
  param([Parameter(Mandatory=$true)][string]$DumpDir,[hashtable]$PreviousSizes=@{})
  $files=[Collections.Generic.List[object]]::new();$completed=0;$growing=0
  if(Test-Path -LiteralPath $DumpDir -PathType Container){
    foreach($item in @(Get-ChildItem -LiteralPath $DumpDir -File|Sort-Object Name|Select-Object -First 64)){
      $prior=if($PreviousSizes.ContainsKey($item.FullName)){[long]$PreviousSizes[$item.FullName]}else{$null}
      $stable=($null-ne$prior -and $prior-eq$item.Length)
      if($stable){$completed++}else{$growing++}
      $PreviousSizes[$item.FullName]=[long]$item.Length
      $files.Add([ordered]@{name=$item.Name;bytes=[long]$item.Length;last_write_utc=$item.LastWriteTimeUtc.ToString('o');stable=$stable;sha256=$null})
    }
  }
  return [ordered]@{count=$files.Count;stable_count=$completed;growing_count=$growing;files=@($files)}
}

function Get-Phase6IlProcessSnapshot {
  param(
    [Parameter(Mandatory=$true)][Diagnostics.Process]$Process,
    [Parameter(Mandatory=$true)][string]$ExpectedExecutable,
    [Parameter(Mandatory=$true)][datetime]$ExpectedStartTimeUtc,
    [Parameter(Mandatory=$true)][IntPtr]$NativeHandle,
    [Parameter(Mandatory=$true)][double]$OffsetSeconds,
    [Parameter(Mandatory=$true)][string]$DumpDir,
    [Parameter(Mandatory=$true)][string]$KitLogPath,
    [Parameter(Mandatory=$true)][hashtable]$PreviousDumpSizes,
    [double]$PreviousCpuSeconds=0.0,
    [double]$PreviousSampleOffset=0.0
  )
  $hasExited=$false;try{$hasExited=[bool]$Process.HasExited}catch{}
  $nativeRaw=[Phase6IlNativeWait]::Poll($NativeHandle)
  $nativeState=if($nativeRaw-eq0){"signaled"}elseif($nativeRaw-eq258){"timeout"}else{"failed"}
  $nativeExit=$null;try{$nativeExit=[long][Phase6EaFileSafety]::ReadExitCode($NativeHandle)}catch{}
  $identity=Get-Phase6EaProcessIdentityState -ProcessId $Process.Id -ExpectedExecutable $ExpectedExecutable -ExpectedStartTimeUtc $ExpectedStartTimeUtc
  $private=$null;$working=$null;$threads=$null;$handles=$null;$cpu=$null;$threadStates=@{};$waitReasons=@{}
  try{
    $Process.Refresh();$private=[long]$Process.PrivateMemorySize64;$working=[long]$Process.WorkingSet64;$threads=[int]$Process.Threads.Count;$handles=[int]$Process.HandleCount;$cpu=[double]$Process.TotalProcessorTime.TotalSeconds
    foreach($thread in @($Process.Threads|Select-Object -First 512)){
      try{$state=[string]$thread.ThreadState;if(-not$threadStates.ContainsKey($state)){$threadStates[$state]=0};$threadStates[$state]++
        if($state-eq'Wait' -or $state-eq'Waiting'){$reason=[string]$thread.WaitReason;if(-not$waitReasons.ContainsKey($reason)){$waitReasons[$reason]=0};$waitReasons[$reason]++}}
      catch{}
    }
  }catch{}
  $logTail=@();$logBytes=0
  if(Test-Path -LiteralPath $KitLogPath -PathType Leaf){$logBytes=(Get-Item -LiteralPath $KitLogPath).Length;$logTail=@(Get-Content -LiteralPath $KitLogPath -Tail 8 -Encoding UTF8|ForEach-Object{if($_.Length-gt512){$_.Substring(0,512)}else{$_}})}
  $interval=[math]::Max(0.0,$OffsetSeconds-$PreviousSampleOffset)
  $cpuDelta=if($null-ne$cpu){[math]::Max(0.0,$cpu-$PreviousCpuSeconds)}else{$null}
  return [ordered]@{
    sample_offset_seconds=[double]$OffsetSeconds;process_object_has_exited=[bool]$hasExited
    native_wait_state=$nativeState;native_wait_raw=[long]$nativeRaw;native_exit_code=$nativeExit
    os_identity_state=[string]$identity.state;same_exact_kit_alive=([string]$identity.state-eq'alive_identity_match')
    private_bytes=$private;working_set_bytes=$working;thread_count=$threads;handle_count=$handles
    cpu_total_seconds=$cpu;cpu_interval_seconds=$cpuDelta;sample_interval_seconds=$interval
    thread_states=$threadStates;wait_reasons=$waitReasons
    tree=Get-Phase6IlTreeProjection -RootPid $Process.Id
    dump_state=Get-Phase6IlDumpState -DumpDir $DumpDir -PreviousSizes $PreviousDumpSizes
    kit_log=[ordered]@{bytes=[long]$logBytes;tail=$logTail}
    parent_wait_state="sampling";outer_elapsed_seconds=$script:Phase6IlStarted.Elapsed.TotalSeconds
  }
}

function Wait-Phase6IlPostShutdown {
  param(
    [Parameter(Mandatory=$true)][Diagnostics.Process]$Process,
    [Parameter(Mandatory=$true)][string]$ExpectedExecutable,
    [Parameter(Mandatory=$true)][string]$AttemptId,
    [Parameter(Mandatory=$true)][string]$MarkerPath,
    [Parameter(Mandatory=$true)][string]$DumpDir,
    [Parameter(Mandatory=$true)][string]$KitLogPath,
    [Parameter(Mandatory=$true)][string]$DiagnosticDir,
    [double[]]$ScheduleSeconds=@(0,0.25,0.5,1,2,5,10,15,30,60,120,175),
    [double]$BoundarySeconds=180,
    [switch]$EnableCdb
  )
  $expected=[IO.Path]::GetFullPath($ExpectedExecutable);$expectedStart=$Process.StartTime.ToUniversalTime();$native=$Process.Handle
  $waitForMarker=[Diagnostics.Stopwatch]::StartNew()
  while((Get-Phase6IlLifecycleMarker -Path $MarkerPath)-ne'shutdown_complete'){
    if($waitForMarker.Elapsed.TotalSeconds-ge30){throw 'phase6il_shutdown_marker_timeout'}
    if($Process.HasExited){throw 'phase6il_child_exited_before_shutdown_marker'}
    Start-Sleep -Milliseconds 25
  }
  $monitor=[Diagnostics.Stopwatch]::StartNew();$samples=[Collections.Generic.List[object]]::new();$dumpSizes=@{};$priorCpu=0.0;$priorOffset=0.0;$cdb=$null;$cdbAttempted=$false
  Write-Phase6IlMarker -OutputPath $MarkerPath -AttemptId $AttemptId -StepId 'post_shutdown_monitor_started' -Actor 'parent_powershell' -Details @{child_pid=$Process.Id;schedule_seconds=$ScheduleSeconds;boundary_seconds=$BoundarySeconds}
  foreach($target in $ScheduleSeconds){
    while($monitor.Elapsed.TotalSeconds-lt$target){
      if([Phase6IlNativeWait]::Poll($native)-eq0){break}
      Start-Sleep -Milliseconds 25
    }
    $offset=$monitor.Elapsed.TotalSeconds
    $sample=Get-Phase6IlProcessSnapshot -Process $Process -ExpectedExecutable $expected -ExpectedStartTimeUtc $expectedStart -NativeHandle $native -OffsetSeconds $offset -DumpDir $DumpDir -KitLogPath $KitLogPath -PreviousDumpSizes $dumpSizes -PreviousCpuSeconds $priorCpu -PreviousSampleOffset $priorOffset
    $samples.Add($sample);if($null-ne$sample.cpu_total_seconds){$priorCpu=[double]$sample.cpu_total_seconds};$priorOffset=$offset
    Write-Phase6IlMarker -OutputPath $MarkerPath -AttemptId $AttemptId -StepId 'post_shutdown_sample' -Actor 'parent_powershell' -Details @{sample_index=$samples.Count-1;sample=$sample}
    if($sample.native_wait_state-eq'signaled' -or $sample.os_identity_state-eq'confirmed_exited'){
      Write-Phase6IlMarker -OutputPath $MarkerPath -AttemptId $AttemptId -StepId 'child_process_exit' -Actor 'parent_powershell' -Details @{child_pid=$Process.Id;native_exit_code=$sample.native_exit_code;sample_offset_seconds=$offset}
      break
    }
    if($EnableCdb.IsPresent -and -not$cdbAttempted -and $target-ge60 -and $sample.same_exact_kit_alive){
      $cdbAttempted=$true
      $cdb=Invoke-CampfireCdbStackFirstCapture -ProcessId $Process.Id -ExpectedExecutable $expected -ExpectedStartTimeUtc $expectedStart -OutputDir $DiagnosticDir -MarkerPath $MarkerPath -StackTimeoutSeconds 20 -ModuleTimeoutSeconds 10 -DetachTimeoutSeconds 5 -NoProgressTimeoutSeconds 15
    }
  }
  $last=$samples[$samples.Count-1]
  if($last.native_wait_state-ne'signaled' -and $monitor.Elapsed.TotalSeconds-lt$BoundarySeconds){
    while($monitor.Elapsed.TotalSeconds-lt$BoundarySeconds -and [Phase6IlNativeWait]::Poll($native)-ne0){Start-Sleep -Milliseconds 25}
    if([Phase6IlNativeWait]::Poll($native)-eq0){
      $offset=$monitor.Elapsed.TotalSeconds;$sample=Get-Phase6IlProcessSnapshot -Process $Process -ExpectedExecutable $expected -ExpectedStartTimeUtc $expectedStart -NativeHandle $native -OffsetSeconds $offset -DumpDir $DumpDir -KitLogPath $KitLogPath -PreviousDumpSizes $dumpSizes -PreviousCpuSeconds $priorCpu -PreviousSampleOffset $priorOffset
      $samples.Add($sample);Write-Phase6IlMarker -OutputPath $MarkerPath -AttemptId $AttemptId -StepId 'post_shutdown_sample' -Actor 'parent_powershell' -Details @{sample_index=$samples.Count-1;sample=$sample;unscheduled_exit_sample=$true}
      Write-Phase6IlMarker -OutputPath $MarkerPath -AttemptId $AttemptId -StepId 'child_process_exit' -Actor 'parent_powershell' -Details @{child_pid=$Process.Id;native_exit_code=$sample.native_exit_code;sample_offset_seconds=$offset}
    }
  }
  if([Phase6IlNativeWait]::Poll($native)-ne0){Write-Phase6IlMarker -OutputPath $MarkerPath -AttemptId $AttemptId -StepId 'post_shutdown_boundary_reached' -Actor 'parent_powershell' -Details @{child_pid=$Process.Id;boundary_seconds=$BoundarySeconds}}
  $finalExit=$null;try{$finalExit=[long][Phase6EaFileSafety]::ReadExitCode($native)}catch{}
  return [ordered]@{samples=@($samples);cdb_attempted=$cdbAttempted;cdb=$cdb;monitor_elapsed_seconds=$monitor.Elapsed.TotalSeconds;native_handle_signaled=([Phase6IlNativeWait]::Poll($native)-eq0);native_exit_code=$finalExit}
}
