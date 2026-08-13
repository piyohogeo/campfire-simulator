param(
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [string]$ContractPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$contract = if ([string]::IsNullOrWhiteSpace($ContractPath)) {
    Join-Path $PSScriptRoot "phase6fx_memory_ceiling_qualification_contract.json"
} else {
    [IO.Path]::GetFullPath($ContractPath)
}
$engine = Join-Path $PSScriptRoot "run_phase6fv_memory_ceiling_qualification.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6fx_memory_ceiling_qualification.py"
& $engine -OutputRoot $OutputRoot -ContractPath $contract -Phase phase6fx -AnalyzerPath $analyzer -CaseReportPhase phase6fv
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
