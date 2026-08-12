param(
    [string]$OutputRoot = "",
    [string]$SourceStage = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
$contractPath = Join-Path $PSScriptRoot "phase6en_static_pose_engineering_contract.json"
$expectedContractHash = "C6A73B07385519160488DA07C023EC5E5104BB0A8C1BDAD70D01B15327CAE1AF"
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash -ne $expectedContractHash) {
    throw "Phase 6EN frozen contract SHA-256 mismatch"
}
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $root "artifacts\phase6en-static-pose-engineering-qualification-1"
}
$arguments = @{
    OutputRoot = $OutputRoot
    ContractPath = $contractPath
}
if ($SourceStage) { $arguments.SourceStage = $SourceStage }
& (Join-Path $PSScriptRoot "run_phase6eg_static_pose_set_qualification.ps1") @arguments
exit $LASTEXITCODE
