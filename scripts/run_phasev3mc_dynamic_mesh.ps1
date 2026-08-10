param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "isolated_kit_crash_safety.ps1")
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = New-CampfireIsolatedKitApp -SourceApp (Join-Path $releaseRoot "apps\campfire.simulator.kit")
$probeScript = Join-Path $PSScriptRoot "probe_phasev3mc_dynamic_mesh.py"
$nativeDll = Join-Path $releaseRoot "exts\campfire.app\bin\campfire_wood_native.dll"
if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phasev3mc" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$kitLog = Join-Path $OutputDir "kit.log"
$dumpDir = Join-Path $OutputDir "sensitive-crash-dumps"
$probe = Join-Path $OutputDir "dynamic_mesh_probe.json"
$captures = Join-Path $OutputDir "captures"
$gpuCsv = Join-Path $OutputDir "gpu_samples.csv"
$gpuError = Join-Path $OutputDir "gpu_monitor.stderr.log"
if (Test-Path -LiteralPath $OutputDir) {
    throw "Phase V3M-C refuses to reuse output: $OutputDir"
}
New-Item -ItemType Directory -Path $captures -Force | Out-Null
if (-not (Test-Path -LiteralPath $nativeDll)) {
    throw "Phase V3M-C requires the packaged production native library: $nativeDll"
}

$gpuMonitor = $null
$nvidiaSmi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
if ($nvidiaSmi) {
    $gpuMonitor = Start-Process -FilePath $nvidiaSmi.Source -ArgumentList @(
        "--query-gpu=timestamp,utilization.gpu,memory.used,power.draw,clocks.current.graphics,clocks.current.sm,temperature.gpu,pstate,power.limit,enforced.power.limit",
        "--format=csv,noheader,nounits",
        "--loop-ms=250"
    ) -RedirectStandardOutput $gpuCsv -RedirectStandardError $gpuError -PassThru -WindowStyle Hidden
}
try {
    $arguments = @(
        $app,
        "--/app/file/ignoreUnsavedOnExit=true",
        "--/app/quitAfter=10000",
        "--/app/settings/persistent=0",
        "--/app/settings/loadUserConfig=0",
        "--/exts/campfire.app/autoCreateScene=false",
        "--/app/viewport/defaults/fillViewport=false",
        "--/phasev3mc/output=$probe",
        "--/phasev3mc/captureDir=$captures",
        "--/phasev3mc/nativeLibrary=$nativeDll",
        "--/log/file=$kitLog",
        "--exec",
        $probeScript
    ) + @(Get-CampfireIsolatedKitCrashSafetyArgs -DumpDir $dumpDir)
    $process = Start-Process $kit -ArgumentList $arguments -PassThru
    $process.WaitForExit()
    $process.Refresh()
    $exitCode = $process.ExitCode
}
finally {
    if ($gpuMonitor -and -not $gpuMonitor.HasExited) {
        Stop-Process -Id $gpuMonitor.Id -Force
        Wait-Process -Id $gpuMonitor.Id -Timeout 5 -ErrorAction SilentlyContinue
    }
}
$fatalTokens = @(
    "IRenderSettings::getRenderSettings failed getting a stage-id",
    "Traceback (most recent call last)",
    "CUDA_ERROR_ILLEGAL_ADDRESS",
    "device lost",
    "invalid pointer",
    "[crash] A crash has occurred"
)
$fatalCounts = [ordered]@{}
foreach ($token in $fatalTokens) {
    $fatalCounts[$token] = if (Test-Path -LiteralPath $kitLog) {
        @(Select-String -LiteralPath $kitLog -SimpleMatch $token).Count
    } else { 0 }
}
$crashSafety = Get-CampfireCrashSafetyEvidence -LogPath $kitLog -DumpDir $dumpDir
$uploadAttempts = if (Test-Path -LiteralPath $kitLog) {
    @(Select-String -LiteralPath $kitLog -SimpleMatch "Uploading minidump:").Count
} else { 0 }
if (
    $exitCode -ne 0 -or
    ($fatalCounts.Values | Measure-Object -Sum).Sum -ne 0 -or
    @($crashSafety.dump_inventory).Count -ne 0 -or
    $uploadAttempts -ne 0
) {
    throw "Phase V3M-C rejected isolated Kit run; no retry: exit=$exitCode, fatal=$($fatalCounts | ConvertTo-Json -Compress), dumps=$(@($crashSafety.dump_inventory).Count), uploads=$uploadAttempts"
}
$result = Get-Content -LiteralPath $probe -Raw | ConvertFrom-Json
if ($result.status -ne "qualified") {
    throw "Phase V3M-C dynamic Mesh probe did not qualify: $probe"
}
$gpuSamples = @()
if (Test-Path -LiteralPath $gpuCsv) {
    $gpuSamples = @(Get-Content -LiteralPath $gpuCsv | ForEach-Object {
        $columns = $_ -split ','
        if ($columns.Count -ge 3) {
            [PSCustomObject]@{
                UtilizationPercent = [double]$columns[1].Trim()
                MemoryUsedMiB = [double]$columns[2].Trim()
            }
        }
    })
}
$gpu = [ordered]@{
    samples = $gpuSamples.Count
    interval_ms = 250
    max_utilization_percent = $null
    mean_utilization_percent = $null
    min_memory_used_mib = $null
    max_memory_used_mib = $null
    memory_span_mib = $null
    method = "Whole-GPU nvidia-smi sampling; the memory span is not a provider-scoped allocation."
}
if ($gpuSamples.Count -gt 0) {
    $utilization = @($gpuSamples | ForEach-Object { $_.UtilizationPercent })
    $memory = @($gpuSamples | ForEach-Object { $_.MemoryUsedMiB })
    $gpu.max_utilization_percent = ($utilization | Measure-Object -Maximum).Maximum
    $gpu.mean_utilization_percent = [math]::Round(($utilization | Measure-Object -Average).Average, 2)
    $gpu.min_memory_used_mib = ($memory | Measure-Object -Minimum).Minimum
    $gpu.max_memory_used_mib = ($memory | Measure-Object -Maximum).Maximum
    $gpu.memory_span_mib = $gpu.max_memory_used_mib - $gpu.min_memory_used_mib
}
$result | Add-Member -NotePropertyName runner_gpu -NotePropertyValue $gpu -Force
$result | Add-Member -NotePropertyName crash_safety -NotePropertyValue ([ordered]@{
    process_exit_code = $exitCode
    fatal_log_counts = $fatalCounts
    dump_count = @($crashSafety.dump_inventory).Count
    automatic_upload_attempt_count = $uploadAttempts
    automatic_upload_disabled_by = @($crashSafety.automatic_upload_disabled_by)
    preserve_dump_requested = $crashSafety.preserve_dump_requested
    configured_log_lines = @($crashSafety.configured_log_lines)
}) -Force
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($probe, ($result | ConvertTo-Json -Depth 12) + [Environment]::NewLine, $utf8NoBom)
Write-Host ("Phase V3M-C: status={0}, gates={1}/{2}, publication p95={3:N4} ms" -f $result.status, @($result.gates.psobject.Properties | Where-Object { $_.Value }).Count, @($result.gates.psobject.Properties).Count, $result.performance.visual_publication.total_ms.p95_ms)
