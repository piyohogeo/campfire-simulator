param(
    [ValidateSet("float4", "rgba8")]
    [string]$Encoding = "float4",
    [ValidateSet("direct", "flow-point-cloud")]
    [string]$Container = "direct",
    [ValidateSet("direct-array", "volume-asset", "asset-attribute")]
    [string]$Source = "direct-array",
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
$benchmark = Join-Path $PSScriptRoot "benchmark_flow_nanovdb_consumer.py"

if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) {
    throw "Application is not built. Run .\repo.bat build first."
}
if (-not $Output) {
    $Output = Join-Path $repositoryRoot (
        "artifacts\phase6\phase6bt-nanovdb-consumer-{0}-{1}-{2}.json" -f $Encoding, $Container, $Source
    )
}
$Output = [System.IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Path (Split-Path -Parent $Output) -Force | Out-Null

& $kit @(
    $app,
    "--no-window",
    "--/app/quitAfter=300",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/rtx/flow/enabled=true",
    "--/phase6bt/frames=$Frames",
    "--/phase6bt/warmup=$Warmup",
    "--/phase6bt/encoding=$Encoding",
    "--/phase6bt/container=$Container",
    "--/phase6bt/source=$Source",
    "--/phase6bt/output=$Output",
    "--exec",
    $benchmark
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$report = Get-Content -LiteralPath $Output -Raw | ConvertFrom-Json
if ($report.status -ne "ok" -or $report.phase -ne "phase6bt") {
    throw "Phase 6BT report failed: $Output"
}
if ($report.revision.published -ne $report.revision.attached_consumer) {
    throw "Phase 6BT consumer revision mismatch."
}

if ($report.flow.consumer_qualified) {
    Write-Host (
        "Phase 6BT qualified: active blocks peak={0}, update p95={1} ms: {2}" -f
        $report.flow.active_blocks_peak,
        $report.flow.kit_flow_render_update.p95_ms,
        $Output
    )
} else {
    Write-Host (
        "Phase 6BT completed safely but consumer remains unqualified: active blocks peak={0}: {1}" -f
        $report.flow.active_blocks_peak,
        $Output
    )
}
