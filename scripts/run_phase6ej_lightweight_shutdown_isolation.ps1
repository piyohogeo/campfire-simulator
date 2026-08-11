param(
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [string]$P0Stage = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
$output = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $output) { throw "Phase 6EJ refuses artifact root reuse: $output" }
New-Item -ItemType Directory -Path $output | Out-Null
$productionApp = Join-Path $root "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$contract = Join-Path $PSScriptRoot "phase6eg_static_pose_set_contract.json"
$guardScript = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
$fixtureRunner = Join-Path $PSScriptRoot "run_phase6ej_shutdown_diagnostic_fixtures.ps1"
$resourceFixture = Join-Path $PSScriptRoot "phase6eg_resource_guard_fixture.ps1"
$normalKitRunner = Join-Path $PSScriptRoot "run_phase6dw_gpu_renderer_case.ps1"
$flowRunner = Join-Path $PSScriptRoot "run_phase6dt_flow_collision_case.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6ej_lightweight_shutdown_isolation.py"
$powershell = (Get-Process -Id $PID).Path
if (-not $P0Stage) { $P0Stage = Join-Path $root "artifacts\phase6eg-static-pose-qualification-3\prepared-stages\P0_identity.usda" }
$P0Stage = [IO.Path]::GetFullPath($P0Stage)
foreach ($path in @($productionApp, $contract, $guardScript, $fixtureRunner, $resourceFixture, $normalKitRunner, $flowRunner, $analyzer, $P0Stage)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Phase 6EJ input missing: $path" }
}
$productionHashBefore = (Get-FileHash -LiteralPath $productionApp -Algorithm SHA256).Hash
$contractHashBefore = (Get-FileHash -LiteralPath $contract -Algorithm SHA256).Hash
$limits = [ordered]@{
    runner = 536870912
    kit = 15032385536
    diagnostic = 536870912
    tree = 17179869184
    available = 8589934592
    commit = 8589934592
}

function Write-SafeStop([string]$Step, [string]$Message) {
    $payload = [ordered]@{
        schema = "campfire.phase6ej.safe-stop.v1"
        phase = "phase6ej"
        status = "safe_stop"
        step = $Step
        error = $Message
        phase6eg_formal_restarted = $false
        automatic_retry = $false
        production_app_sha256_before = $productionHashBefore
        production_app_sha256_after = (Get-FileHash -LiteralPath $productionApp -Algorithm SHA256).Hash
        contract_sha256_before = $contractHashBefore
        contract_sha256_after = (Get-FileHash -LiteralPath $contract -Algorithm SHA256).Hash
    }
    [IO.File]::WriteAllText((Join-Path $output "safe_stop.json"), (($payload | ConvertTo-Json -Depth 8) + [Environment]::NewLine), [Text.UTF8Encoding]::new($false))
}

function Invoke-GuardedCase {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Command,
        [int]$TimeoutSeconds = 120,
        [switch]$CpuTelemetry,
        [string]$LifecyclePath = "",
        [string]$DiagnosticMarkerPath = ""
    )
    $dir = Join-Path $output $Name
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    $arguments = @(
        $guardScript,
        "--trace", (Join-Path $dir "memory.jsonl"),
        "--summary", (Join-Path $dir "guard.json"),
        "--stdout", (Join-Path $dir "stdout.log"),
        "--stderr", (Join-Path $dir "stderr.log"),
        "--timeout-seconds", [string]$TimeoutSeconds,
        "--runner-private-limit", [string]$limits.runner,
        "--kit-private-limit", [string]$limits.kit,
        "--diagnostic-private-limit", [string]$limits.diagnostic,
        "--tree-private-limit", [string]$limits.tree,
        "--available-memory-floor", [string]$limits.available,
        "--commit-headroom-floor", [string]$limits.commit
    )
    if ($CpuTelemetry) { $arguments += "--cpu-telemetry" }
    if ($LifecyclePath) { $arguments += @("--lifecycle-path", $LifecyclePath) }
    if ($DiagnosticMarkerPath) { $arguments += @("--diagnostic-marker-path", $DiagnosticMarkerPath) }
    $arguments += @("--") + $Command
    & python @arguments
    $launcherExit = $LASTEXITCODE
    $summaryPath = Join-Path $dir "guard.json"
    if (-not (Test-Path -LiteralPath $summaryPath -PathType Leaf)) { throw "resource guard omitted summary for $Name" }
    $summary = Get-Content -LiteralPath $summaryPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($launcherExit -ne 0 -or $summary.status -ne "ok" -or -not $summary.process_absent) {
        throw "guarded case $Name failed: status=$($summary.status) reason=$($summary.stop_reason) exit=$($summary.exit_code)"
    }
    return $summary
}

$step = "diagnostic_child_fixtures"
try {
    $fixtureRoot = Join-Path $output "diagnostic-fixtures"
    $fixtureGuard = Invoke-GuardedCase -Name "diagnostic-fixture-guard" -TimeoutSeconds 90 -CpuTelemetry -Command @(
        $powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $fixtureRunner, "-OutputRoot", $fixtureRoot
    )

    $step = "known_normal_kit"
    $normalCase = Join-Path $output "known-normal-kit\case"
    $normal = Invoke-GuardedCase -Name "known-normal-kit-guard" -TimeoutSeconds 120 -CpuTelemetry -LifecyclePath (Join-Path $normalCase "raw.json") -DiagnosticMarkerPath ((Join-Path $normalCase "sensitive-shutdown-diagnostics") + ".markers.jsonl") -Command @(
        $powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $normalKitRunner,
        "-Condition", "kit_only", "-CacheKind", "normal", "-OutputDir", $normalCase, "-TimeoutSeconds", "90", "-ShutdownGraceSeconds", "10"
    )

    $step = "telemetry_off_on"
    $telemetry = @()
    foreach ($run in 1..3) {
        foreach ($enabled in @($false, $true)) {
            $label = "telemetry-" + ($(if ($enabled) { "on" } else { "off" })) + "-run-$run"
            $marker = Join-Path $output "$label\fixture.markers.jsonl"
            $summary = Invoke-GuardedCase -Name $label -TimeoutSeconds 30 -CpuTelemetry:$enabled -Command @(
                $powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $resourceFixture,
                "-Mode", "tree", "-MarkerPath", $marker, "-HoldMilliseconds", "2500"
            )
            $telemetry += [ordered]@{ enabled=$enabled; run=$run; summary=$summary }
        }
    }

    $step = "p0_equivalent_probe"
    $p0Case = Join-Path $output "p0-equivalent\case"
    $p0Spatial = Join-Path $output "p0-equivalent\spatial"
    $p0 = Invoke-GuardedCase -Name "p0-equivalent-guard" -TimeoutSeconds 720 -CpuTelemetry -LifecyclePath (Join-Path $p0Case "raw.json") -DiagnosticMarkerPath ((Join-Path $p0Case "sensitive-shutdown-diagnostics") + ".markers.jsonl") -Command @(
        $powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $flowRunner,
        "-Mode", "phase6ec_rotated_mesh", "-SourceStage", $P0Stage, "-OutputDir", $p0Case,
        "-AppKind", "reference", "-RunIndex", "1", "-SpatialOutputRoot", $p0Spatial,
        "-SpatialCondition", "P0_identity_on", "-SpatialVelocityOnly"
    )

    $manifest = [ordered]@{
        schema = "campfire.phase6ej.run-manifest.v1"
        phase = "phase6ej"
        status = "complete"
        phase6eg_formal_restarted = $false
        frozen_contract_sha256 = $contractHashBefore
        p0_stage = $P0Stage
        p0_stage_sha256 = (Get-FileHash -LiteralPath $P0Stage -Algorithm SHA256).Hash
        limits = $limits
        diagnostic_fixture_guard = $fixtureGuard
        known_normal_guard = $normal
        telemetry_comparison = $telemetry
        p0_guard = $p0
        production_app_sha256_before = $productionHashBefore
        production_app_sha256_after = (Get-FileHash -LiteralPath $productionApp -Algorithm SHA256).Hash
        contract_sha256_after = (Get-FileHash -LiteralPath $contract -Algorithm SHA256).Hash
    }
    [IO.File]::WriteAllText((Join-Path $output "run_manifest.json"), (($manifest | ConvertTo-Json -Depth 20) + [Environment]::NewLine), [Text.UTF8Encoding]::new($false))
    & python $analyzer --root $output --output (Join-Path $output "report.json")
    if ($LASTEXITCODE -ne 0) { throw "Phase 6EJ analyzer rejected the probe" }
} catch {
    Write-SafeStop -Step $step -Message $_.Exception.Message
    throw
}

if ((Get-FileHash -LiteralPath $productionApp -Algorithm SHA256).Hash -ne $productionHashBefore) { throw "Phase 6EJ changed production app" }
if ((Get-FileHash -LiteralPath $contract -Algorithm SHA256).Hash -ne $contractHashBefore) { throw "Phase 6EJ changed frozen Phase 6EG contract" }
Write-Host "Phase 6EJ diagnostic isolation complete; Phase 6EG formal matrix remains stopped"
