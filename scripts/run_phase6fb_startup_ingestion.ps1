param([Parameter(Mandatory = $true)][string]$OutputRoot)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6FB refuses artifact root reuse: $OutputRoot" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
$logs = Join-Path $OutputRoot "runner-logs"
New-Item -ItemType Directory -Path $logs | Out-Null

$contractPath = Join-Path $PSScriptRoot "phase6fb_startup_ingestion_contract.json"
$hashPath = Join-Path $PSScriptRoot "phase6fb_startup_ingestion_contract.sha256"
$expectedHash = ((Get-Content -Encoding UTF8 $hashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($actualHash -ne $expectedHash) { throw "Phase 6FB contract hash mismatch" }
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
Copy-Item -LiteralPath $hashPath -Destination (Join-Path $OutputRoot "frozen_contract.sha256")
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
$limits = $contract.safety
$guard = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
$caseRunner = Join-Path $PSScriptRoot "run_phase6ep_point_collision_case.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6fb_startup_ingestion.py"
$powershell = (Get-Command powershell.exe).Source
$productionApp = Join-Path $root "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$reportPath = Join-Path $OutputRoot "startup_ingestion_report.json"
$statePath = Join-Path $OutputRoot "incremental_state.json"
$timingPath = Join-Path $OutputRoot "process_timing.jsonl"

& python (Join-Path $PSScriptRoot "audit_phase6fb_startup_history.py") `
    --phase6fa-root (Join-Path $root "artifacts\phase6fa-flow-liveness-1") `
    --output (Join-Path $OutputRoot "historical_startup_audit.json")
if ($LASTEXITCODE -ne 0) { throw "Phase 6FB read-only audit failed; Kit was not started" }

function Write-State([string]$Status, [int]$Completed, [string]$Active, [string]$Reason) {
    $payload = [ordered]@{
        schema="campfire.phase6fb.incremental-state.v1"; phase="phase6fb"; status=$Status
        completed_conditions=$Completed; active_condition=$Active; stop_reason=$Reason
        contract_sha256=$actualHash; timestamp_utc=[DateTime]::UtcNow.ToString("o")
    }
    [IO.File]::WriteAllText($statePath, ($payload | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Write-Timing([string]$Label, [string]$Marker) {
    $payload = [ordered]@{schema="campfire.phase6fb.process-timing.v1"; label=$Label; marker=$Marker; timestamp_utc=[DateTime]::UtcNow.ToString("o")}
    [IO.File]::AppendAllText($timingPath, ($payload | ConvertTo-Json -Compress) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Update-Report {
    & python $analyzer --root $OutputRoot --contract $contractPath --output $reportPath
    if ($LASTEXITCODE -ne 0) { throw "Phase 6FB analyzer failed" }
}

function Stop-Safely([int]$Completed, [string]$Active, [string]$Reason) {
    Write-State "safe_stop" $Completed $Active $Reason
    Update-Report
    Write-Error "Phase 6FB safe stop at ${Active}: $Reason"
    exit 2
}

function Invoke-StartupCase([string]$Label) {
    $caseDir = Join-Path $OutputRoot $Label
    $arguments = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $caseRunner,
        "-Scenario", "production_four", "-OutputDir", $caseDir,
        "-OffsetM", "-0.0125", "-SupportRadiusM", "0.05", "-Filtering", "true",
        "-Collision", "true", "-Policy", "allow_self_center", "-ReportPhase", "phase6fb",
        "-GeometryVariant", "phase6er_corrected", "-FuelScale", "1", "-TemperatureScale", "1", "-SmokeScale", "1",
        "-SampleFrames", "30,60,90,120", "-ReadbackChannels", "none", "-ReadbackMode", "none",
        "-ReadbackFrames", "30", "-ReferenceDisposal", "natural",
        "-SynchronousMemoryMarkers", "true", "-PythonMemoryTelemetry", "false",
        "-SpatialCollectorsEnabled", "false", "-RunIndex", "1", "-LifecycleCalibration",
        "-FlowLivenessAudit", "true", "-FuelLivenessDecode", "false",
        "-StartupProbe", "true", "-StartupProbeLabel", $Label,
        "-RendererDrainUpdates", "$($contract.lifecycle.renderer_pre_close_drain_updates)",
        "-StageCloseTimeoutSeconds", "$($contract.lifecycle.stage_close_timeout_seconds)",
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
        "--gpu-sample-ms", "$($limits.gpu_sampling_ms)",
        "--lifecycle-path", (Join-Path $caseDir "raw.json"),
        "--diagnostic-marker-path", (Join-Path $caseDir "resource_markers.jsonl"), "--", $powershell
    ) + $arguments
    Write-Timing $Label "process_launch_started"
    & python @guardArgs
    $guardExit = $LASTEXITCODE
    Write-Timing $Label "guard_returned"
    Update-Report
    if ($guardExit -ne 0) { return "resource_or_lifecycle:guard_exit=$guardExit" }
    $guardResult = Get-Content -Raw -Encoding UTF8 (Join-Path $logs "$Label.guard.json") | ConvertFrom-Json
    if ($guardResult.status -ne "ok" -or $guardResult.exit_code -ne 0 -or -not $guardResult.process_absent) {
        return "resource_or_lifecycle:status=$($guardResult.status);process_exit=$($guardResult.exit_code);stop_reason=$($guardResult.stop_reason)"
    }
    $report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
    $case = $report.cases.PSObject.Properties[$Label].Value
    if (-not $case.startup_markers_complete -or -not $case.lifecycle_pass) {
        return "startup_or_lifecycle_gate:classification=$($case.classification.classification);missing=$($case.missing_startup_markers -join ',')"
    }
    return $case.classification.classification
}

$completed = 0
Write-State "running" $completed "P0_no_readback" ""
$classification0 = Invoke-StartupCase "P0_no_readback"
if ($classification0 -ne "representative_ingestion") {
    Stop-Safely $completed "P0_no_readback" "classification=$classification0; P1 prohibited by frozen branch"
}
$completed++

Write-State "running" $completed "P1_no_readback_repeat" ""
$classification1 = Invoke-StartupCase "P1_no_readback_repeat"
if ($classification1 -ne "representative_ingestion") {
    Stop-Safely $completed "P1_no_readback_repeat" "startup split: P0=$classification0; P1=$classification1"
}
$completed++

$productionAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
if ($productionBefore -ne $productionAfter) { Stop-Safely $completed "final" "production_app_hash_changed" }
Update-Report
$final = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
if (-not $final.reproducible_representative_startup) { Stop-Safely $completed "final" "reproducibility_report_failed" }
Write-State "completed" $completed "complete" "historical 24-block cause not reproduced; no long population started"
Write-Host "Phase 6FB completed: two short representative startup probes passed; long population remains blocked"
