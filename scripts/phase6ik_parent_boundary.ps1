Set-StrictMode -Version 3.0

$script:Phase6IkStarted = [Diagnostics.Stopwatch]::StartNew()
$script:Phase6IkParentSteps = @(
  "child_wait_started", "child_process_exit", "child_wait_completed",
  "runner_evidence_write_started", "runner_evidence_write_completed", "parent_return"
)

function Get-Phase6IkCreationEpoch {
  param([Parameter(Mandatory=$true)][Diagnostics.Process]$Process)
  return [DateTimeOffset]::new($Process.StartTime.ToUniversalTime()).ToUnixTimeMilliseconds() / 1000.0
}

function Write-Phase6IkParentMarker {
  param(
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [Parameter(Mandatory=$true)][string]$AttemptId,
    [Parameter(Mandatory=$true)][string]$StepId,
    [hashtable]$Details = @{}
  )
  if ($script:Phase6IkParentSteps -notcontains $StepId) { throw "phase6ik_parent_step_invalid:$StepId" }
  $self = [Diagnostics.Process]::GetCurrentProcess()
  $record = [ordered]@{
    schema = "campfire.phase6ik.parent-lifecycle-marker.v1"
    attempt_id = $AttemptId
    marker = $StepId
    step_id = $StepId
    actor = "parent_powershell"
    pid = $PID
    creation_time_utc_epoch = Get-Phase6IkCreationEpoch -Process $self
    timestamp_utc_epoch = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0
    monotonic_elapsed_seconds = $script:Phase6IkStarted.Elapsed.TotalSeconds
    details = $Details
  }
  $line = ($record | ConvertTo-Json -Depth 8 -Compress) + [Environment]::NewLine
  $bytes = [Text.UTF8Encoding]::new($false).GetBytes($line)
  if ($bytes.Length -gt 16384) { throw "phase6ik_marker_row_oversize" }
  $stream = [IO.FileStream]::new([IO.Path]::GetFullPath($OutputPath), [IO.FileMode]::Append, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite)
  try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
}

