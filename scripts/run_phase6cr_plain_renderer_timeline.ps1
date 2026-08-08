param([string]$Scene = "", [string]$Output = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$probe = Join-Path $PSScriptRoot "probe_plain_renderer_timeline.py"
$kitPython = Join-Path $releaseRoot "kit\python\python.exe"
$analyzer = Join-Path $PSScriptRoot "analyze_plain_renderer_timeline.py"
if (-not $Scene) { $Scene = Join-Path $repositoryRoot "artifacts\phase3\phase6cq-renderer\scene\phase3_point_application.usda" }
if (-not $Output) { $Output = Join-Path $repositoryRoot "artifacts\phase3\phase6cr-plain-renderer\plain_renderer_timeline.json" }
$Scene = [System.IO.Path]::GetFullPath($Scene)
$Output = [System.IO.Path]::GetFullPath($Output)
if (-not (Test-Path -LiteralPath $Scene)) { throw "Phase 6CR input scene is missing: $Scene" }
New-Item -ItemType Directory -Path (Split-Path -Parent $Output) -Force | Out-Null

& $kit @(
    $app,
    "--no-window",
    "--/app/quitAfter=900",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/phase6cr/scene=$Scene",
    "--/phase6cr/output=$Output",
    "--/rtx/flow/enabled=true",
    "--exec",
    $probe
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$result = Get-Content -LiteralPath $Output -Raw | ConvertFrom-Json
if ($result.status -ne "ok") { throw "Phase 6CR plain renderer probe failed: $Output" }
$before = $result.cases | Where-Object { $_.name -eq "before_viewport_frame" }
$after = $result.cases | Where-Object { $_.name -eq "after_viewport_frame" }
$report = Join-Path $repositoryRoot "docs\devlog\assets\phase6\plain_renderer_timeline_report.json"
$svg = Join-Path $repositoryRoot "docs\devlog\assets\phase6\plain_renderer_timeline_report.svg"
& $kitPython $analyzer --raw $Output --report $report --svg $svg
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host ("Phase 6CR plain stage: beforePlay={0}, afterPlay={1}, afterStops={2}" -f $before.remained_playing, $after.remained_playing, $after.stop_event_count)
