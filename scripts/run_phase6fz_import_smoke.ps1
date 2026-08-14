param([Parameter(Mandatory = $true)][string]$OutputRoot)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$repo = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "phase6ea_diagnostic_common.ps1")
$root = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $root) { throw "Phase 6FZ import smoke refuses root reuse: $root" }
New-Item -ItemType Directory -Path $root | Out-Null
$release = Join-Path $repo "_build\windows-x86_64\release"
$kit = Join-Path $release "kit\kit.exe"
$app = Join-Path $release "kit\apps\omni.app.editor.base.kit"
$probe = Join-Path $PSScriptRoot "probe_phase6fz_import_smoke.py"
$shared = Join-Path $PSScriptRoot "probe_phase6fo_supply_comparison.py"
$baselineKitPids = @(Get-Process kit -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
$cases = @(
    [ordered]@{ name="app_ready_success"; expectation="success" },
    [ordered]@{ name="module_missing"; expectation="missing" },
    [ordered]@{ name="wrong_path"; expectation="wrong_path" }
)
$results = @()
foreach ($case in $cases) {
    $caseDir = Join-Path $root $case.name
    New-Item -ItemType Directory -Path $caseDir | Out-Null
    $report = Join-Path $caseDir "import_smoke_report.json"
    $log = Join-Path $caseDir "kit.log"
    $stdout = Join-Path $caseDir "kit.stdout.log"
    $stderr = Join-Path $caseDir "kit.stderr.log"
    $target = $shared
    $expected = $shared
    if ($case.expectation -eq "missing") { $target = Join-Path $caseDir "absent_probe.py" }
    if ($case.expectation -eq "wrong_path") {
        $target = Join-Path $caseDir "decoy_probe.py"
        [IO.File]::WriteAllText($target, "def _run(): pass`ndef _append_resource_marker(): pass`n", [Text.UTF8Encoding]::new($false))
    }
    $arguments = @(
        $app, "--no-window", "--/app/settings/persistent=0", "--/app/settings/loadUserConfig=0",
        "--/app/window/hideUi=true", "--/app/asyncRendering=false", "--/app/quitAfter=180000",
        "--/renderer/enabled=rtx", "--/renderer/active=rtx", "--/rtx/flow/enabled=true",
        "--/phase6fz/importSmokeReport=$report", "--/phase6fz/importTarget=$target",
        "--/phase6fz/importExpected=$expected", "--/phase6fz/importExpectation=$($case.expectation)",
        "--/log/file=$log", "--/log/fileLogLevel=Info",
        "--enable", "omni.flowusd", "--enable", "omni.volume", "--enable", "omni.hydra.rtx",
        "--enable", "omni.kit.viewport.window", "--enable", "omni.kit.renderer.capture",
        "--enable", "omni.physx.cooking", "--enable", "omni.physx.stageupdate", "--exec", $probe
    )
    $guard = Invoke-Phase6EaGuardedHelper -FilePath $kit -ArgumentList $arguments -StdoutPath $stdout -StderrPath $stderr -TimeoutSeconds 180 -PrivateBytesLimit 16GB -MaximumStdoutBytes 8MB -MaximumStderrBytes 8MB
    $parsed = if (Test-Path -LiteralPath $report -PathType Leaf) { Get-Content -Raw -Encoding UTF8 $report | ConvertFrom-Json } else { $null }
    $expectedStatus = if ($case.expectation -eq "success") { "pass" } else { "expected_failure" }
    $remaining = @(Get-Process kit -ErrorAction SilentlyContinue | Where-Object { $baselineKitPids -notcontains $_.Id } | ForEach-Object { $_.Id })
    $passed = ($null -ne $parsed -and $parsed.status -eq $expectedStatus -and $parsed.kit_app_ready -and
        -not $guard.timed_out -and -not $guard.private_bytes_exceeded -and -not $guard.output_bytes_exceeded -and
        $guard.exit_code -eq 0 -and $guard.process_absent -and $remaining.Count -eq 0)
    if ($case.expectation -eq "success") {
        $passed = $passed -and $parsed.import_audit.resolved_file -eq ([IO.Path]::GetFullPath($shared)) -and
            @($parsed.import_audit.required_entrypoints).Count -eq 2
    }
    $results += [ordered]@{ name=$case.name; expectation=$case.expectation; status=if($passed){"pass"}else{"fail"}; guard=$guard; report=$parsed; unexpected_kit_pids=$remaining }
    if (-not $passed) { break }
}
$summary = [ordered]@{
    schema="campfire.phase6fz.import-smoke-suite.v1"; phase="phase6fz"
    passed=($results.Count -eq 3 -and @($results | Where-Object { $_.status -ne "pass" }).Count -eq 0)
    expected_count=3; completed_count=$results.Count; cases=$results
    kit_path=[IO.Path]::GetFullPath($kit); shared_probe=[IO.Path]::GetFullPath($shared)
    baseline_kit_pids=$baselineKitPids; timestamp_utc=[DateTime]::UtcNow.ToString("o")
}
[IO.File]::WriteAllText((Join-Path $root "import_smoke_suite.json"), ($summary | ConvertTo-Json -Depth 30) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
if (-not $summary.passed) { exit 13 }

