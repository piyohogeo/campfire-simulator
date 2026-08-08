param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$productionRoot = Join-Path $repositoryRoot "source\extensions\campfire.app"
$audit = Join-Path $PSScriptRoot "audit_phase6dm_layout_compatibility.py"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6dm_layout_compatibility.py"
$python = (Get-Command python.exe -ErrorAction Stop).Source

if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase6\phase6dm"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$rawReport = Join-Path $OutputDir "resident_layout_compatibility_raw.json"
$productionFiles = Get-ChildItem -LiteralPath $productionRoot -Recurse -File | Sort-Object FullName
$hashesBefore = @($productionFiles | ForEach-Object {
    "{0}:{1}" -f $_.FullName, (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
})

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
Remove-Item -LiteralPath $rawReport -Force -ErrorAction SilentlyContinue
& $python $audit --output $rawReport
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not (Test-Path -LiteralPath $rawReport)) {
    throw "Phase 6DM raw report is missing."
}

$hashesAfter = @($productionFiles | ForEach-Object {
    "{0}:{1}" -f $_.FullName, (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
})
$productionUnchanged = ($hashesBefore -join "|") -ceq ($hashesAfter -join "|")
$productionUnchangedText = $productionUnchanged.ToString().ToLowerInvariant()
& $python $analyzer --raw $rawReport --production-unchanged $productionUnchangedText
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
