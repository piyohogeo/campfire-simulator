param(
    [string]$OutputDir = "",
    [int]$Warmup = 20,
    [int]$Samples = 120,
    [int]$Runs = 3,
    [int]$CorrectnessSamples = 10,
    [int]$LongUpdates = 1200,
    [switch]$Quick,
    [switch]$SkipAnalyze,
    [switch]$AnalyzeRetainedEvidence
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$probeScript = Join-Path $PSScriptRoot "probe_phasev3tf_production_gpu.py"
$analyzer = Join-Path $PSScriptRoot "analyze_phasev3tf_production_gpu.py"
$rejectionFinalizer = Join-Path $PSScriptRoot "finalize_phasev3tf_rejection.py"
$kitPython = Join-Path $releaseRoot "kit\python\python.exe"
$nativeDll = Join-Path $repositoryRoot "artifacts\phasev2\native-build\campfire_wood_native.dll"
$lifecycleExtension = Join-Path $PSScriptRoot "phasev3te_extension"
if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phasev3tf" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
if ($AnalyzeRetainedEvidence) {
    & $kitPython $rejectionFinalizer
    exit $LASTEXITCODE
}
$productionConsumer = Join-Path $repositoryRoot "source\extensions\campfire.app\campfire\app\wood_visual_v3.py"
if (-not (Select-String -LiteralPath $productionConsumer -SimpleMatch "gpu_transport_enabled" -Quiet)) {
    throw "Phase V3T-F runtime probe is archived: the candidate production transport was intentionally reverted after shutdown crash 0xC0000005. Use -AnalyzeRetainedEvidence to regenerate the rejection report without exercising the reverted candidate."
}
if (-not (Test-Path -LiteralPath $nativeDll)) {
    throw "Phase V3T-F requires the qualified V2 native library: $nativeDll"
}
if ($Quick) {
    $Runs = 1
    $Warmup = [Math]::Max(2, [Math]::Min($Warmup, 4))
    $Samples = [Math]::Max(8, [Math]::Min($Samples, 12))
    $CorrectnessSamples = [Math]::Max(3, [Math]::Min($CorrectnessSamples, 4))
    $LongUpdates = [Math]::Max(30, [Math]::Min($LongUpdates, 60))
}

$runsManifest = @()
for ($processIndex = 0; $processIndex -lt ($Runs + 1); $processIndex++) {
    $lifecycleRun = $processIndex -eq $Runs
    $scenario = if ($lifecycleRun) { "lifecycle" } else { "performance" }
    $run = if ($lifecycleRun) { 0 } else { $processIndex }
    $runName = if ($lifecycleRun) { "lifecycle" } else { "performance_{0}" -f ($run + 1) }
    $runDir = Join-Path $OutputDir $runName
    $captures = Join-Path $runDir "captures"
    $raw = Join-Path $runDir "samples.json"
    $kitLog = Join-Path $runDir "kit.log"
    $gpuCsv = Join-Path $runDir "gpu_samples.csv"
    New-Item -ItemType Directory -Path $captures -Force | Out-Null
    Remove-Item -LiteralPath $raw,$kitLog,$gpuCsv -Force -ErrorAction SilentlyContinue
    $monitor = $null
    $nvidiaSmi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
    if ($nvidiaSmi) {
        $monitor = Start-Process -FilePath $nvidiaSmi.Source -ArgumentList @(
            "--query-gpu=timestamp,utilization.gpu,memory.used",
            "--format=csv,noheader,nounits",
            "--loop-ms=250"
        ) -RedirectStandardOutput $gpuCsv -PassThru -WindowStyle Hidden
    }
    try {
        & $kit @(
            $app,
            "--no-window",
            "--/app/file/ignoreUnsavedOnExit=true",
            "--/app/quitAfter=30000",
            "--/app/settings/persistent=0",
            "--/app/settings/loadUserConfig=0",
            "--/app/window/hideUi=true",
            "--/app/viewport/defaults/fillViewport=false",
            "--/renderer/multiGpu/enabled=false",
            "--/rtx/flow/enabled=true",
            "--/exts/campfire.app/autoCreateScene=false",
            "--/exts/campfire.app/woodVisualV3Enabled=false",
            "--/exts/campfire.app/woodVisualV3GpuTransportEnabled=false",
            "--ext-folder", $lifecycleExtension,
            "--enable", "omni.campfire.phasev3te_lifecycle",
            "--/log/file=$kitLog",
            "--/phasev3tf/output=$raw",
            "--/phasev3tf/captureDir=$captures",
            "--/phasev3tf/nativeLibrary=$nativeDll",
            "--/phasev3tf/run=$run",
            "--/phasev3tf/warmup=$Warmup",
            "--/phasev3tf/samples=$Samples",
            "--/phasev3tf/correctness=$CorrectnessSamples",
            "--/phasev3tf/longUpdates=$LongUpdates",
            "--/phasev3tf/lifecycle=$lifecycleRun",
            "--/phasev3tf/scenario=$scenario",
            "--exec", $probeScript
        )
        if ($LASTEXITCODE -ne 0) { throw "Phase V3T-F Kit process failed: $runName" }
    }
    finally {
        if ($monitor -and -not $monitor.HasExited) {
            Stop-Process -Id $monitor.Id -Force
            Wait-Process -Id $monitor.Id -Timeout 5 -ErrorAction SilentlyContinue
        }
    }
    $result = Get-Content -Raw -LiteralPath $raw | ConvertFrom-Json
    if ($result.status -ne "ok") { throw "Phase V3T-F probe error: $($result.error)" }
    $runsManifest += [ordered]@{
        run = if ($lifecycleRun) { $null } else { $run + 1 }
        scenario = $scenario
        raw = $raw
        captures = $captures
        kit_log = $kitLog
        gpu_samples = if (Test-Path -LiteralPath $gpuCsv) { $gpuCsv } else { $null }
    }
}

$manifest = [ordered]@{
    schema = "campfire.phasev3tf.manifest.v1"
    kit = "110.2"
    flow = "110.0.0"
    runs = $Runs
    warmup = $Warmup
    samples = $Samples
    correctness_samples = $CorrectnessSamples
    long_updates = $LongUpdates
    production_default_changed = $false
    entries = $runsManifest
}
$manifestPath = Join-Path $OutputDir "manifest.json"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText(
    $manifestPath,
    ($manifest | ConvertTo-Json -Depth 8) + [Environment]::NewLine,
    $utf8NoBom
)
if (-not $SkipAnalyze) {
    & $kitPython $analyzer --manifest $manifestPath
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
