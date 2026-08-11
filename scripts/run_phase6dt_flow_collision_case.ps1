param(
    [Parameter(Mandatory = $true)][ValidateSet(
        "reference_unmodified_on",
        "reference_numeric_on",
        "reference_numeric_off",
        "phase6ds_baseline_on",
        "phase6ds_physx_collision_api",
        "phase6ds_force_simulate_false",
        "phase6ds_layer_2",
        "phase6ds_physics_convex_false",
        "phase6ds_collision_relation",
        "phase6ds_cube_reference_schema_bundle",
        "phase6ds_mesh_collision_only",
        "phase6ds_mesh_no_collision_schema",
        "phase6ds_mesh_usd_mesh_collision",
        "phase6ds_mesh_usd_mesh_collision_none",
        "phase6ds_mesh_usd_mesh_collision_convex_hull",
        "phase6ds_mesh_reference_schema_bundle",
        "phase6ds_mesh_reference_collision_disabled",
        "phase6ds_mesh_flow_collision_disabled",
        "phase6ds_physx_api_force_false"
    )][string]$Mode,
    [Parameter(Mandatory = $true)][string]$SourceStage,
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [ValidateSet("reference", "campfire")][string]$AppKind = "reference",
    [int]$RunIndex = 1,
    [switch]$Capture
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
$release = Join-Path $root "_build\windows-x86_64\release"
$kit = Join-Path $release "kit\kit.exe"
$source = [IO.Path]::GetFullPath($SourceStage)
$output = [IO.Path]::GetFullPath($OutputDir)
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Phase 6DT source stage missing: $source" }
if (Test-Path -LiteralPath $output) { throw "Phase 6DT refuses output reuse: $output" }
New-Item -ItemType Directory -Path $output | Out-Null
$raw = Join-Path $output "raw.json"
$log = Join-Path $output "kit.log"
$dumpDir = Join-Path $output "sensitive-crash-dumps"
$evidencePath = Join-Path $output "runner_evidence.json"
$productionApp = Join-Path $release "apps\campfire.simulator.kit"
$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
if ($AppKind -eq "reference") {
    $app = Join-Path $release "kit\apps\omni.app.editor.base.kit"
    $extensionArgs = @(
        "--enable", "omni.flowusd",
        "--enable", "omni.volume",
        "--enable", "omni.hydra.rtx",
        "--enable", "omni.kit.viewport.window",
        "--enable", "omni.kit.renderer.capture",
        "--enable", "omni.physx.cooking",
        "--enable", "omni.physx.stageupdate"
    )
} else {
    $app = New-CampfireIsolatedKitApp -SourceApp $productionApp
    $extensionArgs = @()
}
$probe = Join-Path $PSScriptRoot "probe_phase6dt_flow_collision_reference.py"
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
    "--/exts/campfire.app/autoCreateScene=false",
    "--/phase6dt/output=$raw",
    "--/phase6dt/mode=$Mode",
    "--/phase6dt/source=$source",
    "--/phase6dt/runIndex=$RunIndex",
    "--/phase6dt/appKind=$AppKind",
    "--/phase6dt/capture=$($Capture.IsPresent.ToString().ToLowerInvariant())",
    "--/rtx/flow/enabled=true",
    "--/log/file=$log",
    "--/log/fileLogLevel=Info"
) + $extensionArgs + @("--exec", $probe) + @(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $dumpDir)

$registryBefore = Get-CampfireCrashRegistrySnapshot
$started = Get-Date
$process = Start-Process -FilePath $kit -ArgumentList $arguments -PassThru -WindowStyle Hidden
if (-not $process.WaitForExit(330000)) {
    Stop-Process -Id $process.Id -Force
    throw "Phase 6DT timed out: $Mode"
}
$process.Refresh()
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
    "IRenderSettings::getRenderSettings failed getting a stage-id"
)
$fatalLines = @()
foreach ($pattern in $fatalPatterns) {
    $fatalLines += @(Select-String -LiteralPath $log -SimpleMatch $pattern -ErrorAction SilentlyContinue | ForEach-Object { $_.Line })
}
$uploadAttemptLines = @(Select-String -LiteralPath $log -Pattern "upload(?:ing|ed)? (?:mini)?dump|sending crash|submit.*crash" -CaseSensitive:$false -ErrorAction SilentlyContinue | ForEach-Object { $_.Line })
$probeReport = $null
if (Test-Path -LiteralPath $raw) { $probeReport = Get-Content -Raw -Encoding UTF8 $raw | ConvertFrom-Json }
$evidence = [ordered]@{
    schema = "campfire.phase6dt.flow-collision-runner.v1"
    phase = "phase6dt"
    mode = $Mode
    app_kind = $AppKind
    run_index = $RunIndex
    started_local = $started.ToString("o")
    process_exit_code = $process.ExitCode
    fatal_lines = @($fatalLines)
    dump_inventory = $dumps
    automatic_upload_attempt_lines = @($uploadAttemptLines)
    crash_reporter = Get-CampfireCrashSafetyEvidence -LogPath $log -DumpDir $dumpDir
    relevant_crash_registry_unchanged = $registryUnchanged
    production_app_sha256_before = $productionHashBefore
    production_app_sha256_after = $productionHashAfter
    production_changed = ($productionHashBefore -ne $productionHashAfter)
    lifecycle_marker = if ($null -ne $probeReport) { $probeReport.lifecycle_marker } else { $null }
    probe_status = if ($null -ne $probeReport) { $probeReport.status } else { "missing" }
}
[IO.File]::WriteAllText($evidencePath, ($evidence | ConvertTo-Json -Depth 12) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))

if (-not $registryUnchanged) { throw "Phase 6DT changed crash-reporting registry settings" }
if ($productionHashBefore -ne $productionHashAfter) { throw "Phase 6DT changed production app" }
if ($dumps.Count -gt 0) { throw "Phase 6DT produced a dump; do not retry $Mode" }
if ($fatalLines.Count -gt 0) { throw "Phase 6DT fatal token detected; do not retry $Mode" }
if ($uploadAttemptLines.Count -gt 0) { throw "Phase 6DT detected automatic crash upload" }
if ($process.ExitCode -ne 0) { throw "Phase 6DT Kit exited $($process.ExitCode); do not retry $Mode" }
if ($null -eq $probeReport -or $probeReport.status -ne "ok") { throw "Phase 6DT probe failed: $raw" }
if ($probeReport.lifecycle_marker -ne "shutdown_complete") { throw "Phase 6DT unsafe shutdown: $($probeReport.lifecycle_marker)" }
Write-Host "Phase 6DT passed: $Mode run $RunIndex ($AppKind)"
