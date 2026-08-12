param(
    [Parameter(Mandatory=$true)][string]$OutputRoot,
    [switch]$ResumeAfterL0AnalysisFailure
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$repo = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
$rootAlreadyExists = Test-Path -LiteralPath $OutputRoot
if ($rootAlreadyExists -and -not $ResumeAfterL0AnalysisFailure) { throw "Phase 6EW refuses artifact root reuse: $OutputRoot" }
if (-not $rootAlreadyExists -and $ResumeAfterL0AnalysisFailure) { throw "Phase 6EW resume requires the existing L0-only artifact root" }
if (-not $rootAlreadyExists) { New-Item -ItemType Directory -Path $OutputRoot | Out-Null }
$logs = Join-Path $OutputRoot "runner-logs"
if (-not (Test-Path -LiteralPath $logs)) { New-Item -ItemType Directory -Path $logs | Out-Null }

$contractPath = Join-Path $PSScriptRoot "phase6ew_r0_lifecycle_contract.json"
$hashPath = Join-Path $PSScriptRoot "phase6ew_r0_lifecycle_contract.sha256"
$expectedHash = ((Get-Content -Raw -Encoding ASCII $hashPath).Trim().Split(' ')[0]).ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($actualHash -ne $expectedHash) { throw "Phase 6EW contract hash mismatch" }
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
if (-not $rootAlreadyExists) {
    Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
    [IO.File]::WriteAllText((Join-Path $OutputRoot "frozen_contract.sha256"), "$actualHash  frozen_contract.json`n", [Text.UTF8Encoding]::new($false))
} else {
    $frozenContract = Join-Path $OutputRoot "frozen_contract.json"
    $frozenHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $frozenContract).Hash
    if ($frozenHash -ne $actualHash) { throw "Phase 6EW resume rejected a changed frozen contract" }
}

$guard = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
$caseRunner = Join-Path $PSScriptRoot "run_phase6ep_point_collision_case.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6ew_r0_lifecycle.py"
$powershell = (Get-Process -Id $PID).Path
$productionApp = Join-Path $repo "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$reportPath = Join-Path $OutputRoot "r0_lifecycle_report.json"
$statePath = Join-Path $OutputRoot "incremental_state.json"
$resumeState = $null
if ($ResumeAfterL0AnalysisFailure) {
    if (-not (Test-Path -LiteralPath $statePath)) { throw "Phase 6EW resume state is missing" }
    $resumeState = Get-Content -Raw -Encoding UTF8 $statePath | ConvertFrom-Json
    if ($resumeState.status -ne "running" -or $resumeState.active_condition -ne "L0_short" -or [int]$resumeState.completed_processes -ne 0) {
        throw "Phase 6EW resume rejected a non-L0 analysis-failure state"
    }
    if ($resumeState.contract_sha256 -ne $actualHash -or $resumeState.production_changed) {
        throw "Phase 6EW resume rejected changed contract or production evidence"
    }
    foreach ($unexpected in @("calibration", "R1_acquire_discard")) {
        if (Test-Path -LiteralPath (Join-Path $OutputRoot $unexpected)) { throw "Phase 6EW resume found a later condition: $unexpected" }
    }
}
$productionBefore = if ($null -ne $resumeState) { [string]$resumeState.production_app_sha256_before } else { (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash -ne $productionBefore) { throw "Phase 6EW production app changed before execution" }
$limits = $contract.safety

function Write-State([string]$Status, [int]$Completed, [string]$Active, [string]$Reason) {
    $after = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
    $state = [ordered]@{
        schema="campfire.phase6ew.incremental-state.v1"; phase="phase6ew"; status=$Status
        completed_processes=$Completed; maximum_processes=[int]$contract.execution.maximum_processes
        active_condition=$Active; reason=$Reason; contract_sha256=$actualHash
        production_app_sha256_before=$productionBefore; production_app_sha256_current=$after
        production_changed=($productionBefore -ne $after); updated_utc=[DateTime]::UtcNow.ToString("o")
    }
    [IO.File]::WriteAllText($statePath, ($state | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Update-Report {
    & python $analyzer --root $OutputRoot --contract $contractPath --output $reportPath
    if ($LASTEXITCODE -ne 0) { throw "Phase 6EW analyzer failed" }
}

function Stop-Safely([int]$Completed, [string]$Active, [string]$Reason) {
    Write-State "safe_stop" $Completed $Active $Reason
    Update-Report
    Write-Error "Phase 6EW safe stop at ${Active}: $Reason"
    exit 2
}

function Invoke-Case([string]$Label, [string]$Relative, [string]$Prefix, [int]$RunIndex, [string]$Mode, [string]$ReadbackFrames, [string]$SampleFrames, [bool]$RequirePlateau) {
    $caseDir = Join-Path $OutputRoot $Relative
    $arguments = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $caseRunner,
        "-Scenario", "production_four", "-OutputDir", $caseDir,
        "-OffsetM", "-0.0125", "-SupportRadiusM", "0.05", "-Filtering", "true",
        "-Collision", "true", "-Policy", "allow_self_center", "-ReportPhase", "phase6ew",
        "-GeometryVariant", "phase6er_corrected", "-FuelScale", "1", "-TemperatureScale", "1", "-SmokeScale", "1",
        "-SampleFrames", $SampleFrames, "-ReadbackChannels", "none", "-ReadbackMode", $Mode,
        "-ReferenceDisposal", "natural", "-SynchronousMemoryMarkers", "true", "-PythonMemoryTelemetry", "true",
        "-SpatialCollectorsEnabled", "false", "-RunIndex", "$RunIndex", "-LifecycleCalibration",
        "-RendererDrainUpdates", "$($contract.lifecycle.renderer_pre_close_drain_updates)",
        "-StageCloseTimeoutSeconds", "$($contract.lifecycle.stage_close_timeout_seconds)",
        "-AbsoluteTimeoutSeconds", "$($contract.lifecycle.inner_absolute_timeout_seconds)"
    )
    if ($ReadbackFrames) { $arguments += @("-ReadbackFrames", $ReadbackFrames) }
    $guardArgs = @(
        $guard, "--trace", (Join-Path $logs "$Prefix.resource.jsonl"),
        "--summary", (Join-Path $logs "$Prefix.guard.json"),
        "--stdout", (Join-Path $logs "$Prefix.stdout.log"),
        "--stderr", (Join-Path $logs "$Prefix.stderr.log"),
        "--timeout-seconds", "$($contract.lifecycle.outer_condition_timeout_seconds)",
        "--sample-seconds", "$($limits.resource_sampling_seconds)",
        "--runner-private-limit", "$($limits.runner_private_limit_bytes)",
        "--diagnostic-private-limit", "$($limits.diagnostic_private_limit_bytes)",
        "--kit-private-limit", "$($limits.kit_private_limit_bytes)",
        "--tree-private-limit", "$($limits.unique_tree_private_limit_bytes)",
        "--available-memory-floor", "$($limits.physical_memory_floor_bytes)",
        "--commit-headroom-floor", "$($limits.commit_headroom_floor_bytes)",
        "--cpu-telemetry", "--gpu-csv", (Join-Path $logs "$Prefix.gpu.csv"),
        "--gpu-sample-ms", "$($limits.gpu_sampling_ms)", "--lifecycle-path", (Join-Path $caseDir "raw.json"),
        "--diagnostic-marker-path", (Join-Path $caseDir "resource_markers.jsonl"), "--", $powershell
    ) + $arguments
    & python @guardArgs
    $guardExit = $LASTEXITCODE
    if (-not (Test-Path -LiteralPath (Join-Path $logs "$Prefix.guard.json"))) { return "resource_guard_summary_missing" }
    Update-Report
    $guardResult = Get-Content -Raw -Encoding UTF8 (Join-Path $logs "$Prefix.guard.json") | ConvertFrom-Json
    if ($guardExit -ne 0 -or $guardResult.status -ne "ok" -or $guardResult.exit_code -ne 0 -or -not $guardResult.process_absent) {
        return "resource_or_lifecycle:$($guardResult.stop_reason)"
    }
    $report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
    $case = $report.cases.PSObject.Properties[$Label].Value
    if (-not $case.normal_exit) { return "normal_os_exit_not_confirmed" }
    if (-not $case.probe_markers_complete) { return "probe_markers_incomplete:$($case.last_probe_marker)" }
    if (-not $case.extension_markers_complete) { return "extension_markers_incomplete:$($case.last_extension_marker)" }
    if (-not $case.runner_markers_complete) { return "runner_marker_missing" }
    if (-not $case.synchronous_memory_valid) { return "synchronous_memory_invalid" }
    if ($case.stage_close_timeout_marker) { return "stage_close_timeout" }
    if ($case.stage_close_seconds -gt [double]$contract.lifecycle.stage_close_timeout_seconds) { return "stage_close_duration_gate" }
    if ($RequirePlateau -and -not $case.plateau) { return "incremental_plateau_gate_failed" }
    if ($Mode -eq "acquire_discard" -and $null -eq $case.acquire_private_bytes.before) { return "acquire_markers_missing" }
    return $null
}

$completed = 0
if ($ResumeAfterL0AnalysisFailure) {
    Update-Report
    $report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
    if (-not $report.l0_gate_pass) { Stop-Safely $completed "L0_short" "existing_l0_gate_failed" }
    $completed = 1
    Write-State "running" $completed "R0_run01" "resumed_after_bounded_analyzer_correction_without_rerunning_L0"
} else {
    Write-State "running" $completed "L0_short" ""
    $reason = Invoke-Case "L0_short" "L0_short" "L0_short" 0 "none" "" "30,60" $false
    if ($reason) { Stop-Safely $completed "L0_short" $reason }
    $completed++
}

for ($run = 1; $run -le 3; $run++) {
    $label = "R0_run$('{0:d2}' -f $run)"
    $relative = "calibration\run$('{0:d2}' -f $run)\R0_none"
    $prefix = "run$('{0:d2}' -f $run)_R0_none"
    Write-State "running" $completed $label ""
    $reason = Invoke-Case $label $relative $prefix $run "none" "" "30,60,90,120,150,180,200,240,280,320" $true
    if ($reason) { Stop-Safely $completed $label $reason }
    $completed++
}

Update-Report
$report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
if (-not $report.r0_gate_pass) { Stop-Safely $completed "R0_cross_run" "three_run_reproducibility_gate_failed" }

Write-State "running" $completed "R1_acquire_discard" ""
$reason = Invoke-Case "R1_acquire_discard" "R1_acquire_discard" "R1_acquire_discard" 1 "acquire_discard" "60" "30,60,90,120,150,180,200,240,280,320" $false
if ($reason) { Stop-Safely $completed "R1_acquire_discard" $reason }
$completed++

$productionAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
if ($productionBefore -ne $productionAfter) { Stop-Safely $completed "final" "production_app_hash_changed" }
Update-Report
$report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
if (-not $report.r1_gate_pass) { Stop-Safely $completed "R1_acquire_discard" "r1_gate_failed" }
Write-State "qualified" $completed "complete" ""
Write-Host "Phase 6EW completed: corrected L0, R0 3/3 plateau, and one bounded R1 acquisition qualified"
