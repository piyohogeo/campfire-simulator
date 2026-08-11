param([string]$OutputRoot = "")

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
if (-not $OutputRoot) { $OutputRoot = Join-Path $root "artifacts\phase6eg-resource-calibration-1" }
$output = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $output) { throw "Phase 6EG calibration refuses artifact root reuse: $output" }
New-Item -ItemType Directory -Path $output | Out-Null

$release = Join-Path $root "_build\windows-x86_64\release"
$kit = Join-Path $release "kit\kit.exe"
$emptyApp = Join-Path $release "kit\apps\omni.app.empty.kit"
$productionApp = Join-Path $release "apps\campfire.simulator.kit"
$contract = Join-Path $PSScriptRoot "phase6eg_static_pose_set_contract.json"
$source = Join-Path $root "artifacts\phase6dy-calibrated-stage-open-1\prepared-stages\D_cylinder_decomposition.usda"
$prepareProbe = Join-Path $PSScriptRoot "prepare_phase6eg_static_pose_set.py"
$flowRunner = Join-Path $PSScriptRoot "run_phase6dt_flow_collision_case.ps1"
$guard = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
$fixture = Join-Path $PSScriptRoot "phase6eg_resource_guard_fixture.ps1"
$powershell = (Get-Process -Id $PID).Path
$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$qualifiedSourceHash = "BC65721F4C6D4ECF1F35C736F2DD10F7A47C9F2B361E45898032E869D894D5F9"
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash -ne $qualifiedSourceHash) { throw "qualified source hash changed" }

function Invoke-ResourceGuard {
    param([string]$Name, [int]$TimeoutSeconds, [string[]]$Command)
    $dir = Join-Path $output $Name
    New-Item -ItemType Directory -Path $dir | Out-Null
    $args = @(
        $guard,
        "--trace", (Join-Path $dir "memory.jsonl"),
        "--summary", (Join-Path $dir "guard.json"),
        "--stdout", (Join-Path $dir "stdout.log"),
        "--stderr", (Join-Path $dir "stderr.log"),
        "--timeout-seconds", "$TimeoutSeconds",
        "--runner-private-limit", "536870912",
        "--kit-private-limit", "12884901888",
        "--diagnostic-private-limit", "536870912",
        "--tree-private-limit", "15032385536",
        "--available-memory-floor", "8589934592",
        "--commit-headroom-floor", "8589934592",
        "--"
    ) + $Command
    & python @args
    $exit = $LASTEXITCODE
    if (-not (Test-Path -LiteralPath (Join-Path $dir "guard.json"))) { throw "resource guard did not write summary for $Name" }
    $summary = Get-Content -Raw -Encoding UTF8 (Join-Path $dir "guard.json") | ConvertFrom-Json
    return [pscustomobject]@{ name=$Name; launcher_exit=$exit; summary=$summary }
}

$fixtureMarker = Join-Path $output "guard-self-test.markers.jsonl"
$selfTest = Invoke-ResourceGuard "guard-self-test" 30 @($powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $fixture, "-Mode", "tree", "-MarkerPath", $fixtureMarker)
if ($selfTest.launcher_exit -ne 0 -or $selfTest.summary.status -ne "ok") { throw "resource guard tree self-test failed" }
$cdbMarker = Join-Path $output "cdb-path-self-test.markers.jsonl"
$cdbTest = Invoke-ResourceGuard "cdb-path-self-test" 30 @($powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $fixture, "-Mode", "cdb_path", "-MarkerPath", $cdbMarker)
if ($cdbTest.launcher_exit -ne 0 -or $cdbTest.summary.status -ne "ok") { throw "CDB path self-test failed" }

$prepared = Join-Path $output "prepared-stages"
$preflight = Join-Path $output "preflight.json"
$prepareLog = Join-Path $output "prepare.log"
$prepareDumps = Join-Path $output "prepare-sensitive-crash-dumps"
$prepareArgs = @(
    $emptyApp, "--no-window", "--/app/fastShutdown=0", "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0", "--/phase6eg/source=$source", "--/phase6eg/contract=$contract",
    "--/phase6eg/outputRoot=$prepared", "--/phase6eg/report=$preflight",
    "--/phase6eg/referenceNpz=$(Join-Path $root 'artifacts\phase6ef-static-y40-qualification-1\spatial\run_1\B_rotate_y40_on\B_rotate_y40_on_f0060_velocity.npz')",
    "--/log/file=$prepareLog", "--/log/fileLogLevel=Info", "--enable", "omni.usd", "--enable", "omni.flowusd", "--exec", $prepareProbe
) + @(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $prepareDumps)
$prepare = Start-Process -FilePath $kit -ArgumentList $prepareArgs -PassThru -WindowStyle Hidden
if (-not $prepare.WaitForExit(180000)) { Stop-Process -Id $prepare.Id -Force; throw "calibration stage preparation timed out" }
if ($prepare.ExitCode -ne 0) { throw "calibration stage preparation failed" }

$results = @()
foreach ($condition in @("P0_identity", "P3_z33")) {
    $case = Join-Path $output $condition
    $caseOutput = Join-Path $case "case"
    $stage = Join-Path $prepared "$condition.usda"
    $command = @(
        $powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $flowRunner,
        "-Mode", "phase6ec_rotated_mesh", "-SourceStage", $stage, "-OutputDir", $caseOutput,
        "-AppKind", "reference", "-RunIndex", "1", "-StageOpenOnly"
    )
    $result = Invoke-ResourceGuard "$condition-stage-open" 120 $command
    $results += $result
    if ($result.launcher_exit -ne 0 -or $result.summary.status -ne "ok") { break }
}

$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$report = [ordered]@{
    schema = "campfire.phase6eg.resource-calibration.v1"
    phase = "phase6eg_resource_calibration"
    status = if ($results.Count -eq 2 -and @($results | Where-Object { $_.summary.status -ne "ok" }).Count -eq 0) { "ok" } else { "safe_stop" }
    prior_artifact_read_only = (Join-Path $root "artifacts\phase6eg-static-pose-qualification-1")
    old_guard = [ordered]@{ target="direct runner PowerShell only"; private_bytes_limit=536870912; observed_peak_private_bytes=552259584; tree_aggregate=$false }
    budgets = [ordered]@{ runner=536870912; kit=12884901888; diagnostic=536870912; deduplicated_tree=15032385536; available_memory_floor=8589934592; commit_headroom_floor=8589934592 }
    deduplication_key = @("pid", "create_time_utc_epoch")
    self_test = $selfTest.summary
    cdb_path_self_test = $cdbTest.summary
    stage_open_results = @($results | ForEach-Object { $_.summary })
    formal_restart_safe = ($results.Count -eq 2 -and @($results | Where-Object { $_.summary.status -ne "ok" }).Count -eq 0)
    production_app_sha256_before = $productionHashBefore
    production_app_sha256_after = $productionHashAfter
    production_changed = ($productionHashBefore -ne $productionHashAfter)
}
[IO.File]::WriteAllText((Join-Path $output "report.json"), ($report | ConvertTo-Json -Depth 20) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
if (-not $report.formal_restart_safe) { throw "Phase 6EG formal restart is not safe" }
Write-Host "Phase 6EG resource calibration passed; formal restart is safe"
