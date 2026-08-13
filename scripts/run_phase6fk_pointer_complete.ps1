param([Parameter(Mandatory = $true)][string]$OutputRoot)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$runner = Join-Path $PSScriptRoot "run_phase6fj_balanced_single_readback.ps1"
$contract = Join-Path $PSScriptRoot "phase6fk_pointer_complete_contract.json"
& $runner -OutputRoot $OutputRoot -ContractPath $contract
exit $LASTEXITCODE
