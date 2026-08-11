param(
    [Parameter(Mandatory = $true)][ValidateSet(
        "box_control",
        "box_hull",
        "cylinder_decomposition"
    )][string]$Mode,
    [Parameter(Mandatory = $true)][int]$RunIndex,
    [Parameter(Mandatory = $true)][string]$SourceStage,
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [int]$TimeoutSeconds = 420
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
$release = Join-Path $root "_build\windows-x86_64\release"
$kit = Join-Path $release "kit\kit.exe"
$productionApp = Join-Path $release "apps\campfire.simulator.kit"
$app = Join-Path $release "kit\apps\omni.app.viewport.kit"
$probe = Join-Path $PSScriptRoot "probe_phase6dv_stage_open_boundary.py"
$source = [IO.Path]::GetFullPath($SourceStage)
$output = [IO.Path]::GetFullPath($OutputDir)
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Phase 6DX source missing: $source" }
if (Test-Path -LiteralPath $output) { throw "Phase 6DX refuses output reuse: $output" }
New-Item -ItemType Directory -Path $output | Out-Null
$dumpDir = Join-Path $output "sensitive-crash-dumps"
$raw = Join-Path $output "raw.json"
$log = Join-Path $output "kit.log"
$evidencePath = Join-Path $output "runner_evidence.json"
$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
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
    "--/renderer/enabled=rtx",
    "--/renderer/active=rtx",
    "--/renderer/multiGpu/enabled=false",
    "--/renderer/multiGpu/autoEnable=false",
    "--/persistent/rtx/modes/rt/enabled=false",
    "--/persistent/rtx/modes/pt/enabled=true",
    "--/persistent/rtx/modes/rt2/enabled=true",
    "--/phase6dx/output=$raw",
    "--/phase6dx/mode=$Mode",
    "--/phase6dx/source=$source",
    "--/phase6dx/runIndex=$RunIndex",
    "--/rtx/flow/enabled=true",
    "--/log/file=$log",
    "--/log/fileLogLevel=Info",
    "--enable", "omni.usd",
    "--enable", "omni.hydra.rtx",
    "--enable", "omni.hydra.usdrt_delegate",
    "--enable", "omni.kit.viewport.utility",
    "--enable", "omni.flowusd",
    "--enable", "omni.volume",
    "--enable", "omni.physx.cooking",
    "--enable", "omni.physx.stageupdate",
    "--exec", $probe
) + @(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $dumpDir)

function Get-GpuSnapshot {
    $rows = @()
    foreach ($line in @(& nvidia-smi --query-gpu=index,name,pci.bus_id,memory.used,utilization.gpu,power.draw,temperature.gpu --format=csv,noheader,nounits)) {
        $values = @($line -split ',\s*')
        if ($values.Count -ne 7) { continue }
        $rows += [ordered]@{ index=$values[0]; name=$values[1]; pci_bus_id=$values[2]; memory_used_mib=$values[3]; utilization_percent=$values[4]; power_w=$values[5]; temperature_c=$values[6] }
    }
    return @($rows)
}

$registryBefore = Get-CampfireCrashRegistrySnapshot
$gpuBefore = @(Get-GpuSnapshot)
$started = Get-Date
$process = Start-Process -FilePath $kit -ArgumentList $arguments -PassThru -WindowStyle Hidden
$timedOut = -not $process.WaitForExit($TimeoutSeconds * 1000)
if ($timedOut) {
    $actual = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.Id)" -ErrorAction SilentlyContinue
    if ($null -ne $actual -and [IO.Path]::GetFullPath($actual.ExecutablePath) -eq [IO.Path]::GetFullPath($kit)) {
        Stop-Process -Id $process.Id -Force
        $process.WaitForExit(10000) | Out-Null
    }
}
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
    "device lost",
    "invalid pointer",
    "TDR",
    "IRenderSettings::getRenderSettings failed getting a stage-id"
)
$fatalLines = @()
if (Test-Path -LiteralPath $log) {
    foreach ($pattern in $fatalPatterns) { $fatalLines += @(Select-String -LiteralPath $log -SimpleMatch $pattern | ForEach-Object { $_.Line }) }
}
$uploadAttemptLines = @()
$deviceLines = @()
$pluginShutdownLines = @()
if (Test-Path -LiteralPath $log) {
    $uploadAttemptLines = @(Select-String -LiteralPath $log -Pattern "upload(?:ing|ed)? (?:mini)?dump|sending crash|submit.*crash" -CaseSensitive:$false | ForEach-Object { $_.Line })
    $deviceLines = @(Select-String -LiteralPath $log -Pattern "Active GPU:|CUDA device index:|CUDA device ordinal:|getHydraEngineDeviceMask|assigned to device|Reducing '/app/runLoops/present/rateLimitFrequency'" | ForEach-Object { $_.Line })
    $pluginShutdownLines = @(Select-String -LiteralPath $log -Pattern "omni\.hydra\.rtx.*shutdown|omni\.flowusd.*shutdown|omni\.kit\.renderer\.plugin.*shutdown" | ForEach-Object { $_.Line })
}
$probeReport = $null
if (Test-Path -LiteralPath $raw) { $probeReport = Get-Content -Raw -Encoding UTF8 $raw | ConvertFrom-Json }
$exitCode = if ($timedOut) { -1 } else { $process.ExitCode }
$evidence = [ordered]@{
    schema = "campfire.phase6dx.stage-open-runner.v1"
    phase = "phase6dx"
    mode = $Mode
    run_index = $RunIndex
    source_stage = $source
    started_local = $started.ToString("o")
    ended_local = $ended.ToString("o")
    duration_seconds = ($ended - $started).TotalSeconds
    process_exit_code = $exitCode
    timed_out = $timedOut
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

if (-not $registryUnchanged) { throw "Phase 6DX changed crash-reporting registry settings" }
if ($productionHashBefore -ne $productionHashAfter) { throw "Phase 6DX changed production app" }
if ($dumps.Count -gt 0) { throw "Phase 6DX produced a dump; stop and do not retry $Mode" }
if ($fatalLines.Count -gt 0) { throw "Phase 6DX fatal token detected; stop and do not retry $Mode" }
if ($uploadAttemptLines.Count -gt 0) { throw "Phase 6DX detected automatic crash upload" }
if ($timedOut) { throw "Phase 6DX timed out; stop and do not retry $Mode" }
if ($process.ExitCode -ne 0) { throw "Phase 6DX Kit exited $($process.ExitCode); stop and do not retry $Mode" }
if ($null -eq $probeReport -or $probeReport.status -ne "ok") { throw "Phase 6DX probe failed: $raw" }
if ($probeReport.lifecycle_marker -ne "shutdown_complete") { throw "Phase 6DX unsafe lifecycle marker: $($probeReport.lifecycle_marker)" }
Write-Host "Phase 6DX passed: $Mode run $RunIndex"
