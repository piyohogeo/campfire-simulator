param(
 [Parameter(Mandatory=$true)][string]$KitPath,
 [Parameter(Mandatory=$true)][string]$AppPath,
 [Parameter(Mandatory=$true)][string]$ProbePath,
 [Parameter(Mandatory=$true)][string]$MarkersPath,
 [Parameter(Mandatory=$true)][string]$AuditPath,
 [Parameter(Mandatory=$true)][string]$RunnerEvidencePath,
 [Parameter(Mandatory=$true)][string]$KitLogPath,
 [Parameter(Mandatory=$true)][string]$KitStdoutPath,
 [Parameter(Mandatory=$true)][string]$KitStderrPath,
 [Parameter(Mandatory=$true)][string]$AttemptId
)
$ErrorActionPreference="Stop"
Set-StrictMode -Version 3.0
$repo=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
. (Join-Path $PSScriptRoot "kit_shutdown_policy.ps1")
$kit=[IO.Path]::GetFullPath($KitPath);$app=[IO.Path]::GetFullPath($AppPath);$probe=[IO.Path]::GetFullPath($ProbePath)
$markers=[IO.Path]::GetFullPath($MarkersPath);$audit=[IO.Path]::GetFullPath($AuditPath);$evidence=[IO.Path]::GetFullPath($RunnerEvidencePath)
$kitLog=[IO.Path]::GetFullPath($KitLogPath);$kitStdout=[IO.Path]::GetFullPath($KitStdoutPath);$kitStderr=[IO.Path]::GetFullPath($KitStderrPath)
$attempt=Split-Path -Parent $audit;$dumpDir=Join-Path $attempt "sensitive-crash-dumps";$diagnosticDir=Join-Path $attempt "sensitive-shutdown-diagnostics"
$arguments=@($app,"--no-window","--/app/file/ignoreUnsavedOnExit=true","--/app/fastShutdown=0","--/app/quitAfter=120000",
 "--/app/settings/persistent=0","--/app/settings/loadUserConfig=0","--/app/window/hideUi=true",
 "--/exts/campfire.app/autoCreateScene=false","--/phase6hs/markers=$markers","--/phase6hs/attemptId=$AttemptId",
 "--/phase6hy/importSmoke=true","--/phase6hy/importAudit=$audit","--/log/file=$kitLog","--/log/fileLogLevel=Info","--exec",$probe) + @(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $dumpDir)
$process=$null;$monitor=$null;$failure=$null;$exitCode=1
try {
 $process=Start-Process -FilePath $kit -ArgumentList $arguments -WorkingDirectory $repo -PassThru -WindowStyle Hidden -RedirectStandardOutput $kitStdout -RedirectStandardError $kitStderr
 $monitor=Wait-CampfireKitProcessWithShutdownPolicy -Process $process -ExpectedExecutable $kit -LifecyclePath $audit -LogPath $kitLog -DiagnosticDir $diagnosticDir -ShutdownGraceSeconds 30 -AbsoluteTimeoutSeconds 180
 $exitCode=if($null -eq $monitor.exit_code){1}else{[int]$monitor.exit_code}
} catch {$failure=$_.Exception.Message}
$markerNames=@();if(Test-Path -LiteralPath $markers){$markerNames=@(Get-Content -Encoding UTF8 $markers|ForEach-Object{try{($_|ConvertFrom-Json).marker}catch{$null}}|Where-Object{$_})}
$required=@("kit_app_ready","wrapper_resolved","scripts_resolved","probe_source_resolved","probe_source_sha256","loaded_module_file","required_callable_identity","import_complete","operation_complete","smoke_shutdown_complete")
$missing=@($required|Where-Object{$markerNames -notcontains $_})
$auditObject=if(Test-Path -LiteralPath $audit){Get-Content -Raw -Encoding UTF8 $audit|ConvertFrom-Json}else{$null}
$dumps=@(Get-CampfireCrashDumpInventory -DumpDir $dumpDir)
$fatal=@(Select-String -LiteralPath $kitLog -Pattern '0xC0000005|access violation|device lost|TDR|\[crash\] A crash has occurred' -ErrorAction SilentlyContinue|ForEach-Object{$_.Line})
$qualified=($null-eq$failure -and $exitCode-eq 0 -and $null-ne$auditObject -and $auditObject.status-eq"qualified" -and $missing.Count-eq 0 -and $fatal.Count-eq 0 -and $dumps.Count-eq 0)
$report=[ordered]@{schema="campfire.phase6hy.import-smoke-runner.v1";status=if($qualified){"qualified"}else{"failed"};attempt_id=$AttemptId;runner_pid=$PID;kit_launch_count=if($null-eq$process){0}else{1};process_exit_code=if($null-eq$monitor){$null}else{$monitor.exit_code};shutdown_monitor=$monitor;failure=$failure;missing_markers=$missing;marker_names=$markerNames;audit_path=$audit;fatal_lines=$fatal;dump_inventory=$dumps;kit_arguments=$arguments;large_output_buffered_in_runner=$false}
[IO.File]::WriteAllText($evidence,($report|ConvertTo-Json -Depth 20)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
if(-not$qualified){exit 1};exit 0
