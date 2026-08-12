param(
    [Parameter(Mandatory = $true)][ValidateSet("single", "near_two", "lower_upper", "production_four")][string]$Scenario,
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [double]$OffsetM = 0.075,
    [double]$SupportRadiusM = 0.05,
    [ValidateSet("true", "false")][string]$Filtering = "true",
    [ValidateSet("true", "false")][string]$Collision = "true",
    [ValidateSet("strict_all", "allow_self_support", "allow_self_center")][string]$Policy = "strict_all",
    [ValidateSet("phase6ep", "phase6eq")][string]$ReportPhase = "phase6ep",
    [string]$SampleFrames = "60,120,180,200",
    [switch]$SpatialAllChannels,
    [int]$RunIndex = 1,
    [switch]$Capture,
    [int]$CaptureStart = 21,
    [int]$CaptureEnd = 200
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
. (Join-Path $PSScriptRoot "kit_shutdown_policy.ps1")
$release = Join-Path $root "_build\windows-x86_64\release"
$kit = Join-Path $release "kit\kit.exe"
$output = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $output) { throw "Phase 6EP refuses output reuse: $output" }
New-Item -ItemType Directory -Path $output | Out-Null
$raw = Join-Path $output "raw.json"
$log = Join-Path $output "kit.log"
$dumpDir = Join-Path $output "sensitive-crash-dumps"
$diagnosticDir = Join-Path $output "sensitive-shutdown-diagnostics"
$evidencePath = Join-Path $output "runner_evidence.json"
$productionApp = Join-Path $release "apps\campfire.simulator.kit"
$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$app = Join-Path $release "kit\apps\omni.app.editor.base.kit"
$probe = Join-Path $PSScriptRoot "probe_phase6ep_point_collision_coexistence.py"
$filterValue = $Filtering
$collisionValue = $Collision
$captureValue = $Capture.IsPresent.ToString().ToLowerInvariant()
$arguments = @(
    $app,
    "--no-window",
    "--/app/file/ignoreUnsavedOnExit=true",
    "--/app/fastShutdown=0",
    "--/app/quitAfter=300000",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/app/window/hideUi=true",
    "--/app/asyncRendering=false",
    "--/renderer/enabled=rtx",
    "--/renderer/active=rtx",
    "--/persistent/rtx/modes/rt/enabled=false",
    "--/persistent/rtx/modes/pt/enabled=true",
    "--/persistent/rtx/modes/rt2/enabled=true",
    "--/phase6ep/output=$raw",
    "--/phase6ep/scenario=$Scenario",
    "--/phase6ep/offsetM=$OffsetM",
    "--/phase6ep/supportRadiusM=$SupportRadiusM",
    "--/phase6ep/filtering=$filterValue",
    "--/phase6ep/collision=$collisionValue",
    "--/phase6ep/policy=$Policy",
    "--/phase6ep/reportPhase=$ReportPhase",
    "--/phase6ep/sampleFrames=$SampleFrames",
    "--/phase6ep/spatialAllChannels=$($SpatialAllChannels.IsPresent.ToString().ToLowerInvariant())",
    "--/phase6ep/runIndex=$RunIndex",
    "--/phase6ep/capture=$captureValue",
    "--/phase6ep/captureStart=$CaptureStart",
    "--/phase6ep/captureEnd=$CaptureEnd",
    "--/rtx/flow/enabled=true",
    "--/log/file=$log",
    "--/log/fileLogLevel=Info",
    "--enable", "omni.flowusd",
    "--enable", "omni.volume",
    "--enable", "omni.hydra.rtx",
    "--enable", "omni.kit.viewport.window",
    "--enable", "omni.kit.renderer.capture",
    "--enable", "omni.physx.cooking",
    "--enable", "omni.physx.stageupdate",
    "--exec", $probe
) + @(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $dumpDir)

$registryBefore = Get-CampfireCrashRegistrySnapshot
$process = Start-Process -FilePath $kit -ArgumentList $arguments -PassThru -WindowStyle Hidden
$monitor = Wait-CampfireKitProcessWithShutdownPolicy -Process $process -ExpectedExecutable $kit -LifecyclePath $raw -LogPath $log -DiagnosticDir $diagnosticDir -ShutdownGraceSeconds 60 -AbsoluteTimeoutSeconds 330
$logEvidenceReadiness = [ordered]@{ available=$false; attempts=0; waited_seconds=0.0; last_error=$null; maximum_wait_seconds=15 }
$logReadyStopwatch = [Diagnostics.Stopwatch]::StartNew()
do {
    $logEvidenceReadiness.attempts += 1
    $readinessProbe = Get-CampfireWindowsExceptionEvidence -Path $log
    $logEvidenceReadiness.available = [bool]$readinessProbe.available
    $logEvidenceReadiness.last_error = $readinessProbe.error
    if ($logEvidenceReadiness.available -or $logReadyStopwatch.Elapsed.TotalSeconds -ge $logEvidenceReadiness.maximum_wait_seconds) { break }
    Start-Sleep -Milliseconds 100
} while ($true)
$logReadyStopwatch.Stop()
$logEvidenceReadiness.waited_seconds = $logReadyStopwatch.Elapsed.TotalSeconds
$registryAfter = Get-CampfireCrashRegistrySnapshot
$registryUnchanged = (($registryBefore | ConvertTo-Json -Depth 12 -Compress) -eq ($registryAfter | ConvertTo-Json -Depth 12 -Compress))
$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$dumps = @(Get-CampfireCrashDumpInventory -DumpDir $dumpDir)
$fatalPatterns = @(
    "[crash] A crash has occurred", "Traceback (most recent call last)",
    "CUDA illegal address", "0xC0000005", "access violation", "device lost",
    "invalid pointer", "TDR", "IRenderSettings::getRenderSettings failed getting a stage-id"
)
$fatalLines = @()
foreach ($pattern in $fatalPatterns) {
    $fatalLines += @(Select-String -LiteralPath $log -SimpleMatch $pattern -ErrorAction SilentlyContinue | ForEach-Object { $_.Line })
}
$uploadAttemptLines = @(Select-String -LiteralPath $log -Pattern "upload(?:ing|ed)? (?:mini)?dump|sending crash|submit.*crash" -CaseSensitive:$false -ErrorAction SilentlyContinue | ForEach-Object { $_.Line })
$probeReport = $null
if (Test-Path -LiteralPath $raw) { $probeReport = Get-Content -Raw -Encoding UTF8 $raw | ConvertFrom-Json }
$outcome = $null
if ($null -ne $probeReport) {
    $outcome = Invoke-CampfireShutdownOutcomeClassification -Monitor $monitor -ProbeReport $probeReport -LogPath $log -FatalLines $fatalLines -DumpCount $dumps.Count -UploadAttemptCount $uploadAttemptLines.Count -ProductionHashBefore $productionHashBefore -ProductionHashAfter $productionHashAfter -OutputDir $output
}
$evidence = [ordered]@{
    schema = "campfire.$ReportPhase.point-collision-runner.v1"
    phase = $ReportPhase
    scenario = $Scenario
    offset_m = $OffsetM
    filtering = ($Filtering -eq "true")
    collision = ($Collision -eq "true")
    policy = $Policy
    sample_frames = $SampleFrames
    spatial_all_channels = $SpatialAllChannels.IsPresent
    run_index = $RunIndex
    process_exit_code = $monitor.exit_code
    shutdown_monitor = $monitor
    log_evidence_readiness = $logEvidenceReadiness
    outcome = $outcome
    fatal_lines = @($fatalLines)
    dump_inventory = $dumps
    automatic_upload_attempt_lines = @($uploadAttemptLines)
    relevant_crash_registry_unchanged = $registryUnchanged
    production_app_sha256_before = $productionHashBefore
    production_app_sha256_after = $productionHashAfter
    production_changed = ($productionHashBefore -ne $productionHashAfter)
    lifecycle_marker = if ($null -ne $probeReport) { $probeReport.lifecycle_marker } else { $null }
    probe_status = if ($null -ne $probeReport) { $probeReport.status } else { "missing" }
}
[IO.File]::WriteAllText($evidencePath, ($evidence | ConvertTo-Json -Depth 12) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))

if (-not $registryUnchanged) { throw "Phase 6EP changed crash registry" }
if ($productionHashBefore -ne $productionHashAfter) { throw "Phase 6EP changed production app" }
if ($dumps.Count -gt 0 -or $fatalLines.Count -gt 0 -or $uploadAttemptLines.Count -gt 0) { throw "Phase 6EP safety evidence failed" }
if ($null -eq $probeReport -or $probeReport.status -ne "ok" -or $probeReport.lifecycle_marker -ne "shutdown_complete") { throw "Phase 6EP probe failed" }
if ($null -eq $outcome -or $outcome.functional_status -ne "pass" -or $outcome.lifecycle_status -ne "normal_exit") { throw "Phase 6EP normal exit required" }
Write-Host "$ReportPhase passed: $Scenario offset=$OffsetM policy=$Policy filtering=$Filtering collision=$Collision run=$RunIndex"
