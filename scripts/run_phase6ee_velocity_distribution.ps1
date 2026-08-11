param(
    [string]$OutputRoot = "",
    [string]$SourceStage = "",
    [switch]$AnalyzeExisting
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
. (Join-Path $PSScriptRoot "phase6ea_diagnostic_common.ps1")
if (-not $OutputRoot) { $OutputRoot = Join-Path $root "artifacts\phase6ee-velocity-distribution-1" }
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
$release = Join-Path $root "_build\windows-x86_64\release"
$kit = Join-Path $release "kit\kit.exe"
$emptyApp = Join-Path $release "kit\apps\omni.app.empty.kit"
$productionApp = Join-Path $release "apps\campfire.simulator.kit"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6ee_velocity_distribution.py"

if ($AnalyzeExisting) {
    if (-not (Test-Path -LiteralPath $OutputRoot -PathType Container)) { throw "Phase 6EE existing artifact root missing: $OutputRoot" }
    & python $analyzer --root $OutputRoot --output (Join-Path $OutputRoot "report.json") --svg (Join-Path $OutputRoot "report.svg") --section-svg (Join-Path $OutputRoot "velocity_section.svg") --archive (Join-Path $OutputRoot "spatial_neighborhoods.zip")
    if ($LASTEXITCODE -ne 0) { throw "Phase 6EE existing spatial analysis failed" }
    $report = Get-Content -Raw -Encoding UTF8 (Join-Path $OutputRoot "report.json") | ConvertFrom-Json
    if (-not [bool]$report.measurement_qualified) { throw "Phase 6EE existing measurement gates failed" }
    $outcomes = @()
    foreach ($label in @("A_axis_on", "B_rotate_y40_on", "C_rotate_y40_off")) {
        $evidence = Get-Content -Raw -Encoding UTF8 (Join-Path $OutputRoot "formal\$label\runner_evidence.json") | ConvertFrom-Json
        $outcomes += [pscustomobject]@{
            label = $label
            functional_status = $evidence.outcome.functional_status
            lifecycle_status = $evidence.outcome.lifecycle_status
            performance_sample_accepted = [bool]$evidence.outcome.performance_sample_accepted
            exit_code = $evidence.process_exit_code
        }
    }
    $productionHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
    $matrix = [ordered]@{
        schema = "campfire.phase6ee.matrix-complete.v1"
        phase = "phase6ee"
        status = "ok"
        formal_order = @("A_axis_on", "B_rotate_y40_on", "C_rotate_y40_off")
        completed = @("A_axis_on", "B_rotate_y40_on", "C_rotate_y40_off")
        outcomes = $outcomes
        report = (Join-Path $OutputRoot "report.json")
        production_app_sha256_before = $productionHash
        production_app_sha256_after = $productionHash
        production_changed = $false
        phase6ec_artifacts_overwritten = $false
        offline_analysis_reused_completed_raw_samples = $true
    }
    [IO.File]::WriteAllText((Join-Path $OutputRoot "matrix_complete.json"), ($matrix | ConvertTo-Json -Depth 12) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Write-Host "Phase 6EE existing samples finalized without rerunning Kit"
    exit 0
}

if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6EE refuses artifact root reuse: $OutputRoot" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
if (-not $SourceStage) {
    $SourceStage = Join-Path $root "artifacts\phase6dy-calibrated-stage-open-1\prepared-stages\D_cylinder_decomposition.usda"
}
$source = [IO.Path]::GetFullPath($SourceStage)
$qualifiedSourceHash = "BC65721F4C6D4ECF1F35C736F2DD10F7A47C9F2B361E45898032E869D894D5F9"
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Phase 6EE source stage missing: $source" }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash -ne $qualifiedSourceHash) {
    throw "Phase 6EE source is not the qualified Phase 6DY stage"
}

$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$preparedRoot = Join-Path $OutputRoot "prepared-stages"
$prepareReport = Join-Path $OutputRoot "prepared_stages.json"
$prepareLog = Join-Path $OutputRoot "prepare.log"
$prepareDump = Join-Path $OutputRoot "prepare-sensitive-crash-dumps"
$prepareProbe = Join-Path $PSScriptRoot "prepare_phase6ec_static_rotated_cylinder.py"
$flowRunner = Join-Path $PSScriptRoot "run_phase6dt_flow_collision_case.ps1"
$caseRunnerLogRoot = Join-Path $OutputRoot "case-runner-logs"
$caseRunnerPrivateBytesLimit = 512MB
$caseRunnerTimeoutSeconds = 720
$powershell = (Get-Process -Id $PID).Path

function Write-SafeStop([string]$Step, [string]$Condition, [object[]]$Completed, [string]$Message) {
    $payload = [ordered]@{
        schema = "campfire.phase6ee.safe-stop.v1"
        phase = "phase6ee"
        status = "safe_stop"
        step = $Step
        condition = $Condition
        completed = @($Completed)
        automatic_retry = $false
        error = $Message
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
        if ($actual -eq [IO.Path]::GetFullPath($ExpectedExecutable)) {
            throw "Phase 6EE left a Kit process after runner completion: $ProcessId"
        }
    }
}

function Invoke-Phase6EeCaseRunner {
    param(
        [Parameter(Mandatory = $true)][object]$Case,
        [Parameter(Mandatory = $true)][string]$CaseOutput
    )
    New-Item -ItemType Directory -Path $caseRunnerLogRoot -Force | Out-Null
    $stdout = Join-Path $caseRunnerLogRoot ($Case.label + ".stdout.log")
    $stderr = Join-Path $caseRunnerLogRoot ($Case.label + ".stderr.log")
    $spatialRoot = Join-Path $OutputRoot ("spatial\" + $Case.label)
    $arguments = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", $flowRunner,
        "-Mode", $Case.mode,
        "-SourceStage", (Join-Path $preparedRoot $Case.stage),
        "-OutputDir", $CaseOutput,
        "-AppKind", "reference",
        "-RunIndex", "1",
        "-SpatialOutputRoot", $spatialRoot,
        "-SpatialCondition", $Case.label
    )
    $guard = Invoke-Phase6EaGuardedHelper `
        -FilePath $powershell `
        -ArgumentList $arguments `
        -StdoutPath $stdout `
        -StderrPath $stderr `
        -TimeoutSeconds $caseRunnerTimeoutSeconds `
        -PrivateBytesLimit $caseRunnerPrivateBytesLimit
    if ($guard.timed_out -or $guard.private_bytes_exceeded -or -not $guard.process_absent -or $guard.exit_code_error -ne $null -or $guard.exit_code -ne 0) {
        throw "guarded Phase 6EE case runner failed: timed_out=$($guard.timed_out) private_bytes_exceeded=$($guard.private_bytes_exceeded) process_absent=$($guard.process_absent) exit_code=$($guard.exit_code) exit_code_error=$($guard.exit_code_error) peak_private_bytes=$($guard.peak_private_bytes)"
    }
    return $guard
}

$prepareArgs = @(
    $emptyApp,
    "--no-window",
    "--/app/fastShutdown=0",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/phase6ec/source=$source",
    "--/phase6ec/outputRoot=$preparedRoot",
    "--/phase6ec/report=$prepareReport",
    "--/log/file=$prepareLog",
    "--/log/fileLogLevel=Info",
    "--enable", "omni.usd",
    "--exec", $prepareProbe
) + @(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $prepareDump)
$prepareProcess = Start-Process -FilePath $kit -ArgumentList $prepareArgs -PassThru -WindowStyle Hidden
if (-not $prepareProcess.WaitForExit(180000)) {
    $candidate = Get-CimInstance Win32_Process -Filter "ProcessId=$($prepareProcess.Id)" -ErrorAction SilentlyContinue
    if ($null -ne $candidate -and [IO.Path]::GetFullPath($candidate.ExecutablePath) -eq [IO.Path]::GetFullPath($kit)) {
        Stop-Process -Id $prepareProcess.Id -Force
        $prepareProcess.WaitForExit(10000) | Out-Null
    }
    Write-SafeStop "prepare" "offline_stage_preparation" @() "offline preparation timed out"
    throw "Phase 6EE offline preparation timed out"
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
    Write-SafeStop "prepare" "offline_stage_preparation" @() "offline preparation failed safety gates"
    throw "Phase 6EE offline preparation failed safely"
}
$prepared = Get-Content -Raw -Encoding UTF8 $prepareReport | ConvertFrom-Json
if ($prepared.status -ne "ok" -or @($prepared.gates.psobject.Properties | Where-Object { -not [bool]$_.Value }).Count) {
    throw "Phase 6EE offline stage gates failed"
}

$formalCases = @(
    [pscustomobject]@{ label = "A_axis_on"; stage = "axis_control.usda"; mode = "phase6ec_rotated_mesh" },
    [pscustomobject]@{ label = "B_rotate_y40_on"; stage = "rotate_y40.usda"; mode = "phase6ec_rotated_mesh" },
    [pscustomobject]@{ label = "C_rotate_y40_off"; stage = "rotate_y40.usda"; mode = "phase6ec_rotated_mesh_collision_off" }
)
$completed = @()
$outcomes = @()
$consecutiveKnownResiduals = 0
foreach ($case in $formalCases) {
    $caseOutput = Join-Path $OutputRoot ("formal\" + $case.label)
    try {
        $caseGuard = Invoke-Phase6EeCaseRunner -Case $case -CaseOutput $caseOutput
        $evidence = Get-Content -Raw -Encoding UTF8 (Join-Path $caseOutput "runner_evidence.json") | ConvertFrom-Json
        if ($null -eq $evidence.outcome -or $evidence.outcome.functional_status -ne "pass") { throw "functional classification did not pass" }
        $lifecycle = [string]$evidence.outcome.lifecycle_status
        if ($lifecycle -eq "known_ngx_shutdown_residual") { $consecutiveKnownResiduals += 1 } else { $consecutiveKnownResiduals = 0 }
        $outcomes += [pscustomobject]@{
            label = $case.label
            functional_status = $evidence.outcome.functional_status
            lifecycle_status = $lifecycle
            performance_sample_accepted = [bool]$evidence.outcome.performance_sample_accepted
            exit_code = $evidence.process_exit_code
            runner_peak_private_bytes = $caseGuard.peak_private_bytes
        }
        $completed += $case.label
        if ($consecutiveKnownResiduals -ge 2) { throw "two consecutive known NGX shutdown residuals require Phase 6EB reinvestigation" }
    } catch {
        Write-SafeStop "formal_flow_readback" $case.label $completed $_.Exception.Message
        throw
    }
}

& python $analyzer --root $OutputRoot --output (Join-Path $OutputRoot "report.json") --svg (Join-Path $OutputRoot "report.svg") --section-svg (Join-Path $OutputRoot "velocity_section.svg") --archive (Join-Path $OutputRoot "spatial_neighborhoods.zip")
if ($LASTEXITCODE -ne 0) {
    Write-SafeStop "analysis" "spatial_distribution" $completed "Phase 6EE spatial analyzer failed"
    throw "Phase 6EE spatial analyzer failed"
}

$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
if ($productionHashBefore -ne $productionHashAfter) { throw "Phase 6EE changed production app" }
$matrix = [ordered]@{
    schema = "campfire.phase6ee.matrix-complete.v1"
    phase = "phase6ee"
    status = "ok"
    formal_order = @($formalCases.label)
    completed = @($completed)
    outcomes = @($outcomes)
    prepared_stage_report = $prepareReport
    report = (Join-Path $OutputRoot "report.json")
    production_app_sha256_before = $productionHashBefore
    production_app_sha256_after = $productionHashAfter
    production_changed = $false
    phase6ec_artifacts_overwritten = $false
}
[IO.File]::WriteAllText((Join-Path $OutputRoot "matrix_complete.json"), ($matrix | ConvertTo-Json -Depth 12) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host "Phase 6EE complete: $($completed.Count) formal processes and compact spatial analysis"
