param([Parameter(Mandatory = $true)][string]$OutputRoot)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
. (Join-Path $PSScriptRoot "phase6ea_diagnostic_common.ps1")
$repo = Split-Path -Parent $PSScriptRoot
$root = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $root) { throw "Phase 6GN exact-wrapper smoke refuses root reuse: $root" }
New-Item -ItemType Directory -Path $root | Out-Null
$release = Join-Path $repo "_build\windows-x86_64\release"
$kit = Join-Path $release "kit\kit.exe"
$app = Join-Path $release "kit\apps\omni.app.editor.base.kit"
$probe = Join-Path $PSScriptRoot "probe_phase6gn_exact_wrapper_smoke.py"
$wrapper = Join-Path $PSScriptRoot "probe_phase6gn_supply_comparison.py"
$baselineKitPids = @(Get-Process kit -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
$cases = @(
    [ordered]@{name="positive_exact_wrapper";mode="positive";expected_exit=0;expected_status="pass"},
    [ordered]@{name="negative_wrong_path";mode="wrong_path";expected_exit=0;expected_status="expected_failure"},
    [ordered]@{name="negative_legacy_shared_callable";mode="legacy_shared_callable_declaration";expected_exit=0;expected_status="expected_failure"},
    [ordered]@{name="negative_missing_attribute";mode="missing_required_attribute";expected_exit=0;expected_status="expected_failure"},
    [ordered]@{name="exit_code_propagation";mode="exit_code_propagation";expected_exit=29;expected_status="fail"}
)
$results = @()
foreach ($case in $cases) {
    $caseDir = Join-Path $root $case.name
    New-Item -ItemType Directory -Path $caseDir | Out-Null
    $report = Join-Path $caseDir "report.json"
    $markers = Join-Path $caseDir "markers.jsonl"
    $audit = Join-Path $caseDir "import_audit.json"
    $stdout = Join-Path $caseDir "kit.stdout.log"
    $stderr = Join-Path $caseDir "kit.stderr.log"
    $log = Join-Path $caseDir "kit.log"
    $target = $wrapper
    $expected = $wrapper
    if ($case.mode -eq "wrong_path") {
        $expected = Join-Path $caseDir "expected-decoy.py"
        [IO.File]::WriteAllText($expected, "def _build_stage_with_qualified_exports(): pass`n", [Text.UTF8Encoding]::new($false))
    }
    $arguments = @(
        $app, "--no-window", "--/app/settings/persistent=0", "--/app/settings/loadUserConfig=0",
        "--/app/window/hideUi=true", "--/app/asyncRendering=false", "--/app/quitAfter=180000",
        "--/renderer/enabled=rtx", "--/renderer/active=rtx", "--/rtx/flow/enabled=true",
        "--/phase6gn/smokeReport=$report", "--/phase6gn/smokeMarkers=$markers",
        "--/phase6gn/wrapperPath=$target", "--/phase6gn/expectedWrapperPath=$expected",
        "--/phase6gn/smokeMode=$($case.mode)", "--/phase6fz/importAuditPath=$audit",
        "--/log/file=$log", "--/log/fileLogLevel=Info",
        "--enable", "omni.flowusd", "--enable", "omni.volume", "--enable", "omni.hydra.rtx",
        "--enable", "omni.kit.viewport.window", "--enable", "omni.kit.renderer.capture",
        "--enable", "omni.physx.cooking", "--enable", "omni.physx.stageupdate", "--exec", $probe
    )
    $commandAudit = [ordered]@{file=[IO.Path]::GetFullPath($kit);arguments=$arguments;mode=$case.mode;expected_exit=$case.expected_exit}
    [IO.File]::WriteAllText((Join-Path $caseDir "exact_command_line.json"), ($commandAudit | ConvertTo-Json -Depth 6)+[Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    $guard = Invoke-Phase6EaGuardedHelper -FilePath $kit -ArgumentList $arguments -StdoutPath $stdout -StderrPath $stderr -TimeoutSeconds 180 -PrivateBytesLimit 16GB -MaximumStdoutBytes 8MB -MaximumStderrBytes 8MB
    $parsed = if (Test-Path -LiteralPath $report -PathType Leaf) { Get-Content -Raw -Encoding UTF8 $report | ConvertFrom-Json } else { $null }
    $rows = if (Test-Path -LiteralPath $markers -PathType Leaf) { @(Get-Content -Encoding UTF8 $markers | ForEach-Object { $_ | ConvertFrom-Json }) } else { @() }
    $markerNames = @($rows | ForEach-Object { $_.marker })
    $remaining = @(Get-Process kit -ErrorAction SilentlyContinue | Where-Object { $baselineKitPids -notcontains $_.Id } | ForEach-Object { $_.Id })
    $passed = ($null -ne $parsed -and $markerNames.Count -ge 2 -and $parsed.status -eq $case.expected_status -and $guard.exit_code -eq $case.expected_exit -and
        -not $guard.timed_out -and -not $guard.private_bytes_exceeded -and -not $guard.output_bytes_exceeded -and
        $guard.process_absent -and $remaining.Count -eq 0 -and $markerNames[0] -eq "import_started" -and $markerNames[-1] -eq "smoke_complete")
    if ($case.mode -eq "positive") {
        $passed = $passed -and ($markerNames -join ',') -eq "import_started,import_complete,wrapper_wiring_complete,smoke_complete" -and
            $parsed.wrapper_runtime_import_audit.status -eq "pass" -and $parsed.wrapper_wiring.patched_identity_matches -and
            $parsed.descriptor_digest -eq "53CDE38FD5B1A5F48AB2E7B896F6EF391DDA4D5F6621B21FDB1B435F34BDA8CE"
    }
    $results += [ordered]@{name=$case.name;mode=$case.mode;status=if($passed){"pass"}else{"fail"};guard=$guard;report=$parsed;markers=$markerNames;unexpected_kit_pids=$remaining}
    if (-not $passed) { break }
}
$summary = [ordered]@{
    schema="campfire.phase6gn.exact-wrapper-smoke-suite.v1";phase="phase6gn"
    passed=($results.Count -eq $cases.Count -and @($results|Where-Object{$_.status -ne "pass"}).Count -eq 0)
    expected_count=$cases.Count;completed_count=$results.Count;cases=$results
    kit_path=[IO.Path]::GetFullPath($kit);wrapper_path=[IO.Path]::GetFullPath($wrapper)
    baseline_kit_pids=$baselineKitPids;timestamp_utc=[DateTime]::UtcNow.ToString("o")
}
[IO.File]::WriteAllText((Join-Path $root "summary.json"), ($summary|ConvertTo-Json -Depth 30)+[Environment]::NewLine, [Text.UTF8Encoding]::new($false))
if (-not $summary.passed) { exit 31 }
