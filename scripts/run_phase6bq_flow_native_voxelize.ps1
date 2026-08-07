param(
    [ValidateSet(1, 5, 10, 20)]
    [int]$LogCount = 20,
    [ValidateRange(20, 1000)]
    [int]$Frames = 120,
    [ValidateRange(1, 300)]
    [int]$Warmup = 30,
    [ValidateRange(0.001, 1.0)]
    [double]$CellSize = 0.025,
    [ValidateRange(1, 1048576)]
    [int]$MaxBlocks = 256,
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.benchmark.kit"
$benchmark = Join-Path $PSScriptRoot "benchmark_flow_native_voxelize.py"

if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) {
    throw "Application is not built. Run .\repo.bat build first."
}
if (-not $Output) {
    $Output = Join-Path $repositoryRoot (
        "artifacts\phase6\phase6bq-native-voxelize-{0:D2}.json" -f $LogCount
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
    "--/phase6bq/logCount=$LogCount",
    "--/phase6bq/frames=$Frames",
    "--/phase6bq/warmup=$Warmup",
    "--/phase6bq/cellSize=$CellSize",
    "--/phase6bq/maxBlocks=$MaxBlocks",
    "--/phase6bq/output=$Output",
    "--exec",
    $benchmark
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$report = Get-Content -LiteralPath $Output -Raw | ConvertFrom-Json
if ($report.status -ne "ok" -or $report.phase -ne "phase6bq") {
    throw "Phase 6BQ report failed: $Output"
}
if ($report.configuration.log_count -ne $LogCount -or
    $report.configuration.measured_frames -ne $Frames -or
    $report.configuration.warmup_frames -ne $Warmup) {
    throw "Phase 6BQ report configuration mismatch."
}
if ($report.output.buffer_count -ne 5 -or $report.output.bytes_maximum -le 0) {
    throw "Phase 6BQ produced no NanoVDB payload."
}

Write-Host (
    "Phase 6BQ logs={0}, points={1}, output={2} bytes, voxelize p95={3} ms" -f
    $LogCount,
    $report.configuration.point_count,
    $report.output.bytes_maximum,
    $report.timing.python_cpp_gpu_voxelize_nanovdb_sync.p95_ms
)
