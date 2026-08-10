param([string]$OutputDir = "", [int]$TimeoutSeconds = 90)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
if (-not $OutputDir) { $OutputDir = Join-Path $root "artifacts\isolated-kit-native-crash-fixture" }
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $OutputDir) { throw "Native crash fixture refuses to reuse output: $OutputDir" }
New-Item -ItemType Directory -Path $OutputDir | Out-Null

$tools = Join-Path $OutputDir "tools"
& (Join-Path $PSScriptRoot "build_phasev3tj_dump_collector.ps1") -OutputDir $tools
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$triggerLibrary = Join-Path $tools "build\Release\phasev3tj_crash_handler.dll"
$release = Join-Path $root "_build\windows-x86_64\release"
$kit = Join-Path $release "kit\kit.exe"
$app = New-CampfireIsolatedKitApp -SourceApp (Join-Path $release "kit\apps\omni.app.mini.kit")
$probe = Join-Path $PSScriptRoot "probe_isolated_kit_crash_fixture.py"
$analyzer = Join-Path $PSScriptRoot "analyze_phasev3tl_native_dump.py"
$dumpDir = Join-Path $OutputDir "sensitive-crash-dumps"
$log = Join-Path $OutputDir "kit.log"
$fixtureJson = Join-Path $OutputDir "fixture.json"
$markerJson = Join-Path $OutputDir "lifecycle_marker.json"
$analysisJson = Join-Path $OutputDir "native_crash_analysis.json"
$evidenceJson = Join-Path $OutputDir "evidence.json"
$arguments = @(
    $app, "--no-window",
    "--/app/settings/persistent=0", "--/app/settings/loadUserConfig=0",
    "--/app/window/hideUi=true", "--/log/file=$log",
    "--/campfire/crashFixture/output=$fixtureJson",
    "--/campfire/crashFixture/marker=$markerJson",
    "--/campfire/crashFixture/library=$triggerLibrary",
    "--exec", $probe
) + @(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $dumpDir)

$existingReporterIds = @(Get-Process -Name "crashreport.gui" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
$registryBefore = Get-CampfireCrashRegistrySnapshot
$started = [DateTimeOffset]::UtcNow
$process = Start-Process -FilePath $kit -ArgumentList $arguments -PassThru -WindowStyle Hidden
$deadline = $started.AddSeconds($TimeoutSeconds)
$crashObserved = $false
while (-not $process.WaitForExit(250)) {
    if (Test-Path -LiteralPath $log) {
        $crashObserved = (Select-String -LiteralPath $log -SimpleMatch "[crash] A crash has occurred" -Quiet)
        $probeFailure = (Select-String -LiteralPath $log -SimpleMatch "Traceback (most recent call last)" -Quiet)
        if ($probeFailure -and -not $crashObserved) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            throw "Native crash fixture probe failed before the intentional crash; see $log"
        }
    }
    if ([DateTimeOffset]::UtcNow -gt $deadline) {
        Stop-Process -Id $process.Id -Force
        throw "Native crash fixture timed out"
    }
}
$process.WaitForExit(); $process.Refresh()
$registryAfter = Get-CampfireCrashRegistrySnapshot
$registryUnchanged = (($registryBefore | ConvertTo-Json -Depth 12 -Compress) -eq ($registryAfter | ConvertTo-Json -Depth 12 -Compress))
if (-not $registryUnchanged) { throw "Native crash fixture changed relevant Windows crash-reporting registry settings" }
$exitCode = $process.ExitCode
$exitHex = '0x{0:X8}' -f ([int32]$exitCode)
$dumpDeadline = [DateTimeOffset]::UtcNow.AddSeconds(30)
do {
    $inventory = @(Get-CampfireCrashDumpInventory -DumpDir $dumpDir)
    if ($inventory.Count) { break }
    Start-Sleep -Milliseconds 250
} while ([DateTimeOffset]::UtcNow -lt $dumpDeadline)
$newReporterIds = @(Get-Process -Name "crashreport.gui" -ErrorAction SilentlyContinue | Where-Object { $_.Id -notin $existingReporterIds } | Select-Object -ExpandProperty Id)
if ($newReporterIds.Count) {
    foreach ($id in $newReporterIds) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }
    throw "Crash Reporter GUI appeared: $($newReporterIds -join ',')"
}
if (-not $crashObserved -or $exitHex -ne "0xC0000005") { throw "Expected native crash was not observed: crash=$crashObserved exit=$exitHex" }
if (-not $inventory.Count) { throw "Crash Reporter did not preserve a local dump" }
$uploadAttempts = @(Select-String -LiteralPath $log -SimpleMatch "Uploading minidump:")
$prevented = @(Select-String -LiteralPath $log -SimpleMatch "preventing upload of minidump due to user opt-out")
if ($uploadAttempts.Count -ne 0) { throw "Crash Reporter attempted an upload" }
$dump = @($inventory | Where-Object { $_.name -match '\.dmp(?:\.zip)?$' } | Select-Object -First 1)
if (-not $dump.Count) { throw "No parseable dump was preserved" }
& (Join-Path $release "kit\python\python.exe") $analyzer $dump[0].path --output $analysisJson
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$analysis = Get-Content -Raw -Encoding UTF8 $analysisJson | ConvertFrom-Json
$fixture = Get-Content -Raw -Encoding UTF8 $fixtureJson | ConvertFrom-Json
$marker = Get-Content -Raw -Encoding UTF8 $markerJson | ConvertFrom-Json
$evidence = [ordered]@{
    schema = "campfire.isolated-kit-native-crash-fixture-evidence.v1"
    status = "ok"
    started_utc = $started.ToString('o')
    elapsed_seconds = [Math]::Round(([DateTimeOffset]::UtcNow - $started).TotalSeconds, 3)
    exit_code = $exitCode
    exit_code_hex = $exitHex
    crash_log_detected = $crashObserved
    crash_reporter_gui_started = $false
    automatic_upload_attempt_count = $uploadAttempts.Count
    user_opt_out_log_count = $prevented.Count
    preserve_dump_effective = [bool]$fixture.settings.'/crashreporter/preserveDump'
    lifecycle_marker = $marker
    dump_inventory = $inventory
    exception = $analysis.exception
    native_stack = $analysis.native_stack
    dump_is_sensitive_git_ignored = $true
    relevant_crash_registry_unchanged = $registryUnchanged
    machine_wide_settings_changed = (-not $registryUnchanged)
}
[IO.File]::WriteAllText($evidenceJson, ($evidence | ConvertTo-Json -Depth 20) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host "Isolated Kit native crash fixture passed: $evidenceJson"
