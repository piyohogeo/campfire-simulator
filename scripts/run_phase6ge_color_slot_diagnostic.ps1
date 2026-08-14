param(
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [string]$ContractPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0

$repo = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6GE refuses artifact root reuse: $OutputRoot" }
$contractPath = if ([string]::IsNullOrWhiteSpace($ContractPath)) {
    Join-Path $PSScriptRoot "phase6ge_color_slot_diagnostic_contract.json"
} else { [IO.Path]::GetFullPath($ContractPath) }
$hashPath = [IO.Path]::ChangeExtension($contractPath, ".sha256")
$expectedHash = ((Get-Content -Encoding UTF8 $hashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($actualHash -ne $expectedHash) { throw "Phase 6GE contract hash mismatch" }
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
$phase = [string]$contract.phase
if ($phase -notin @("phase6ge", "phase6gf", "phase6gg") -or $contract.schema -ne "campfire.$phase.color-slot-diagnostic-contract.v1") {
    throw "Phase 6GE/6GF contract schema mismatch"
}

$production = Join-Path $repo "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $production).Hash
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
Copy-Item -LiteralPath $hashPath -Destination (Join-Path $OutputRoot "frozen_contract.sha256")

$plan = [ordered]@{
    schema = "campfire.$phase.color-slot-diagnostic-plan.v1"
    phase = $phase
    contract_sha256 = $actualHash
    controls = @($contract.controls.order)
    started_at_utc = [DateTime]::UtcNow.ToString("o")
    results = @()
    formal_s93_s100_population_started = $false
}
$planPath = Join-Path $OutputRoot "diagnostic_plan.json"
function Save-Plan {
    [IO.File]::WriteAllText($planPath, ($plan | ConvertTo-Json -Depth 12) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}
Save-Plan

$childRunner = Join-Path $PSScriptRoot "run_phase6gd_channel_metadata_probe.ps1"
$gate = Join-Path $PSScriptRoot "phase6ge_next_condition_gate.py"
$controlContract = Join-Path $PSScriptRoot "phase6gd_channel_schema_control_contract.json"
$powershell = (Get-Command powershell.exe).Source
foreach ($condition in @($contract.controls.order)) {
    $mode = [string]$contract.controls.runtime_mode.$condition
    $conditionRoot = Join-Path $OutputRoot "$condition-$mode"
    $stdout = Join-Path $OutputRoot "$condition.runner.stdout.log"
    $stderr = Join-Path $OutputRoot "$condition.runner.stderr.log"
    $arguments = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $childRunner,
        "-OutputRoot", $conditionRoot, "-Control", $mode,
        "-DiagnosticResourceContractPath", $contractPath, "-ReportPhase", $phase
    )
    if ($mode -ne "baseline") { $arguments += @("-ControlContractPath", $controlContract) }
    & $powershell @arguments 1> $stdout 2> $stderr
    $childExitCode = $LASTEXITCODE
    $entry = [ordered]@{
        condition = $condition
        control = $mode
        child_exit_code = $childExitCode
        artifact_root = $conditionRoot
        started = $true
        next_condition_allowed = $false
    }
    $plan.results += $entry
    Save-Plan
    if ($childExitCode -ne 0) {
        $plan.safe_stop = [ordered]@{ condition = $condition; reason = "child_runner_failed"; exit_code = $childExitCode }
        Save-Plan
        throw "Phase 6GE stopped at $condition because the child runner failed"
    }
    $attemptId = "metadata_$mode`_attempt01"
    $case = Join-Path $conditionRoot "$attemptId\S93_support_clear"
    $runnerEvidence = Join-Path $case "runner_evidence.json"
    $guardEvidence = Join-Path $conditionRoot "$attemptId\runner-logs\S93_support_clear.guard.json"
    $gatePath = Join-Path $conditionRoot "next_condition_gate.json"
    & python $gate --runner-evidence $runnerEvidence --guard $guardEvidence --output $gatePath
    if ($LASTEXITCODE -ne 0) {
        $plan.safe_stop = [ordered]@{ condition = $condition; reason = "next_condition_gate_failed" }
        Save-Plan
        throw "Phase 6GE stopped at $condition because the three-axis next-condition gate failed"
    }
    $gateResult = Get-Content -Raw -Encoding UTF8 $gatePath | ConvertFrom-Json
    $metadataPath = Join-Path $case "channel-schema-metadata\bounded_handle_metadata.json"
    if (-not (Test-Path -LiteralPath $metadataPath)) { throw "Phase 6GE metadata artifact is missing" }
    $metadata = Get-Content -Raw -Encoding UTF8 $metadataPath | ConvertFrom-Json
    if ([int]$metadata.returned_handle_count -ne [int]$contract.metadata.expected_handle_count) {
        throw "Phase 6GE handle count mismatch"
    }
    $entry.next_condition_allowed = [bool]$gateResult.next_condition_allowed
    $entry.metadata_path = $metadataPath
    $entry.metadata_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $metadataPath).Hash
    $entry.returned_handle_count = [int]$metadata.returned_handle_count
    Save-Plan
}

if ((Get-FileHash -Algorithm SHA256 -LiteralPath $production).Hash -ne $productionBefore) {
    throw "Phase 6GE changed the production app"
}
$plan.status = "metadata_population_complete"
$plan.completed_at_utc = [DateTime]::UtcNow.ToString("o")
$plan.production_sha256 = $productionBefore
Save-Plan
Write-Host "Phase 6GE C0/C1/C2 metadata population complete; mapping analysis remains separate."
