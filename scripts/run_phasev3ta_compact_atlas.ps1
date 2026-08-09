param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$probeScript = Join-Path $PSScriptRoot "probe_phasev3ta_compact_atlas.py"
if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phasev3ta\compact-atlas" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$probe = Join-Path $OutputDir "compact_atlas_probe.json"
$captures = Join-Path $OutputDir "captures"
New-Item -ItemType Directory -Path $captures -Force | Out-Null

& $kit @(
    $app,
    "--/app/file/ignoreUnsavedOnExit=true",
    "--/app/quitAfter=10000",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/app/viewport/defaults/fillViewport=false",
    "--/phasev3ta/output=$probe",
    "--/phasev3ta/captureDir=$captures",
    "--exec",
    $probeScript
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$result = Get-Content -LiteralPath $probe -Raw | ConvertFrom-Json
if ($result.status -ne "qualified") {
    throw "Phase V3T-A compact atlas probe did not qualify."
}
if ($result.twenty_logs.descriptor.bytes_two_rgba8 -ne 57600) {
    throw "Phase V3T-A did not produce the expected 57,600-byte two-atlas transport."
}
Write-Host ("Phase V3T-A compact atlas: status={0}, gates={1}/{2}, bytes/revision={3}" -f $result.status, @($result.gates.psobject.Properties | Where-Object { $_.Value }).Count, @($result.gates.psobject.Properties).Count, $result.twenty_logs.descriptor.bytes_two_rgba8)
