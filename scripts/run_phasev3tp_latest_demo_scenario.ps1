param(
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [Parameter(Mandatory = $true)][string]$CaptureRoot,
    [ValidateSet("CandidatePerformance")][string]$RtxVisualPreset = "CandidatePerformance",
    [ValidateRange(1, 8192)][int]$Width = 1280,
    [ValidateRange(1, 8192)][int]$Height = 720
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if ($Width -ne 1280 -or $Height -ne 720) {
    throw "Phase V3T-P latest demo currently qualifies only 1280x720."
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
$CaptureRoot = [IO.Path]::GetFullPath($CaptureRoot)
$runDir = Join-Path $CaptureRoot "phasev3tp"
$kitLog = Join-Path $runDir "kit.log"
$dumpDir = Join-Path $runDir "sensitive-crash-dumps"
New-Item -ItemType Directory -Path $CaptureRoot -Force | Out-Null

& (Join-Path $PSScriptRoot "run_phase3.ps1") `
    -OutputDir $runDir -AppKind normal -InheritProductionV3Defaults `
    -CaptureVideo -VideoFrameInterval 20 -VideoFps 5 `
    -RtxVisualPreset $RtxVisualPreset -IsolatedCrashSafety `
    -KitLog $kitLog -CrashDumpDir $dumpDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$summaryPath = Join-Path $runDir "summary.json"
$summary = Get-Content -Raw -Encoding UTF8 -LiteralPath $summaryPath | ConvertFrom-Json
$frames = @($summary.video_frames.frames)
$visual = $summary.scenario.wood_visual_v3
if (
    $summary.status -ne "ok" -or
    $summary.phase -ne "phase3" -or
    -not [bool]$visual.enabled -or
    $visual.status_after_timeline_stop.failure_count -ne 0 -or
    $visual.status_after_timeline_stop.revision -ne 1200 -or
    $visual.status_after_timeline_stop.processed_revision -ne 1200 -or
    $frames.Count -ne 60 -or
    @($summary.resolution)[0] -ne $Width -or
    @($summary.resolution)[1] -ne $Height -or
    $summary.flow.active_blocks_peak -le 0 -or
    $summary.wood.dry.mass_balance_error_kg -ne 0 -or
    $summary.wood.wet.mass_balance_error_kg -ne 0
) {
    throw "Phase V3T-P latest-demo scenario did not satisfy its production V3 contract."
}

$segments = @(
    [ordered]@{ Id = "initial"; Label = "Initial: dry and wet surfaces"; First = 1; Last = 15 },
    [ordered]@{ Id = "heating"; Label = "Dry log heats, darkens, and glows"; First = 16; Last = 35 },
    [ordered]@{ Id = "burning"; Label = "Char and emission with fire and smoke"; First = 36; Last = 60 }
)
$segmentManifests = @()
foreach ($segment in $segments) {
    $segmentDir = Join-Path $OutputDir ("frames_" + $segment.Id)
    New-Item -ItemType Directory -Path $segmentDir -Force | Out-Null
    $index = 0
    for ($frameNumber = $segment.First; $frameNumber -le $segment.Last; $frameNumber++) {
        $source = $frames[$frameNumber - 1].path
        if (-not (Test-Path -LiteralPath $source)) { throw "Missing V3 demo frame: $source" }
        Copy-Item -LiteralPath $source -Destination (Join-Path $segmentDir ("frame_{0:D4}.png" -f $index))
        $index++
    }
    $unique = @(
        Get-ChildItem -LiteralPath $segmentDir -Filter "frame_*.png" -File |
            ForEach-Object { (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash } |
            Sort-Object -Unique
    ).Count
    $segmentManifests += [ordered]@{
        id = $segment.Id
        event_label = $segment.Label
        frame_directory = $segmentDir
        frame_count = $index
        unique_frame_count = $unique
    }
}

$commit = (& git -c "safe.directory=$($root.Replace('\', '/'))" rev-parse --short HEAD).Trim()
if (-not $commit) { throw "Unable to resolve the source baseline for the demo." }
$manifest = [ordered]@{
    schema = "campfire.devlog-demo-scenario.v1"
    status = "ok"
    phase = "phasev3tp"
    scenario = "production_v3_burn"
    scenario_runner = "scripts/run_phasev3tp_latest_demo_scenario.ps1"
    source_commit = $commit
    rendering = [ordered]@{
        preset = "CandidatePerformance"
        aa_op = 3
        dlss_exec_mode = 0
        max_bounces = 2
        resolution = @($Width, $Height)
    }
    source_fps = 5
    segments = $segmentManifests
    poster_frame = Join-Path $OutputDir "frames_burning\frame_0020.png"
    kit_logs = @($kitLog)
    crash_dump_directories = @($dumpDir)
    feature_flags = [ordered]@{
        productionAppDefaultsInherited = $true
        residentSnapshotAdapterEnabled = $true
        residentNativeBackendEnabled = $true
        woodRenderHierarchyEnabled = $true
        woodVisualV3Enabled = $true
        woodVisualV0Enabled = $false
        gpuTextureTransportEnabled = $false
        rtxFlowEnabled = $true
    }
    qualification = [ordered]@{
        resident_revision = [int]$summary.scenario.resident_snapshot_adapter.status_after_timeline_stop.revision
        visual_revision = [int]$visual.status_after_timeline_stop.revision
        visual_failure_count = [int]$visual.status_after_timeline_stop.failure_count
        active_blocks_peak = [int]$summary.flow.active_blocks_peak
        dry_surface_temperature_k = [double]$summary.wood.dry.surface_mean_temperature_k
        wet_surface_temperature_k = [double]$summary.wood.wet.surface_mean_temperature_k
        dry_char_mass_kg = [double]$summary.wood.dry.char_mass_kg
        wet_remaining_moisture_kg = [double]$summary.wood.wet.moisture_mass_kg
        mass_balance_error_kg = [double]$summary.wood.dry.mass_balance_error_kg + [double]$summary.wood.wet.mass_balance_error_kg
    }
}
$manifestPath = Join-Path $OutputDir "scenario_manifest.json"
[IO.File]::WriteAllText(
    $manifestPath,
    ($manifest | ConvertTo-Json -Depth 16) + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false)
)
Write-Host "Phase V3T-P latest-demo scenario ready: $manifestPath"
