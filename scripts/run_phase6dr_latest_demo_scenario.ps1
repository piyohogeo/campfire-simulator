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
    throw "Phase 6DR latest demo currently qualifies only 1280x720."
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
$CaptureRoot = [IO.Path]::GetFullPath($CaptureRoot)
$runDir = Join-Path $CaptureRoot "phase6dr"
$reportDir = Join-Path $OutputDir "report"
New-Item -ItemType Directory -Path $CaptureRoot -Force | Out-Null

& (Join-Path $PSScriptRoot "run_phase6dr_rigid_lifecycle.ps1") `
    -OutputDir $runDir -ReportDir $reportDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$summaryPath = Join-Path $runDir "summary.json"
$summary = Get-Content -Raw -Encoding UTF8 -LiteralPath $summaryPath | ConvertFrom-Json
$rendering = $summary.scope.rendering
$demo = $summary.lifecycle.demo_capture
if (
    $summary.status -ne "ok" -or
    $summary.phase -ne "phase6dr" -or
    $rendering.preset -ne $RtxVisualPreset -or
    [int]$rendering.aa_op -ne 3 -or
    [int]$rendering.dlss_exec_mode -ne 0 -or
    [int]$rendering.max_bounces -ne 2 -or
    @($rendering.resolution)[0] -ne $Width -or
    @($rendering.resolution)[1] -ne $Height -or
    [int]$demo.pre_frame_count -ne 30 -or
    [int]$demo.post_frame_count -ne 60
) {
    throw "Phase 6DR latest-demo scenario did not satisfy its capture contract."
}

$commit = (& git -c "safe.directory=$($root.Replace('\', '/'))" rev-parse --short HEAD).Trim()
if (-not $commit) { throw "Unable to resolve the source commit for the demo." }
$manifest = [ordered]@{
    schema = "campfire.devlog-demo-scenario.v1"
    status = "ok"
    phase = "phase6dr"
    scenario = "rigid_lifecycle"
    scenario_runner = "scripts/run_phase6dr_latest_demo_scenario.ps1"
    source_commit = $commit
    rendering = $rendering
    source_fps = 10
    segments = @(
        [ordered]@{
            id = "before"
            event_label = "Before: 37 degree rigid frame"
            frame_directory = $demo.pre_frame_directory
            frame_count = [int]$demo.pre_frame_count
            unique_frame_count = [int]$demo.pre_unique_frame_count
        },
        [ordered]@{
            id = "after"
            event_label = "Refresh 53 deg, resume, recover stage"
            frame_directory = $demo.post_frame_directory
            frame_count = [int]$demo.post_frame_count
            unique_frame_count = [int]$demo.post_unique_frame_count
        }
    )
    poster_frame = Join-Path $demo.post_frame_directory "frame_0005.png"
    kit_logs = @((Join-Path $runDir "kit.log"))
    crash_dump_directories = @((Join-Path $runDir "sensitive-crash-dumps"))
    feature_flags = [ordered]@{
        residentPointApplicationEnabled = $true
        residentPointRigidLayoutEnabled = $true
        residentPointRigidLifecycleQualificationEnabled = $true
        woodVisualV3Enabled = $false
        rtxFlowEnabled = $true
    }
    qualification = [ordered]@{
        gate_count = @($summary.gates.PSObject.Properties).Count
        all_passed = -not (@($summary.gates.PSObject.Properties.Value) -contains $false)
        resident_revision = [int]$summary.publication.revisions[0]
        active_blocks_peak = [int]$summary.flow.active_blocks_peak
    }
}
$manifestPath = Join-Path $OutputDir "scenario_manifest.json"
[IO.File]::WriteAllText(
    $manifestPath,
    ($manifest | ConvertTo-Json -Depth 16) + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false)
)
Write-Host "Phase 6DR latest-demo scenario ready: $manifestPath"
