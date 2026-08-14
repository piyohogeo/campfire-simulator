param([Parameter(Mandatory = $true)][string]$OutputDir)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $OutputDir) { throw "Phase 6GS fixture refuses output reuse: $OutputDir" }
New-Item -ItemType Directory -Path $OutputDir | Out-Null
. (Join-Path $PSScriptRoot "phase6gs_reporting_contract.ps1")

$inputPath = Join-Path $OutputDir "python_child_output.json"
& python (Join-Path $PSScriptRoot "test_phase6gs_harness.py") --emit-parent-fixtures $inputPath *> (Join-Path $OutputDir "python_child.log")
if ($LASTEXITCODE -ne 0) { throw "Phase 6GS Python child fixture failed" }
$input = Get-Content -Raw -Encoding UTF8 $inputPath | ConvertFrom-Json
$results = New-Object System.Collections.Generic.List[object]
function Add-Result([string]$Name, [bool]$Passed, [object]$Observed) {
    $results.Add([ordered]@{name=$Name;passed=$Passed;observed=$Observed})
}

$positive = $input.marker.positive
Add-Result "positive_source_metadata" (($positive.slot -eq 0) -and ($positive.channel -eq "temperature") -and ($positive.nbytes -eq 47641344)) $positive
$duplicate = $input.marker.duplicate_same_value
Add-Result "duplicate_same_channel_normalized_once" (($duplicate.channel -eq "temperature") -and (@($duplicate.PSObject.Properties.Name | Where-Object { $_ -eq "channel" }).Count -eq 1)) $duplicate.channel
Add-Result "conflicting_channel_rejected" ([bool]$input.marker.conflicting_rejected) $input.marker.conflicting_rejected

$normal = Get-Phase6gsOptionalString -InputObject $input.operations.normal_string -PropertyName "last_successful_accessor"
Add-Result "optional_string" ($normal -eq "get_grid_class") $normal
$explicitNull = Get-Phase6gsOptionalString -InputObject $input.operations.explicit_null -PropertyName "last_successful_accessor"
Add-Result "optional_explicit_null" ($null -eq $explicitNull) $explicitNull
$emptyString = Get-Phase6gsOptionalString -InputObject $input.operations.empty_string -PropertyName "last_successful_accessor"
Add-Result "optional_empty_or_whitespace_normalized_null" ($null -eq $emptyString) $emptyString
$missing = Get-Phase6gsOptionalString -InputObject $input.operations.missing -PropertyName "last_successful_accessor"
Add-Result "optional_missing" ($null -eq $missing) $missing
$invalidRejected = $false
try { [void](Get-Phase6gsOptionalString -InputObject $input.operations.invalid_type -PropertyName "last_successful_accessor") } catch { $invalidRejected = $true }
Add-Result "optional_invalid_type_rejected" $invalidRejected $invalidRejected

$zero = Get-Phase6gsOptionalString -InputObject $input.operations.phase6gr_zero -PropertyName "last_successful_accessor"
Add-Result "phase6gr_zero_accessor_summary" ($null -eq $zero) $zero
$partial = Get-Phase6gsOptionalString -InputObject $input.operations.partial -PropertyName "last_successful_accessor"
Add-Result "partial_accessor_summary" ($partial -eq "get_grid_type") $partial
$complete = Get-Phase6gsOptionalString -InputObject $input.operations.complete -PropertyName "last_successful_accessor"
Add-Result "complete_accessor_summary" ($complete -eq "get_world_bounding_box") $complete

$statePath = Join-Path $OutputDir "terminal_state.json"
$state = @{schema="campfire.phase6gs.fixture-state.v1";status="running";terminal=$false}
Write-Phase6gsTerminalState -Path $statePath -State $state -Status "safe_stop" -OperationResult "metadata_accessor_failure" -LifecycleResult "failure" -LastSuccessfulAccessor $zero
$terminal = Get-Content -Raw -Encoding UTF8 $statePath | ConvertFrom-Json
Add-Result "safe_stop_terminal_state" (($terminal.status -eq "safe_stop") -and $terminal.terminal) $terminal.status

$rawPath = Join-Path $OutputDir "raw_evidence.json"
[IO.File]::WriteAllText($rawPath,'{"schema":"campfire.phase6gs.raw-evidence.v1","saved_before_parent":true}'+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$rawHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $rawPath).Hash
try { [void](Get-Phase6gsOptionalString -InputObject $input.operations.invalid_type -PropertyName "last_successful_accessor") } catch {}
$rawHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $rawPath).Hash
Add-Result "raw_evidence_survives_parent_failure" (($rawHashBefore -eq $rawHashAfter) -and (Test-Path -LiteralPath $rawPath)) $rawHashAfter

$passed = @($results | Where-Object { -not $_.passed }).Count -eq 0
$report = [ordered]@{
    schema="campfire.phase6gs.harness-e2e-fixture.v1";passed=$passed;case_count=$results.Count;
    kit_started=$false;cases=$results;child_input_path=$inputPath
}
[IO.File]::WriteAllText((Join-Path $OutputDir "result.json"),($report|ConvertTo-Json -Depth 16)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
if (-not $passed -or $results.Count -ne 13) { throw "Phase 6GS end-to-end fixture failed" }
Write-Host "Phase 6GS end-to-end fixtures passed: 13/13"
