param(
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$probe = Join-Path $PSScriptRoot "probe_plain_renderer_timeline.py"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6cx_quit_limit.py"
$scene = Join-Path $repositoryRoot "artifacts\phase3\phase6cs-minimal-camera\phase3_point_application_minimal_camera.usda"
$oldBaseline = Join-Path $repositoryRoot "artifacts\phase3\phase6ct-campfire-all-known-settings\plain_renderer_timeline_headless_campfire.json"
$report = Join-Path $repositoryRoot "docs\devlog\assets\phase6\renderer_quit_limit_report.json"
$svg = Join-Path $repositoryRoot "docs\devlog\assets\phase6\renderer_quit_limit_report.svg"
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6cx-quit-limit"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$runId = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssfffZ")
$runDir = Join-Path $OutputDir $runId
$legacyReport = Join-Path $runDir "timeline_legacy_900.json"
$legacyLog = Join-Path $runDir "legacy_900_info.log"
$safeReport = Join-Path $runDir "timeline_safe_30000.json"
$safeLog = Join-Path $runDir "safe_30000_info.log"
$isolatedReport = Join-Path $runDir "timeline_isolated_cache_30000.json"
$isolatedLog = Join-Path $runDir "isolated_cache_30000_info.log"
$isolatedCache = Join-Path $runDir "omni-cache"
New-Item -ItemType Directory -Path $runDir -Force | Out-Null

if (-not (Test-Path -LiteralPath $scene)) {
    throw "Phase 6CX scene is missing: $scene"
}
if (-not (Test-Path -LiteralPath $oldBaseline)) {
    throw "Phase 6CX historical Phase 6CT baseline is missing: $oldBaseline"
}

function Invoke-TimelineProbe(
    [string]$Label,
    [int]$FrameLimit,
    [string]$Output,
    [string]$Log,
    [string]$OmniCache = ""
) {
    $arguments = @(
        $app,
        "--no-window",
        "--/app/file/ignoreUnsavedOnExit=true",
        "--/app/quitAfter=$FrameLimit",
        "--/app/settings/persistent=0",
        "--/app/settings/loadUserConfig=0",
        "--/exts/campfire.app/autoCreateScene=false",
        "--/app/viewport/defaults/fillViewport=false",
        "--/phase6cr/scene=$scene",
        "--/phase6cr/output=$Output",
        "--/phase6cr/probeApp=$Label",
        "--/phase6cr/retryAfterStop=true",
        "--/rtx/flow/enabled=true",
        "--/log/file=$Log",
        "--/log/fileLogLevel=Info",
        "--exec",
        $probe
    )
    if ($OmniCache) {
        $arguments = @($app, "--/app/tokens/omni_cache=$OmniCache") + $arguments[1..($arguments.Count - 1)]
    }
    & $kit $arguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$productionShaBefore = (Get-FileHash -LiteralPath $app -Algorithm SHA256).Hash.ToLowerInvariant()
Invoke-TimelineProbe "phase6cx_legacy_900" 900 $legacyReport $legacyLog
Invoke-TimelineProbe "phase6cx_safe_30000" 30000 $safeReport $safeLog
Invoke-TimelineProbe "phase6cx_isolated_cache_30000" 30000 $isolatedReport $isolatedLog $isolatedCache
$productionShaAfter = (Get-FileHash -LiteralPath $app -Algorithm SHA256).Hash.ToLowerInvariant()

& py -3 $analyzer `
    --historical-baseline $oldBaseline `
    --legacy-log $legacyLog `
    --legacy-report $legacyReport `
    --safe-report $safeReport `
    --isolated-report $isolatedReport `
    --production-sha-before $productionShaBefore `
    --production-sha-after $productionShaAfter `
    --report $report `
    --svg $svg
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Phase 6CX quit-limit qualification complete: $report"
