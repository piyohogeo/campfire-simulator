param(
    [string]$ArtifactsRoot = "",
    [switch]$WindowedProbe
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
if (-not $ArtifactsRoot) {
    $ArtifactsRoot = Join-Path $repositoryRoot "artifacts\phase3"
}
$ArtifactsRoot = [System.IO.Path]::GetFullPath($ArtifactsRoot)
$runner = Join-Path $PSScriptRoot "run_phase6cu_app_variant.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6cu_app_variants.py"
$report = Join-Path $repositoryRoot "docs\devlog\assets\phase6\renderer_app_initialization_report.json"
$svg = Join-Path $repositoryRoot "docs\devlog\assets\phase6\renderer_app_initialization_report.svg"
$variants = @(
    "editor_declared_head",
    "editor_declared_tail",
    "campfire_editor_order",
    "campfire_editor_order_window_extensions"
)

foreach ($variant in $variants) {
    $outputDir = Join-Path $ArtifactsRoot ("phase6cu-" + $variant.Replace("_", "-"))
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $runner,
        "-Variant", $variant,
        "-OutputDir", $outputDir
    )
    if ($WindowedProbe) { $arguments += "-WindowedProbe" }
    & powershell.exe $arguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

& py -3 $analyzer `
    --artifacts-root $ArtifactsRoot `
    --report $report `
    --svg $svg
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Phase 6CU app matrix complete: $report"
