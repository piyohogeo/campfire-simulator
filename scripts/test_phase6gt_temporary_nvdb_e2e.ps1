param([Parameter(Mandatory = $true)][string]$OutputDir)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $OutputDir) { throw "Phase 6GT E2E fixture refuses output reuse: $OutputDir" }
New-Item -ItemType Directory -Path $OutputDir | Out-Null
. (Join-Path $PSScriptRoot "phase6gt_temporary_file_cleanup.ps1")
$contract = Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot "phase6gt_temporary_nvdb_contract.json") | ConvertFrom-Json
$caseRoot = Join-Path $OutputDir "simulated-case"
New-Item -ItemType Directory -Path $caseRoot | Out-Null
$temporaryPath = Join-Path $caseRoot $contract.temporary_file.filename
$neighborPath = Join-Path $caseRoot "neighbor-must-survive.txt"
$stream = [IO.File]::Open($temporaryPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try { $stream.SetLength(4096); $stream.Flush($true) } finally { $stream.Dispose() }
$neighbor = [IO.File]::Open($neighborPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try { $neighbor.SetLength(1); $neighbor.Flush($true) } finally { $neighbor.Dispose() }
$cleanup = Invoke-Phase6gtExactTemporaryCleanup -TemporaryPath $temporaryPath -CaseRoot $caseRoot -ExpectedFilename $contract.temporary_file.filename
$missingCleanup = Invoke-Phase6gtExactTemporaryCleanup -TemporaryPath $temporaryPath -CaseRoot $caseRoot -ExpectedFilename $contract.temporary_file.filename
$escapeRejected = $false
try {
    Invoke-Phase6gtExactTemporaryCleanup -TemporaryPath (Join-Path $OutputDir "outside.nvdb") -CaseRoot $caseRoot -ExpectedFilename $contract.temporary_file.filename | Out-Null
} catch { $escapeRejected = $true }
$cases = @(
    [ordered]@{name="exact_file_removed";passed=($cleanup.removed_by_parent -and -not $cleanup.exists_after_cleanup);observed=$cleanup},
    [ordered]@{name="exact_size_recorded";passed=($cleanup.size_before_cleanup_bytes -eq 4096);observed=$cleanup.size_before_cleanup_bytes},
    [ordered]@{name="neighbor_preserved";passed=[bool](Test-Path -LiteralPath $neighborPath);observed=$null},
    [ordered]@{name="missing_file_is_absent_not_removed";passed=(-not $missingCleanup.existed_after_process -and -not $missingCleanup.removed_by_parent);observed=$missingCleanup},
    [ordered]@{name="path_escape_rejected";passed=$escapeRejected;observed=$escapeRejected}
)
Remove-Item -LiteralPath $neighborPath -Force
$passed = @($cases | Where-Object { -not $_.passed }).Count -eq 0
$report = [ordered]@{
    schema="campfire.phase6gt.temporary-nvdb-e2e-fixture.v1";passed=$passed;
    case_count=$cases.Count;kit_started=$false;cases=$cases
}
[IO.File]::WriteAllText((Join-Path $OutputDir "result.json"),($report|ConvertTo-Json -Depth 8)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
if (-not $passed) { throw "Phase 6GT end-to-end cleanup fixture failed" }
Write-Host "Phase 6GT end-to-end fixtures passed: $($cases.Count)/$($cases.Count)"
