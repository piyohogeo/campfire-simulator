param(
    [string]$OutputDir = "",
    [ValidateSet("enabled", "disabled")][string]$Mode = "enabled",
    [string]$Label = "trial"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$probe = Join-Path $PSScriptRoot "probe_phase6df_stageupdate_case.py"
$nativeLibrary = Join-Path $repositoryRoot "artifacts\phase3\phase6co-resident\native-build\campfire_wood_native.dll"
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6df-stageupdate-trial"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$caseDir = Join-Path $OutputDir "$Label-$Mode"
$output = Join-Path $caseDir "case.json"
$scene = Join-Path $caseDir "phase6df.usda"
$log = Join-Path $caseDir "case.log"
$flowEnabled = $Mode -eq "enabled"

if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) {
    throw "Application is not built."
}
if (-not (Test-Path -LiteralPath $nativeLibrary)) {
    throw "Phase 6DF requires the existing Phase 6CO native build: $nativeLibrary"
}
New-Item -ItemType Directory -Path $caseDir -Force | Out-Null
foreach ($path in @($output, $scene, $log)) {
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
    "--/phase6df/output=$output",
    "--/phase6df/scene=$scene",
    "--/phase6df/nativeLibrary=$nativeLibrary",
    "--/phase6df/flowUsdEnabled=$($flowEnabled.ToString().ToLowerInvariant())",
    "--/phase6df/label=$Label",
    "--/rtx/flow/enabled=true",
    "--/log/file=$log",
    "--/log/fileLogLevel=Info",
    "--exec",
    $probe
)
$kitExitCode = $LASTEXITCODE
$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $app).Hash
if ($productionHashBefore -ne $productionHashAfter) {
    throw "Phase 6DF changed the production app file."
}
if (-not (Test-Path -LiteralPath $output)) {
    throw "Phase 6DF case report is missing."
}
$case = Get-Content -LiteralPath $output -Raw | ConvertFrom-Json
if ($kitExitCode -ne 0 -or $case.status -ne "ok") {
    throw "Phase 6DF $Mode case failed: Kit=$kitExitCode status=$($case.status) error=$($case.error)"
}
$manifest = [ordered]@{
    schema_version = 1
    phase = "phase6df"
    status = "ok"
    mode = $Mode
    label = $Label
    case = $output
    kit_exit_code = $kitExitCode
    production_app_sha256_before = $productionHashBefore
    production_app_sha256_after = $productionHashAfter
    production_changed = ($productionHashBefore -ne $productionHashAfter)
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $caseDir "manifest.json") -Encoding utf8
Write-Host "Phase 6DF $Mode trial completed: $output"
