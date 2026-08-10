param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
$release = Join-Path $root "_build\windows-x86_64\release"
$kit = Join-Path $release "kit\kit.exe"
$app = Join-Path $release "kit\apps\omni.app.mini.kit"
$app = New-CampfireIsolatedKitApp -SourceApp $app
$probe = Join-Path $PSScriptRoot "probe_isolated_kit_crash_settings.py"
if (-not $OutputDir) { $OutputDir = Join-Path $root "artifacts\isolated-kit-crash-safety-smoke" }
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $OutputDir) { throw "Crash-safety smoke refuses to reuse output: $OutputDir" }
New-Item -ItemType Directory -Path $OutputDir | Out-Null
$dumpDir = Join-Path $OutputDir "sensitive-crash-dumps"
$log = Join-Path $OutputDir "kit.log"
$settingsJson = Join-Path $OutputDir "effective_settings.json"
$evidenceJson = Join-Path $OutputDir "evidence.json"
$arguments = @(
    $app,
    "--no-window",
    "--/app/file/ignoreUnsavedOnExit=true",
    "--/app/quitAfter=60000",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/app/window/hideUi=true",
    "--/log/file=$log",
    "--/campfire/crashSafety/output=$settingsJson",
    "--exec", $probe
) + @(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $dumpDir)

$registryBefore = Get-CampfireCrashRegistrySnapshot
$process = Start-Process -FilePath $kit -ArgumentList $arguments -PassThru -WindowStyle Hidden
if (-not $process.WaitForExit(90000)) {
    Stop-Process -Id $process.Id -Force
    throw "Crash-safety smoke timed out"
}
$process.Refresh()
$registryAfter = Get-CampfireCrashRegistrySnapshot
$registryUnchanged = (($registryBefore | ConvertTo-Json -Depth 12 -Compress) -eq ($registryAfter | ConvertTo-Json -Depth 12 -Compress))
if (-not $registryUnchanged) { throw "Crash-safety smoke changed relevant Windows crash-reporting registry settings" }
if ($process.ExitCode -ne 0) { throw "Crash-safety smoke exited $($process.ExitCode)" }
$settingsReport = Get-Content -Raw -Encoding UTF8 $settingsJson | ConvertFrom-Json
if (-not $settingsReport.all_gates_passed) { throw "Crash-safety effective-setting gate failed" }
$startupUploadLines = @(Select-String -LiteralPath $log -SimpleMatch "upload enabled:")
if (@($startupUploadLines | Where-Object { $_.Line -match "upload enabled:\s*true" }).Count -ne 0) {
    throw "Crash Reporter startup log reported upload enabled"
}
$evidence = Get-CampfireCrashSafetyEvidence -LogPath $log -DumpDir $dumpDir
$payload = [ordered]@{
    schema = "campfire.isolated-kit-crash-safety-smoke.v1"
    status = "ok"
    process_exit_code = $process.ExitCode
    effective_settings = $settingsReport.effective_settings
    gates = $settingsReport.gates
    startup_upload_log = @($startupUploadLines | ForEach-Object { $_.Line })
    crash_reporter = $evidence
    popup_expected = $false
    interactive_input_supplied = $false
    relevant_crash_registry_unchanged = $registryUnchanged
    machine_wide_settings_changed = (-not $registryUnchanged)
}
[IO.File]::WriteAllText($evidenceJson, ($payload | ConvertTo-Json -Depth 12) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host "Isolated Kit crash-safety smoke passed: $evidenceJson"
