param(
    [string]$OutputRoot = "",
    [string]$SourceStage = "",
    [switch]$SkipVisualEvidence
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
. (Join-Path $PSScriptRoot "phase6ea_diagnostic_common.ps1")
if (-not $OutputRoot) { $OutputRoot = Join-Path $root "artifacts\phase6ec-static-rotation-1" }
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6EC refuses artifact root reuse: $OutputRoot" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null

$release = Join-Path $root "_build\windows-x86_64\release"
$kit = Join-Path $release "kit\kit.exe"
$emptyApp = Join-Path $release "kit\apps\omni.app.empty.kit"
$productionApp = Join-Path $release "apps\campfire.simulator.kit"
if (-not $SourceStage) {
    $SourceStage = Join-Path $root "artifacts\phase6dy-calibrated-stage-open-1\prepared-stages\D_cylinder_decomposition.usda"
}
$source = [IO.Path]::GetFullPath($SourceStage)
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Phase 6EC source stage missing: $source" }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash -ne "BC65721F4C6D4ECF1F35C736F2DD10F7A47C9F2B361E45898032E869D894D5F9") {
    throw "Phase 6EC source is not the qualified Phase 6DY stage"
}

$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$preparedRoot = Join-Path $OutputRoot "prepared-stages"
$prepareReport = Join-Path $OutputRoot "prepared_stages.json"
$prepareLog = Join-Path $OutputRoot "prepare.log"
$prepareDump = Join-Path $OutputRoot "prepare-sensitive-crash-dumps"
$prepareProbe = Join-Path $PSScriptRoot "prepare_phase6ec_static_rotated_cylinder.py"
$flowRunner = Join-Path $PSScriptRoot "run_phase6dt_flow_collision_case.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6ec_static_rotated_cylinder.py"
$mediaBuilder = Join-Path $PSScriptRoot "build_phase6ec_static_rotation_media.py"
$caseRunnerLogRoot = Join-Path $OutputRoot "case-runner-logs"
$caseRunnerPrivateBytesLimit = 512MB
$caseRunnerTimeoutSeconds = 720
$powershell = (Get-Process -Id $PID).Path

function Write-SafeStop([string]$Step, [string]$Condition, [object[]]$Completed, [string]$Message) {
    $payload = [ordered]@{
        schema = "campfire.phase6ec.safe-stop.v1"
        phase = "phase6ec"
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
            throw "Phase 6EC left a Kit process after runner completion: $ProcessId"
        }
    }
}

function Invoke-Phase6EcCaseRunner {
    param(
        [Parameter(Mandatory = $true)][object]$Case,
        [Parameter(Mandatory = $true)][string]$CaseOutput,
        [switch]$Capture
    )
    New-Item -ItemType Directory -Path $caseRunnerLogRoot -Force | Out-Null
    $stdout = Join-Path $caseRunnerLogRoot ($Case.label + ".stdout.log")
    $stderr = Join-Path $caseRunnerLogRoot ($Case.label + ".stderr.log")
    $arguments = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", $flowRunner,
        "-Mode", $Case.mode,
        "-SourceStage", (Join-Path $preparedRoot $Case.stage),
        "-OutputDir", $CaseOutput,
        "-AppKind", "reference",
        "-RunIndex", "1"
    )
    if ($Capture) { $arguments += "-Capture" }
    $guard = Invoke-Phase6EaGuardedHelper `
        -FilePath $powershell `
        -ArgumentList $arguments `
        -StdoutPath $stdout `
        -StderrPath $stderr `
        -TimeoutSeconds $caseRunnerTimeoutSeconds `
        -PrivateBytesLimit $caseRunnerPrivateBytesLimit
    if ($guard.timed_out -or $guard.private_bytes_exceeded -or -not $guard.process_absent -or $guard.exit_code_error -ne $null -or $guard.exit_code -ne 0) {
        throw "guarded Phase 6EC case runner failed: timed_out=$($guard.timed_out) private_bytes_exceeded=$($guard.private_bytes_exceeded) process_absent=$($guard.process_absent) exit_code=$($guard.exit_code) exit_code_error=$($guard.exit_code_error) peak_private_bytes=$($guard.peak_private_bytes)"
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
    throw "Phase 6EC offline preparation timed out"
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
    throw "Phase 6EC offline preparation failed safely"
}
$prepared = Get-Content -Raw -Encoding UTF8 $prepareReport | ConvertFrom-Json
if ($prepared.status -ne "ok") { throw "Phase 6EC offline stage gates failed" }

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
        $caseGuard = Invoke-Phase6EcCaseRunner -Case $case -CaseOutput $caseOutput
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

& python $analyzer --root $OutputRoot --output (Join-Path $OutputRoot "report.json") --svg (Join-Path $OutputRoot "report.svg")
if ($LASTEXITCODE -ne 0) {
    Write-SafeStop "analysis" "formal_numeric_gates" $completed "Phase 6EC numeric analyzer rejected the result"
    throw "Phase 6EC numeric gates failed"
}

$visualCompleted = @()
if (-not $SkipVisualEvidence) {
    $visualCases = @(
        [pscustomobject]@{ label = "axis_on"; stage = "axis_control_debug.usda"; mode = "phase6ec_rotated_mesh" },
        [pscustomobject]@{ label = "rotate_y40_on"; stage = "rotate_y40_debug.usda"; mode = "phase6ec_rotated_mesh" },
        [pscustomobject]@{ label = "rotate_y40_off"; stage = "rotate_y40_debug.usda"; mode = "phase6ec_rotated_mesh_collision_off" }
    )
    foreach ($case in $visualCases) {
        $caseOutput = Join-Path $OutputRoot ("visual\" + $case.label)
        try {
            $caseGuard = Invoke-Phase6EcCaseRunner -Case $case -CaseOutput $caseOutput -Capture
            $evidence = Get-Content -Raw -Encoding UTF8 (Join-Path $caseOutput "runner_evidence.json") | ConvertFrom-Json
            if ($null -eq $evidence.outcome -or $evidence.outcome.functional_status -ne "pass") { throw "visual functional classification did not pass" }
            $lifecycle = [string]$evidence.outcome.lifecycle_status
            if ($lifecycle -eq "known_ngx_shutdown_residual") { $consecutiveKnownResiduals += 1 } else { $consecutiveKnownResiduals = 0 }
            $outcomes += [pscustomobject]@{
                label = "visual_" + $case.label
                functional_status = $evidence.outcome.functional_status
                lifecycle_status = $lifecycle
                performance_sample_accepted = [bool]$evidence.outcome.performance_sample_accepted
                exit_code = $evidence.process_exit_code
                runner_peak_private_bytes = $caseGuard.peak_private_bytes
            }
            $visualCompleted += $case.label
            if ($consecutiveKnownResiduals -ge 2) { throw "two consecutive known NGX shutdown residuals require Phase 6EB reinvestigation" }
        } catch {
            Write-SafeStop "visual_evidence" $case.label ($completed + $visualCompleted) $_.Exception.Message
            throw
        }
    }
    & python $mediaBuilder --root $OutputRoot --output (Join-Path $root "docs\devlog\assets\phase6\rotated_cylinder_collision_comparison.mp4") --poster (Join-Path $root "docs\devlog\assets\phase6\rotated_cylinder_collision_comparison.png") --manifest (Join-Path $OutputRoot "media_manifest.json")
    if ($LASTEXITCODE -ne 0) { throw "Phase 6EC media build or validation failed" }
}

$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
if ($productionHashBefore -ne $productionHashAfter) { throw "Phase 6EC changed production app" }
$matrix = [ordered]@{
    schema = "campfire.phase6ec.matrix-complete.v1"
    phase = "phase6ec"
    status = "complete"
    purpose = "static Y40 closed-Mesh Flow collision qualification"
    source_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash
    formal_completed = @($completed)
    visual_completed = @($visualCompleted)
    outcomes = @($outcomes)
    consecutive_known_residuals_at_end = $consecutiveKnownResiduals
    production_app_sha256_before = $productionHashBefore
    production_app_sha256_after = $productionHashAfter
    production_changed = $false
    timestamp_local = (Get-Date).ToString("o")
}
[IO.File]::WriteAllText((Join-Path $OutputRoot "matrix_complete.json"), ($matrix | ConvertTo-Json -Depth 12) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host "Phase 6EC complete: $($completed.Count) formal and $($visualCompleted.Count) visual processes"
