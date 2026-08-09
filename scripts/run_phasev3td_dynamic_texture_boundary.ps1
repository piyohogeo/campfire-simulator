param(
    [string]$OutputDir = "",
    [int]$Warmup = 20,
    [int]$Samples = 120,
    [int]$Runs = 3,
    [string]$ModeFilter = "",
    [switch]$SkipAnalyze,
    [switch]$Quick
)

$ErrorActionPreference = "Stop"
# Some Codex/VS Code hosts expose both PATH and Path. Start-Process rejects
# that case-insensitive duplicate while constructing the child environment.
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
$providerOnlyApp = Join-Path $PSScriptRoot "phasev3td_provider_only.kit"
$probe = Join-Path $PSScriptRoot "probe_phasev3td_dynamic_texture_boundary.py"
$analyzer = Join-Path $PSScriptRoot "analyze_phasev3td_dynamic_texture_boundary.py"
$kitPython = Join-Path $releaseRoot "kit\python\python.exe"
if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phasev3td" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$modes = @(
    "cpu_unconnected_fixed",
    "cpu_unconnected_changing",
    "cpu_connected_no_rtx",
    "cpu_rtx_flow_off",
    "cpu_rtx_flow_on",
    "gpu_rtx_flow_off",
    "gpu_rtx_flow_on"
)
if ($ModeFilter) {
    $requestedModes = @($ModeFilter.Split(",", [System.StringSplitOptions]::RemoveEmptyEntries) | ForEach-Object { $_.Trim() })
    $unknownModes = @($requestedModes | Where-Object { $_ -notin $modes })
    if ($unknownModes.Count) { throw "Unknown Phase V3T-D modes: $($unknownModes -join ', ')" }
    $modes = $requestedModes
}
$atlases = @(
    [ordered]@{ width = 96; height = 15 },
    [ordered]@{ width = 120; height = 60 }
)
if ($Quick) {
    $modes = @("cpu_unconnected_fixed", "cpu_rtx_flow_off", "gpu_rtx_flow_off")
    $atlases = @([ordered]@{ width = 96; height = 15 })
    $Warmup = [Math]::Max($Warmup, 2)
    $Samples = [Math]::Max($Samples, 100)
    $Runs = 1
}
$manifestRuns = @()
$nvidiaSmi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
for ($run = 0; $run -lt $Runs; $run++) {
    $orderedModes = @($modes[$run..($modes.Count - 1)] + $modes[0..([Math]::Max(0, $run - 1))])
    if ($run -eq 0) { $orderedModes = $modes }
    foreach ($mode in $orderedModes) {
        foreach ($atlas in $atlases) {
            $name = "{0}_{1}x{2}_r{3}" -f $mode, $atlas.width, $atlas.height, ($run + 1)
            $runDir = Join-Path $OutputDir $name
            New-Item -ItemType Directory -Path $runDir -Force | Out-Null
            $raw = Join-Path $runDir "samples.json"
            $gpuCsv = Join-Path $runDir "gpu_samples.csv"
            $gpuError = Join-Path $runDir "gpu_monitor.stderr.log"
            Remove-Item -LiteralPath $raw,$gpuCsv,$gpuError -Force -ErrorAction SilentlyContinue
            $monitor = $null
            if ($nvidiaSmi) {
                $monitor = Start-Process -FilePath $nvidiaSmi.Source -ArgumentList @(
                    "--query-gpu=timestamp,utilization.gpu,memory.used",
                    "--format=csv,noheader,nounits",
                    "--loop-ms=250"
                ) -RedirectStandardOutput $gpuCsv -RedirectStandardError $gpuError -PassThru -WindowStyle Hidden
            }
            try {
                $selectedApp = if ($mode -like "*_rtx_flow_*") { $app } else { $providerOnlyApp }
                & $kit @(
                    $selectedApp,
                    "--no-window",
                    "--/app/file/ignoreUnsavedOnExit=true",
                    "--/app/quitAfter=30000",
                    "--/app/settings/persistent=0",
                    "--/app/settings/loadUserConfig=0",
                    "--/exts/campfire.app/autoCreateScene=false",
                    "--/app/viewport/defaults/fillViewport=false",
                    "--/rtx/flow/enabled=$($mode.EndsWith('flow_on').ToString().ToLowerInvariant())",
                    "--/phasev3td/output=$raw",
                    "--/phasev3td/mode=$mode",
                    "--/phasev3td/width=$($atlas.width)",
                    "--/phasev3td/height=$($atlas.height)",
                    "--/phasev3td/run=$run",
                    "--/phasev3td/warmup=$Warmup",
                    "--/phasev3td/samples=$Samples",
                    "--exec", $probe
                )
                if ($LASTEXITCODE -ne 0) { throw "Phase V3T-D process failed: $name" }
            }
            finally {
                if ($monitor -and -not $monitor.HasExited) {
                    Stop-Process -Id $monitor.Id -Force
                    Wait-Process -Id $monitor.Id -Timeout 5 -ErrorAction SilentlyContinue
                }
            }
            $result = Get-Content -Raw -LiteralPath $raw | ConvertFrom-Json
            if ($result.status -ne "ok") { throw "Phase V3T-D probe error in ${name}: $($result.error)" }
            $manifestRuns += [ordered]@{
                mode = $mode
                atlas = "$($atlas.width)x$($atlas.height)"
                run = $run + 1
                samples = $raw
                gpu_samples = if (Test-Path -LiteralPath $gpuCsv) { $gpuCsv } else { $null }
            }
        }
    }
}
$manifest = [ordered]@{
    schema = "campfire.phasev3td.matrix.v1"
    warmup_per_case = $Warmup
    samples_per_case = $Samples
    independent_runs = $Runs
    same_gpu = $true
    runs = $manifestRuns
}
$manifestPath = Join-Path $OutputDir "matrix_manifest.json"
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding utf8
if (-not $SkipAnalyze) {
    & $kitPython $analyzer --manifest $manifestPath
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
