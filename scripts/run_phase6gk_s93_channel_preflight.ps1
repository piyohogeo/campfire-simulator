param([Parameter(Mandatory = $true)][string]$OutputRoot, [string]$ContractPath = "")

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$repo = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6GK refuses artifact root reuse: $OutputRoot" }
$contractPath = if ([string]::IsNullOrWhiteSpace($ContractPath)) {
    Join-Path $PSScriptRoot "phase6gk_bounded_artifact_interface_contract.json"
} else { [IO.Path]::GetFullPath($ContractPath) }
$hashPath = [IO.Path]::ChangeExtension($contractPath, ".sha256")
$expectedHash = ((Get-Content -Encoding UTF8 $hashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($actualHash -ne $expectedHash) { throw "Phase 6GK contract hash mismatch" }
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
if ($contract.schema -ne "campfire.phase6gk.bounded-artifact-interface-preflight-contract.v1" -or $contract.phase -ne "phase6gk") {
    throw "Phase 6GK contract schema mismatch"
}
$candidatePath = Join-Path $repo ([string]$contract.candidate_schema.path)
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $candidatePath).Hash -ne [string]$contract.candidate_schema.sha256) {
    throw "Phase 6GK frozen Phase 6GH candidate schema changed"
}
$production = Join-Path $repo "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $production).Hash
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "frozen_contract.json")
Copy-Item -LiteralPath $hashPath -Destination (Join-Path $OutputRoot "frozen_contract.sha256")
Copy-Item -LiteralPath $candidatePath -Destination (Join-Path $OutputRoot "frozen_candidate_schema.json")

$fixturePath = Join-Path $OutputRoot "schema_fixtures.json"
& python (Join-Path $PSScriptRoot "phase6gj_empty_rgba_alias_policy.py") --contract $contractPath --fixtures --output $fixturePath
if ($LASTEXITCODE -ne 0) { throw "Phase 6GK schema fixture failed before Kit" }
$fixture = Get-Content -Raw -Encoding UTF8 $fixturePath | ConvertFrom-Json
if (-not $fixture.all_pass) { throw "Phase 6GK schema fixture report is not all-pass" }
$interfaceFixtureRoot = Join-Path $OutputRoot "bounded-artifact-interface-fixtures"
$fixtureRunner = Join-Path $PSScriptRoot "run_phase6gk_bounded_artifact_interface_fixtures.ps1"
$powershell = (Get-Command powershell.exe).Source
& $powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $fixtureRunner -OutputRoot $interfaceFixtureRoot
if ($LASTEXITCODE -ne 0) { throw "Phase 6GK bounded artifact interface fixture failed before Kit" }
$interfaceFixturePath = Join-Path $interfaceFixtureRoot "summary.json"
if (-not (Test-Path -LiteralPath $interfaceFixturePath)) { throw "Phase 6GK bounded artifact interface fixture summary is missing" }
$interfaceFixture = Get-Content -Raw -Encoding UTF8 $interfaceFixturePath | ConvertFrom-Json
if (-not $interfaceFixture.all_pass) { throw "Phase 6GK bounded artifact interface fixture report is not all-pass" }
$startupFixturePath = Join-Path $OutputRoot "startup_replacement_fixtures.json"
& python (Join-Path $PSScriptRoot "phase6gh_startup_replacement_policy.py") --fixtures --output $startupFixturePath
if ($LASTEXITCODE -ne 0) { throw "Phase 6GK startup replacement fixture failed before Kit" }
$startupFixture = Get-Content -Raw -Encoding UTF8 $startupFixturePath | ConvertFrom-Json
if ($startupFixture.status -ne "pass") { throw "Phase 6GK startup replacement fixture report is not pass" }

$plan = [ordered]@{
    schema = "campfire.phase6gk.s93-channel-preflight-plan.v1"; phase = "phase6gk"; status = "running"
    contract_sha256 = $actualHash; candidate_schema_sha256 = [string]$contract.candidate_schema.sha256
    replacement_budget = [int]$contract.startup_population.startup_prerequisite_replacement_budget
    replacements_used = 0; total_launches = 0; attempts = @(); accepted_attempt = $null
    formal_s93_s100_population_started = $false; started_at_utc = [DateTime]::UtcNow.ToString("o")
}
$planPath = Join-Path $OutputRoot "preflight_plan.json"
function Save-Plan { [IO.File]::WriteAllText($planPath, ($plan | ConvertTo-Json -Depth 16) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false)) }
function Stop-Preflight([string]$Reason, [string]$Classification) {
    $plan.status = "safe_stop"
    $plan.safe_stop = [ordered]@{ reason = $Reason; classification = $Classification; timestamp_utc = [DateTime]::UtcNow.ToString("o") }
    Save-Plan
    throw "Phase 6GK safe stop: $Reason ($Classification)"
}
Save-Plan

$child = Join-Path $PSScriptRoot "run_phase6gd_channel_metadata_probe.ps1"
$probe = Join-Path $PSScriptRoot "probe_phase6gk_s93_channel_preflight.py"
$policy = Join-Path $PSScriptRoot "phase6gk_preflight_attempt_policy.py"
$controlContract = Join-Path $PSScriptRoot "phase6gd_channel_schema_control_contract.json"
$powershell = (Get-Command powershell.exe).Source
$accepted = $false
$attemptNumber = 0
while (-not $accepted) {
    $attemptNumber++
    $plan.total_launches = [int]$plan.total_launches + 1
    if ([int]$plan.total_launches -gt [int]$contract.startup_population.maximum_total_launches) {
        Stop-Preflight "maximum_total_launches_exceeded" "startup_prerequisite_failure"
    }
    $label = "S93-attempt$($attemptNumber.ToString('D2'))"
    $attemptRoot = Join-Path $OutputRoot $label
    $stdout = Join-Path $OutputRoot "$label.runner.stdout.log"
    $stderr = Join-Path $OutputRoot "$label.runner.stderr.log"
    $arguments = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $child,
        "-OutputRoot", $attemptRoot, "-Control", "divergence", "-ControlContractPath", $controlContract,
        "-ReportPhase", "phase6gk", "-ProbePath", $probe, "-RequireDiscoveryUnmapped", "false",
        "-SpatialCollectorsEnabled", "false", "-ShortPreflight"
    )
    $savedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $powershell @arguments 1> $stdout 2> $stderr
        $childExitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $savedPreference }
    $inner = Join-Path $attemptRoot "metadata_divergence_attempt01"
    $case = Join-Path $inner "S93_support_clear"
    $rawPath = Join-Path $case "raw.json"
    $runnerPath = Join-Path $case "runner_evidence.json"
    $guardPath = Join-Path $inner "runner-logs\S93_support_clear.guard.json"
    $preflightPath = Join-Path $case "channel-schema-metadata\qualified_channel_preflight.json"
    $classificationPath = Join-Path $attemptRoot "attempt_classification.json"
    $entry = [ordered]@{ attempt = $attemptNumber; launch_index = [int]$plan.total_launches; artifact_root = $attemptRoot
        child_exit_code = $childExitCode; classification = "unavailable"; replacement_eligible = $false
        replacement_scheduled = $false; accepted = $false; preflight_path = $null }
    $plan.attempts += $entry
    Save-Plan
    if (-not (Test-Path $rawPath) -or -not (Test-Path $runnerPath) -or -not (Test-Path $guardPath)) {
        Stop-Preflight "classification_artifact_missing" "artifact_failure"
    }
    $policyArgs = @($policy, "--raw", $rawPath, "--runner", $runnerPath, "--guard", $guardPath, "--output", $classificationPath)
    if (Test-Path $preflightPath) { $policyArgs += @("--preflight", $preflightPath) }
    & python @policyArgs
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $classificationPath)) { Stop-Preflight "classifier_failed" "artifact_failure" }
    $classification = Get-Content -Raw -Encoding UTF8 $classificationPath | ConvertFrom-Json
    $entry.classification = [string]$classification.classification
    $entry.replacement_eligible = [bool]$classification.replacement_eligible
    if (Test-Path $preflightPath) { $entry.preflight_path = $preflightPath }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $production).Hash -ne $productionBefore) {
        Stop-Preflight "production_hash_changed" "artifact_failure"
    }
    if ($classification.classification -eq "accepted_normal_sample") {
        if ($childExitCode -ne 0 -or -not (Test-Path $preflightPath)) {
            Stop-Preflight "accepted_exit_or_artifact_mismatch" "artifact_failure"
        }
        $entry.accepted = $true; $plan.accepted_attempt = $attemptNumber; $accepted = $true; Save-Plan; continue
    }
    if ($classification.classification -eq "startup_prerequisite_failure" -and $classification.replacement_eligible) {
        if ([int]$plan.replacements_used -ge [int]$plan.replacement_budget) {
            Stop-Preflight "replacement_budget_exhausted" "startup_prerequisite_failure"
        }
        $plan.replacements_used = [int]$plan.replacements_used + 1
        $entry.replacement_scheduled = $true; Save-Plan; continue
    }
    Stop-Preflight "nonreplaceable_attempt_failure" ([string]$classification.classification)
}

$plan.status = "preflight_qualified"
$plan.completed_at_utc = [DateTime]::UtcNow.ToString("o")
$plan.production_sha256 = $productionBefore
$plan.next_step_requires_explicit_approval = $true
Save-Plan
$summary = [ordered]@{
    schema = "campfire.phase6gk.s93-channel-preflight-summary.v1"; phase = "phase6gk"; status = "qualified"
    contract_sha256 = $actualHash; candidate_schema_id = [string]$contract.candidate_schema.schema_id
    candidate_schema_sha256 = [string]$contract.candidate_schema.sha256; fixture_passed = [int]$fixture.passed
    fixture_total = [int]$fixture.total; bounded_artifact_interface_fixture_passed = [int]$interfaceFixture.passed
    bounded_artifact_interface_fixture_total = [int]$interfaceFixture.total; total_launches = [int]$plan.total_launches
    startup_fixture_passed = [int]$startupFixture.passed; startup_fixture_total = [int]$startupFixture.total
    replacements_used = [int]$plan.replacements_used; accepted_attempt = [int]$plan.accepted_attempt
    formal_s93_s100_population_started = $false; production_sha256 = $productionBefore
    next_step_requires_explicit_approval = $true; timestamp_utc = [DateTime]::UtcNow.ToString("o")
}
[IO.File]::WriteAllText((Join-Path $OutputRoot "summary.json"), ($summary | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host "Phase 6GK S93 channel preflight qualified; formal comparison remains blocked."
