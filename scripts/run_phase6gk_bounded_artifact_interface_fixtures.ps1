param(
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [string]$Phase6GJRawArtifact = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0

$repo = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6GK fixture refuses output-root reuse: $OutputRoot" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
$inputs = Join-Path $OutputRoot "inputs"
$casesRoot = Join-Path $OutputRoot "cases"
New-Item -ItemType Directory -Path $inputs | Out-Null
New-Item -ItemType Directory -Path $casesRoot | Out-Null

$canonical = "field_body_json_npz_or_openvdb_written"
$legacy = "full_field_json_or_npz_written"
$sharedRunner = Join-Path $PSScriptRoot "run_phase6gd_channel_metadata_probe.ps1"
$powershell = (Get-Command powershell.exe).Source
$phase6gjRaw = if ([string]::IsNullOrWhiteSpace($Phase6GJRawArtifact)) {
    Join-Path $repo "artifacts\phase6gj-s93-channel-preflight-1\S93-attempt01\metadata_divergence_attempt01\S93_support_clear\channel-schema-metadata\bounded_handle_metadata.json"
} else { [IO.Path]::GetFullPath($Phase6GJRawArtifact) }
if (-not (Test-Path -LiteralPath $phase6gjRaw)) {
    throw "Phase 6GK requires the frozen Phase 6GJ raw artifact for round-trip fixture: $phase6gjRaw"
}
$phase6gjRawHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $phase6gjRaw).Hash

function New-BaseArtifact {
    return [ordered]@{
        schema = "campfire.phase6gk.fixture-bounded-handle-metadata.v1"
        phase = "phase6gk"
        status = "pass"
        returned_handle_count = 7
        handles = @()
        formal_channel_names_assigned = $true
    }
}

$specifications = @()
function Add-Case([string]$Name, [hashtable]$Properties, [int]$ExpectedExit, [string]$ExpectedMode) {
    $payload = New-BaseArtifact
    foreach ($key in $Properties.Keys) { $payload[$key] = $Properties[$key] }
    $script:specifications += [pscustomobject]@{
        name = $Name; payload = $payload; source_path = $null
        expected_exit = $ExpectedExit; expected_mode = $ExpectedMode
    }
}

Add-Case "canonical_false" @{$canonical = $false} 0 "canonical_only"
Add-Case "canonical_true" @{$canonical = $true} 1 "canonical_only"
Add-Case "missing_required_property" @{} 1 "invalid"
Add-Case "legacy_false" @{$legacy = $false} 0 "legacy_normalized"
Add-Case "dual_equal_false" @{$canonical = $false; $legacy = $false} 0 "dual_equal_normalized"
Add-Case "dual_conflict" @{$canonical = $false; $legacy = $true} 1 "invalid"
Add-Case "canonical_null" @{$canonical = $null} 1 "invalid"
Add-Case "canonical_string" @{$canonical = "false"} 1 "invalid"
Add-Case "canonical_number" @{$canonical = 0} 1 "invalid"
$specifications += [pscustomobject]@{
    name = "phase6gj_raw_artifact_round_trip"; payload = $null; source_path = $phase6gjRaw
    expected_exit = 0; expected_mode = "canonical_only"
}

$results = @()
foreach ($specification in $specifications) {
    $inputPath = Join-Path $inputs "$($specification.name).json"
    if ($null -ne $specification.source_path) {
        Copy-Item -LiteralPath $specification.source_path -Destination $inputPath
    } else {
        [IO.File]::WriteAllText(
            $inputPath,
            ($specification.payload | ConvertTo-Json -Depth 12) + [Environment]::NewLine,
            [Text.UTF8Encoding]::new($false))
    }
    $caseRoot = Join-Path $casesRoot $specification.name
    $wrapperReport = Join-Path $caseRoot "shared_runner_fixture_report.json"
    $stdoutPath = Join-Path $OutputRoot "$($specification.name).stdout.log"
    $stderrPath = Join-Path $OutputRoot "$($specification.name).stderr.log"
    $arguments = @(
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $sharedRunner,
        "-OutputRoot", $caseRoot, "-ReportPhase", "phase6gk",
        "-BoundedArtifactFixtureInput", $inputPath,
        "-BoundedArtifactFixtureReport", $wrapperReport
    )
    $savedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $powershell @arguments 1> $stdoutPath 2> $stderrPath
        $childExitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $savedPreference }

    $normalizationReportPath = Join-Path $caseRoot "bounded_artifact_interface_report.json"
    $normalizedPath = Join-Path $caseRoot "normalized_bounded_artifact.json"
    $reasons = @()
    $normalizationReport = $null
    $wrapper = $null
    if (-not (Test-Path -LiteralPath $wrapperReport)) { $reasons += "wrapper_report_missing" }
    else { $wrapper = Get-Content -Raw -Encoding UTF8 $wrapperReport | ConvertFrom-Json }
    if (-not (Test-Path -LiteralPath $normalizationReportPath)) { $reasons += "normalization_report_missing" }
    else { $normalizationReport = Get-Content -Raw -Encoding UTF8 $normalizationReportPath | ConvertFrom-Json }
    if ($childExitCode -ne [int]$specification.expected_exit) { $reasons += "child_exit_code_mismatch" }
    if ($null -ne $wrapper) {
        if ([int]$wrapper.normalizer_exit_code -ne $childExitCode) { $reasons += "wrapper_exit_code_not_propagated" }
        if (-not [bool]$wrapper.exit_code_propagated) { $reasons += "wrapper_exit_propagation_marker_false" }
    }
    if ($null -ne $normalizationReport) {
        if ([string]$normalizationReport.normalization_mode -ne [string]$specification.expected_mode) {
            $reasons += "normalization_mode_mismatch"
        }
        if ([bool]$normalizationReport.pass -ne ($specification.expected_exit -eq 0)) {
            $reasons += "normalization_pass_mismatch"
        }
    }
    if ($specification.expected_exit -eq 0) {
        if (-not (Test-Path -LiteralPath $normalizedPath)) { $reasons += "normalized_artifact_missing" }
        else {
            $normalized = Get-Content -Raw -Encoding UTF8 $normalizedPath | ConvertFrom-Json
            $canonicalProperty = $normalized.PSObject.Properties[$canonical]
            $legacyProperty = $normalized.PSObject.Properties[$legacy]
            if ($null -eq $canonicalProperty -or $canonicalProperty.Value -isnot [bool] -or [bool]$canonicalProperty.Value) {
                $reasons += "normalized_canonical_value_invalid"
            }
            if ($null -ne $legacyProperty) { $reasons += "normalized_legacy_property_retained" }
        }
    }
    $results += [ordered]@{
        name = $specification.name
        expected_exit_code = [int]$specification.expected_exit
        observed_exit_code = $childExitCode
        expected_normalization_mode = [string]$specification.expected_mode
        observed_normalization_mode = if ($null -eq $normalizationReport) { $null } else { [string]$normalizationReport.normalization_mode }
        compatibility_normalization_applied = if ($null -eq $normalizationReport) { $null } else { [bool]$normalizationReport.compatibility_normalization_applied }
        wrapper_exit_code_propagated = if ($null -eq $wrapper) { $false } else { [bool]$wrapper.exit_code_propagated }
        source_is_frozen_phase6gj_artifact = $null -ne $specification.source_path
        source_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $inputPath).Hash
        pass = $reasons.Count -eq 0
        reasons = $reasons
    }
}

$passed = @($results | Where-Object { $_.pass }).Count
$summary = [ordered]@{
    schema = "campfire.phase6gk.bounded-artifact-interface-fixtures.v1"
    phase = "phase6gk"
    status = if ($passed -eq $results.Count) { "pass" } else { "fail" }
    all_pass = $passed -eq $results.Count
    canonical_property = $canonical
    legacy_property = $legacy
    compatibility_policy = "legacy is accepted only at the explicit normalization boundary"
    phase6gj_artifact_read_only = $true
    phase6gj_artifact_path = $phase6gjRaw
    phase6gj_artifact_sha256 = $phase6gjRawHash
    passed = $passed
    total = $results.Count
    results = $results
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
}
[IO.File]::WriteAllText(
    (Join-Path $OutputRoot "summary.json"),
    ($summary | ConvertTo-Json -Depth 16) + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false))
if (-not $summary.all_pass) { exit 1 }
exit 0
