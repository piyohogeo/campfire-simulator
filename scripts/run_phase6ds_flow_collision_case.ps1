param(
    [Parameter(Mandatory = $true)][ValidateSet("collision_off", "box_aligned", "box_shift_half", "box_shift_one")][string]$Condition,
    [Parameter(Mandatory = $true)][int]$RunIndex,
    [Parameter(Mandatory = $true)][double]$BoxShiftM,
    [string]$OutputDir = "",
    [switch]$Capture
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
$release = Join-Path $root "_build\windows-x86_64\release"
$kit = Join-Path $release "kit\kit.exe"
$productionApp = Join-Path $release "apps\campfire.simulator.kit"
$app = New-CampfireIsolatedKitApp -SourceApp $productionApp
$probe = Join-Path $PSScriptRoot "probe_phase6ds_flow_collision.py"
if (-not $OutputDir) {
    $OutputDir = Join-Path $root ("artifacts\phase6ds-flow-collision\{0}\run-{1}" -f $Condition, $RunIndex)
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $OutputDir) { throw "Phase 6DS refuses to reuse output: $OutputDir" }
New-Item -ItemType Directory -Path $OutputDir | Out-Null
$dumpDir = Join-Path $OutputDir "sensitive-crash-dumps"
$raw = Join-Path $OutputDir "raw.json"
$log = Join-Path $OutputDir "kit.log"
$evidencePath = Join-Path $OutputDir "runner_evidence.json"
$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$collisionEnabled = ($Condition -ne "collision_off")
$arguments = @(
    $app,
    "--no-window",
    "--/app/file/ignoreUnsavedOnExit=true",
    "--/app/quitAfter=300000",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/app/window/hideUi=true",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/exts/campfire.app/woodVisualV3Enabled=false",
    "--/phase6ds/output=$raw",
    "--/phase6ds/condition=$Condition",
    "--/phase6ds/runIndex=$RunIndex",
    "--/phase6ds/collisionEnabled=$($collisionEnabled.ToString().ToLowerInvariant())",
    "--/phase6ds/boxShiftM=$($BoxShiftM.ToString('R', [Globalization.CultureInfo]::InvariantCulture))",
    "--/phase6ds/capture=$($Capture.IsPresent.ToString().ToLowerInvariant())",
    "--/rtx/flow/enabled=true",
    "--/log/file=$log",
    "--/log/fileLogLevel=Info",
    "--exec", $probe
) + @(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $dumpDir)

$registryBefore = Get-CampfireCrashRegistrySnapshot
$started = Get-Date
$process = Start-Process -FilePath $kit -ArgumentList $arguments -PassThru -WindowStyle Hidden
if (-not $process.WaitForExit(330000)) {
    Stop-Process -Id $process.Id -Force
    throw "Phase 6DS timed out: $Condition run $RunIndex"
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
$safety = Get-CampfireCrashSafetyEvidence -LogPath $log -DumpDir $dumpDir
$evidence = [ordered]@{
    schema = "campfire.phase6ds.flow-collision-runner.v1"
    phase = "phase6ds"
    condition = $Condition
    run_index = $RunIndex
    started_local = $started.ToString("o")
    process_exit_code = $process.ExitCode
    fatal_lines = @($fatalLines)
    native_crash = (@($fatalLines | Where-Object { $_ -like "*[crash] A crash has occurred*" }).Count -gt 0)
    dump_inventory = $dumps
    automatic_upload_attempt_lines = @($uploadAttemptLines)
    crash_reporter = $safety
    relevant_crash_registry_unchanged = $registryUnchanged
    machine_wide_settings_changed = (-not $registryUnchanged)
    production_app_sha256_before = $productionHashBefore
    production_app_sha256_after = $productionHashAfter
    production_changed = ($productionHashBefore -ne $productionHashAfter)
    lifecycle_marker = if ($null -ne $probeReport) { $probeReport.lifecycle_marker } else { $null }
    probe_status = if ($null -ne $probeReport) { $probeReport.status } else { "missing" }
}
[IO.File]::WriteAllText($evidencePath, ($evidence | ConvertTo-Json -Depth 12) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))

if (-not $registryUnchanged) { throw "Phase 6DS changed relevant crash-reporting registry settings" }
if ($productionHashBefore -ne $productionHashAfter) { throw "Phase 6DS changed the production app" }
if ($dumps.Count -gt 0) { throw "Phase 6DS produced a crash dump; do not retry this condition" }
if ($fatalLines.Count -gt 0) { throw "Phase 6DS fatal log token detected; do not retry this condition" }
if ($uploadAttemptLines.Count -gt 0) { throw "Phase 6DS detected an automatic crash-upload attempt" }
if ($process.ExitCode -ne 0) { throw "Phase 6DS Kit exited $($process.ExitCode); do not retry this condition" }
if ($null -eq $probeReport -or $probeReport.status -ne "ok") { throw "Phase 6DS probe did not complete: $raw" }
if ($probeReport.lifecycle_marker -ne "shutdown_complete") { throw "Phase 6DS did not complete safe shutdown: $($probeReport.lifecycle_marker)" }
Write-Host ("Phase 6DS case passed: {0} run {1}" -f $Condition, $RunIndex)
