param(
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [string]$ContractPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$repo = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6GH refuses artifact root reuse: $OutputRoot" }
$contractPath = if ([string]::IsNullOrWhiteSpace($ContractPath)) {
    Join-Path $PSScriptRoot "phase6gh_color_slot_diagnostic_contract.json"
} else { [IO.Path]::GetFullPath($ContractPath) }
$hashPath = [IO.Path]::ChangeExtension($contractPath, ".sha256")
$expectedHash = ((Get-Content -Encoding UTF8 $hashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($actualHash -ne $expectedHash) { throw "Phase 6GH contract hash mismatch" }
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
if ($contract.phase -ne "phase6gh" -or $contract.schema -ne "campfire.phase6gh.color-slot-diagnostic-contract.v1") {
    throw "Phase 6GH contract schema mismatch"
}

$production = Join-Path $repo "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $production).Hash
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
Copy-Item -LiteralPath $hashPath -Destination (Join-Path $OutputRoot "frozen_contract.sha256")

$plan = [ordered]@{
    schema = "campfire.phase6gh.color-slot-diagnostic-plan.v1"
    phase = "phase6gh"
    contract_sha256 = $actualHash
    controls = @($contract.controls.order)
    replacement_budget = [int]$contract.population.startup_prerequisite_replacement_budget
    replacements_used = 0
    total_launches = 0
    accepted_conditions = @()
    attempts = @()
    status = "running"
    safe_stop = $null
    started_at_utc = [DateTime]::UtcNow.ToString("o")
    formal_s93_s100_population_started = $false
}
$planPath = Join-Path $OutputRoot "diagnostic_plan.json"
function Save-Plan {
    [IO.File]::WriteAllText($planPath, ($plan | ConvertTo-Json -Depth 16) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}
function Stop-Population([string]$Condition, [string]$Reason, [string]$Classification) {
    $plan.status = "safe_stop"
    $plan.safe_stop = [ordered]@{ condition = $Condition; reason = $Reason; classification = $Classification; timestamp_utc = [DateTime]::UtcNow.ToString("o") }
    Save-Plan
    throw "Phase 6GH safe stop at $Condition`: $Reason ($Classification)"
}
Save-Plan

$childRunner = Join-Path $PSScriptRoot "run_phase6gd_channel_metadata_probe.ps1"
$policy = Join-Path $PSScriptRoot "phase6gh_startup_replacement_policy.py"
$controlContract = Join-Path $PSScriptRoot "phase6gd_channel_schema_control_contract.json"
$powershell = (Get-Command powershell.exe).Source

foreach ($condition in @($contract.controls.order)) {
    $mode = [string]$contract.controls.runtime_mode.$condition
    $conditionAccepted = $false
    $conditionAttempt = 0
    while (-not $conditionAccepted) {
        $conditionAttempt++
        $plan.total_launches = [int]$plan.total_launches + 1
        if ([int]$plan.total_launches -gt [int]$contract.population.maximum_total_launches) {
            Stop-Population $condition "maximum_total_launches_exceeded" "startup_prerequisite_failure"
        }
        $attemptLabel = "$condition-attempt$($conditionAttempt.ToString('D2'))-$mode"
        $attemptRoot = Join-Path $OutputRoot $attemptLabel
        $stdout = Join-Path $OutputRoot "$attemptLabel.runner.stdout.log"
        $stderr = Join-Path $OutputRoot "$attemptLabel.runner.stderr.log"
        $arguments = @(
            "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $childRunner,
            "-OutputRoot", $attemptRoot, "-Control", $mode,
            "-DiagnosticResourceContractPath", $contractPath, "-ReportPhase", "phase6gh"
        )
        if ($mode -ne "baseline") { $arguments += @("-ControlContractPath", $controlContract) }
        $savedPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & $powershell @arguments 1> $stdout 2> $stderr
            $childExitCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $savedPreference
        }

        $innerAttempt = "metadata_$mode`_attempt01"
        $case = Join-Path $attemptRoot "$innerAttempt\S93_support_clear"
        $rawPath = Join-Path $case "raw.json"
        $runnerPath = Join-Path $case "runner_evidence.json"
        $guardPath = Join-Path $attemptRoot "$innerAttempt\runner-logs\S93_support_clear.guard.json"
        $metadataPath = Join-Path $case "channel-schema-metadata\bounded_handle_metadata.json"
        $classificationPath = Join-Path $attemptRoot "attempt_classification.json"
        $attemptEntry = [ordered]@{
            condition = $condition
            control = $mode
            condition_attempt = $conditionAttempt
            launch_index = [int]$plan.total_launches
            child_exit_code = $childExitCode
            artifact_root = $attemptRoot
            classification = "unavailable"
            replacement_eligible = $false
            accepted = $false
            replacement_scheduled = $false
            classification_path = $null
            metadata_path = $null
            metadata_sha256 = $null
        }
        $plan.attempts += $attemptEntry
        Save-Plan
        if (-not (Test-Path -LiteralPath $rawPath) -or -not (Test-Path -LiteralPath $runnerPath) -or -not (Test-Path -LiteralPath $guardPath)) {
            Stop-Population $condition "classification_artifact_missing" "artifact_or_identity_failure"
        }
        $policyArguments = @($policy, "--raw", $rawPath, "--runner", $runnerPath, "--guard", $guardPath, "--output", $classificationPath)
        if (Test-Path -LiteralPath $metadataPath) { $policyArguments += @("--metadata", $metadataPath) }
        & python @policyArguments
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $classificationPath)) {
            Stop-Population $condition "attempt_classifier_failed" "artifact_or_identity_failure"
        }
        $classification = Get-Content -Raw -Encoding UTF8 $classificationPath | ConvertFrom-Json
        $attemptEntry.classification = [string]$classification.classification
        $attemptEntry.replacement_eligible = [bool]$classification.replacement_eligible
        $attemptEntry.classification_path = $classificationPath
        if (Test-Path -LiteralPath $metadataPath) {
            $attemptEntry.metadata_path = $metadataPath
            $attemptEntry.metadata_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $metadataPath).Hash
        }
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $production).Hash -ne $productionBefore) {
            Stop-Population $condition "production_app_hash_changed" "artifact_or_identity_failure"
        }

        if ($classification.classification -eq "accepted_normal_sample") {
            if ($childExitCode -ne 0 -or -not (Test-Path -LiteralPath $metadataPath)) {
                Stop-Population $condition "accepted_sample_exit_or_metadata_mismatch" "artifact_or_identity_failure"
            }
            $attemptEntry.accepted = $true
            $plan.accepted_conditions += $condition
            $conditionAccepted = $true
            Save-Plan
            continue
        }
        if ($classification.classification -eq "startup_prerequisite_failure") {
            if (-not $classification.replacement_eligible) {
                Stop-Population $condition "startup_classification_not_replacement_eligible" "operation_failure"
            }
            if ([int]$plan.replacements_used -ge [int]$plan.replacement_budget) {
                Stop-Population $condition "startup_replacement_budget_exhausted" "startup_prerequisite_failure"
            }
            $plan.replacements_used = [int]$plan.replacements_used + 1
            $attemptEntry.replacement_scheduled = $true
            Save-Plan
            continue
        }
        Stop-Population $condition "nonreplaceable_attempt_failure" ([string]$classification.classification)
    }
}

if (@($plan.accepted_conditions).Count -ne 3) {
    Stop-Population "complete" "accepted_population_incomplete" "operation_failure"
}
$plan.status = "metadata_population_complete"
$plan.completed_at_utc = [DateTime]::UtcNow.ToString("o")
$plan.production_sha256 = $productionBefore
Save-Plan
Write-Host "Phase 6GH accepted C0/C1/C2 metadata population complete; formal comparison remains blocked."
