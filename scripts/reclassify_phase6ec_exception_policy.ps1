param(
    [string]$SourceRoot = "",
    [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "kit_shutdown_policy.ps1")
if (-not $SourceRoot) { $SourceRoot = Join-Path $root "artifacts\phase6ec-static-rotation-1\formal\A_axis_on" }
if (-not $OutputRoot) { $OutputRoot = Join-Path $root "artifacts\phase6eb-exception-policy-correction-1" }
$source = [IO.Path]::GetFullPath($SourceRoot)
$output = [IO.Path]::GetFullPath($OutputRoot)
if (-not (Test-Path -LiteralPath $source -PathType Container)) { throw "Phase 6EC condition A artifact is missing: $source" }
if (Test-Path -LiteralPath $output) { throw "Phase 6EB correction refuses output reuse: $output" }
New-Item -ItemType Directory -Path $output | Out-Null

$logPath = Join-Path $source "kit.log"
$rawPath = Join-Path $source "raw.json"
$evidencePath = Join-Path $source "runner_evidence.json"
$sourceFiles = @($logPath, $rawPath, $evidencePath)
foreach ($path in $sourceFiles) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required Phase 6EC artifact is missing: $path" }
}
$sourceHashesBefore = [ordered]@{}
foreach ($path in $sourceFiles) { $sourceHashesBefore[[IO.Path]::GetFileName($path)] = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash }

$probeReport = Get-Content -LiteralPath $rawPath -Raw -Encoding UTF8 | ConvertFrom-Json
$runnerEvidence = Get-Content -LiteralPath $evidencePath -Raw -Encoding UTF8 | ConvertFrom-Json
$monitor = $runnerEvidence.shutdown_monitor
$exceptionEvidence = Get-CampfireWindowsExceptionEvidence -Path $logPath
$outcome = Invoke-CampfireShutdownOutcomeClassification `
    -Monitor $monitor `
    -ProbeReport $probeReport `
    -LogPath $logPath `
    -FatalLines @($runnerEvidence.fatal_lines) `
    -DumpCount @($runnerEvidence.dump_inventory).Count `
    -UploadAttemptCount @($runnerEvidence.automatic_upload_attempt_lines).Count `
    -ProductionHashBefore $runnerEvidence.production_app_sha256_before `
    -ProductionHashAfter $runnerEvidence.production_app_sha256_after `
    -OutputDir $output

$classificationInput = Get-Content -LiteralPath (Join-Path $output "shutdown_classification_input.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$productionApp = Join-Path $root "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionHashCurrent = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$sourceHashesAfter = [ordered]@{}
foreach ($path in $sourceFiles) { $sourceHashesAfter[[IO.Path]::GetFileName($path)] = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash }
$sourceUnchanged = (($sourceHashesBefore | ConvertTo-Json -Compress) -eq ($sourceHashesAfter | ConvertTo-Json -Compress))
$subsystemLines = @(Select-String -LiteralPath $logPath -SimpleMatch "Sub System Id                                  : 0xC75C1462" -Encoding UTF8)
$gates = [ordered]@{
    source_artifacts_unchanged = $sourceUnchanged
    exception_evidence_available = [bool]$exceptionEvidence.available
    windows_exception_absent = -not [bool]$exceptionEvidence.windows_exception_present
    access_violation_absent = -not [bool]$exceptionEvidence.access_violation_present
    no_windows_exception_true = [bool]$classificationInput.safety.no_windows_exception
    monitor_fault_module_cleared = ($null -eq $classificationInput.process.fault_module)
    monitor_fault_offset_cleared = ($null -eq $classificationInput.process.fault_offset)
    functional_pass = ($outcome.functional_status -eq "pass")
    lifecycle_normal_exit = ($outcome.lifecycle_status -eq "normal_exit")
    performance_sample_accepted = [bool]$outcome.performance_sample_accepted
    os_process_normal_exit = [bool]$outcome.os_process_normal_exit
    production_hash_matches_recorded = ($productionHashCurrent -eq $runnerEvidence.production_app_sha256_before -and $productionHashCurrent -eq $runnerEvidence.production_app_sha256_after)
    subsystem_identifier_observed = ($subsystemLines.Count -eq 1)
}
$summary = [ordered]@{
    schema = "campfire.phase6eb.windows-exception-policy-correction.v1"
    phase = "phase6eb-policy-correction"
    source = "artifacts/phase6ec-static-rotation-1/formal/A_axis_on"
    mode = "read-only offline reclassification"
    kit_or_flow_started = $false
    original_outcome = $runnerEvidence.outcome
    exception_evidence = $exceptionEvidence
    corrected_input = [ordered]@{
        windows_exception_present = $classificationInput.process.windows_exception_present
        windows_exception_evidence_available = $classificationInput.process.windows_exception_evidence_available
        fault_module = $classificationInput.process.fault_module
        fault_offset = $classificationInput.process.fault_offset
        no_windows_exception = $classificationInput.safety.no_windows_exception
    }
    corrected_outcome = $outcome
    observed_negative_line = "Sub System Id : 0xC75C1462"
    source_hashes_before = $sourceHashesBefore
    source_hashes_after = $sourceHashesAfter
    production_app_sha256 = $productionHashCurrent
    gates = $gates
    qualified = -not ($gates.Values -contains $false)
    phase6ec_restarted = $false
    restart_contract = "start Phase 6EC from condition A in a new artifact root only after this correction is committed"
}
[IO.File]::WriteAllText((Join-Path $output "offline_reclassification.json"), ($summary | ConvertTo-Json -Depth 20) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
if (-not $summary.qualified) { throw "Phase 6EB exception-policy correction offline reclassification failed" }
Write-Host "Phase 6EC condition A reclassified offline: normal_exit; source artifacts unchanged"
