param(
    [string]$OutputRoot = "",
    [string]$SourceStage = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
if (-not $OutputRoot) { $OutputRoot = Join-Path $root "artifacts\phase6dz-rotated-cylinder-1" }
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6DZ refuses artifact root reuse: $OutputRoot" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null

$release = Join-Path $root "_build\windows-x86_64\release"
$kit = Join-Path $release "kit\kit.exe"
$emptyApp = Join-Path $release "kit\apps\omni.app.empty.kit"
$productionApp = Join-Path $release "apps\campfire.simulator.kit"
if (-not $SourceStage) {
    $SourceStage = Join-Path $root "artifacts\phase6dy-calibrated-stage-open-1\prepared-stages\D_cylinder_decomposition.usda"
}
$source = [IO.Path]::GetFullPath($SourceStage)
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Phase 6DZ qualified Phase 6DY Cylinder is missing: $source"
}
$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$prepareProbe = Join-Path $PSScriptRoot "prepare_phase6dz_rotated_cylinder_cases.py"
$stageRunner = Join-Path $PSScriptRoot "run_phase6dw_gpu_renderer_case.ps1"
$flowRunner = Join-Path $PSScriptRoot "run_phase6dt_flow_collision_case.ps1"
$preparedRoot = Join-Path $OutputRoot "prepared-stages"
$prepareReport = Join-Path $OutputRoot "prepared_stages.json"
$prepareLog = Join-Path $OutputRoot "prepare.log"
$prepareDump = Join-Path $OutputRoot "prepare-sensitive-crash-dumps"

$prepareArgs = @(
    $emptyApp,
    "--no-window",
    "--/app/fastShutdown=0",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/phase6dz/source=$source",
    "--/phase6dz/outputRoot=$preparedRoot",
    "--/phase6dz/report=$prepareReport",
    "--/log/file=$prepareLog",
    "--/log/fileLogLevel=Info",
    "--enable", "omni.usd",
    "--exec", $prepareProbe
) + @(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $prepareDump)
$prepareProcess = Start-Process -FilePath $kit -ArgumentList $prepareArgs -PassThru -WindowStyle Hidden
if (-not $prepareProcess.WaitForExit(120000)) {
    $actual = Get-CimInstance Win32_Process -Filter "ProcessId=$($prepareProcess.Id)" -ErrorAction SilentlyContinue
    if ($null -ne $actual -and [IO.Path]::GetFullPath($actual.ExecutablePath) -eq [IO.Path]::GetFullPath($kit)) {
        Stop-Process -Id $prepareProcess.Id -Force
        $prepareProcess.WaitForExit(10000) | Out-Null
    }
    throw "Phase 6DZ offline preparation timed out"
}
$prepareProcess.Refresh()
$prepareFatal = @()
foreach ($token in @("[crash] A crash has occurred", "Traceback (most recent call last)", "CUDA illegal address", "device lost", "invalid pointer", "TDR")) {
    $prepareFatal += @(Select-String -LiteralPath $prepareLog -SimpleMatch $token -ErrorAction SilentlyContinue | ForEach-Object { $_.Line })
}
$prepareDumps = @(Get-CampfireCrashDumpInventory -DumpDir $prepareDump)
$prepareUploads = @(Select-String -LiteralPath $prepareLog -Pattern "upload(?:ing|ed)? (?:mini)?dump|sending crash|submit.*crash" -CaseSensitive:$false -ErrorAction SilentlyContinue)
if ($prepareProcess.ExitCode -ne 0 -or $prepareFatal.Count -or $prepareDumps.Count -or $prepareUploads.Count) {
    throw "Phase 6DZ offline preparation failed safely"
}
$prepared = Get-Content -Raw -Encoding UTF8 $prepareReport | ConvertFrom-Json
if ($prepared.status -ne "ok") { throw "Phase 6DZ offline rotation gates failed" }

$cases = @(
    "axis_control_start",
    "rotate_x17",
    "rotate_y12",
    "rotate_z90_log02",
    "phase6dr_z37",
    "rotate_xyz_17_12_37",
    "axis_control_end"
)

function Write-SafeStop([string]$Step, [string]$FailedCondition, [object[]]$Completed, [string]$ErrorMessage) {
    $stop = [ordered]@{
        schema = "campfire.phase6dz.matrix-safe-stop.v1"
        phase = "phase6dz"
        status = "safe_stop"
        step = $Step
        failed_condition = $FailedCondition
        completed = @($Completed)
        automatic_retry = $false
        error = $ErrorMessage
        production_app_sha256_before = $productionHashBefore
        production_app_sha256_after = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
        timestamp_local = (Get-Date).ToString("o")
    }
    [IO.File]::WriteAllText((Join-Path $OutputRoot "matrix_safe_stop.json"), ($stop | ConvertTo-Json -Depth 10) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

$stageCompleted = @()
foreach ($label in $cases) {
    $stage = Join-Path $preparedRoot "$label.usda"
    $output = Join-Path $OutputRoot "stage-open\$label"
    try {
        # Reuse the exact Phase 6DW lifecycle implementation; do not reimplement its waits.
        & $stageRunner -Condition box_rtx -CacheKind normal -OutputDir $output -SourceStage $stage -TimeoutSeconds 420
        $evidence = Get-Content -Raw -Encoding UTF8 (Join-Path $output "runner_evidence.json") | ConvertFrom-Json
        $markers = @($evidence.lifecycle_history | ForEach-Object { $_.marker })
        $required = @(
            "pure_openusd_open_complete", "renderer_readiness_complete",
            "usd_context_connection_complete", "hydra_delegate_connection_observed",
            "first_renderer_update_complete", "first_viewport_frame_started", "first_viewport_frame_complete",
            "stage_close_complete", "renderer_drain_started", "renderer_drain_complete", "shutdown_requested"
        )
        $last = -1
        foreach ($marker in $required) {
            $index = [Array]::IndexOf($markers, $marker)
            if ($index -le $last) { throw "Phase 6DZ marker order failed for $label at $marker" }
            $last = $index
        }
        $stageCompleted += $label
    } catch {
        Write-SafeStop -Step "stage_open" -FailedCondition $label -Completed $stageCompleted -ErrorMessage $_.Exception.Message
        throw
    }
}

$flowCompleted = @()
foreach ($label in $cases) {
    $stage = Join-Path $preparedRoot "$label.usda"
    $output = Join-Path $OutputRoot "flow-readback\$label"
    try {
        & $flowRunner -Mode phase6dz_rotated_mesh -SourceStage $stage -OutputDir $output -AppKind reference -RunIndex 1
        $raw = Get-Content -Raw -Encoding UTF8 (Join-Path $output "raw.json") | ConvertFrom-Json
        $scalarThreshold = 1.0e-6
        $velocityThreshold = 1.0e-5
        foreach ($sample in @($raw.samples)) {
            foreach ($channel in @("temperature", "fuel", "burn", "smoke", "velocity")) {
                $value = $sample.channels.$channel.local_rois.cylinder_inside
                if (-not $value.available) { throw "Phase 6DZ local ROI unavailable: $label frame $($sample.frame) $channel" }
                $threshold = if ($channel -eq "velocity") { $velocityThreshold } else { $scalarThreshold }
                if ([double]$value.maximum -gt $threshold) {
                    throw "Phase 6DZ interior threshold exceeded: $label frame $($sample.frame) $channel=$($value.maximum) > $threshold"
                }
            }
        }
        $flowCompleted += $label
    } catch {
        Write-SafeStop -Step "flow_readback" -FailedCondition $label -Completed $flowCompleted -ErrorMessage $_.Exception.Message
        throw
    }
}

$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
if ($productionHashBefore -ne $productionHashAfter) { throw "Phase 6DZ changed production app" }
$result = [ordered]@{
    schema = "campfire.phase6dz.matrix-complete.v1"
    phase = "phase6dz"
    status = "complete"
    lifecycle_implementation = "scripts/run_phase6dw_gpu_renderer_case.ps1 + scripts/probe_phase6dw_gpu_renderer_lifecycle.py"
    stage_open_completed = @($stageCompleted)
    flow_readback_completed = @($flowCompleted)
    local_roi_contract = "inverse world transform into analytic local Cylinder volume"
    scalar_noise_threshold = 1.0e-6
    velocity_noise_threshold_m_s = 1.0e-5
    production_app_sha256_before = $productionHashBefore
    production_app_sha256_after = $productionHashAfter
    timestamp_local = (Get-Date).ToString("o")
}
[IO.File]::WriteAllText((Join-Path $OutputRoot "matrix_complete.json"), ($result | ConvertTo-Json -Depth 10) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host "Phase 6DZ rotated Cylinder matrix complete: $($stageCompleted.Count) stage-open + $($flowCompleted.Count) readback processes"
