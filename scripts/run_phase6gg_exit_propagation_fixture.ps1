param([Parameter(Mandatory = $true)][string]$OutputRoot)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6GG fixture refuses output reuse" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
$powershell = (Get-Command powershell.exe).Source
& $powershell -NoProfile -NonInteractive -Command "exit 0" 1> (Join-Path $OutputRoot "exit0.stdout.log") 2> (Join-Path $OutputRoot "exit0.stderr.log")
$exit0 = $LASTEXITCODE
& $powershell -NoProfile -NonInteractive -Command "exit 7" 1> (Join-Path $OutputRoot "exit7.stdout.log") 2> (Join-Path $OutputRoot "exit7.stderr.log")
$exit7 = $LASTEXITCODE

$caseRunner = Join-Path $PSScriptRoot "run_phase6fo_supply_case.ps1"
$audit = Join-Path $OutputRoot "argument_audit.json"
& $powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $caseRunner `
    -Scenario production_four -OutputDir (Join-Path $OutputRoot "case") -ReportPhase phase6gg `
    -GeometryVariant phase6er_corrected -ExpectedGeometryConcept corrected `
    -ChannelSchemaControl baseline -ValidateArgumentsOnly -ArgumentAuditPath $audit `
    1> (Join-Path $OutputRoot "binding.stdout.log") 2> (Join-Path $OutputRoot "binding.stderr.log")
$bindingExit = $LASTEXITCODE
$binding = Get-Content -Raw -Encoding UTF8 $audit | ConvertFrom-Json
$passed = $exit0 -eq 0 -and $exit7 -eq 7 -and $bindingExit -eq 0 -and -not $binding.kit_started -and $binding.report_phase -eq "phase6gg"
$summary = [ordered]@{
    schema = "campfire.phase6gg.exit-propagation-fixture.v1"
    status = if ($passed) { "pass" } else { "fail" }
    external_exit_zero = $exit0
    external_exit_nonzero = $exit7
    binding_exit = $bindingExit
    binding_report_phase = [string]$binding.report_phase
    kit_started = [bool]$binding.kit_started
}
[IO.File]::WriteAllText((Join-Path $OutputRoot "fixture_summary.json"), ($summary | ConvertTo-Json -Depth 6) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
if (-not $passed) { throw "Phase 6GG exit propagation fixture failed" }
