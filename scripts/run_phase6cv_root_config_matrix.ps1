param(
    [string]$ArtifactsRoot = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
if (-not $ArtifactsRoot) {
    $ArtifactsRoot = Join-Path $repositoryRoot "artifacts\phase3"
}
$ArtifactsRoot = [System.IO.Path]::GetFullPath($ArtifactsRoot)
$runner = Join-Path $PSScriptRoot "run_phase6cv_settings_variant.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6cv_root_config.py"
$report = Join-Path $repositoryRoot "docs\devlog\assets\phase6\renderer_root_config_report.json"
$svg = Join-Path $repositoryRoot "docs\devlog\assets\phase6\renderer_root_config_report.svg"
$variants = @(
    "all_static",
    "lock_only",
    "static_and_lock",
    "package_only",
    "static_lock_package",
    "full_config_absolute_paths"
)

foreach ($variant in $variants) {
    $outputDir = Join-Path $ArtifactsRoot ("phase6cv-" + $variant.Replace("_", "-"))
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $runner `
        -Variant $variant `
        -OutputDir $outputDir
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

& py -3 $analyzer `
    --artifacts-root $ArtifactsRoot `
    --report $report `
    --svg $svg
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Phase 6CV root-config matrix complete: $report"
