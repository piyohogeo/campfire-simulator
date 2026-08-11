param(
    [Parameter(Mandatory = $true)][ValidateSet(
        "box_offline",
        "failed_cylinder_offline",
        "box_control",
        "box_hull",
        "cylinder_decomposition",
        "cylinder_hull",
        "cylinder_hull_hierarchy",
        "cylinder_hull_render_surface",
        "cylinder_hull_analytic_sibling"
    )][string]$Mode,
    [Parameter(Mandatory = $true)][int]$RunIndex,
    [Parameter(Mandatory = $true)][string]$SourceStage,
    [Parameter(Mandatory = $true)][string]$OutputDir
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
$release = Join-Path $root "_build\windows-x86_64\release"
$kit = Join-Path $release "kit\kit.exe"
$productionApp = Join-Path $release "apps\campfire.simulator.kit"
$app = New-CampfireIsolatedKitApp -SourceApp $productionApp
$probe = Join-Path $PSScriptRoot "probe_phase6dv_stage_open_boundary.py"
$source = [IO.Path]::GetFullPath($SourceStage)
$output = [IO.Path]::GetFullPath($OutputDir)
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Phase 6DV source missing: $source" }
if (Test-Path -LiteralPath $output) { throw "Phase 6DV refuses output reuse: $output" }
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
    "--/renderer/enabled=rtx",
    "--/renderer/active=rtx",
    "--/persistent/rtx/modes/rt/enabled=false",
    "--/persistent/rtx/modes/pt/enabled=true",
    "--/persistent/rtx/modes/rt2/enabled=true",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/exts/campfire.app/woodVisualV3Enabled=false",
    "--/phase6dv/output=$raw",
    "--/phase6dv/mode=$Mode",
    "--/phase6dv/source=$source",
    "--/phase6dv/runIndex=$RunIndex",
    "--/rtx/flow/enabled=true",
    "--/log/file=$log",
    "--/log/fileLogLevel=Info",
    "--exec", $probe
) + @(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $dumpDir)

$registryBefore = Get-CampfireCrashRegistrySnapshot
$started = Get-Date
$process = Start-Process -FilePath $kit -ArgumentList $arguments -PassThru -WindowStyle Hidden
if (-not $process.WaitForExit(900000)) {
    Stop-Process -Id $process.Id -Force
    throw "Phase 6DV timed out after 900 seconds: $Mode run $RunIndex"
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
if (Test-Path -LiteralPath $log) {
    foreach ($pattern in $fatalPatterns) {
        $fatalLines += @(Select-String -LiteralPath $log -SimpleMatch $pattern | ForEach-Object { $_.Line })
    }
}
$uploadAttemptLines = @()
if (Test-Path -LiteralPath $log) {
    $uploadAttemptLines = @(Select-String -LiteralPath $log -Pattern "upload(?:ing|ed)? (?:mini)?dump|sending crash|submit.*crash" -CaseSensitive:$false | ForEach-Object { $_.Line })
}
$probeReport = $null
if (Test-Path -LiteralPath $raw) { $probeReport = Get-Content -Raw -Encoding UTF8 $raw | ConvertFrom-Json }
$evidence = [ordered]@{
    schema = "campfire.phase6dv.stage-open-runner.v1"
    phase = "phase6dv"
    mode = $Mode
    run_index = $RunIndex
    source_stage = $source
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
    lifecycle_history = if ($null -ne $probeReport) { @($probeReport.lifecycle_history) } else { @() }
    probe_status = if ($null -ne $probeReport) { $probeReport.status } else { "missing" }
}
[IO.File]::WriteAllText($evidencePath, ($evidence | ConvertTo-Json -Depth 16) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))

if (-not $registryUnchanged) { throw "Phase 6DV changed crash-reporting registry settings" }
if ($productionHashBefore -ne $productionHashAfter) { throw "Phase 6DV changed production app" }
if ($dumps.Count -gt 0) { throw "Phase 6DV produced a dump; do not retry $Mode" }
if ($fatalLines.Count -gt 0) { throw "Phase 6DV fatal token detected; do not retry $Mode" }
if ($uploadAttemptLines.Count -gt 0) { throw "Phase 6DV detected automatic crash upload" }
if ($process.ExitCode -ne 0) { throw "Phase 6DV Kit exited $($process.ExitCode); do not retry $Mode" }
if ($null -eq $probeReport -or $probeReport.status -ne "ok") { throw "Phase 6DV probe failed: $raw" }
if ($probeReport.lifecycle_marker -ne "shutdown_complete") { throw "Phase 6DV unsafe shutdown: $($probeReport.lifecycle_marker)" }
Write-Host "Phase 6DV passed: $Mode run $RunIndex"
