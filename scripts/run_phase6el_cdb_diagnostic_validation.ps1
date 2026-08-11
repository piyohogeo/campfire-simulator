param(
    [Parameter(Mandatory = $true)][string]$OutputRoot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
$output = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $output) { throw "Phase 6EL refuses artifact root reuse: $output" }
New-Item -ItemType Directory -Path $output | Out-Null
. (Join-Path $PSScriptRoot "phase6ea_diagnostic_common.ps1")
$powershell = (Get-Process -Id $PID).Path
$fixture = Join-Path $PSScriptRoot "run_phase6el_cdb_diagnostic_fixtures.ps1"
$productionApp = Join-Path $root "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$contract = Join-Path $PSScriptRoot "phase6eg_static_pose_set_contract.json"
$productionHashBefore = (Get-FileHash -LiteralPath $productionApp -Algorithm SHA256).Hash
$contractHashBefore = (Get-FileHash -LiteralPath $contract -Algorithm SHA256).Hash
$fixtureRoot = Join-Path $output "fixtures"
$guard = Invoke-Phase6EaGuardedHelper -FilePath $powershell -ArgumentList @(
    "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
    "-File", $fixture, "-OutputRoot", $fixtureRoot
) -StdoutPath (Join-Path $output "fixture-runner.stdout.log") -StderrPath (Join-Path $output "fixture-runner.stderr.log") -TimeoutSeconds 240 -PrivateBytesLimit 512MB -MaximumStdoutBytes 2MB -MaximumStderrBytes 2MB
$productionHashAfter = (Get-FileHash -LiteralPath $productionApp -Algorithm SHA256).Hash
$contractHashAfter = (Get-FileHash -LiteralPath $contract -Algorithm SHA256).Hash
$fixtureReport = if (Test-Path -LiteralPath (Join-Path $fixtureRoot "report.json")) { Get-Content -LiteralPath (Join-Path $fixtureRoot "report.json") -Raw -Encoding UTF8 | ConvertFrom-Json } else { $null }
$status = if ($guard.exit_code -eq 0 -and -not $guard.timed_out -and -not $guard.private_bytes_exceeded -and -not $guard.output_bytes_exceeded -and $guard.process_absent -and $null -ne $fixtureReport -and $fixtureReport.status -eq "pass" -and $productionHashBefore -eq $productionHashAfter -and $contractHashBefore -eq $contractHashAfter) { "pass" } else { "fail" }
$manifest = [ordered]@{
    schema = "campfire.phase6el.cdb-diagnostic-validation.v1"
    phase = "phase6el"
    status = $status
    phase6eg_formal_restarted = $false
    fixture_guard = $guard
    fixture_report = $fixtureReport
    production_app_sha256_before = $productionHashBefore
    production_app_sha256_after = $productionHashAfter
    phase6eg_contract_sha256_before = $contractHashBefore
    phase6eg_contract_sha256_after = $contractHashAfter
}
[IO.File]::WriteAllText((Join-Path $output "run_manifest.json"), (($manifest | ConvertTo-Json -Depth 30) + [Environment]::NewLine), [Text.UTF8Encoding]::new($false))
if ($status -ne "pass") { throw "Phase 6EL CDB diagnostic validation failed" }
Write-Host "Phase 6EL CDB diagnostic validation passed; Phase 6EG remains stopped"
