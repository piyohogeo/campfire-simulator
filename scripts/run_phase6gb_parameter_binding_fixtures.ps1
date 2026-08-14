param(
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [Parameter(Mandatory = $true)][string]$ContractPath,
    [Parameter(Mandatory = $true)][string]$ProbePath
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6GB parameter fixture refuses output reuse: $OutputRoot" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
$contract = Get-Content -Raw -Encoding UTF8 ([IO.Path]::GetFullPath($ContractPath)) | ConvertFrom-Json
$phase = if ($contract.phase) { [string]$contract.phase } else { "phase6gb" }
if ($phase -notin @("phase6gb", "phase6gc", "phase6gl")) { throw "Unsupported geometry-binding fixture phase: $phase" }
$mapping = $contract.fixture.geometry
if ($mapping.concept -ne "corrected" -or $mapping.runtime_token -ne "phase6er_corrected") {
    throw "Phase 6GB contract geometry mapping is not the frozen corrected mapping."
}
if ($mapping.runtime_token -eq $mapping.legacy_runtime_token) {
    throw "Phase 6GB corrected geometry maps to the legacy runtime token."
}

$caseRunner = Join-Path $PSScriptRoot "run_phase6fo_supply_case.ps1"
$powershell = (Get-Command powershell.exe).Source
$positive = $contract.conditions.S93
$source = $positive.expected_source_sums
$baseArguments = @(
    "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $caseRunner,
    "-Scenario", $contract.fixture.scenario,
    "-OffsetM", "$($contract.fixture.point_offset_m)",
    "-SupportRadiusM", "$($contract.fixture.support_radius_assumption_m)",
    "-Filtering", "true", "-Collision", "true", "-Policy", $positive.policy,
    "-ReportPhase", $phase, "-GeometryVariant", $mapping.runtime_token,
    "-ExpectedGeometryConcept", $mapping.concept,
    "-ProbePath", ([IO.Path]::GetFullPath($ProbePath)),
    "-SampleFrames", ($contract.sample_frames -join ','),
    "-OperationFrames", ($contract.readback_frames -join ','),
    "-ReadbackFrames", ($contract.readback_frames -join ','),
    "-ReadbackChannels", ($contract.spatial.required_channels -join ','),
    "-ReadbackMode", "p3_spatial_release", "-ReferenceDisposal", "del",
    "-SynchronousMemoryMarkers", "true", "-PythonMemoryTelemetry", "true",
    "-SpatialCollectorsEnabled", "true", "-SpatialColliderIndices", ($contract.spatial.all_collider_indices -join ','),
    "-SpatialAllChannels", "-RunIndex", "1", "-LifecycleCalibration", "-RendererDrainUpdates", "8",
    "-LifecycleReferenceReleaseOrder", "after_stage_close",
    "-StageCloseTimeoutSeconds", "$($contract.safety.stage_close_timeout_seconds)",
    "-FlowLivenessAudit", "true", "-StartupProbe", "true", "-StartupProbeLabel", "phase6gb_binding_fixture",
    "-StartupLivenessGate", "true", "-StartupExpectedFuelSum", "$($source.fuel)",
    "-StartupExpectedTemperatureSum", "$($source.temperature)", "-StartupExpectedSmokeSum", "$($source.smoke)",
    "-StartupSourceSumTolerance", "$($contract.channel_preflight.startup_source_sum_absolute_tolerance)",
    "-StartupSourceContractMode", $(if($phase -eq "phase6gc"){[string]$contract.source_contract.mode}else{"decimal_legacy"}),
    "-AbsoluteTimeoutSeconds", "$($contract.safety.inner_absolute_timeout_seconds)",
    "-ValidateArgumentsOnly"
)

function Invoke-BindingCase([string]$Name, [string]$GeometryToken, [bool]$ExpectedPass) {
    $root = Join-Path $OutputRoot $Name
    New-Item -ItemType Directory -Path $root | Out-Null
    $caseOutput = Join-Path $root "case-output"
    $audit = Join-Path $root "argument_audit.json"
    $stdout = Join-Path $root "stdout.log"
    $stderr = Join-Path $root "stderr.log"
    $arguments = @($baseArguments)
    $geometryIndex = [Array]::IndexOf($arguments, "-GeometryVariant")
    $arguments[$geometryIndex + 1] = $GeometryToken
    $arguments += @("-OutputDir", $caseOutput, "-ArgumentAuditPath", $audit)
    $beforeKit = @(Get-Process -Name kit -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
    $process = Start-Process -FilePath $powershell -ArgumentList $arguments -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    if (-not $process.WaitForExit(30000)) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        throw "Phase 6GB binding fixture '$Name' timed out."
    }
    $process.WaitForExit()
    $process.Refresh()
    $exitCode = [int]$process.ExitCode
    $afterKit = @(Get-Process -Name kit -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
    $newKit = @($afterKit | Where-Object { $_ -notin $beforeKit })
    $stderrBytes = if (Test-Path -LiteralPath $stderr) { (Get-Item -LiteralPath $stderr).Length } else { 0 }
    if ($stderrBytes -gt 65536) { throw "Phase 6GB binding fixture '$Name' stderr exceeded 64 KiB." }
    $rejected = (-not (Test-Path -LiteralPath $audit)) -and $stderrBytes -gt 0
    $passed = if ($ExpectedPass) { $exitCode -eq 0 -and (Test-Path -LiteralPath $audit) } else { $rejected }
    $auditValue = if (Test-Path -LiteralPath $audit) { Get-Content -Raw -Encoding UTF8 $audit | ConvertFrom-Json } else { $null }
    if ($ExpectedPass) {
        $passed = $passed -and $auditValue.kit_started -eq $false -and $auditValue.geometry_concept -eq "corrected" -and $auditValue.geometry_runtime_token -eq "phase6er_corrected"
    }
    $passed = $passed -and $newKit.Count -eq 0
    return [ordered]@{
        name = $Name
        expected_pass = $ExpectedPass
        geometry_concept = "corrected"
        geometry_runtime_token = $GeometryToken
        runner_path = [IO.Path]::GetFullPath($caseRunner)
        powershell_argument_count = $arguments.Count
        powershell_arguments = $arguments
        exit_code = $exitCode
        parameter_binding_or_mapping_rejected = [bool]$rejected
        stderr_bytes = $stderrBytes
        audit_path = $audit
        audit_written = (Test-Path -LiteralPath $audit)
        kit_processes_started = $newKit.Count
        passed = [bool]$passed
    }
}

$results = @(
    Invoke-BindingCase "positive_corrected_mapping" "phase6er_corrected" $true
    Invoke-BindingCase "negative_direct_concept_token" "corrected" $false
    Invoke-BindingCase "negative_unknown_runtime_token" "unknown_geometry" $false
    Invoke-BindingCase "negative_legacy_misroute" "legacy_phase6ep" $false
)
$report = [ordered]@{
    schema = "campfire.$phase.parameter-binding-fixture-report.v1"
    phase = $phase
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
    contract_path = [IO.Path]::GetFullPath($ContractPath)
    contract_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $ContractPath).Hash
    no_kit_launch = (@($results | Where-Object { $_.kit_processes_started -ne 0 }).Count -eq 0)
    passed = (@($results | Where-Object { -not $_.passed }).Count -eq 0)
    results = $results
}
$reportText = $report | ConvertTo-Json -Depth 12
if ([Text.Encoding]::UTF8.GetByteCount($reportText) -gt 1048576) { throw "Phase 6GB fixture report exceeded 1 MiB." }
$reportPath = Join-Path $OutputRoot "parameter_binding_fixture_report.json"
[IO.File]::WriteAllText($reportPath, $reportText + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
if (-not $report.passed) { throw "Phase 6GB parameter-binding fixture failed." }
Write-Host "Phase 6GB parameter-binding fixture passed: 4/4"
