param([Parameter(Mandatory = $true)][string]$OutputRoot)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$output = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $output) { throw "Phase 6FU refuses artifact root reuse: $output" }
New-Item -ItemType Directory -Path $output | Out-Null
. (Join-Path $PSScriptRoot "kit_shutdown_policy.ps1")

$contract = Join-Path $PSScriptRoot "phase6fu_diagnostic_cleanup_contract.json"
$sidecar = Join-Path $PSScriptRoot "phase6fu_diagnostic_cleanup_contract.sha256"
$expected = ((Get-Content -LiteralPath $sidecar -Encoding UTF8 | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
$actual = (Get-FileHash -LiteralPath $contract -Algorithm SHA256).Hash
if ($actual -ne $expected) { throw "Phase 6FU contract hash mismatch" }
Copy-Item -LiteralPath $contract -Destination (Join-Path $output "frozen_contract.json")
Copy-Item -LiteralPath $sidecar -Destination (Join-Path $output "frozen_contract.sha256")

$powershell = (Get-Process -Id $PID).Path
$python = (Get-Command python.exe -ErrorAction Stop | Select-Object -First 1).Source
$cdbRoot = Join-Path $output "cdb-fixtures"
$cdbGuard = Invoke-Phase6EaGuardedHelper -FilePath $powershell -ArgumentList @(
    "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
    (Join-Path $PSScriptRoot "run_phase6fr_cdb_stack_first_fixtures.ps1"), "-OutputRoot", $cdbRoot
) -StdoutPath (Join-Path $output "cdb-fixtures.stdout.log") -StderrPath (Join-Path $output "cdb-fixtures.stderr.log") -TimeoutSeconds 300 -PrivateBytesLimit 512MB -MaximumStdoutBytes 2MB -MaximumStderrBytes 2MB
$cdbReport = Read-CampfireBoundedJson -Path (Join-Path $cdbRoot "report.json")
$cdbPass = $cdbGuard.exit_code -eq 0 -and -not $cdbGuard.timed_out -and -not $cdbGuard.private_bytes_exceeded -and $cdbGuard.process_absent -and $cdbReport.status -eq "pass"
if (-not $cdbPass) { throw "Phase 6FU CDB fixture gate failed" }

$identityRoot = Join-Path $output "identity-fixtures"
$identityGuard = Invoke-Phase6EaGuardedHelper -FilePath $python -ArgumentList @(
    (Join-Path $PSScriptRoot "run_phase6fu_identity_cleanup_fixtures.py"), "--output", $identityRoot
) -StdoutPath (Join-Path $output "identity-fixtures.stdout.log") -StderrPath (Join-Path $output "identity-fixtures.stderr.log") -TimeoutSeconds 120 -PrivateBytesLimit 512MB -MaximumStdoutBytes 2MB -MaximumStderrBytes 2MB
$identityReport = Read-CampfireBoundedJson -Path (Join-Path $identityRoot "report.json")
$identityPass = $identityGuard.exit_code -eq 0 -and -not $identityGuard.timed_out -and -not $identityGuard.private_bytes_exceeded -and $identityGuard.process_absent -and $identityReport.status -eq "pass"
if (-not $identityPass) { throw "Phase 6FU identity fixture gate failed" }

# Exercise the actual outer guard: its root exits while an owned child holds a
# cleanup-suppression lock.  Cleanup must wait, then stop only the recorded
# child and commit the summary after dual-source absence confirmation.
$race = Join-Path $output "guard-race"
New-Item -ItemType Directory -Path $race | Out-Null
$lock = Join-Path $race "diagnostic.ownership.json"
$guard = Join-Path $PSScriptRoot "phase6fu_resource_guard.py"
$fixture = Join-Path $PSScriptRoot "phase6fu_process_tree_fixture.py"
& $python $guard `
    --trace (Join-Path $race "resource.jsonl") --summary (Join-Path $race "guard.json") `
    --stdout (Join-Path $race "stdout.log") --stderr (Join-Path $race "stderr.log") `
    --timeout-seconds 20 --sample-seconds 0.1 --runner-private-limit 536870912 `
    --kit-private-limit 536870912 --diagnostic-private-limit 536870912 --tree-private-limit 1073741824 `
    --available-memory-floor 1073741824 --commit-headroom-floor 1073741824 `
    --attempt-id phase6fu_guard_race --cleanup-suppression-lock $lock `
    --cleanup-suppression-deadline-seconds 3 --cleanup-marker-path (Join-Path $race "cleanup.jsonl") `
    -- $python $fixture --mode suppression-parent --ready (Join-Path $race "parent.json") `
    --child-ready (Join-Path $race "child.json") --lock $lock --seconds 120
$guardExit = $LASTEXITCODE
$guardReport = Read-CampfireBoundedJson -Path (Join-Path $race "guard.json")
$racePass = $guardExit -eq 2 -and $guardReport.cleanup_suppression.observed -and $guardReport.cleanup_suppression.released -and `
    $guardReport.observed_process_cleanup.all_matching_absent -and $guardReport.observed_process_cleanup.killed_pids.Count -ge 1
if (-not $racePass) { throw "Phase 6FU outer guard suppression fixture failed" }

$cdbRemainder = @(Get-Process cdb -ErrorAction SilentlyContinue).Count
$fixturePids = @()
foreach ($path in @((Join-Path $race "parent.json"), (Join-Path $race "child.json"))) {
    if (Test-Path -LiteralPath $path) { $fixturePids += [int](Read-CampfireBoundedJson -Path $path).pid }
}
$fixtureResidual = @($fixturePids | Where-Object { $null -ne (Get-Process -Id $_ -ErrorAction SilentlyContinue) })
$allPass = $cdbPass -and $identityPass -and $racePass -and $cdbRemainder -eq 0 -and $fixtureResidual.Count -eq 0
$report = [ordered]@{
    schema="campfire.phase6fu.diagnostic-cleanup-qualification.v1"; phase="phase6fu"
    status=if ($allPass) { "pass" } else { "fail" }; contract_sha256=$actual
    phase6ft_reclassified=$false; phase6fo_restarted=$false; memory_population_restarted=$false
    cdb=[ordered]@{ passed=$cdbPass; guard=$cdbGuard; report=$cdbReport }
    identity=[ordered]@{ passed=$identityPass; guard=$identityGuard; report=$identityReport }
    outer_guard_race=[ordered]@{ passed=$racePass; exit_code=$guardExit; report=$guardReport }
    residual=[ordered]@{ cdb=$cdbRemainder; fixture_pids=@($fixtureResidual); count=($cdbRemainder + $fixtureResidual.Count) }
    runner_peak_private_bytes=[long]$identityReport.runner_peak_private_bytes
    diagnostic_peak_private_bytes=[long](($cdbGuard.peak_private_bytes, $identityGuard.peak_private_bytes | Measure-Object -Maximum).Maximum)
    production_changed=$false; full_dump_created=$false; automatic_upload_enabled=$false
}
Write-CampfireBoundedJson -Path (Join-Path $output "qualification_report.json") -Value $report
if (-not $allPass) { throw "Phase 6FU qualification failed" }
Write-Host "Phase 6FU diagnostic and cleanup fixtures passed; no Kit population was started"
