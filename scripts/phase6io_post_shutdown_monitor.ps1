Set-StrictMode -Version 3.0
. (Join-Path $PSScriptRoot 'phase6in_post_shutdown_monitor.ps1')

# Phase 6IM is the running-process path authority.  The parent sets this only
# after the Phase 6IO handle-based producer/consumer report is accepted.  The
# retained native process handle plus PID and creation ticks prevents PID reuse;
# this override stops MainModule's junction spelling from becoming a second path
# authority during bounded samples.
$script:Phase6IoCanonicalIdentity = $null

function Set-Phase6IoCanonicalIdentity {
  param([Parameter(Mandatory=$true)][System.Collections.IDictionary]$Identity)
  $script:Phase6IoCanonicalIdentity = [ordered]@{
    pid=[int]$Identity.pid
    creation_time_filetime_ticks=[long]$Identity.creation_time_filetime_ticks
    executable_path=[string]$Identity.executable_path
  }
}

function Get-Phase6InProcessIdentity {
  param([Parameter(Mandatory=$true)][Diagnostics.Process]$Process)
  $Process.Refresh()
  $pidValue=[int]$Process.Id
  $ticks=[long]$Process.StartTime.ToUniversalTime().ToFileTimeUtc()
  if($null-ne$script:Phase6IoCanonicalIdentity){
    if($pidValue-ne$script:Phase6IoCanonicalIdentity.pid -or $ticks-ne$script:Phase6IoCanonicalIdentity.creation_time_filetime_ticks){
      return [ordered]@{pid=$pidValue;creation_time_filetime_ticks=$ticks;executable_path='identity-mismatch'}
    }
    return [ordered]@{pid=$pidValue;creation_time_filetime_ticks=$ticks;executable_path=[string]$script:Phase6IoCanonicalIdentity.executable_path}
  }
  return [ordered]@{pid=$pidValue;creation_time_filetime_ticks=$ticks;executable_path=[IO.Path]::GetFullPath($Process.MainModule.FileName).ToLowerInvariant()}
}
