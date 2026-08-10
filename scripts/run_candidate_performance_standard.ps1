param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
$release = Join-Path $root "_build\windows-x86_64\release"
$kit = Join-Path $release "kit\kit.exe"
$probe = Join-Path $PSScriptRoot "probe_candidate_performance_standard.py"
if (-not $OutputDir) { $OutputDir = Join-Path $root "artifacts\candidate-performance-standard" }
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $OutputDir) { throw "Candidate Performance validation refuses to reuse output: $OutputDir" }
New-Item -ItemType Directory -Path $OutputDir | Out-Null
$apps = [ordered]@{
    normal = Join-Path $release "apps\campfire.simulator.kit"
    benchmark = Join-Path $release "apps\campfire.simulator.benchmark.kit"
}
$entries = @()
foreach ($item in $apps.GetEnumerator()) {
    $dir = Join-Path $OutputDir $item.Key
    New-Item -ItemType Directory -Path $dir | Out-Null
    $app = New-CampfireIsolatedKitApp -SourceApp $item.Value
    $output = Join-Path $dir "effective_settings.json"
    $log = Join-Path $dir "kit.log"
    $args = @(
        $app, "--/app/file/ignoreUnsavedOnExit=true", "--/app/quitAfter=120000",
        "--/app/settings/persistent=0", "--/app/settings/loadUserConfig=0",
        "--/app/window/hideUi=false", "--/app/window/width=1280", "--/app/window/height=720",
        "--/app/viewport/defaults/fillViewport=false", "--/renderer/multiGpu/enabled=false",
        "--/exts/campfire.app/autoCreateScene=false", "--/log/file=$log",
        "--/campfire/candidatePerformance/output=$output",
        "--/campfire/candidatePerformance/appKind=$($item.Key)", "--exec", $probe
    ) + @(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir (Join-Path $dir "sensitive-crash-dumps"))
    $process = Start-Process -FilePath $kit -ArgumentList $args -PassThru
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds(180)
    $earlyFailure = $null
    while (-not $process.WaitForExit(250)) {
        if (Test-Path -LiteralPath $log) {
            foreach ($token in @("[crash] A crash has occurred", "IRenderSettings::getRenderSettings failed getting a stage-id", "Traceback (most recent call last)", "CUDA_ERROR_ILLEGAL_ADDRESS", "device lost", "invalid pointer", "Uploading minidump:")) {
                if (Select-String -LiteralPath $log -SimpleMatch $token -Quiet) { $earlyFailure = $token; break }
            }
        }
        if ($earlyFailure) { if ($earlyFailure -eq "[crash] A crash has occurred") { Start-Sleep -Seconds 5 }; if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }; throw "Candidate Performance $($item.Key) fail-fast: $earlyFailure" }
        if ([DateTimeOffset]::UtcNow -gt $deadline) { Stop-Process -Id $process.Id -Force; throw "Candidate Performance $($item.Key) timed out" }
    }
    $process.Refresh()
    if ($process.ExitCode -ne 0) { throw "Candidate Performance $($item.Key) exited $($process.ExitCode)" }
    $fatal = @("[crash] A crash has occurred", "IRenderSettings::getRenderSettings failed getting a stage-id", "Traceback (most recent call last)", "CUDA_ERROR_ILLEGAL_ADDRESS", "device lost", "invalid pointer", "Uploading minidump:")
    foreach ($token in $fatal) { if (@(Select-String -LiteralPath $log -SimpleMatch $token).Count) { throw "Candidate Performance $($item.Key) rejected by $token" } }
    $report = Get-Content -Raw -Encoding UTF8 $output | ConvertFrom-Json
    if ($report.status -ne "ok") { throw "Candidate Performance effective-setting gate failed for $($item.Key)" }
    $entries += $report
}
$gpu = $null
$nvidiaSmi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
if ($nvidiaSmi) {
    $line = & $nvidiaSmi.Source --query-gpu=name,driver_version,power.limit,enforced.power.limit --format=csv,noheader,nounits
    $parts = $line -split ','
    if ($parts.Count -ge 4) { $gpu = [ordered]@{name=$parts[0].Trim();driver=$parts[1].Trim();power_limit_w=[double]$parts[2].Trim();enforced_power_limit_w=[double]$parts[3].Trim()} }
}
$manifest = [ordered]@{
    schema = "campfire.candidate-performance-standard-validation.v1"
    status = "ok"
    standard = "Candidate Performance"
    comparison_presets = @("AutoBaseline", "CandidateBalanced")
    rejected_production_presets = @("Minimal", "AO OFF")
    entries = $entries
    gpu = $gpu
    visible_render_counter_is_display_present_fps = $false
}
[IO.File]::WriteAllText((Join-Path $OutputDir "manifest.json"), ($manifest | ConvertTo-Json -Depth 16) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host "Candidate Performance standard validation passed: $OutputDir"
