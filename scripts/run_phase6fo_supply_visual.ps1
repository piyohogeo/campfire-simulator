param(
    [Parameter(Mandatory = $true)][string]$NumericRoot,
    [string]$AssetDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$repo = Split-Path -Parent $PSScriptRoot
$NumericRoot = [IO.Path]::GetFullPath($NumericRoot)
$contractPath = Join-Path $NumericRoot "frozen_contract.json"
$hashPath = Join-Path $NumericRoot "frozen_contract.sha256"
$reportPath = Join-Path $NumericRoot "supply_comparison_report.json"
if (-not (Test-Path $contractPath) -or -not (Test-Path $reportPath)) { throw "Phase 6FO numeric evidence missing" }
$expectedHash = ((Get-Content -Encoding UTF8 $hashPath | Select-Object -First 1) -split '\s+')[0].ToUpperInvariant()
if ((Get-FileHash -Algorithm SHA256 $contractPath).Hash -ne $expectedHash) { throw "Phase 6FO frozen contract changed" }
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
$numeric = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
if (-not $numeric.numeric_qualified) { throw "Phase 6FO forbids visual capture before numeric qualification" }
$visualRoot = Join-Path $NumericRoot "visual"
if (Test-Path -LiteralPath $visualRoot) { throw "Phase 6FO visual root reuse refused: $visualRoot" }
New-Item -ItemType Directory -Path $visualRoot | Out-Null
$logs = Join-Path $visualRoot "runner-logs"
New-Item -ItemType Directory -Path $logs | Out-Null
$guard = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
$caseRunner = Join-Path $PSScriptRoot "run_phase6fo_supply_case.ps1"
$powershell = (Get-Command powershell.exe).Source
$productionApp = Join-Path $repo "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$productionBefore = (Get-FileHash -Algorithm SHA256 $productionApp).Hash
$previousExitUtc = ""
foreach($condition in @("S93","S100")) {
    $spec = $contract.conditions.$condition
    $caseDir = Join-Path $visualRoot $condition
    $source = $spec.expected_source_sums
    $arguments = @(
        "-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",$caseRunner,
        "-Scenario",$contract.fixture.scenario,"-OutputDir",$caseDir,"-OffsetM","$($contract.fixture.point_offset_m)",
        "-SupportRadiusM","$($contract.fixture.support_radius_assumption_m)","-Filtering","true","-Collision","true",
        "-Policy",$spec.policy,"-ReportPhase","phase6fo","-GeometryVariant",$contract.fixture.geometry_variant,
        "-SampleFrames","60,120,359","-OperationFrames","359","-ReadbackChannels","none","-ReadbackMode","none",
        "-SynchronousMemoryMarkers","true","-PythonMemoryTelemetry","true","-SpatialCollectorsEnabled","false",
        "-RunIndex","1","-Capture","-CaptureStart","$($contract.capture.start_frame)","-CaptureEnd","$($contract.capture.end_frame)",
        "-LifecycleCalibration","-RendererDrainUpdates","8","-StageCloseTimeoutSeconds","$($contract.safety.stage_close_timeout_seconds)",
        "-FlowLivenessAudit","true","-StartupProbe","true","-StartupProbeLabel","visual_$condition",
        "-StartupFlowAcquirePosition","before_updates","-StartupPreTimelineUpdateCount","12","-StartupExtraUpdateBeforePlayCount","0",
        "-StartupLivenessGate","true","-StartupExpectedFuelSum","$($source.fuel)","-StartupExpectedTemperatureSum","$($source.temperature)",
        "-StartupExpectedSmokeSum","$($source.smoke)","-StartupSourceSumTolerance","$($contract.hard_gates.source_sum_relative_tolerance)",
        "-AbsoluteTimeoutSeconds","$($contract.safety.inner_absolute_timeout_seconds)"
    )
    if (-not [string]::IsNullOrWhiteSpace($previousExitUtc)) { $arguments += @("-PreviousProcessExitUtc",$previousExitUtc) }
    $limits=$contract.safety
    $guardArgs=@(
        $guard,"--trace",(Join-Path $logs "$condition.resource.jsonl"),"--summary",(Join-Path $logs "$condition.guard.json"),
        "--stdout",(Join-Path $logs "$condition.stdout.log"),"--stderr",(Join-Path $logs "$condition.stderr.log"),
        "--timeout-seconds","$($limits.outer_condition_timeout_seconds)","--sample-seconds","$($limits.resource_sampling_seconds)",
        "--runner-private-limit","$($limits.runner_private_limit_bytes)","--diagnostic-private-limit","$($limits.diagnostic_private_limit_bytes)",
        "--kit-private-limit","$($limits.kit_private_limit_bytes)","--tree-private-limit","$($limits.unique_tree_private_limit_bytes)",
        "--available-memory-floor","$($limits.physical_memory_floor_bytes)","--commit-headroom-floor","$($limits.commit_headroom_floor_bytes)",
        "--cpu-telemetry","--gpu-csv",(Join-Path $logs "$condition.gpu.csv"),"--gpu-sample-ms","$($limits.gpu_sampling_ms)",
        "--lifecycle-path",(Join-Path $caseDir "raw.json"),"--diagnostic-marker-path",(Join-Path $caseDir "resource_markers.jsonl"),
        "--",$powershell
    )+$arguments
    & python @guardArgs
    if($LASTEXITCODE -ne 0){throw "Phase 6FO visual $condition failed; no retry is permitted"}
    $evidence=Get-Content -Raw -Encoding UTF8 (Join-Path $caseDir "runner_evidence.json")|ConvertFrom-Json
    if($evidence.outcome.functional_status -ne "pass" -or $evidence.outcome.lifecycle_status -ne "normal_exit" -or $evidence.process_exit_code -ne 0){throw "Phase 6FO visual $condition lifecycle failed"}
    if((Get-FileHash -Algorithm SHA256 $productionApp).Hash -ne $productionBefore){throw "Phase 6FO visual changed production app"}
    $previousExitUtc=[DateTime]::UtcNow.ToString("o")
}
$asset = if([string]::IsNullOrWhiteSpace($AssetDir)){Join-Path $repo "docs\devlog\assets\phase6"}else{[IO.Path]::GetFullPath($AssetDir)}
$work=Join-Path $NumericRoot "media-work"
$manifest=Join-Path $NumericRoot "media_manifest.json"
& python (Join-Path $PSScriptRoot "build_phase6fo_supply_comparison_media.py") --root $NumericRoot --work $work --asset-dir $asset --manifest $manifest
if($LASTEXITCODE -ne 0){throw "Phase 6FO media build failed"}
Write-Host "Phase 6FO comparison media encoded; visual review is still required before latest-demo update"
