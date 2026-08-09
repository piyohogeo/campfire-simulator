param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.benchmark.kit"
$kitPython = Join-Path $releaseRoot "kit\python\python.exe"
$auditScript = Join-Path $PSScriptRoot "audit_phase6dn_layout_representation.py"
$probeScript = Join-Path $PSScriptRoot "probe_phase6dn_layout_representation.py"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6dn_layout_representation.py"
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase6dn"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$audit = Join-Path $OutputDir "layout_representation_audit.json"
$probe = Join-Path $OutputDir "layout_representation_probe.json"
$report = Join-Path $repositoryRoot "docs\devlog\assets\phase6\layout_representation_report.json"
$svg = Join-Path $repositoryRoot "docs\devlog\assets\phase6\layout_representation_report.svg"
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

python $auditScript --output $audit
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $kit @(
    $app,
    "--no-window",
    "--/app/quitAfter=300",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/phase6dn/output=$probe",
    "--exec",
    $probeScript
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $kitPython $analyzer --audit $audit --probe $probe --report $report --svg $svg
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$result = Get-Content -Raw -LiteralPath $report | ConvertFrom-Json
Write-Host ("Phase 6DN qualified: status={0}, static={1}/{2}, runtime={3}/{4}" -f `
    $result.status, $result.audit_gates.passed, $result.audit_gates.total, `
    $result.runtime_gates.passed, $result.runtime_gates.total)
