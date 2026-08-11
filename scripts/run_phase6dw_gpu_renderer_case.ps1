param(
    [Parameter(Mandatory = $true)][ValidateSet(
        "kit_only",
        "openusd_empty",
        "rtx_empty",
        "box_openusd",
        "box_rtx",
        "flow_load",
        "flow_sim"
    )][string]$Condition,
    [Parameter(Mandatory = $true)][ValidateSet("normal", "isolated")][string]$CacheKind,
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [string]$SourceStage = "",
    [int]$TimeoutSeconds = 420,
    [ValidateRange(1, 60)][int]$ShutdownGraceSeconds = 60,
    [int]$ActiveGpu = -1
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
. (Join-Path $PSScriptRoot "kit_shutdown_policy.ps1")
$release = Join-Path $root "_build\windows-x86_64\release"
$kit = Join-Path $release "kit\kit.exe"
$productionApp = Join-Path $release "apps\campfire.simulator.kit"
$emptyApp = Join-Path $release "kit\apps\omni.app.empty.kit"
$viewportApp = Join-Path $release "kit\apps\omni.app.viewport.kit"
$probe = Join-Path $PSScriptRoot "probe_phase6dw_gpu_renderer_lifecycle.py"
$output = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $output) { throw "Phase 6DW refuses output reuse: $output" }
New-Item -ItemType Directory -Path $output | Out-Null
$raw = Join-Path $output "raw.json"
$log = Join-Path $output "kit.log"
$evidencePath = Join-Path $output "runner_evidence.json"
$diagnosticDir = Join-Path $output "sensitive-shutdown-diagnostics"
$dumpDir = Join-Path $output "sensitive-crash-dumps"
$cacheDir = Join-Path $output "isolated-omni-cache"
$source = if ($SourceStage) { [IO.Path]::GetFullPath($SourceStage) } else { "" }
$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$rendererConditions = @("rtx_empty", "box_rtx", "flow_load", "flow_sim")
$flowConditions = @("flow_load", "flow_sim")
$app = if ($Condition -in $rendererConditions) { $viewportApp } else { $emptyApp }
$extensionArgs = @()
$openUsdConditions = @("openusd_empty", "box_openusd")
if ($Condition -in $openUsdConditions) {
    $extensionArgs += @("--enable", "omni.usd")
}
if ($Condition -in $rendererConditions) {
    $extensionArgs += @(
        "--enable", "omni.usd",
        "--enable", "omni.hydra.rtx",
        "--enable", "omni.hydra.usdrt_delegate",
        "--enable", "omni.kit.viewport.utility"
    )
}
if ($Condition -in $flowConditions) {
    $extensionArgs += @("--enable", "omni.flowusd")
}
if ($Condition -eq "flow_sim") {
    $extensionArgs += @("--enable", "omni.volume")
}
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
    "--/app/useFabricSceneDelegate=true",
    "--/renderer/multiGpu/enabled=false",
    "--/renderer/multiGpu/autoEnable=false",
    "--/phase6dw/output=$raw",
    "--/phase6dw/condition=$Condition",
    "--/phase6dw/cacheKind=$CacheKind",
    "--/phase6dw/source=$source",
    "--/rtx/flow/enabled=true",
    "--/log/file=$log",
    "--/log/fileLogLevel=Info"
)
if ($Condition -in $rendererConditions) {
    $arguments += @(
        "--/renderer/enabled=rtx",
        "--/renderer/active=rtx",
        "--/persistent/rtx/modes/rt/enabled=false",
        "--/persistent/rtx/modes/pt/enabled=true",
        "--/persistent/rtx/modes/rt2/enabled=true"
    )
    if ($ActiveGpu -ge 0) {
        $arguments += "--/renderer/activeGpu=$ActiveGpu"
    }
}
if ($CacheKind -eq "isolated") {
    New-Item -ItemType Directory -Path $cacheDir | Out-Null
    $arguments += "--/app/tokens/omni_cache=$cacheDir"
}
$arguments += $extensionArgs
$arguments += @("--exec", $probe)
$arguments += @(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $dumpDir)

function Get-GpuSnapshot {
    $rows = @()
    $text = & nvidia-smi --query-gpu=index,uuid,name,pci.bus_id,pci.device_id,driver_version,display_active,memory.total,memory.used,utilization.gpu,power.draw,temperature.gpu --format=csv,noheader,nounits
    foreach ($line in @($text)) {
        $values = @($line -split ',\s*')
        if ($values.Count -ne 12) { continue }
        $rows += [ordered]@{
            index = $values[0]; uuid = $values[1]; name = $values[2]; pci_bus_id = $values[3]
            pci_device_id = $values[4]; driver_version = $values[5]; display_active = $values[6]
            memory_total_mib = $values[7]; memory_used_mib = $values[8]; utilization_percent = $values[9]
            power_w = $values[10]; temperature_c = $values[11]
        }
    }
    return @($rows)
}

$registryBefore = Get-CampfireCrashRegistrySnapshot
$gpuBefore = @(Get-GpuSnapshot)
$started = Get-Date
$process = Start-Process -FilePath $kit -ArgumentList $arguments -PassThru -WindowStyle Hidden
$monitor = Wait-CampfireKitProcessWithShutdownPolicy -Process $process -ExpectedExecutable $kit -LifecyclePath $raw -LogPath $log -DiagnosticDir $diagnosticDir -ShutdownGraceSeconds $ShutdownGraceSeconds -AbsoluteTimeoutSeconds $TimeoutSeconds
$process.Refresh()
$ended = Get-Date
$gpuAfter = @(Get-GpuSnapshot)
$registryAfter = Get-CampfireCrashRegistrySnapshot
$registryUnchanged = (($registryBefore | ConvertTo-Json -Depth 12 -Compress) -eq ($registryAfter | ConvertTo-Json -Depth 12 -Compress))
$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$dumps = @(Get-CampfireCrashDumpInventory -DumpDir $dumpDir)
$fatalPatterns = @(
    "[crash] A crash has occurred",
    "Traceback (most recent call last)",
    "CUDA illegal address",
    "0xC0000005",
    "access violation",
    "device lost",
    "invalid pointer",
    "TDR",
    "IRenderSettings::getRenderSettings failed getting a stage-id"
)
$fatalLines = @()
if (Test-Path -LiteralPath $log) {
    foreach ($pattern in $fatalPatterns) {
        $fatalLines += @(Select-String -LiteralPath $log -SimpleMatch $pattern | ForEach-Object { $_.Line })
    }
}
$uploadAttemptLines = @()
if (Test-Path -LiteralPath $log) {
    $uploadAttemptLines = @(Select-String -LiteralPath $log -Pattern "upload(?:ing|ed)? (?:mini)?dump|sending crash|submit.*crash" -CaseSensitive:$false | ForEach-Object { $_.Line })
}
$deviceLines = @()
$pluginShutdownLines = @()
if (Test-Path -LiteralPath $log) {
    $deviceLines = @(Select-String -LiteralPath $log -Pattern "Active GPU:|CUDA device index:|CUDA device ordinal:|Using CUDA device ordinal|Found [0-9]+ CUDA device|Device [0-9]+: NVIDIA|\| [01] +\| NVIDIA GeForce|getHydraEngineDeviceMask|assigned to device|Reducing '/app/runLoops/present/rateLimitFrequency'" | ForEach-Object { $_.Line })
    $pluginShutdownLines = @(Select-String -LiteralPath $log -Pattern "omni\.hydra\.rtx.*shutdown|omni\.flowusd.*shutdown|omni\.kit\.renderer\.plugin.*shutdown|unloaded$" | ForEach-Object { $_.Line })
}
$probeReport = $null
if (Test-Path -LiteralPath $raw) { $probeReport = Get-Content -Raw -Encoding UTF8 $raw | ConvertFrom-Json }
$timedOut = [bool]$monitor.absolute_timeout
$exitCode = $monitor.exit_code
$outcome = $null
if ($null -ne $probeReport) {
    $outcome = Invoke-CampfireShutdownOutcomeClassification -Monitor $monitor -ProbeReport $probeReport -LogPath $log -FatalLines $fatalLines -DumpCount $dumps.Count -UploadAttemptCount $uploadAttemptLines.Count -ProductionHashBefore $productionHashBefore -ProductionHashAfter $productionHashAfter -OutputDir $output
}
$evidence = [ordered]@{
    schema = "campfire.phase6dw.gpu-renderer-lifecycle-runner.v2"
    phase = "phase6dw"
    condition = $Condition
    cache_kind = $CacheKind
    started_local = $started.ToString("o")
    ended_local = $ended.ToString("o")
    duration_seconds = ($ended - $started).TotalSeconds
    process_exit_code = $exitCode
    timed_out = $timedOut
    shutdown_monitor = $monitor
    outcome = $outcome
    fatal_lines = @($fatalLines)
    dump_inventory = $dumps
    automatic_upload_attempt_lines = @($uploadAttemptLines)
    crash_reporter = Get-CampfireCrashSafetyEvidence -LogPath $log -DumpDir $dumpDir
    relevant_crash_registry_unchanged = $registryUnchanged
    production_app_sha256_before = $productionHashBefore
    production_app_sha256_after = $productionHashAfter
    production_changed = ($productionHashBefore -ne $productionHashAfter)
    gpu_before = $gpuBefore
    gpu_after = $gpuAfter
    selected_device_log_lines = @($deviceLines)
    plugin_shutdown_log_lines = @($pluginShutdownLines)
    lifecycle_marker = if ($null -ne $probeReport) { $probeReport.lifecycle_marker } else { $null }
    lifecycle_history = if ($null -ne $probeReport) { @($probeReport.lifecycle_history) } else { @() }
    probe_status = if ($null -ne $probeReport) { $probeReport.status } else { "missing" }
}
[IO.File]::WriteAllText($evidencePath, ($evidence | ConvertTo-Json -Depth 18) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))

if (-not $registryUnchanged) { throw "Phase 6DW changed crash-reporting registry settings" }
if ($productionHashBefore -ne $productionHashAfter) { throw "Phase 6DW changed production app" }
if ($dumps.Count -gt 0) { throw "Phase 6DW produced a dump; stop the matrix" }
if ($fatalLines.Count -gt 0) { throw "Phase 6DW fatal token detected; stop the matrix" }
if ($uploadAttemptLines.Count -gt 0) { throw "Phase 6DW detected automatic crash upload" }
if ($null -eq $probeReport -or $probeReport.status -ne "ok") { throw "Phase 6DW probe failed: $raw" }
if ($probeReport.lifecycle_marker -ne "shutdown_requested") { throw "Phase 6DW unsafe lifecycle marker: $($probeReport.lifecycle_marker)" }
if ($null -eq $outcome -or $outcome.functional_status -ne "pass") { throw "Phase 6DW shutdown classification failed: $Condition / $CacheKind" }
Write-Host "Phase 6DW functionally passed: $Condition / $CacheKind ($($outcome.lifecycle_status))"
