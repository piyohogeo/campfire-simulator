param([Parameter(Mandatory = $true)][string]$OutputRoot)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6GF fixture refuses output reuse" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
$caseRunner = Join-Path $PSScriptRoot "run_phase6fo_supply_case.ps1"
$caseRoot = Join-Path $OutputRoot "case"
$audit = Join-Path $OutputRoot "argument_audit.json"
& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $caseRunner `
    -Scenario production_four -OutputDir $caseRoot -ReportPhase phase6gf `
    -GeometryVariant phase6er_corrected -ExpectedGeometryConcept corrected `
    -ChannelSchemaControl baseline -ValidateArgumentsOnly -ArgumentAuditPath $audit
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $audit)) { throw "Phase 6GF real parameter-binding fixture failed" }
$evidence = Get-Content -Raw -Encoding UTF8 $audit | ConvertFrom-Json
if ($evidence.kit_started -or $evidence.report_phase -ne "phase6gf") { throw "Phase 6GF parameter-binding audit mismatch" }
$summary = [ordered]@{
    schema = "campfire.phase6gf.parameter-binding-fixture.v1"
    status = "pass"
    report_phase = [string]$evidence.report_phase
    kit_started = [bool]$evidence.kit_started
    runner_path = $caseRunner
    audit_path = $audit
    audit_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $audit).Hash
}
[IO.File]::WriteAllText((Join-Path $OutputRoot "fixture_summary.json"), ($summary | ConvertTo-Json -Depth 6) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
