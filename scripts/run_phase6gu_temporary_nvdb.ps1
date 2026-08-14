param(
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [string]$ContractPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$contract = if ($ContractPath) { $ContractPath } else { Join-Path $PSScriptRoot "phase6gu_temporary_nvdb_contract.json" }
& (Join-Path $PSScriptRoot "run_phase6gt_temporary_nvdb.ps1") `
    -OutputRoot $OutputRoot `
    -ContractPath $contract `
    -PhaseSlug "phase6gu" `
    -ReportPhase "phase6gu" `
    -FixtureScript "test_phase6gu_marker_contract.py" `
    -FixtureReportEnvironmentVariable "PHASE6GU_FIXTURE_REPORT" `
    -ExpectedFixtureCount 20 `
    -EndToEndFixtureScript "test_phase6gu_marker_e2e.ps1" `
    -ExpectedEndToEndFixtureCount 5
exit $LASTEXITCODE
