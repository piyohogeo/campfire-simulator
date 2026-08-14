param([Parameter(Mandatory = $true)][string]$OutputDir)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $OutputDir) { throw "Phase 6GU E2E refuses output reuse: $OutputDir" }
New-Item -ItemType Directory -Path $OutputDir | Out-Null
$childPath = Join-Path $OutputDir "child.json"
$env:PHASE6GU_FIXTURE_REPORT = $childPath
try {
    & python (Join-Path $PSScriptRoot "test_phase6gu_marker_contract.py") *> (Join-Path $OutputDir "child.log")
    $childExit = $LASTEXITCODE
} finally {
    Remove-Item Env:PHASE6GU_FIXTURE_REPORT -ErrorAction SilentlyContinue
}
$child = Get-Content -Raw -Encoding UTF8 $childPath | ConvertFrom-Json
$state = $child.safe_stop_incremental_state
$cases = @(
    [ordered]@{name="child_exit_propagated";passed=($childExit -eq 0);observed=$childExit},
    [ordered]@{name="child_contract_passed";passed=($child.passed -and $child.actual_resource_marker_helper_called);observed=$child.case_count},
    [ordered]@{name="actual_payload_round_trip";passed=($child.actual_phase6gt_payload_shape.slot -eq 0 -and $child.actual_phase6gt_payload_shape.channel -eq "temperature" -and $child.actual_phase6gt_payload_shape.temporary_file_path);observed=$child.actual_phase6gt_payload_shape},
    [ordered]@{name="safe_stop_state_terminal";passed=($state.status -eq "safe_stop" -and $state.terminal -and $state.operation_result -eq "fixture_safe_stop");observed=$state},
    [ordered]@{name="raw_evidence_preserved_before_parent_report";passed=(Test-Path -LiteralPath $childPath);observed=$childPath}
)
$passed = @($cases | Where-Object { -not $_.passed }).Count -eq 0
$report = [ordered]@{schema="campfire.phase6gu.marker-e2e-fixture.v1";passed=$passed;case_count=$cases.Count;kit_started=$false;child_exit_code=$childExit;cases=$cases}
[IO.File]::WriteAllText((Join-Path $OutputDir "result.json"),($report|ConvertTo-Json -Depth 10)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
if (-not $passed) { throw "Phase 6GU marker E2E fixture failed" }
Write-Host "Phase 6GU marker E2E fixtures passed: $($cases.Count)/$($cases.Count)"
