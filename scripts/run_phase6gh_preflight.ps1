param([Parameter(Mandatory = $true)][string]$OutputRoot)

$ErrorActionPreference = "Stop"
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6GH preflight refuses artifact root reuse" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
$policy = Join-Path $PSScriptRoot "phase6gh_startup_replacement_policy.py"
& python $policy --fixtures --output (Join-Path $OutputRoot "startup_replacement_fixtures.json")
if ($LASTEXITCODE -ne 0) { throw "Phase 6GH startup replacement fixtures failed" }

$caseRunner = Join-Path $PSScriptRoot "run_phase6fo_supply_case.ps1"
$probe = Join-Path $PSScriptRoot "probe_phase6gd_channel_metadata.py"
$output = Join-Path $OutputRoot "binding"
& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $caseRunner `
    -Scenario production_four -OutputDir $output -OffsetM -0.0125 -SupportRadiusM 0.05 `
    -Filtering true -Collision true -Policy allow_self_center -ReportPhase phase6gh `
    -GeometryVariant phase6er_corrected -ExpectedGeometryConcept corrected -ProbePath $probe `
    -ReadbackMode p3_spatial_release -ReadbackFrames 180 -ChannelSchemaControl baseline `
    -ValidateArgumentsOnly -ArgumentAuditPath (Join-Path $output "argument_validation.json")
if ($LASTEXITCODE -ne 0) { throw "Phase 6GH real command-line binding failed" }
$audit = Get-Content -Raw -Encoding UTF8 (Join-Path $output "argument_validation.json") | ConvertFrom-Json
if ($audit.report_phase -ne "phase6gh" -or $audit.kit_started) { throw "Phase 6GH binding audit mismatch" }
$summary = [ordered]@{
    schema = "campfire.phase6gh.preflight.v1"
    status = "pass"
    policy_fixture = "startup_replacement_fixtures.json"
    command_line_fixture = "binding/argument_validation.json"
    kit_started = $false
}
[IO.File]::WriteAllText((Join-Path $OutputRoot "preflight_summary.json"), ($summary | ConvertTo-Json -Depth 6) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host "Phase 6GH preflight passed without Kit"
