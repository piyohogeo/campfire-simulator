param([Parameter(Mandatory=$true)][string]$OutputRoot)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$repo = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6ET refuses artifact root reuse: $OutputRoot" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
$logs = Join-Path $OutputRoot "runner-logs"
New-Item -ItemType Directory -Path $logs | Out-Null

$contractPath = Join-Path $PSScriptRoot "phase6et_memory_calibration_contract.json"
$hashPath = Join-Path $PSScriptRoot "phase6et_memory_calibration_contract.sha256"
$expectedHash = ((Get-Content -Raw -Encoding ASCII $hashPath).Trim().Split(' ')[0]).ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($expectedHash -ne $actualHash) { throw "Phase 6ET contract hash mismatch" }
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
[IO.File]::WriteAllText((Join-Path $OutputRoot "frozen_contract.sha256"), "$actualHash  frozen_contract.json`n", [Text.UTF8Encoding]::new($false))

$guard = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
$caseRunner = Join-Path $PSScriptRoot "run_phase6ep_point_collision_case.ps1"
$transport = Join-Path $PSScriptRoot "phase6es_directional_transport.py"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6et_memory_calibration.py"
$powershell = (Get-Process -Id $PID).Path
$productionApp = Join-Path $repo "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$limits = $contract.safety
$statePath = Join-Path $OutputRoot "incremental_state.json"

function Write-State([string]$Status, [int]$Completed, [string]$Active, [string]$Reason) {
    $productionAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
    $payload = [ordered]@{
        schema = "campfire.phase6et.incremental-state.v1"
        phase = "phase6et"
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
    & python $analyzer --root $OutputRoot --contract $contractPath --output (Join-Path $OutputRoot "memory_calibration_report.json") | Out-Host
}

function Stop-Safely([int]$Completed, [string]$Active, [string]$Reason) {
    Write-State "safe_stop" $Completed $Active $Reason
    Update-Report
    Write-Error "Phase 6ET safe stop at ${Active}: $Reason"
    exit 2
}

function Invoke-GuardedCase([string]$Label, [string]$Scenario, [int]$RunIndex, [string]$ReadbackChannels, [bool]$SpatialEnabled, [string]$SpatialIndices, [bool]$AllChannels, [string]$SampleFrames) {
    $caseDir = if ($Label -eq "warmup") { Join-Path $OutputRoot "warmup" } else { Join-Path $OutputRoot "calibration\run$('{0:d2}' -f $RunIndex)\$Label" }
    $prefix = if ($Label -eq "warmup") { "warmup" } else { "run$('{0:d2}' -f $RunIndex)_$Label" }
    $arguments = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $caseRunner,
        "-Scenario", $Scenario, "-OutputDir", $caseDir,
        "-OffsetM", "-0.0125", "-SupportRadiusM", "0.05",
        "-Filtering", "true", "-Collision", "true", "-Policy", "allow_self_center",
        "-ReportPhase", "phase6et", "-GeometryVariant", "phase6er_corrected",
        "-FuelScale", "1", "-TemperatureScale", "1", "-SmokeScale", "1",
        "-SampleFrames", $SampleFrames, "-ReadbackChannels", $ReadbackChannels,
        "-SpatialCollectorsEnabled", $SpatialEnabled.ToString().ToLowerInvariant(),
        "-SpatialColliderIndices", $SpatialIndices,
        "-SpatialScalarColliderIndices", $SpatialIndices,
        "-RunIndex", "$RunIndex"
    )
    if ($AllChannels) { $arguments += "-SpatialAllChannels" }
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
    $raw = Get-Content -Raw -Encoding UTF8 (Join-Path $caseDir "raw.json") | ConvertFrom-Json
    $evidence = Get-Content -Raw -Encoding UTF8 (Join-Path $caseDir "runner_evidence.json") | ConvertFrom-Json
    if ($raw.status -ne "ok" -or $raw.lifecycle_marker -ne "shutdown_complete") { return [ordered]@{ok=$false;reason="probe_lifecycle";case_dir=$caseDir;prefix=$prefix} }
    if ($evidence.outcome.lifecycle_status -ne "normal_exit" -or @($evidence.fatal_lines).Count -ne 0 -or @($evidence.dump_inventory).Count -ne 0 -or @($evidence.automatic_upload_attempt_lines).Count -ne 0) {
        return [ordered]@{ok=$false;reason="shutdown_or_fatal_evidence";case_dir=$caseDir;prefix=$prefix}
    }
    return [ordered]@{ok=$true;reason=$null;case_dir=$caseDir;prefix=$prefix}
}

Write-State "preflight" 0 "warmup" ""
$warmup = Invoke-GuardedCase "warmup" ([string]$contract.warmup.scenario) 0 "none" $false "" $false (($contract.warmup.sample_frames -join ','))
if (-not $warmup.ok) { Stop-Safely 0 "warmup" $warmup.reason }

$conditions = @{}
foreach ($condition in $contract.conditions) { $conditions[[string]$condition.id] = $condition }
$completed = 0
for ($run = 1; $run -le 3; $run++) {
    $order = @($contract.run_orders[$run - 1])
    foreach ($idValue in $order) {
        $id = [string]$idValue
        $condition = $conditions[$id]
        Write-State "running" $completed "run$('{0:d2}' -f $run)/$id" ""
        $channels = if (@($condition.readback_channels).Count -eq 0) { "none" } else { @($condition.readback_channels) -join ',' }
        $indices = @($condition.spatial_collider_indices) -join ','
        $allChannels = (@($condition.readback_channels) -contains "temperature") -or (@($condition.readback_channels) -contains "smoke")
        $result = Invoke-GuardedCase $id "production_four" $run $channels ([bool]$condition.spatial_collectors_enabled) $indices $allChannels (($contract.sample_frames -join ','))
        if (-not $result.ok) { Stop-Safely $completed "run$('{0:d2}' -f $run)/$id" $result.reason }
        if ([bool]$condition.offline_transport) {
            $transportOut = Join-Path $result.case_dir "directional_transport.json"
            $transportPrefix = "$($result.prefix).transport"
            $transportArgs = @(
                $guard, "--trace", (Join-Path $logs "$transportPrefix.resource.jsonl"),
                "--summary", (Join-Path $logs "$transportPrefix.guard.json"),
                "--stdout", (Join-Path $logs "$transportPrefix.stdout.log"),
                "--stderr", (Join-Path $logs "$transportPrefix.stderr.log"),
                "--timeout-seconds", "120", "--runner-private-limit", "$($limits.runner_private_limit_bytes)",
                "--diagnostic-private-limit", "$($limits.diagnostic_private_limit_bytes)",
                "--kit-private-limit", "$($limits.kit_private_limit_bytes)",
                "--tree-private-limit", "$($limits.unique_tree_private_limit_bytes)",
                "--available-memory-floor", "$($limits.physical_memory_floor_bytes)",
                "--commit-headroom-floor", "$($limits.commit_headroom_floor_bytes)", "--",
                "python", $transport, "--condition", $result.case_dir, "--output", $transportOut, "--plane-offset-m", "0.05"
            )
            & python @transportArgs | Out-Host
            if ($LASTEXITCODE -ne 0) { Stop-Safely $completed "run$('{0:d2}' -f $run)/$id/transport" "offline_transport_guard" }
        }
        $completed += 1
        Update-Report
    }
}

$productionAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
if ($productionBefore -ne $productionAfter) { Stop-Safely $completed "final" "production_app_hash_changed" }
Update-Report
$report = Get-Content -Raw -Encoding UTF8 (Join-Path $OutputRoot "memory_calibration_report.json") | ConvertFrom-Json
if (-not [bool]$report.return_gate_satisfied) { Stop-Safely $completed "final" "plateau_or_completion_gate_failed" }
Write-State "qualified" $completed "complete" ""
Write-Host "Phase 6ET calibration qualified: $completed/$($contract.formal_process_count) independent processes"
