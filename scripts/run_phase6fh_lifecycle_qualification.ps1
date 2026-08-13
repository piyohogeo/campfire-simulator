param([Parameter(Mandatory = $true)][string]$OutputRoot)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6FH refuses artifact root reuse: $OutputRoot" }
$contractPath = Join-Path $PSScriptRoot "phase6fh_lifecycle_qualification_contract.json"
$hashPath = Join-Path $PSScriptRoot "phase6fh_lifecycle_qualification_contract.sha256"
$expectedHash = ((Get-Content -Encoding UTF8 $hashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($actualHash -ne $expectedHash) { throw "Phase 6FH contract hash mismatch" }
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
Copy-Item -LiteralPath $hashPath -Destination (Join-Path $OutputRoot "frozen_contract.sha256")
$logs = Join-Path $OutputRoot "runner-logs"
New-Item -ItemType Directory -Path $logs | Out-Null
$guard = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
$caseRunner = Join-Path $PSScriptRoot "run_phase6ep_point_collision_case.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6fh_lifecycle_qualification.py"
$powershell = (Get-Command powershell.exe).Source
$productionApp = Join-Path $root "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$statePath = Join-Path $OutputRoot "incremental_state.json"
$reportPath = Join-Path $OutputRoot "lifecycle_qualification_report.json"
$previousExitUtc = ""

function Write-State([string]$Status, [int]$Attempted, [string]$Active, [string]$Reason) {
    $payload = [ordered]@{ schema="campfire.phase6fh.incremental-state.v1"; phase="phase6fh"; status=$Status; attempted_processes=$Attempted; active_condition=$Active; stop_reason=$Reason; contract_sha256=$actualHash; timestamp_utc=[DateTime]::UtcNow.ToString("o") }
    [IO.File]::WriteAllText($statePath, ($payload | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Update-Report {
    & python $analyzer --root $OutputRoot --contract $contractPath --output $reportPath
    if ($LASTEXITCODE -ne 0) { throw "Phase 6FH analyzer failed" }
}

for ($run = 1; $run -le [int]$contract.population.planned_processes; $run++) {
    $label = "run{0:D2}" -f $run
    $caseDir = Join-Path $OutputRoot $label
    Write-State "running" ($run - 1) $label ""
    $source = $contract.startup.expected_source_sums
    $condition = $contract.condition
    $window = $contract.lifecycle
    $arguments = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $caseRunner,
        "-Scenario", $condition.scenario, "-OutputDir", $caseDir,
        "-OffsetM", "$($condition.point_offset_m)", "-SupportRadiusM", "$($condition.support_radius_m)",
        "-Filtering", "true", "-Collision", "true", "-Policy", $condition.point_policy,
        "-ReportPhase", "phase6fh", "-GeometryVariant", $condition.geometry_variant,
        "-FuelScale", "1", "-TemperatureScale", "1", "-SmokeScale", "1",
        "-SampleFrames", ($condition.sample_frames -join ','), "-ReadbackChannels", "none",
        "-ReadbackMode", "none", "-ReadbackFrames", "120", "-ReferenceDisposal", "natural",
        "-SynchronousMemoryMarkers", "true", "-PythonMemoryTelemetry", "true",
        "-SpatialCollectorsEnabled", "false", "-RunIndex", "$run", "-LifecycleCalibration",
        "-RendererDrainUpdates", "$($window.renderer_pre_close_drain_updates)",
        "-StageCloseTimeoutSeconds", "$($window.stage_close_timeout_seconds)",
        "-StabilityObservationStartFrame", "240", "-StabilityObservationExtraSeconds", "$($condition.running_flow_observation_seconds)",
        "-StabilityActiveBlockSampleSeconds", "0.5", "-FlowLivenessAudit", "true",
        "-StartupProbe", "true", "-StartupProbeLabel", $label,
        "-StartupFlowAcquirePosition", $contract.startup.flow_acquire_position,
        "-StartupPreTimelineUpdateCount", "$($contract.startup.stopped_update_count)",
        "-StartupExtraUpdateBeforePlayCount", "$($contract.startup.extra_update_before_play_count)",
        "-StartupLivenessGate", "true", "-StartupExpectedFuelSum", "$($source.fuel)",
        "-StartupExpectedTemperatureSum", "$($source.temperature)", "-StartupExpectedSmokeSum", "$($source.smoke)",
        "-StartupSourceSumTolerance", "$($contract.startup.source_sum_absolute_tolerance)",
        "-AbsoluteTimeoutSeconds", "$($window.inner_absolute_timeout_seconds)"
    )
    if (-not [string]::IsNullOrWhiteSpace($previousExitUtc)) { $arguments += @("-PreviousProcessExitUtc", $previousExitUtc) }
    $safety = $contract.safety
    $guardArgs = @(
        $guard, "--trace", (Join-Path $logs "$label.resource.jsonl"), "--summary", (Join-Path $logs "$label.guard.json"),
        "--stdout", (Join-Path $logs "$label.stdout.log"), "--stderr", (Join-Path $logs "$label.stderr.log"),
        "--timeout-seconds", "$($window.outer_condition_timeout_seconds)", "--sample-seconds", "$($safety.resource_sampling_seconds)",
        "--runner-private-limit", "$($safety.runner_private_limit_bytes)", "--diagnostic-private-limit", "$($safety.diagnostic_private_limit_bytes)",
        "--kit-private-limit", "$($safety.kit_private_limit_bytes)", "--tree-private-limit", "$($safety.unique_tree_private_limit_bytes)",
        "--available-memory-floor", "$($safety.physical_memory_floor_bytes)", "--commit-headroom-floor", "$($safety.commit_headroom_floor_bytes)",
        "--cpu-telemetry", "--gpu-csv", (Join-Path $logs "$label.gpu.csv"), "--gpu-sample-ms", "$($safety.gpu_sampling_ms)",
        "--lifecycle-path", (Join-Path $caseDir "raw.json"), "--diagnostic-marker-path", (Join-Path $caseDir "resource_markers.jsonl"),
        "--", $powershell
    ) + $arguments
    & python @guardArgs
    $guardExit = $LASTEXITCODE
    Update-Report
    $report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
    $case = @($report.cases | Where-Object { $_.run -eq $run })[0]
    if ($guardExit -ne 0 -or $case.status -ne "pass") {
        Write-State "safe_stop" $run $label (($case.failures -join ',') + ";guard_exit=$guardExit")
        Write-Error "Phase 6FH captured lifecycle failure at $label; no retry or later process was started"
        exit 2
    }
    $previousExitUtc = [DateTime]::UtcNow.ToString("o")
}
$productionAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
if ($productionBefore -ne $productionAfter) { throw "Phase 6FH production app hash changed" }
Update-Report
Write-State "completed_no_reproduction" ([int]$contract.population.planned_processes) "complete" ""
Write-Host "Phase 6FH completed all readback-free lifecycle controls without reproducing the hang"
