param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$probeScript = Join-Path $PSScriptRoot "probe_phasev3mb_stable_mesh.py"
if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phasev3mb\mesh" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$probe = Join-Path $OutputDir "stable_mesh_probe.json"
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
    "--/phasev3mb/output=$probe",
    "--/phasev3mb/captureDir=$captures",
    "--exec",
    $probeScript
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$result = Get-Content -LiteralPath $probe -Raw | ConvertFrom-Json
if ($result.status -ne "qualified") {
    throw "Phase V3M-B stable Mesh probe did not qualify."
}
Write-Host ("Phase V3M-B Mesh: status={0}, gates={1}/{2}" -f $result.status, @($result.gates.psobject.Properties | Where-Object { $_.Value }).Count, @($result.gates.psobject.Properties).Count)
