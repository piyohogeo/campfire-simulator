param(
    [Parameter(Mandatory = $true)][string]$OutputRoot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6FA refuses artifact root reuse: $OutputRoot" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
$logs = Join-Path $OutputRoot "runner-logs"
New-Item -ItemType Directory -Path $logs | Out-Null

$contractPath = Join-Path $PSScriptRoot "phase6fa_flow_liveness_contract.json"
$hashPath = Join-Path $PSScriptRoot "phase6fa_flow_liveness_contract.sha256"
$expectedHash = ((Get-Content -Encoding UTF8 $hashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($actualHash -ne $expectedHash) { throw "Phase 6FA contract hash mismatch" }
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
Copy-Item -LiteralPath $hashPath -Destination (Join-Path $OutputRoot "frozen_contract.sha256")
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
$limits = $contract.safety
$window = $contract.observation
$guard = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
$caseRunner = Join-Path $PSScriptRoot "run_phase6ep_point_collision_case.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6fa_flow_liveness.py"
$powershell = (Get-Command powershell.exe).Source
$productionApp = Join-Path $root "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$reportPath = Join-Path $OutputRoot "flow_liveness_report.json"
$statePath = Join-Path $OutputRoot "incremental_state.json"

& python (Join-Path $PSScriptRoot "audit_phase6fa_phase6ez_history.py") `
    --prior-root (Join-Path $root "artifacts\phase6ez-fuel-conversion-3") `
    --output (Join-Path $OutputRoot "phase6ez_read_only_audit.json")
if ($LASTEXITCODE -ne 0) { throw "Phase 6FA read-only history audit failed" }
& python (Join-Path $PSScriptRoot "run_phase6fa_synthetic_fixture.py") `
    --contract $contractPath --output (Join-Path $OutputRoot "synthetic-fixture")
if ($LASTEXITCODE -ne 0) { throw "Phase 6FA synthetic fixture failed; Kit was not started" }

function Write-State([string]$Status, [int]$Completed, [string]$Active, [string]$Reason) {
    $payload = [ordered]@{
        schema="campfire.phase6fa.incremental-state.v1"; phase="phase6fa"; status=$Status
        completed_conditions=$Completed; active_condition=$Active; stop_reason=$Reason
        contract_sha256=$actualHash; timestamp_utc=[DateTime]::UtcNow.ToString("o")
    }
    [IO.File]::WriteAllText($statePath, ($payload | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Update-Report {
    & python $analyzer --root $OutputRoot --contract $contractPath --output $reportPath
    if ($LASTEXITCODE -ne 0) { throw "Phase 6FA analyzer failed" }
}

function Stop-Safely([int]$Completed, [string]$Active, [string]$Reason) {
    Write-State "safe_stop" $Completed $Active $Reason
    Update-Report
    Write-Error "Phase 6FA safe stop at ${Active}: $Reason"
    exit 2
}

function Invoke-Case([string]$Label, [string]$Mode, [bool]$DecodeFuel) {
    $caseDir = Join-Path $OutputRoot $Label
    $arguments = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $caseRunner,
        "-Scenario", "production_four", "-OutputDir", $caseDir,
        "-OffsetM", "-0.0125", "-SupportRadiusM", "0.05", "-Filtering", "true",
        "-Collision", "true", "-Policy", "allow_self_center", "-ReportPhase", "phase6fa",
        "-GeometryVariant", "phase6er_corrected", "-FuelScale", "1", "-TemperatureScale", "1", "-SmokeScale", "1",
        "-SampleFrames", "30,60,90,120,150,180,200,240,280,320", "-ReadbackChannels", "none",
        "-ReadbackMode", $Mode, "-ReadbackFrames", "60", "-ReferenceDisposal", "natural",
        "-SynchronousMemoryMarkers", "true", "-PythonMemoryTelemetry", "true",
        "-SpatialCollectorsEnabled", "false", "-RunIndex", "1", "-LifecycleCalibration",
        "-FlowLivenessAudit", "true", "-FuelLivenessDecode", $DecodeFuel.ToString().ToLowerInvariant(),
        "-RendererDrainUpdates", "$($contract.lifecycle.renderer_pre_close_drain_updates)",
        "-StageCloseTimeoutSeconds", "$($contract.lifecycle.stage_close_timeout_seconds)",
        "-StabilityObservationStartFrame", "$($window.start_frame)",
        "-StabilityObservationExtraSeconds", "$($window.extra_running_flow_wall_seconds)",
        "-StabilityActiveBlockSampleSeconds", "$($window.active_block_sample_seconds)",
        "-AbsoluteTimeoutSeconds", "$($contract.lifecycle.inner_absolute_timeout_seconds)"
    )
    $guardArgs = @(
        $guard, "--trace", (Join-Path $logs "$Label.resource.jsonl"),
        "--summary", (Join-Path $logs "$Label.guard.json"),
        "--stdout", (Join-Path $logs "$Label.stdout.log"),
        "--stderr", (Join-Path $logs "$Label.stderr.log"),
        "--timeout-seconds", "$($contract.lifecycle.outer_condition_timeout_seconds)",
        "--sample-seconds", "$($limits.resource_sampling_seconds)",
        "--runner-private-limit", "$($limits.runner_private_limit_bytes)",
        "--diagnostic-private-limit", "$($limits.diagnostic_private_limit_bytes)",
        "--kit-private-limit", "$($limits.kit_private_limit_bytes)",
        "--tree-private-limit", "$($limits.unique_tree_private_limit_bytes)",
        "--available-memory-floor", "$($limits.physical_memory_floor_bytes)",
        "--commit-headroom-floor", "$($limits.commit_headroom_floor_bytes)",
        "--cpu-telemetry", "--gpu-csv", (Join-Path $logs "$Label.gpu.csv"),
        "--gpu-sample-ms", "$($limits.gpu_sampling_ms)", "--lifecycle-path", (Join-Path $caseDir "raw.json"),
        "--diagnostic-marker-path", (Join-Path $caseDir "resource_markers.jsonl"), "--", $powershell
    ) + $arguments
    & python @guardArgs
    $guardExit = $LASTEXITCODE
    $guardPath = Join-Path $logs "$Label.guard.json"
    if (-not (Test-Path -LiteralPath $guardPath)) { return "resource_guard_summary_missing" }
    Update-Report
    $guardResult = Get-Content -Raw -Encoding UTF8 $guardPath | ConvertFrom-Json
    if ($guardExit -ne 0 -or $guardResult.status -ne "ok" -or $guardResult.exit_code -ne 0 -or -not $guardResult.process_absent) {
        return "resource_or_lifecycle:guard_exit=$guardExit;status=$($guardResult.status);process_exit=$($guardResult.exit_code);stop_reason=$($guardResult.stop_reason)"
    }
    $report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
    $case = $report.cases.PSObject.Properties[$Label].Value
    if (-not $case.condition_gate_pass) { return "condition_gate:$($case.condition_gate_failures -join ',')" }
    return $null
}

$completed = 0
Write-State "running" $completed "D0_no_readback" ""
$reason = Invoke-Case "D0_no_readback" "none" $false
if ($reason) { Stop-Safely $completed "D0_no_readback" $reason }
$completed++

Write-State "running" $completed "D1_readback_release" ""
$reason = Invoke-Case "D1_readback_release" "acquire_discard_release" $true
if ($reason) { Stop-Safely $completed "D1_readback_release" $reason }
$completed++

Write-State "running" $completed "D2_fuel_asarray" ""
$reason = Invoke-Case "D2_fuel_asarray" "fuel_convert_release" $true
if ($reason) { Stop-Safely $completed "D2_fuel_asarray" $reason }
$completed++

$productionAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
if ($productionBefore -ne $productionAfter) { Stop-Safely $completed "final" "production_app_hash_changed" }
Update-Report
$report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
if (-not $report.single_fuel_alias_lifetime_qualified) { Stop-Safely $completed "final" "qualification_report_failed" }
Write-State "qualified" $completed "complete" ""
Write-Host "Phase 6FA completed: D0/D1/D2 functional-liveness and occupancy-aware gates passed"
