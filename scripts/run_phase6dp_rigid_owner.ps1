param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.benchmark.kit"
$buildScript = Join-Path $PSScriptRoot "build_wood_native.ps1"
$probeScript = Join-Path $PSScriptRoot "probe_phase6dp_rigid_owner.py"
$analyzeScript = Join-Path $PSScriptRoot "analyze_phase6dp_rigid_owner.py"
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase6dp"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$nativeBuild = Join-Path $OutputDir "native"
$nativeDll = Join-Path $nativeBuild "campfire_wood_native.dll"
$probe = Join-Path $OutputDir "rigid_owner_probe.json"
$report = Join-Path $repositoryRoot "docs\devlog\assets\phase6\rigid_owner_report.json"
$svg = Join-Path $repositoryRoot "docs\devlog\assets\phase6\rigid_owner_report.svg"
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

& $buildScript -OutputDir $nativeBuild
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $kit @(
    $app,
    "--no-window",
    "--/app/quitAfter=600",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/phase6dp/output=$probe",
    "--/phase6dp/nativeDll=$nativeDll",
    "--exec",
    $probeScript
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$result = Get-Content -Raw -LiteralPath $probe | ConvertFrom-Json
if ($result.status -ne "ok") {
    throw "Phase 6DP rigid owner did not qualify: $probe"
}
& (Join-Path $releaseRoot "kit\python\python.exe") $analyzeScript `
    --probe $probe `
    --report $report `
    --svg $svg
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host ("Phase 6DP qualified: gates={0}, revision={1}, replacement={2}" -f `
    @($result.gates.PSObject.Properties).Count, `
    $result.publication.revision, `
    $result.publication.consumer_replace_count)
