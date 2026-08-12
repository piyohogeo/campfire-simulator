param([Parameter(Mandatory=$true)][string]$OutputRoot)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$repo = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6EU refuses artifact root reuse: $OutputRoot" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
$logs = Join-Path $OutputRoot "runner-logs"
New-Item -ItemType Directory -Path $logs | Out-Null

$contractPath = Join-Path $PSScriptRoot "phase6eu_readback_lifetime_contract.json"
$hashPath = Join-Path $PSScriptRoot "phase6eu_readback_lifetime_contract.sha256"
$expectedHash = ((Get-Content -Raw -Encoding ASCII $hashPath).Trim().Split(' ')[0]).ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($expectedHash -ne $actualHash) { throw "Phase 6EU contract hash mismatch" }
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
[IO.File]::WriteAllText((Join-Path $OutputRoot "frozen_contract.sha256"), "$actualHash  frozen_contract.json`n", [Text.UTF8Encoding]::new($false))

$guard = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
$caseRunner = Join-Path $PSScriptRoot "run_phase6ep_point_collision_case.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6eu_readback_lifetime.py"
$powershell = (Get-Process -Id $PID).Path
$productionApp = Join-Path $repo "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$limits = $contract.safety
$statePath = Join-Path $OutputRoot "incremental_state.json"
$reportPath = Join-Path $OutputRoot "readback_lifetime_report.json"

function Write-State([string]$Status, [int]$Completed, [string]$Active, [string]$Reason) {
    $productionAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
    $payload = [ordered]@{
        schema = "campfire.phase6eu.incremental-state.v1"
        phase = "phase6eu"
        status = $Status
        completed_processes = $Completed
        expected_processes = [int]$contract.formal_process_count
        active_condition = $Active
        reason = $Reason
        contract_sha256 = $actualHash
        production_app_sha256_before = $productionBefore
        production_app_sha256_current = $productionAfter
        production_changed = ($productionBefore -ne $productionAfter)
        updated_utc = [DateTime]::UtcNow.ToString("o")
    }
    [IO.File]::WriteAllText($statePath, ($payload | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Update-Report {
    & python $analyzer --root $OutputRoot --contract $contractPath --output $reportPath | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Phase 6EU analyzer failed" }
}

function Stop-Safely([int]$Completed, [string]$Active, [string]$Reason) {
    Write-State "safe_stop" $Completed $Active $Reason
    Update-Report
    Write-Error "Phase 6EU safe stop at ${Active}: $Reason"
    exit 2
}

function Test-Marker([string]$Path, [string]$Marker) {
    return $null -ne (Select-String -LiteralPath $Path -SimpleMatch "`"marker`":`"$Marker`"" -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Invoke-GuardedCase([string]$Label, [string]$Scenario, [int]$RunIndex, [string]$Mode, [string]$ReadbackFrames, [string]$Disposal, [string]$SampleFrames) {
    $caseDir = if ($Label -eq "warmup") { Join-Path $OutputRoot "warmup" } else { Join-Path $OutputRoot "calibration\run$('{0:d2}' -f $RunIndex)\$Label" }
    $prefix = if ($Label -eq "warmup") { "warmup" } else { "run$('{0:d2}' -f $RunIndex)_$Label" }
    $boundedJsonl = Join-Path $caseDir "fuel_aggregate.jsonl"
    $arguments = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $caseRunner,
        "-Scenario", $Scenario, "-OutputDir", $caseDir,
        "-OffsetM", "-0.0125", "-SupportRadiusM", "0.05",
        "-Filtering", "true", "-Collision", "true", "-Policy", "allow_self_center",
        "-ReportPhase", "phase6eu", "-GeometryVariant", "phase6er_corrected",
        "-FuelScale", "1", "-TemperatureScale", "1", "-SmokeScale", "1",
        "-SampleFrames", $SampleFrames, "-ReadbackChannels", "none",
        "-ReadbackMode", $Mode, "-ReferenceDisposal", $Disposal,
        "-SynchronousMemoryMarkers", "true", "-PythonMemoryTelemetry", "true",
        "-BoundedJsonlPath", $boundedJsonl,
        "-SpatialCollectorsEnabled", "false", "-RunIndex", "$RunIndex"
    )
    if (-not [string]::IsNullOrWhiteSpace($ReadbackFrames)) { $arguments += @("-ReadbackFrames", $ReadbackFrames) }
    $trace = Join-Path $logs "$prefix.resource.jsonl"
    $summary = Join-Path $logs "$prefix.guard.json"
    $stdout = Join-Path $logs "$prefix.stdout.log"
    $stderr = Join-Path $logs "$prefix.stderr.log"
    $gpu = Join-Path $logs "$prefix.gpu.csv"
    $guardArgs = @(
        $guard, "--trace", $trace, "--summary", $summary, "--stdout", $stdout, "--stderr", $stderr,
        "--timeout-seconds", "$($limits.condition_timeout_seconds)",
        "--sample-seconds", "$($contract.resource_sampling_seconds)",
        "--runner-private-limit", "$($limits.runner_private_limit_bytes)",
        "--diagnostic-private-limit", "$($limits.diagnostic_private_limit_bytes)",
        "--kit-private-limit", "$($limits.kit_private_limit_bytes)",
        "--tree-private-limit", "$($limits.unique_tree_private_limit_bytes)",
        "--available-memory-floor", "$($limits.physical_memory_floor_bytes)",
        "--commit-headroom-floor", "$($limits.commit_headroom_floor_bytes)",
        "--cpu-telemetry", "--gpu-csv", $gpu, "--gpu-sample-ms", "$($contract.gpu_sampling_ms)",
        "--lifecycle-path", (Join-Path $caseDir "raw.json"),
        "--diagnostic-marker-path", (Join-Path $caseDir "resource_markers.jsonl"),
        "--", $powershell
    ) + $arguments
    & python @guardArgs | Out-Host
    $guardExit = $LASTEXITCODE
    if (-not (Test-Path -LiteralPath $summary)) { return [ordered]@{ok=$false;reason="resource_guard_summary_missing";case_dir=$caseDir;prefix=$prefix} }
    $guardResult = Get-Content -Raw -Encoding UTF8 $summary | ConvertFrom-Json
    if ($guardExit -ne 0 -or $guardResult.status -ne "ok" -or $guardResult.exit_code -ne 0 -or -not $guardResult.process_absent) {
        return [ordered]@{ok=$false;reason="resource_guard:$($guardResult.stop_reason)";case_dir=$caseDir;prefix=$prefix}
    }
    if ($guardResult.cpu_telemetry.gpu_sampling.status -ne "completed") {
        return [ordered]@{ok=$false;reason="gpu_telemetry:$($guardResult.cpu_telemetry.gpu_sampling.status)";case_dir=$caseDir;prefix=$prefix}
    }
    $rawPath = Join-Path $caseDir "raw.json"
    $evidencePath = Join-Path $caseDir "runner_evidence.json"
    $markerPath = Join-Path $caseDir "resource_markers.jsonl"
    if (-not (Test-Path -LiteralPath $rawPath) -or -not (Test-Path -LiteralPath $evidencePath) -or -not (Test-Path -LiteralPath $markerPath)) {
        return [ordered]@{ok=$false;reason="required_artifact_missing";case_dir=$caseDir;prefix=$prefix}
    }
    $raw = Get-Content -Raw -Encoding UTF8 $rawPath | ConvertFrom-Json
    $evidence = Get-Content -Raw -Encoding UTF8 $evidencePath | ConvertFrom-Json
    if ($raw.status -ne "ok" -or $raw.lifecycle_marker -ne "shutdown_complete") { return [ordered]@{ok=$false;reason="probe_lifecycle";case_dir=$caseDir;prefix=$prefix} }
    if ($evidence.outcome.lifecycle_status -ne "normal_exit" -or @($evidence.fatal_lines).Count -ne 0 -or @($evidence.dump_inventory).Count -ne 0 -or @($evidence.automatic_upload_attempt_lines).Count -ne 0) {
        return [ordered]@{ok=$false;reason="shutdown_or_fatal_evidence";case_dir=$caseDir;prefix=$prefix}
    }
    foreach ($required in @("timeline_playing", "timeline_stopped", "renderer_drain_complete", "shutdown_complete")) {
        if (-not (Test-Marker $markerPath $required)) { return [ordered]@{ok=$false;reason="marker_missing:$required";case_dir=$caseDir;prefix=$prefix} }
    }
    if ($Mode -ne "none") {
        foreach ($required in @("readback_call_before", "readback_call_after", "tuple_elements_checked", "python_references_released")) {
            if (-not (Test-Marker $markerPath $required)) { return [ordered]@{ok=$false;reason="marker_missing:$required";case_dir=$caseDir;prefix=$prefix} }
        }
    }
    if ($Mode -in @("fuel_convert", "fuel_scalar", "fuel_jsonl", "fuel_spatial")) {
        foreach ($required in @("fuel_conversion_before", "fuel_conversion_after")) {
            if (-not (Test-Marker $markerPath $required)) { return [ordered]@{ok=$false;reason="marker_missing:$required";case_dir=$caseDir;prefix=$prefix} }
        }
    }
    return [ordered]@{ok=$true;reason=$null;case_dir=$caseDir;prefix=$prefix}
}

Write-State "preflight" 0 "warmup" ""
$warmup = Invoke-GuardedCase "warmup" ([string]$contract.warmup.scenario) 0 "none" "" "natural" (($contract.warmup.sample_frames -join ','))
if (-not $warmup.ok) { Stop-Safely 0 "warmup" $warmup.reason }

$completed = 0
$sampleFrames = @($contract.timeline.observation_frames) -join ','
foreach ($group in $contract.condition_groups) {
    foreach ($condition in $group.conditions) {
        for ($run = 1; $run -le [int]$contract.runs_per_condition; $run++) {
            $active = "$($group.id)/run$('{0:d2}' -f $run)/$($condition.id)"
            Write-State "running" $completed $active ""
            $readbackFrames = @($condition.readback_frames) -join ','
            $result = Invoke-GuardedCase ([string]$condition.id) "production_four" $run ([string]$condition.readback_mode) $readbackFrames ([string]$condition.reference_disposal) $sampleFrames
            if (-not $result.ok) { Stop-Safely $completed $active $result.reason }
            $completed += 1
            Update-Report
        }
    }
    $report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
    $groupResult = $report.groups.PSObject.Properties[[string]$group.id].Value
    if (-not [bool]$groupResult.gate_pass) {
        Stop-Safely $completed ([string]$group.id) "group_plateau_or_completion_gate_failed"
    }
}

$productionAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
if ($productionBefore -ne $productionAfter) { Stop-Safely $completed "final" "production_app_hash_changed" }
Update-Report
Write-State "qualified" $completed "complete" ""
Write-Host "Phase 6EU calibration completed: $completed/$($contract.formal_process_count) independent processes"
