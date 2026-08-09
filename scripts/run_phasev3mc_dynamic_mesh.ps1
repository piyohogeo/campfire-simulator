param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$probeScript = Join-Path $PSScriptRoot "probe_phasev3mc_dynamic_mesh.py"
$nativeDll = Join-Path $repositoryRoot "artifacts\phasev2\native-build\campfire_wood_native.dll"
if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phasev3mc" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$probe = Join-Path $OutputDir "dynamic_mesh_probe.json"
$captures = Join-Path $OutputDir "captures"
$gpuCsv = Join-Path $OutputDir "gpu_samples.csv"
$gpuError = Join-Path $OutputDir "gpu_monitor.stderr.log"
New-Item -ItemType Directory -Path $captures -Force | Out-Null
if (-not (Test-Path -LiteralPath $nativeDll)) {
    throw "Phase V3M-C requires the previously qualified V2 native library: $nativeDll"
}

$gpuMonitor = $null
$nvidiaSmi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
if ($nvidiaSmi) {
    $gpuMonitor = Start-Process -FilePath $nvidiaSmi.Source -ArgumentList @(
        "--query-gpu=timestamp,utilization.gpu,memory.used",
        "--format=csv,noheader,nounits",
        "--loop-ms=250"
    ) -RedirectStandardOutput $gpuCsv -RedirectStandardError $gpuError -PassThru -WindowStyle Hidden
}
try {
    & $kit @(
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
        "--exec",
        $probeScript
    )
    $exitCode = $LASTEXITCODE
}
finally {
    if ($gpuMonitor -and -not $gpuMonitor.HasExited) {
        Stop-Process -Id $gpuMonitor.Id -Force
        Wait-Process -Id $gpuMonitor.Id -Timeout 5 -ErrorAction SilentlyContinue
    }
}
if ($exitCode -ne 0) { exit $exitCode }
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
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($probe, ($result | ConvertTo-Json -Depth 12) + [Environment]::NewLine, $utf8NoBom)
Write-Host ("Phase V3M-C: status={0}, gates={1}/{2}, publication p95={3:N4} ms" -f $result.status, @($result.gates.psobject.Properties | Where-Object { $_.Value }).Count, @($result.gates.psobject.Properties).Count, $result.performance.visual_publication.total_ms.p95_ms)
