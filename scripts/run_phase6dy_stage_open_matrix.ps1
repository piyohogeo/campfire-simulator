param(
    [string]$OutputRoot = "",
    [string]$SourceStage = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
if (-not $OutputRoot) { $OutputRoot = Join-Path $root "artifacts\phase6dy-calibrated-stage-open-1" }
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6DY refuses artifact root reuse: $OutputRoot" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null

$release = Join-Path $root "_build\windows-x86_64\release"
$kit = Join-Path $release "kit\kit.exe"
$emptyApp = Join-Path $release "kit\apps\omni.app.empty.kit"
$productionApp = Join-Path $release "apps\campfire.simulator.kit"
if (-not $SourceStage) {
    $SourceStage = Join-Path $root "artifacts\phase6dt-reference-audit-2\phase6ds_mesh_usd_mesh_collision\run-1\raw.prepared.usda"
}
$source = [IO.Path]::GetFullPath($SourceStage)
$prepareProbe = Join-Path $PSScriptRoot "prepare_phase6dy_stage_open_cases.py"
$runner = Join-Path $PSScriptRoot "run_phase6dw_gpu_renderer_case.ps1"
$preparedRoot = Join-Path $OutputRoot "prepared-stages"
$prepareReport = Join-Path $OutputRoot "prepared_stages.json"
$prepareLog = Join-Path $OutputRoot "prepare.log"
$prepareDump = Join-Path $OutputRoot "prepare-sensitive-crash-dumps"
$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Phase 6DY known-good source missing: $source" }

$prepareArgs = @(
    $emptyApp,
    "--no-window",
    "--/app/fastShutdown=0",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/phase6dy/source=$source",
    "--/phase6dy/outputRoot=$preparedRoot",
    "--/phase6dy/report=$prepareReport",
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
    throw "Phase 6DY offline preparation timed out"
}
$prepareProcess.Refresh()
$prepareFatal = @()
foreach ($token in @("[crash] A crash has occurred", "Traceback (most recent call last)", "CUDA illegal address", "device lost", "invalid pointer", "TDR")) {
    $prepareFatal += @(Select-String -LiteralPath $prepareLog -SimpleMatch $token -ErrorAction SilentlyContinue | ForEach-Object { $_.Line })
}
$prepareDumps = @(Get-CampfireCrashDumpInventory -DumpDir $prepareDump)
$prepareUploads = @(Select-String -LiteralPath $prepareLog -Pattern "upload(?:ing|ed)? (?:mini)?dump|sending crash|submit.*crash" -CaseSensitive:$false -ErrorAction SilentlyContinue)
if ($prepareProcess.ExitCode -ne 0 -or $prepareFatal.Count -or $prepareDumps.Count -or $prepareUploads.Count) {
    throw "Phase 6DY offline preparation failed safely"
}
$prepared = Get-Content -Raw -Encoding UTF8 $prepareReport | ConvertFrom-Json
if ($prepared.status -ne "ok") { throw "Phase 6DY prepared-stage gates failed" }

$cases = @(
    [ordered]@{ label="A_box_decomposition"; file="A_box_decomposition.usda" },
    [ordered]@{ label="B_box_hull"; file="B_box_hull.usda" },
    [ordered]@{ label="C_box_decomposition"; file="C_box_decomposition.usda" },
    [ordered]@{ label="D_cylinder_decomposition"; file="D_cylinder_decomposition.usda" },
    [ordered]@{ label="E_box_decomposition"; file="E_box_decomposition.usda" }
)
$completed = @()
foreach ($case in $cases) {
    $label = $case.label
    $stage = Join-Path $preparedRoot $case.file
    $output = Join-Path $OutputRoot "stage-open\$label"
    try {
        # This is the calibrated Phase 6DW runner and probe, not a reimplementation.
        & $runner -Condition box_rtx -CacheKind normal -OutputDir $output -SourceStage $stage -TimeoutSeconds 420
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
            if ($index -le $last) { throw "Phase 6DY marker order failed for $label at $marker" }
            $last = $index
        }
        $completed += $label
    } catch {
        $stop = [ordered]@{
            schema = "campfire.phase6dy.matrix-safe-stop.v1"
            phase = "phase6dy"
            status = "safe_stop"
            failed_condition = $label
            completed = @($completed)
            automatic_retry = $false
            error = $_.Exception.Message
            production_app_sha256_before = $productionHashBefore
            production_app_sha256_after = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
            timestamp_local = (Get-Date).ToString("o")
        }
        [IO.File]::WriteAllText((Join-Path $OutputRoot "matrix_safe_stop.json"), ($stop | ConvertTo-Json -Depth 10) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
        throw
    }
}

$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
if ($productionHashBefore -ne $productionHashAfter) { throw "Phase 6DY changed production app" }
$result = [ordered]@{
    schema = "campfire.phase6dy.matrix-complete.v1"
    phase = "phase6dy"
    status = "complete"
    lifecycle_implementation = "scripts/run_phase6dw_gpu_renderer_case.ps1 + scripts/probe_phase6dw_gpu_renderer_lifecycle.py"
    completed = @($completed)
    production_app_sha256_before = $productionHashBefore
    production_app_sha256_after = $productionHashAfter
    timestamp_local = (Get-Date).ToString("o")
}
[IO.File]::WriteAllText((Join-Path $OutputRoot "matrix_complete.json"), ($result | ConvertTo-Json -Depth 10) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host "Phase 6DY calibrated stage-open matrix complete: $($completed.Count) processes"
