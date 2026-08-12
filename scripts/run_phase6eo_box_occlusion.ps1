param([string]$OutputRoot = "")

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutputRoot) { $OutputRoot = Join-Path $root "artifacts\phase6eo-box-occlusion-1" }
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6EO refuses artifact root reuse: $OutputRoot" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null

$release = Join-Path $root "_build\windows-x86_64\release"
$kit = Join-Path $release "kit\kit.exe"
$emptyApp = Join-Path $release "kit\apps\omni.app.editor.base.kit"
$productionApp = Join-Path $release "apps\campfire.simulator.kit"
$contractPath = Join-Path $PSScriptRoot "phase6eo_box_occlusion_contract.json"
$contractHashPath = Join-Path $PSScriptRoot "phase6eo_box_occlusion_contract.sha256"
$prepareProbe = Join-Path $PSScriptRoot "prepare_phase6eo_box_source.py"
$flowRunner = Join-Path $PSScriptRoot "run_phase6dt_flow_collision_case.ps1"
$resourceGuard = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6eo_box_occlusion.py"
$mediaBuilder = Join-Path $PSScriptRoot "build_phase6eo_box_occlusion_media.py"
foreach ($required in @($kit,$emptyApp,$productionApp,$contractPath,$contractHashPath,$prepareProbe,$flowRunner,$resourceGuard,$analyzer,$mediaBuilder)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Phase 6EO input missing: $required" }
}
$expectedContractHash = ((Get-Content -Raw -Encoding ASCII $contractHashPath).Trim().Split(' ')[0]).ToUpperInvariant()
$contractHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($contractHash -ne $expectedContractHash) { throw "Phase 6EO contract hash mismatch" }
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
if ($contract.phase -ne "phase6eo" -or -not [bool]$contract.declared_before_formal_runs) { throw "Phase 6EO contract is not frozen" }
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "predeclared_contract.json")

$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$sourceStage = Join-Path $OutputRoot "source\phase6eo_box_source.usda"
$preflightReport = Join-Path $OutputRoot "source\preflight.json"
$preflightLog = Join-Path $OutputRoot "source\prepare.log"
$preflightDump = Join-Path $OutputRoot "source\sensitive-crash-dumps"
New-Item -ItemType Directory -Path (Split-Path -Parent $sourceStage) -Force | Out-Null
$prepareArgs = @(
    $emptyApp,"--no-window","--/app/fastShutdown=0","--/app/settings/persistent=0","--/app/settings/loadUserConfig=0",
    "--/phase6eo/sourceStage=$sourceStage","--/phase6eo/preflightReport=$preflightReport",
    "--/log/file=$preflightLog","--/log/fileLogLevel=Info",
    "--enable","omni.usd","--enable","omni.flowusd","--enable","omni.volume","--enable","omni.kit.viewport.window","--enable","omni.physx","--exec",$prepareProbe
)
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
$prepareArgs += @(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $preflightDump)
$prepare = Start-Process -FilePath $kit -ArgumentList $prepareArgs -PassThru -WindowStyle Hidden
if (-not $prepare.WaitForExit(180000)) {
    Stop-Process -Id $prepare.Id -Force -ErrorAction SilentlyContinue
    throw "Phase 6EO source preflight timed out"
}
$prepare.Refresh()
if ($prepare.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $sourceStage) -or -not (Test-Path -LiteralPath $preflightReport)) { throw "Phase 6EO source preflight failed" }
if (@(Get-CampfireCrashDumpInventory -DumpDir $preflightDump).Count) { throw "Phase 6EO source preflight produced a dump" }
$sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourceStage).Hash

$limits = [ordered]@{
    runner_private_bytes=536870912; diagnostic_private_bytes=536870912; kit_private_bytes=15032385536; tree_private_bytes=17179869184;
    available_memory_floor_bytes=8589934592; commit_headroom_floor_bytes=8589934592
}
$powershell = (Get-Process -Id $PID).Path
$outcomes = @()
$runnerLogs = Join-Path $OutputRoot "runner-logs"
New-Item -ItemType Directory -Path $runnerLogs | Out-Null
foreach ($condition in @($contract.conditions)) {
    $name = [string]$condition.name
    $caseOutput = Join-Path $OutputRoot "formal\$name"
    $spatial = Join-Path $OutputRoot "spatial\$name"
    $stdout = Join-Path $runnerLogs "$name.stdout.log"
    $stderr = Join-Path $runnerLogs "$name.stderr.log"
    $trace = Join-Path $runnerLogs "$name.memory.jsonl"
    $guardSummary = Join-Path $runnerLogs "$name.guard.json"
    $arguments = @(
        "-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",$flowRunner,
        "-Mode",([string]$condition.mode),"-SourceStage",$sourceStage,"-OutputDir",$caseOutput,"-AppKind","reference","-RunIndex","1",
        "-Capture","-CaptureStartFrame","21","-CaptureEndFrame","200","-CaptureStride","1",
        "-SpatialOutputRoot",$spatial,"-SpatialCondition",$name,"-SpatialVelocityOnly"
    )
    $guardArgs = @(
        $resourceGuard,"--trace",$trace,"--summary",$guardSummary,"--stdout",$stdout,"--stderr",$stderr,"--timeout-seconds","1200",
        "--runner-private-limit","$($limits.runner_private_bytes)","--diagnostic-private-limit","$($limits.diagnostic_private_bytes)",
        "--kit-private-limit","$($limits.kit_private_bytes)","--tree-private-limit","$($limits.tree_private_bytes)",
        "--available-memory-floor","$($limits.available_memory_floor_bytes)","--commit-headroom-floor","$($limits.commit_headroom_floor_bytes)",
        "--cpu-telemetry","--lifecycle-path",(Join-Path $caseOutput "raw.json"),
        "--diagnostic-marker-path",((Join-Path $caseOutput "sensitive-shutdown-diagnostics") + ".markers.jsonl"),"--",$powershell
    ) + $arguments
    & python @guardArgs
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $guardSummary)) { throw "Phase 6EO guard failed for $name" }
    $guard = Get-Content -Raw -Encoding UTF8 $guardSummary | ConvertFrom-Json
    $raw = Get-Content -Raw -Encoding UTF8 (Join-Path $caseOutput "raw.json") | ConvertFrom-Json
    $evidence = Get-Content -Raw -Encoding UTF8 (Join-Path $caseOutput "runner_evidence.json") | ConvertFrom-Json
    $manifest = Get-Content -Raw -Encoding UTF8 (Join-Path $spatial "manifest.json") | ConvertFrom-Json
    if ($guard.status -ne "ok" -or -not $guard.process_absent -or $guard.exit_code -ne 0) { throw "Phase 6EO resource/lifecycle guard failed for $name" }
    if ($raw.status -ne "ok" -or $raw.lifecycle_marker -ne "shutdown_complete") { throw "Phase 6EO probe failed for $name" }
    if ($evidence.outcome.functional_status -ne "pass" -or $evidence.outcome.lifecycle_status -ne "normal_exit" -or $evidence.process_exit_code -ne 0) { throw "Phase 6EO normal exit required for $name" }
    if (@($evidence.fatal_lines).Count -or @($evidence.dump_inventory).Count -or @($evidence.automatic_upload_attempt_lines).Count -or [bool]$evidence.production_changed) { throw "Phase 6EO safety evidence failed for $name" }
    if ($manifest.file_count -ne 4) { throw "Phase 6EO requires four velocity NPZ files for $name" }
    if (@($raw.captures).Count -ne 180) { throw "Phase 6EO requires 180 capture frames for $name" }
    $outcomes += [ordered]@{condition=$name; mode=$condition.mode; source_sha256=$sourceHash; lifecycle=$evidence.outcome.lifecycle_status; exit_code=$evidence.process_exit_code; active_blocks=$raw.active_blocks_final; fuel=$raw.stage_audit.emitter.fuel; captures=@($raw.captures).Count; resource_peaks=$guard.peaks; machine_minima=$guard.machine_minima}
}

$reportPath = Join-Path $OutputRoot "report.json"
$svgPath = Join-Path $OutputRoot "qualification.svg"
& python $analyzer --root $OutputRoot --contract $contractPath --output $reportPath --svg $svgPath
if ($LASTEXITCODE -ne 0) { throw "Phase 6EO numeric qualification failed; PointEmitter phase must not start" }
$mediaRoot = Join-Path $OutputRoot "media"
$mediaManifest = Join-Path $mediaRoot "media_manifest.json"
& python $mediaBuilder --root $OutputRoot --work (Join-Path $OutputRoot "media-work") --asset-dir $mediaRoot --manifest $mediaManifest
if ($LASTEXITCODE -ne 0) { throw "Phase 6EO media build failed" }

$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
if ($productionHashBefore -ne $productionHashAfter) { throw "Phase 6EO changed production app" }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash -ne $contractHash) { throw "Phase 6EO contract changed during formal run" }
$matrix = [ordered]@{schema="campfire.phase6eo.box-occlusion-matrix.v1";phase="phase6eo";status="ok";qualified=$true;contract_sha256=$contractHash;source_stage_sha256=$sourceHash;outcomes=$outcomes;report=$reportPath;media_manifest=$mediaManifest;production_app_sha256_before=$productionHashBefore;production_app_sha256_after=$productionHashAfter;production_changed=$false;previous_artifacts_overwritten=$false}
[IO.File]::WriteAllText((Join-Path $OutputRoot "matrix_complete.json"),($matrix|ConvertTo-Json -Depth 12)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
Write-Host "Phase 6EO complete: numeric Box occlusion qualified and media encoded"
