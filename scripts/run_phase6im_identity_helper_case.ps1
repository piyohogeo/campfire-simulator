param(
  [Parameter(Mandatory=$true)][string]$KitPath,
  [Parameter(Mandatory=$true)][string]$AppPath,
  [Parameter(Mandatory=$true)][string]$ProbePath,
  [Parameter(Mandatory=$true)][string]$MarkersPath,
  [Parameter(Mandatory=$true)][string]$ReportPath,
  [Parameter(Mandatory=$true)][string]$RunnerEvidencePath,
  [Parameter(Mandatory=$true)][string]$KitLogPath,
  [Parameter(Mandatory=$true)][string]$KitStdoutPath,
  [Parameter(Mandatory=$true)][string]$KitStderrPath,
  [Parameter(Mandatory=$true)][string]$AttemptId
)
$ErrorActionPreference='Stop';Set-StrictMode -Version 3.0
$repo=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'isolated_kit_crash_safety.ps1')
. (Join-Path $PSScriptRoot 'kit_shutdown_policy.ps1')
$kit=[IO.Path]::GetFullPath($KitPath);$app=[IO.Path]::GetFullPath($AppPath);$probe=[IO.Path]::GetFullPath($ProbePath)
$markers=[IO.Path]::GetFullPath($MarkersPath);$report=[IO.Path]::GetFullPath($ReportPath);$evidence=[IO.Path]::GetFullPath($RunnerEvidencePath)
$kitLog=[IO.Path]::GetFullPath($KitLogPath);$kitStdout=[IO.Path]::GetFullPath($KitStdoutPath);$kitStderr=[IO.Path]::GetFullPath($KitStderrPath)
$attempt=Split-Path -Parent $report;$dumpDir=Join-Path $attempt 'sensitive-crash-dumps';$diagnosticDir=Join-Path $attempt 'sensitive-shutdown-diagnostics'
New-Item -ItemType Directory -Path $dumpDir,$diagnosticDir -Force|Out-Null
$registryBefore=Get-CampfireCrashRegistrySnapshot
$arguments=@($app,'--no-window','--/app/file/ignoreUnsavedOnExit=true','--/app/fastShutdown=0','--/app/quitAfter=120000','--/app/settings/persistent=0','--/app/settings/loadUserConfig=0','--/app/window/hideUi=true','--/exts/campfire.app/autoCreateScene=false',"--/phase6im/markers=$markers","--/phase6im/report=$report","--/phase6im/attemptId=$AttemptId","--/phase6im/expectedKitPath=$kit","--/log/file=$kitLog",'--/log/fileLogLevel=Info','--exec',$probe)+@(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $dumpDir)
$process=$null;$lifecycle=$null;$failure=$null
try{
  $process=Start-Process -FilePath $kit -ArgumentList $arguments -WorkingDirectory $repo -PassThru -WindowStyle Hidden -RedirectStandardOutput $kitStdout -RedirectStandardError $kitStderr
  $lifecycle=Wait-CampfireKitProcessWithShutdownPolicy -Process $process -ExpectedExecutable $kit -LifecyclePath $report -LogPath $kitLog -DiagnosticDir $diagnosticDir -ShutdownGraceSeconds 30 -AbsoluteTimeoutSeconds 120 -SkipLowLevelDiagnostic
}catch{$failure="$($_.Exception.GetType().Name): $($_.Exception.Message)"}
$registryAfter=Get-CampfireCrashRegistrySnapshot;$registryUnchanged=(($registryBefore|ConvertTo-Json -Depth 12 -Compress)-eq($registryAfter|ConvertTo-Json -Depth 12 -Compress))
$operation=if(Test-Path -LiteralPath $report){Read-CampfireBoundedJson -Path $report -MaximumBytes 1MB}else{$null}
$dumps=@(Get-CampfireCrashDumpInventory -DumpDir $dumpDir)
$fatal=@(Select-String -LiteralPath $kitLog -Pattern '0xC0000005|access violation|device lost|TDR|\[crash\] A crash has occurred' -ErrorAction SilentlyContinue|ForEach-Object{$_.Line})
$uploads=@(Select-String -LiteralPath $kitLog -Pattern 'upload(?:ing|ed)? (?:mini)?dump|sending crash|submit.*crash' -ErrorAction SilentlyContinue|ForEach-Object{$_.Line})
$runner=[ordered]@{schema='campfire.phase6im.runner-evidence.v1';attempt_id=$AttemptId;mode='minimal_app_ready_identity_helper';operation=$operation;lifecycle=$lifecycle;fatal_lines=$fatal;dump_inventory=$dumps;automatic_upload_attempt_lines=$uploads;crash_registry_unchanged=$registryUnchanged;large_output_buffered_in_parent=$false;failure=$failure;kit_arguments=$arguments}
Write-CampfireBoundedJson -Path $evidence -Value $runner -MaximumBytes 1MB
if($null-ne$failure){exit 1};exit 0

