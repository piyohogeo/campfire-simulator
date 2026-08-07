param(
    [ValidateSet("sphere", "point-single", "point-per-log")]
    [string]$Layout = "point-single",
    [ValidateSet(1, 5, 10, 20)]
    [int]$LogCount = 20,
    [ValidateRange(20, 1000)]
    [int]$Frames = 120,
    [ValidateRange(1, 300)]
    [int]$Warmup = 30,
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.benchmark.kit"
$benchmark = Join-Path $PSScriptRoot "benchmark_real_flow_emitter_layout.py"

if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) {
    throw "Application is not built. Run .\repo.bat build first."
}
if (-not $Output) {
    $Output = Join-Path $repositoryRoot (
        "artifacts\phase6\phase6bp-{0}-{1:D2}.json" -f $Layout, $LogCount
    )
}
$Output = [System.IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Path (Split-Path -Parent $Output) -Force | Out-Null

& $kit @(
    $app,
    "--no-window",
    "--/app/quitAfter=600",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/rtx/flow/enabled=true",
    "--/app/viewport/grid/enabled=false",
    "--/phase6bp/layout=$Layout",
    "--/phase6bp/logCount=$LogCount",
    "--/phase6bp/frames=$Frames",
    "--/phase6bp/warmup=$Warmup",
    "--/phase6bp/output=$Output",
    "--exec",
    $benchmark
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$report = Get-Content -LiteralPath $Output -Raw | ConvertFrom-Json
if ($report.status -ne "ok" -or $report.phase -ne "phase6bp") {
    throw "Phase 6BP report failed: $Output"
}
if ($report.configuration.layout -ne $Layout -or
    $report.configuration.log_count -ne $LogCount -or
    $report.configuration.measured_frames -ne $Frames -or
    $report.configuration.warmup_frames -ne $Warmup) {
    throw "Phase 6BP report configuration mismatch."
}
if (-not $report.notice.revision_consistent_for_every_notice -or
    -not $report.equivalence.consumer_revision_consistent) {
    throw "Phase 6BP revision contract failed."
}
if ($Layout -ne "sphere" -and (
    -not $report.equivalence.usd_channels.point_counts_exact -or
    -not $report.equivalence.usd_channels.channel_sums_close
)) {
    throw "Phase 6BP Point USD equivalence failed."
}
if ($Layout -eq "sphere" -and $report.flow.active_blocks_peak -le 0) {
    throw "Phase 6BP produced no active Flow blocks."
}

if ($report.flow.active_blocks_peak -gt 0) {
    Write-Host (
        "Phase 6BP qualified {0}, logs={1}, blocks={2}, update p95={3} ms" -f
        $Layout,
        $LogCount,
        $report.flow.active_blocks_peak,
        $report.timing.kit_flow_render_update.p95_ms
    )
} else {
    Write-Host (
        "Phase 6BP completed safely but {0} remains unqualified, logs={1}, blocks=0: {2}" -f
        $Layout,
        $LogCount,
        $Output
    )
}
