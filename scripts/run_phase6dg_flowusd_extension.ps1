param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$probe = Join-Path $PSScriptRoot "probe_phase6dg_flowusd_extension.py"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6dg_flowusd_extension.py"
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6dg-flowusd-extension"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$output = Join-Path $OutputDir "extension_boundary.json"
$log = Join-Path $OutputDir "phase6dg.log"
$report = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_flowusd_extension_report.json"
$svg = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_flowusd_extension_report.svg"

if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) {
    throw "Application is not built."
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
foreach ($path in @($output, $log)) {
    Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
}

$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $app).Hash
& $kit @(
    $app,
    "--no-window",
    "--/app/file/ignoreUnsavedOnExit=true",
    "--/app/quitAfter=30000",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/renderer/enabled=false",
    "--/phase6dg/output=$output",
    "--/log/file=$log",
    "--/log/fileLogLevel=Info",
    "--exec",
    $probe
)
$kitExitCode = $LASTEXITCODE
$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $app).Hash
if ($productionHashBefore -ne $productionHashAfter) {
    throw "Phase 6DG changed the production app file."
}
if (-not (Test-Path -LiteralPath $output)) {
    throw "Phase 6DG extension report is missing."
}
$result = Get-Content -LiteralPath $output -Raw | ConvertFrom-Json
if ($kitExitCode -ne 0 -or $result.status -ne "ok") {
    throw "Phase 6DG probe failed: Kit=$kitExitCode status=$($result.status) error=$($result.error)"
}

$manifest = [ordered]@{
    schema_version = 1
    phase = "phase6dg"
    status = "ok"
    extension_boundary = $output
    kit_exit_code = $kitExitCode
    production_app_sha256_before = $productionHashBefore
    production_app_sha256_after = $productionHashAfter
    production_changed = ($productionHashBefore -ne $productionHashAfter)
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputDir "manifest.json") -Encoding utf8
$python = Join-Path $releaseRoot "kit\python\python.exe"
$flowExtension = Get-ChildItem -LiteralPath (Join-Path $releaseRoot "extscache") -Directory |
    Where-Object { $_.Name -like "omni.flowusd-110.0.0*" } |
    Select-Object -First 1
if (-not $flowExtension) {
    throw "Pinned omni.flowusd 110.0.0 extension was not found."
}
& $python $analyzer `
    --runtime $output `
    --manifest (Join-Path $OutputDir "manifest.json") `
    --app-config (Join-Path $repositoryRoot "source\apps\campfire.simulator.kit") `
    --extension-config (Join-Path $repositoryRoot "source\extensions\campfire.app\config\extension.toml") `
    --flow-config (Join-Path $flowExtension.FullName "config\extension.toml") `
    --report $report `
    --svg $svg
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Phase 6DG extension boundary captured: $output"
