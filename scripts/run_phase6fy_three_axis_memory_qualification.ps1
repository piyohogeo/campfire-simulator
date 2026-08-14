param(
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [string]$ContractPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$repo = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6FY refuses artifact root reuse: $OutputRoot" }
$contractPath = if ([string]::IsNullOrWhiteSpace($ContractPath)) {
    Join-Path $PSScriptRoot "phase6fy_three_axis_memory_qualification_contract.json"
} else { [IO.Path]::GetFullPath($ContractPath) }
$hashPath = [IO.Path]::ChangeExtension($contractPath, ".sha256")
$expectedHash = ((Get-Content -Encoding UTF8 $hashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($actualHash -ne $expectedHash) { throw "Phase 6FY contract hash mismatch" }
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
if ($contract.phase -ne "phase6fy") { throw "Phase 6FY contract phase mismatch" }
$runtimeFiles = [ordered]@{
    phase6fu_resource_guard_sha256 = Join-Path $PSScriptRoot "phase6fu_resource_guard.py"
    phase6fu_process_identity_sha256 = Join-Path $PSScriptRoot "phase6fu_process_identity.py"
    frozen_phase6eg_resource_guard_sha256 = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
    kit_shutdown_policy_sha256 = Join-Path $PSScriptRoot "kit_shutdown_policy.ps1"
    shared_case_runner_sha256 = Join-Path $PSScriptRoot "run_phase6fo_supply_case.ps1"
    shared_probe_sha256 = Join-Path $PSScriptRoot "probe_phase6fo_supply_comparison.py"
    phase6fw_policy_sha256 = Join-Path $PSScriptRoot "phase6fw_pid_reuse_policy.py"
    three_axis_policy_sha256 = Join-Path $PSScriptRoot "phase6fy_three_axis_policy.py"
    preclose_committer_sha256 = Join-Path $PSScriptRoot "phase6fy_preclose_committer.py"
    analyzer_sha256 = Join-Path $PSScriptRoot "analyze_phase6fy_three_axis_memory_qualification.py"
    qualification_runner_sha256 = $PSCommandPath
    synchronized_probe_sha256 = Join-Path $PSScriptRoot "probe_phase6fy_three_axis_memory.py"
    phase6fy_case_runner_sha256 = Join-Path $PSScriptRoot "run_phase6fy_memory_case.ps1"
    fixture_runner_sha256 = Join-Path $PSScriptRoot "run_phase6fy_three_axis_fixtures.py"
}
foreach ($entry in $runtimeFiles.GetEnumerator()) {
    $required = [string]$contract.runtime_hashes.($entry.Key)
    $observed = (Get-FileHash -Algorithm SHA256 -LiteralPath $entry.Value).Hash
    if ($required -ne $observed) { throw "Phase 6FY runtime hash mismatch: $($entry.Key)" }
}

New-Item -ItemType Directory -Path $OutputRoot | Out-Null
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
Copy-Item -LiteralPath $hashPath -Destination (Join-Path $OutputRoot "frozen_contract.sha256")
$python = (Get-Command python.exe).Source
$productionApp = Join-Path $repo "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$fixtureRunner = Join-Path $PSScriptRoot "run_phase6fy_three_axis_fixtures.py"
$fixtureRoot = Join-Path $OutputRoot "fixtures"
& $python $fixtureRunner --contract $contractPath --output-root $fixtureRoot
if ($LASTEXITCODE -ne 0) { throw "Phase 6FY fixture gate failed; real Kit was not started" }
$fixtureReport = Get-Content -Raw -Encoding UTF8 (Join-Path $fixtureRoot "fixture_report.json") | ConvertFrom-Json
if (-not $fixtureReport.passed -or $fixtureReport.total_count -ne 20) { throw "Phase 6FY fixture report failed closed" }

$guard = Join-Path $PSScriptRoot "phase6fu_resource_guard.py"
$caseRunner = Join-Path $PSScriptRoot "run_phase6fy_memory_case.ps1"
$committer = Join-Path $PSScriptRoot "phase6fy_preclose_committer.py"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6fy_three_axis_memory_qualification.py"
$powershell = (Get-Command powershell.exe).Source
$reportPath = Join-Path $OutputRoot "three_axis_memory_qualification_report.json"
$statePath = Join-Path $OutputRoot "incremental_state.json"
$previousExitUtc = ""
$launched = 0
$basicLaunched = 0
$replacementLaunched = 0
$replacementQueue = New-Object System.Collections.Generic.List[object]

function Write-State([string]$Status, [string]$AttemptId, [string]$Classification, [string]$Reason) {
    $state = [ordered]@{
        schema="campfire.phase6fy.incremental-state.v1"; phase="phase6fy"; status=$Status
        launches=$launched; basic_launches=$basicLaunched; replacement_launches=$replacementLaunched
        active_attempt=$AttemptId; active_classification=$Classification; stop_reason=$Reason
        fixture_passed=$true; contract_sha256=$actualHash; production_sha256=$productionBefore
        phase6ft_reclassified=$false; phase6fv_reclassified=$false; phase6fx_reclassified=$false
        phase6fo_restarted=$false; timestamp_utc=[DateTime]::UtcNow.ToString("o")
    }
    [IO.File]::WriteAllText($statePath, ($state | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Update-Report {
    & $python $analyzer --root $OutputRoot --contract $contractPath --output $reportPath
    if ($LASTEXITCODE -ne 0) { throw "Phase 6FY analyzer failed" }
}

function Assert-Production([string]$Boundary) {
    $current = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
    if ($current -ne $productionBefore) {
        Write-State "population_stopped" $Boundary "memory_invalid_operation_failure" "production_app_hash_changed"
        throw "Phase 6FY production app hash changed"
    }
}

function Invoke-Attempt([object]$Slot, [string]$SlotKind, [string]$ReplacementFor) {
    $script:launched++
    if ($SlotKind -eq "basic") { $script:basicLaunched++ } else { $script:replacementLaunched++ }
    if ($launched -gt [int]$contract.population.maximum_total_launches) { throw "Phase 6FY total launch limit exceeded" }
    $attemptId = "attempt{0:D2}" -f $launched
    $attemptRoot = Join-Path $OutputRoot "attempts\$attemptId"
    $caseDir = Join-Path $attemptRoot "case"
    $logs = Join-Path $attemptRoot "runner-logs"
    New-Item -ItemType Directory -Path $logs | Out-Null
    $condition = @($contract.conditions | Where-Object { $_.id -eq $Slot.condition })[0]
    $metadata = [ordered]@{
        schema="campfire.phase6fy.attempt-metadata.v1"; phase="phase6fy"; attempt_id=$attemptId
        slot_id=$Slot.slot_id; slot_kind=$SlotKind; replacement_for=if([string]::IsNullOrWhiteSpace($ReplacementFor)){$null}else{$ReplacementFor}
        sequence=$Slot.sequence; position=$Slot.position; condition=$Slot.condition; run_index=$Slot.sequence
        settings=[ordered]@{
            allocation_level=[int]$condition.allocation_level; terminal_frame=[int]$condition.terminal_frame
            reference_release_order="after_stage_close"; readback_calls=0; capture_calls=0
        }
        previous_process_exit_utc=$previousExitUtc; timestamp_utc=[DateTime]::UtcNow.ToString("o")
    }
    [IO.File]::WriteAllText((Join-Path $attemptRoot "attempt_metadata.json"), ($metadata | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Write-State "running" $attemptId "" ""

    $sampleFrames = ($condition.sample_frames -join ',')
    $spatial = if ($condition.spatial_collectors_enabled) { "true" } else { "false" }
    $caseArgs = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $caseRunner,
        "-OutputDir", $caseDir, "-Condition", $condition.id, "-RunIndex", "$($Slot.sequence)",
        "-AttemptId", $attemptId, "-AllocationLevel", "$($condition.allocation_level)",
        "-SpatialCollectorsEnabled", $spatial, "-SampleFrames", $sampleFrames,
        "-TerminalFrame", "$($condition.terminal_frame)",
        "-StageCloseTimeoutSeconds", "$($contract.safety.stage_close_timeout_seconds)",
        "-AbsoluteTimeoutSeconds", "$($contract.safety.inner_absolute_timeout_seconds)"
    )
    if (-not [string]::IsNullOrWhiteSpace($previousExitUtc)) { $caseArgs += @("-PreviousProcessExitUtc", $previousExitUtc) }
    $guardArgs = @(
        $guard, "--trace", (Join-Path $logs "resource.jsonl"), "--summary", (Join-Path $logs "guard.json"),
        "--stdout", (Join-Path $logs "stdout.log"), "--stderr", (Join-Path $logs "stderr.log"),
        "--timeout-seconds", "$($contract.safety.outer_condition_timeout_seconds)",
        "--sample-seconds", "$($contract.recording.resource_sample_seconds)",
        "--runner-private-limit", "$($contract.safety.runner_private_limit_bytes)",
        "--diagnostic-private-limit", "$($contract.safety.diagnostic_private_limit_bytes)",
        "--kit-private-limit", "$($contract.safety.kit_absolute_stop_bytes)",
        "--tree-private-limit", "$($contract.safety.unique_tree_absolute_stop_bytes)",
        "--available-memory-floor", "$($contract.safety.physical_memory_floor_bytes)",
        "--commit-headroom-floor", "$($contract.safety.commit_headroom_floor_bytes)",
        "--cpu-telemetry", "--gpu-csv", (Join-Path $logs "gpu.csv"),
        "--gpu-sample-ms", "$($contract.recording.gpu_sample_ms)",
        "--lifecycle-path", (Join-Path $caseDir "raw.json"),
        "--diagnostic-marker-path", (Join-Path $caseDir "resource_markers.jsonl"),
        "--attempt-id", $attemptId,
        "--cleanup-suppression-lock", ((Join-Path $caseDir "sensitive-shutdown-diagnostics") + ".ownership.json"),
        "--cleanup-suppression-deadline-seconds", "$($contract.identity_cleanup.cleanup_suppression_deadline_seconds)",
        "--cleanup-marker-path", (Join-Path $logs "cleanup_markers.jsonl"),
        "--", $powershell
    ) + $caseArgs
    $guardProcess = Start-Process -FilePath $python -ArgumentList $guardArgs -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs "guard-launcher.stdout.log") -RedirectStandardError (Join-Path $logs "guard-launcher.stderr.log")
    $committerArgs = @(
        $committer, "--raw-path", (Join-Path $caseDir "raw.json"),
        "--resource-path", (Join-Path $logs "resource.jsonl"), "--gpu-path", (Join-Path $logs "gpu.csv"),
        "--marker-path", (Join-Path $caseDir "resource_markers.jsonl"),
        "--attempt-metadata", (Join-Path $attemptRoot "attempt_metadata.json"),
        "--contract", $contractPath, "--output-dir", (Join-Path $caseDir "memory-measurement"),
        "--stop-file", (Join-Path $attemptRoot "committer.stop"),
        "--timeout-seconds", "$($contract.artifact_commit.helper_timeout_seconds)",
        "--private-limit-bytes", "$($contract.artifact_commit.helper_private_limit_bytes)"
    )
    $committerProcess = Start-Process -FilePath $python -ArgumentList $committerArgs -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs "committer.stdout.log") -RedirectStandardError (Join-Path $logs "committer.stderr.log")
    $guardProcess.WaitForExit()
    [IO.File]::WriteAllText((Join-Path $attemptRoot "committer.stop"), "guard-exited`n", [Text.UTF8Encoding]::new($false))
    if (-not $committerProcess.WaitForExit(15000)) {
        Stop-Process -Id $committerProcess.Id -Force -ErrorAction SilentlyContinue
        throw "Phase 6FY committer child did not exit"
    }
    $script:previousExitUtc = [DateTime]::UtcNow.ToString("o")
    Update-Report
    Assert-Production $attemptId
    $report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
    $row = @($report.attempts | Where-Object { $_.attempt_id -eq $attemptId })[0]
    if ($row.classification -eq "memory_valid_lifecycle_timeout") {
        $replacementQueue.Add([pscustomobject]@{ slot=$Slot; original_attempt=$attemptId })
    } elseif ($row.classification -ne "memory_valid_lifecycle_normal") {
        Write-State "population_stopped" $attemptId $row.classification ($row.failures -join ',')
        throw "Phase 6FY nonreplaceable attempt: $($row.failures -join ',')"
    }
    if ($report.population.population_stopping_failure) {
        Write-State "population_stopped" $attemptId $row.classification ($report.population.failures -join ',')
        throw "Phase 6FY population policy stopped: $($report.population.failures -join ',')"
    }
}

$basicSlots = @()
for ($sequence = 1; $sequence -le $contract.population.basic_orders.Count; $sequence++) {
    $position = 0
    foreach ($conditionId in $contract.population.basic_orders[$sequence - 1]) {
        $position++
        $basicSlots += [pscustomobject]@{
            sequence=$sequence; position=$position; condition=[string]$conditionId
            slot_id=("sequence{0:D2}_position{1:D2}_{2}" -f $sequence, $position, $conditionId)
        }
    }
}
foreach ($slot in $basicSlots) { Invoke-Attempt $slot "basic" "" }
foreach ($item in @($replacementQueue)) {
    if ($replacementLaunched -ge [int]$contract.population.maximum_timeout_replacements) {
        Write-State "population_stopped" "replacement" "" "replacement_limit_exceeded"
        throw "Phase 6FY replacement limit exceeded"
    }
    $replacementSlot = [pscustomobject]@{
        sequence=$item.slot.sequence; position=$item.slot.position; condition=$item.slot.condition
        slot_id=("replacement_for_{0}_{1}" -f $item.original_attempt, $item.slot.condition)
    }
    Invoke-Attempt $replacementSlot "replacement" $item.original_attempt
}

Update-Report
Assert-Production "complete"
$final = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
if (-not $final.memory_ceiling_qualified) {
    Write-State "population_stopped" "complete" "" "memory_ceiling_not_qualified"
    throw "Phase 6FY memory ceiling did not qualify"
}
Write-State "qualified" "complete" "memory_qualified_lifecycle_separate" ""
Write-Host "Phase 6FY memory ceiling qualified; lifecycle remains separate and Phase 6FO remains stopped"
