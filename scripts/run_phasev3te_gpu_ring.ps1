param(
    [string]$OutputDir = "",
    [int]$Warmup = 20,
    [int]$Samples = 120,
    [int]$Runs = 3,
    [int]$CorrectnessSamples = 10,
    [int]$LongUpdates = 1200,
    [ValidateSet("all", "matrix", "lifecycle")]
    [string]$ScenarioFilter = "all",
    [switch]$Resume,
    [switch]$SkipAnalyze,
    [switch]$Quick
)

$ErrorActionPreference = "Stop"
$processPath = $env:Path
$pathKeys = @([System.Environment]::GetEnvironmentVariables().Keys | Where-Object { $_ -ieq "path" })
if ($pathKeys.Count -gt 1) {
    [System.Environment]::SetEnvironmentVariable("Path", $null, [System.EnvironmentVariableTarget]::Process)
    [System.Environment]::SetEnvironmentVariable("Path", $processPath, [System.EnvironmentVariableTarget]::Process)
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$probe = Join-Path $PSScriptRoot "probe_phasev3te_gpu_ring.py"
$analyzer = Join-Path $PSScriptRoot "analyze_phasev3te_gpu_ring.py"
$lifecycleExtension = Join-Path $PSScriptRoot "phasev3te_extension"
$kitPython = Join-Path $releaseRoot "kit\python\python.exe"
if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phasev3te" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$atlases = @(
    [ordered]@{ width = 96; height = 15 },
    [ordered]@{ width = 120; height = 60 }
)
if ($Quick) {
    $Runs = 1
    $Warmup = [Math]::Max(2, $Warmup)
    $Samples = [Math]::Max(100, $Samples)
    $CorrectnessSamples = [Math]::Max(3, [Math]::Min(4, $CorrectnessSamples))
    $LongUpdates = [Math]::Max(30, [Math]::Min(60, $LongUpdates))
    $atlases = @([ordered]@{ width = 96; height = 15 })
}

$nvidiaSmi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
$gpuIdentity = $null
if ($nvidiaSmi) {
    $gpuIdentity = @(& $nvidiaSmi.Source --query-gpu=index,name,uuid,pci.bus_id,driver_version --format=csv,noheader,nounits)
}

function Invoke-PhaseV3TEProcess {
    param(
        [string]$Name,
        [string]$Scenario,
        [int]$Width,
        [int]$Height,
        [int]$RunIndex
    )
    $runDir = Join-Path $OutputDir $Name
    New-Item -ItemType Directory -Path $runDir -Force | Out-Null
    $raw = Join-Path $runDir "samples.json"
    $captures = Join-Path $runDir "captures"
    $gpuCsv = Join-Path $runDir "gpu_samples.csv"
    $gpuError = Join-Path $runDir "gpu_monitor.stderr.log"
    $kitLog = Join-Path $runDir "kit.log"
    if ($Resume -and (Test-Path -LiteralPath $raw)) {
        try {
            $existing = Get-Content -Raw -LiteralPath $raw | ConvertFrom-Json
            if ($existing.status -eq "ok") {
                return [ordered]@{
                    name = $Name
                    scenario = $Scenario
                    atlas = "${Width}x${Height}"
                    run = $RunIndex + 1
                    samples = $raw
                    captures = $captures
                    gpu_samples = if (Test-Path -LiteralPath $gpuCsv) { $gpuCsv } else { $null }
                    kit_log = if (Test-Path -LiteralPath $kitLog) { $kitLog } else { $null }
                }
            }
        }
        catch {
            # Incomplete or malformed interrupted output is rerun below.
        }
    }
    Remove-Item -LiteralPath $raw,$gpuCsv,$gpuError,$kitLog -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $captures) { Remove-Item -LiteralPath $captures -Recurse -Force }
    New-Item -ItemType Directory -Path $captures -Force | Out-Null
    $monitor = $null
    if ($nvidiaSmi) {
        $monitor = Start-Process -FilePath $nvidiaSmi.Source -ArgumentList @(
            "--query-gpu=timestamp,utilization.gpu,memory.used",
            "--format=csv,noheader,nounits",
            "--loop-ms=250"
        ) -RedirectStandardOutput $gpuCsv -RedirectStandardError $gpuError -PassThru -WindowStyle Hidden
    }
    try {
        $kitOutput = & $kit @(
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
            "--/exts/campfire.app/residentPointApplicationEnabled=false",
            "--/exts/campfire.app/residentPointRigidLayoutEnabled=false",
            "--/exts/campfire.app/woodVisualV3Enabled=false",
            "--ext-folder", $lifecycleExtension,
            "--enable", "omni.campfire.phasev3te_lifecycle",
            "--/log/file=$kitLog",
            "--/phasev3te/output=$raw",
            "--/phasev3te/captureDir=$captures",
            "--/phasev3te/scenario=$Scenario",
            "--/phasev3te/width=$Width",
            "--/phasev3te/height=$Height",
            "--/phasev3te/run=$RunIndex",
            "--/phasev3te/warmup=$Warmup",
            "--/phasev3te/samples=$Samples",
            "--/phasev3te/correctness=$CorrectnessSamples",
            "--/phasev3te/longUpdates=$LongUpdates",
            "--exec", $probe
        )
        $kitExitCode = $LASTEXITCODE
        if ($kitOutput) { $kitOutput | ForEach-Object { Write-Host $_ } }
        if ($kitExitCode -ne 0) { throw "Phase V3T-E Kit process failed: $Name" }
    }
    finally {
        if ($monitor -and -not $monitor.HasExited) {
            Stop-Process -Id $monitor.Id -Force
            Wait-Process -Id $monitor.Id -Timeout 5 -ErrorAction SilentlyContinue
        }
    }
    $result = Get-Content -Raw -LiteralPath $raw | ConvertFrom-Json
    if ($result.status -ne "ok") { throw "Phase V3T-E probe error in ${Name}: $($result.error)" }
    return [ordered]@{
        name = $Name
        scenario = $Scenario
        atlas = "${Width}x${Height}"
        run = $RunIndex + 1
        samples = $raw
        captures = $captures
        gpu_samples = if (Test-Path -LiteralPath $gpuCsv) { $gpuCsv } else { $null }
        kit_log = if (Test-Path -LiteralPath $kitLog) { $kitLog } else { $null }
    }
}

$manifestRuns = @()
if ($ScenarioFilter -in @("all", "matrix")) {
    for ($run = 0; $run -lt $Runs; $run++) {
        $orderedAtlases = if (($run % 2) -eq 0) { $atlases } else { @($atlases[1], $atlases[0]) }
        if ($atlases.Count -eq 1) { $orderedAtlases = $atlases }
        foreach ($atlas in $orderedAtlases) {
            $name = "matrix_{0}x{1}_r{2}" -f $atlas.width, $atlas.height, ($run + 1)
            $manifestRuns += Invoke-PhaseV3TEProcess -Name $name -Scenario "matrix" -Width $atlas.width -Height $atlas.height -RunIndex $run
        }
    }
}

if ($ScenarioFilter -in @("all", "lifecycle")) {
    $lifecycle = Invoke-PhaseV3TEProcess -Name "lifecycle_120x60" -Scenario "lifecycle" -Width 120 -Height 60 -RunIndex 0
    $manifestRuns += $lifecycle
}
$manifest = [ordered]@{
    schema = "campfire.phasev3te.matrix.v1"
    kit = "110.2"
    flow = "110.0.0"
    warmup_per_mode = $Warmup
    samples_per_mode = $Samples
    correctness_samples_per_mode = $CorrectnessSamples
    independent_runs = $Runs
    long_updates = $LongUpdates
    gpu_identity = $gpuIdentity
    production_defaults_changed = $false
    runs = $manifestRuns
}
$manifestPath = Join-Path $OutputDir "matrix_manifest.json"
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding utf8
if (-not $SkipAnalyze -and $ScenarioFilter -eq "all") {
    & $kitPython $analyzer --manifest $manifestPath
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
