param(
    [string]$OutputRoot = "",
    [string]$SourceStage = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
. (Join-Path $PSScriptRoot "phase6ea_diagnostic_common.ps1")
if (-not $OutputRoot) { $OutputRoot = Join-Path $root "artifacts\phase6eg-static-pose-qualification-1" }
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6EG refuses artifact root reuse: $OutputRoot" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null

$release = Join-Path $root "_build\windows-x86_64\release"
$kit = Join-Path $release "kit\kit.exe"
$emptyApp = Join-Path $release "kit\apps\omni.app.empty.kit"
$productionApp = Join-Path $release "apps\campfire.simulator.kit"
$contractPath = Join-Path $PSScriptRoot "phase6eg_static_pose_set_contract.json"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6eg_static_pose_set_qualification.py"
$prepareProbe = Join-Path $PSScriptRoot "prepare_phase6eg_static_pose_set.py"
$flowRunner = Join-Path $PSScriptRoot "run_phase6dt_flow_collision_case.ps1"
$referenceNpz = Join-Path $root "artifacts\phase6ef-static-y40-qualification-1\spatial\run_1\B_rotate_y40_on\B_rotate_y40_on_f0060_velocity.npz"
$qualifiedSourceHash = "BC65721F4C6D4ECF1F35C736F2DD10F7A47C9F2B361E45898032E869D894D5F9"
if (-not $SourceStage) { $SourceStage = Join-Path $root "artifacts\phase6dy-calibrated-stage-open-1\prepared-stages\D_cylinder_decomposition.usda" }
$source = [IO.Path]::GetFullPath($SourceStage)
foreach ($required in @($kit, $emptyApp, $productionApp, $contractPath, $analyzer, $prepareProbe, $flowRunner, $referenceNpz, $source)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Phase 6EG input missing: $required" }
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash -ne $qualifiedSourceHash) { throw "Phase 6EG source is not the qualified Phase 6DY stage" }

$contractHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
if ($contract.phase -ne "phase6eg" -or -not [bool]$contract.declared_before_formal_runs) { throw "Phase 6EG predeclared contract is invalid" }
if ($contract.source_stage_sha256 -ne $qualifiedSourceHash) { throw "Phase 6EG source hash contract changed" }
if (@($contract.poses.psobject.Properties).Count -ne 6 -or @($contract.formal_order).Count -ne 3) { throw "Phase 6EG pose/run contract changed" }
if ((@($contract.formal_order | ForEach-Object { @($_).Count }) | Measure-Object -Sum).Sum -ne 36) { throw "Phase 6EG formal process count changed" }
if ([double]$contract.thresholds.existing_velocity_limit_m_s -ne 0.00001 -or [double]$contract.thresholds.collision_off_positive_minimum_m_s -ne 0.1 -or [double]$contract.thresholds.on_to_off_deep_maximum_ratio -ne 0.01) { throw "Phase 6EG inherited Phase 6EF thresholds changed" }
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "predeclared_contract.json")

$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$preparedRoot = Join-Path $OutputRoot "prepared-stages"
$preflightReport = Join-Path $OutputRoot "preflight.json"
$prepareLog = Join-Path $OutputRoot "prepare.log"
$prepareDump = Join-Path $OutputRoot "prepare-sensitive-crash-dumps"
$caseRunnerLogRoot = Join-Path $OutputRoot "case-runner-logs"
$powershell = (Get-Process -Id $PID).Path
$completed = @()
$outcomes = @()

function Write-SafeStop([string]$Step, [string]$Condition, [string]$Message) {
    $payload = [ordered]@{
        schema = "campfire.phase6eg.safe-stop.v1"
        phase = "phase6eg"
        status = "safe_stop"
        step = $Step
        condition = $Condition
        completed = @($script:completed)
        automatic_retry = $false
        error = $Message
        contract_sha256 = $contractHashBefore
        production_app_sha256_before = $productionHashBefore
        production_app_sha256_after = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
        timestamp_local = (Get-Date).ToString("o")
    }
    [IO.File]::WriteAllText((Join-Path $OutputRoot "safe_stop.json"), ($payload | ConvertTo-Json -Depth 12) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Assert-NoResidual([int]$ProcessId, [string]$ExpectedExecutable) {
    $candidate = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if ($null -ne $candidate) {
        $actual = if ($candidate.ExecutablePath) { [IO.Path]::GetFullPath($candidate.ExecutablePath) } else { "" }
        if ($actual -eq [IO.Path]::GetFullPath($ExpectedExecutable)) { throw "Phase 6EG left a Kit process after completion: $ProcessId" }
    }
}

function Invoke-Phase6EgCase {
    param(
        [Parameter(Mandatory = $true)][int]$RunIndex,
        [Parameter(Mandatory = $true)][string]$Condition
    )
    $pose = $Condition -replace '_(on|off)$', ''
    $collisionOn = $Condition.EndsWith("_on")
    $mode = if ($collisionOn) { "phase6ec_rotated_mesh" } else { "phase6ec_rotated_mesh_collision_off" }
    $stage = Join-Path $preparedRoot "$pose.usda"
    if (-not (Test-Path -LiteralPath $stage -PathType Leaf)) { throw "prepared pose stage missing: $stage" }
    $caseOutput = Join-Path $OutputRoot "formal\run_$RunIndex\$Condition"
    $spatialRoot = Join-Path $OutputRoot "spatial\run_$RunIndex\$Condition"
    New-Item -ItemType Directory -Path $caseRunnerLogRoot -Force | Out-Null
    $logStem = "run_${RunIndex}_$Condition"
    $stdout = Join-Path $caseRunnerLogRoot "$logStem.stdout.log"
    $stderr = Join-Path $caseRunnerLogRoot "$logStem.stderr.log"
    $arguments = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", $flowRunner,
        "-Mode", $mode,
        "-SourceStage", $stage,
        "-OutputDir", $caseOutput,
        "-AppKind", "reference",
        "-RunIndex", "$RunIndex",
        "-SpatialOutputRoot", $spatialRoot,
        "-SpatialCondition", $Condition,
        "-SpatialVelocityOnly"
    )
    $guard = Invoke-Phase6EaGuardedHelper -FilePath $powershell -ArgumentList $arguments -StdoutPath $stdout -StderrPath $stderr -TimeoutSeconds 720 -PrivateBytesLimit 512MB
    if ($guard.timed_out -or $guard.private_bytes_exceeded -or -not $guard.process_absent -or $guard.exit_code_error -ne $null -or $guard.exit_code -ne 0) {
        throw "guarded case failed: timed_out=$($guard.timed_out) private_bytes_exceeded=$($guard.private_bytes_exceeded) process_absent=$($guard.process_absent) exit_code=$($guard.exit_code) peak_private_bytes=$($guard.peak_private_bytes)"
    }
    $evidencePath = Join-Path $caseOutput "runner_evidence.json"
    $rawPath = Join-Path $caseOutput "raw.json"
    if (-not (Test-Path -LiteralPath $evidencePath -PathType Leaf) -or -not (Test-Path -LiteralPath $rawPath -PathType Leaf)) { throw "case evidence is missing" }
    $evidence = Get-Content -Raw -Encoding UTF8 $evidencePath | ConvertFrom-Json
    $raw = Get-Content -Raw -Encoding UTF8 $rawPath | ConvertFrom-Json
    if ($evidence.outcome.functional_status -ne "pass") { throw "functional classification did not pass" }
    if ($evidence.outcome.lifecycle_status -ne "normal_exit" -or $evidence.process_exit_code -ne 0) { throw "normal OS exit is required; known residual is not accepted" }
    if ($evidence.timed_out -or @($evidence.fatal_lines).Count -or @($evidence.dump_inventory).Count -or @($evidence.automatic_upload_attempt_lines).Count) { throw "fatal/dump/upload/timeout evidence is not accepted" }
    if (-not [bool]$evidence.relevant_crash_registry_unchanged -or [bool]$evidence.production_changed) { throw "crash registry or production app changed" }
    if ($raw.status -ne "ok" -or $raw.lifecycle_marker -ne "shutdown_complete") { throw "probe result or shutdown marker failed" }
    $manifest = Get-Content -Raw -Encoding UTF8 (Join-Path $spatialRoot "manifest.json") | ConvertFrom-Json
    if ($manifest.file_count -ne 4 -or @($manifest.files | Where-Object { $_.channel -ne "velocity" }).Count) { throw "velocity-only capture contract failed" }
    $script:outcomes += [pscustomobject]@{
        run = $RunIndex
        condition = $Condition
        functional_status = $evidence.outcome.functional_status
        lifecycle_status = $evidence.outcome.lifecycle_status
        exit_code = $evidence.process_exit_code
        active_blocks_final = $raw.active_blocks_final
        source_fuel = $raw.stage_audit.emitter.fuel
        runner_peak_private_bytes = $guard.peak_private_bytes
        spatial_peak_rss_bytes = $manifest.peak_rss_bytes
        spatial_peak_rss_delta_bytes = $manifest.peak_rss_delta_bytes
    }
    $script:completed += "run_${RunIndex}/$Condition"
}

$prepareArgs = @(
    $emptyApp,
    "--no-window",
    "--/app/fastShutdown=0",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/phase6eg/source=$source",
    "--/phase6eg/contract=$contractPath",
    "--/phase6eg/outputRoot=$preparedRoot",
    "--/phase6eg/report=$preflightReport",
    "--/phase6eg/referenceNpz=$referenceNpz",
    "--/log/file=$prepareLog",
    "--/log/fileLogLevel=Info",
    "--enable", "omni.usd",
    "--enable", "omni.flowusd",
    "--exec", $prepareProbe
) + @(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $prepareDump)
$prepareProcess = Start-Process -FilePath $kit -ArgumentList $prepareArgs -PassThru -WindowStyle Hidden
if (-not $prepareProcess.WaitForExit(180000)) {
    $candidate = Get-CimInstance Win32_Process -Filter "ProcessId=$($prepareProcess.Id)" -ErrorAction SilentlyContinue
    if ($null -ne $candidate -and [IO.Path]::GetFullPath($candidate.ExecutablePath) -eq [IO.Path]::GetFullPath($kit)) { Stop-Process -Id $prepareProcess.Id -Force; $prepareProcess.WaitForExit(10000) | Out-Null }
    Write-SafeStop "preflight" "offline_pose_set" "offline preflight timed out"
    throw "Phase 6EG offline preflight timed out"
}
$prepareProcess.Refresh()
Assert-NoResidual $prepareProcess.Id $kit
$prepareFatal = @()
foreach ($token in @("[crash] A crash has occurred", "Traceback (most recent call last)", "CUDA illegal address", "device lost", "invalid pointer", "TDR")) {
    $prepareFatal += @(Select-String -LiteralPath $prepareLog -SimpleMatch $token -ErrorAction SilentlyContinue)
}
$prepareDumps = @(Get-CampfireCrashDumpInventory -DumpDir $prepareDump)
$prepareUploads = @(Select-String -LiteralPath $prepareLog -Pattern "upload(?:ing|ed)? (?:mini)?dump|sending crash|submit.*crash" -CaseSensitive:$false -ErrorAction SilentlyContinue)
if ($prepareProcess.ExitCode -ne 0 -or $prepareFatal.Count -or $prepareDumps.Count -or $prepareUploads.Count) {
    Write-SafeStop "preflight" "offline_pose_set" "offline preflight failed safety gates"
    throw "Phase 6EG offline preflight failed safely"
}
$preflight = Get-Content -Raw -Encoding UTF8 $preflightReport | ConvertFrom-Json
if ($preflight.status -ne "ok" -or @($preflight.gates.psobject.Properties | Where-Object { -not [bool]$_.Value }).Count) { throw "Phase 6EG offline pose gates failed" }

try {
    for ($runIndex = 1; $runIndex -le 3; $runIndex++) {
        foreach ($condition in @($contract.formal_order[$runIndex - 1])) {
            Invoke-Phase6EgCase -RunIndex $runIndex -Condition ([string]$condition)
        }
    }
} catch {
    Write-SafeStop "formal_flow_readback" ([string]$condition) $_.Exception.Message
    throw
}

if ((Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash -ne $contractHashBefore) { throw "Phase 6EG contract changed after formal runs" }
& python $analyzer --root $OutputRoot --contract $contractPath --output (Join-Path $OutputRoot "report.json") --svg (Join-Path $OutputRoot "qualification.svg") --archive (Join-Path $OutputRoot "velocity_samples.zip")
if ($LASTEXITCODE -ne 0) {
    Write-SafeStop "analysis" "qualification" "Phase 6EG predeclared numeric gates failed"
    throw "Phase 6EG qualification failed"
}
$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
if ($productionHashBefore -ne $productionHashAfter) { throw "Phase 6EG changed production app" }
$matrix = [ordered]@{
    schema = "campfire.phase6eg.matrix-complete.v1"
    phase = "phase6eg"
    status = "ok"
    contract_sha256 = $contractHashBefore
    formal_order = @($contract.formal_order)
    completed = @($completed)
    outcomes = @($outcomes)
    report = (Join-Path $OutputRoot "report.json")
    production_app_sha256_before = $productionHashBefore
    production_app_sha256_after = $productionHashAfter
    production_changed = $false
    previous_phase_artifacts_overwritten = $false
}
[IO.File]::WriteAllText((Join-Path $OutputRoot "matrix_complete.json"), ($matrix | ConvertTo-Json -Depth 12) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host "Phase 6EG complete: 36 normal-exit processes and all predeclared gates passed"
