param(
    [string]$OutputDir = "",
    [ValidateRange(1, 3)]
    [int]$Runs = 3,
    [ValidateSet("normal", "developer", "benchmark")]
    [string[]]$Conditions = @("normal", "developer", "benchmark"),
    [switch]$VisibleWindow
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$release = Join-Path $root "_build\windows-x86_64\release"
$phase3Runner = Join-Path $PSScriptRoot "run_phase3.ps1"
$collector = Join-Path $PSScriptRoot "collect_phasev3tr_runs.py"
$diagnosticExtensionRoot = Join-Path $PSScriptRoot "phasev3tq_extension"
if (-not $OutputDir) { $OutputDir = Join-Path $root "artifacts\phasev3tr-debug-split" }
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath (Join-Path $OutputDir "manifest.json")) {
    throw "Phase V3T-R refuses to reuse an existing manifest: $OutputDir"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$candidateApps = Join-Path $OutputDir "candidate-apps"
New-Item -ItemType Directory -Force -Path $candidateApps | Out-Null
$builtNormal = Join-Path $release "apps\campfire.simulator.kit"
$candidateNormal = Join-Path $candidateApps "campfire.simulator.candidate.kit"
$candidateDeveloper = Join-Path $candidateApps "campfire.simulator.developer.candidate.kit"
$normalText = Get-Content -LiteralPath $builtNormal -Raw -Encoding UTF8
$normalText = $normalText -replace '(?m)^"omni\.kit\.developer\.bundle" = \{\}\r?\n', ''
$normalText = $normalText -replace '(?m)^\s*"omni\.kit\.(debug\.settings|dev\.utilities\.bundle|developer\.bundle)-[^\r\n]+\r?\n', ''
Set-Content -LiteralPath $candidateNormal -Value $normalText -Encoding UTF8
$developerText = @'
[package]
title = "Campfire Simulator Developer Candidate"
version = "0.1.0"
description = "Phase V3T-R isolated localhost debug candidate."
template_name = "kit_base_editor"

[dependencies]
"campfire.simulator.candidate" = {}
"omni.kit.developer.bundle" = {}

[settings.app]
window.title = "Campfire Simulator Developer Candidate"

[settings.exts."omni.kit.debug.python"]
host = "127.0.0.1"
port = 3000
mode = "listen"
waitForClient = false
'@
Set-Content -LiteralPath $candidateDeveloper -Value $developerText -Encoding UTF8

$apps = @{
    normal = $candidateNormal
    developer = $candidateDeveloper
    benchmark = Join-Path $release "apps\campfire.simulator.benchmark.kit"
}
foreach ($condition in $Conditions) {
    if (-not (Test-Path -LiteralPath $apps[$condition])) {
        throw "Phase V3T-R app is not built: $($apps[$condition])"
    }
}
$hashesBefore = @{}
foreach ($condition in @("normal", "developer", "benchmark")) {
    $hashesBefore[$condition] = (Get-FileHash -LiteralPath $apps[$condition] -Algorithm SHA256).Hash
}

$developerExtensions = @(
    "omni.kit.debug.python",
    "omni.kit.debug.settings",
    "omni.kit.debug.vscode",
    "omni.kit.dev.utilities.bundle",
    "omni.kit.developer.bundle",
    "omni.kit.widget.text_editor",
    "omni.kit.window.commands",
    "omni.kit.window.extensions",
    "omni.kit.window.script_editor"
)
$baseOrder = @("normal", "developer", "benchmark")
$orders = @()
for ($run = 0; $run -lt $Runs; $run++) {
    $rotated = @($baseOrder[$run..($baseOrder.Count - 1)] + $baseOrder[0..($run - 1)])
    if ($run -eq 0) { $rotated = @($baseOrder) }
    $orders += ,@($rotated | Where-Object { $Conditions -contains $_ })
}

function Get-NumberSummary {
    param([object[]]$Values)
    $values = @($Values | Where-Object { $null -ne $_ })
    if (-not $values.Count) { return $null }
    return [ordered]@{
        count = $values.Count
        mean = [Math]::Round(($values | Measure-Object -Average).Average, 4)
        min = [Math]::Round(($values | Measure-Object -Minimum).Minimum, 4)
        max = [Math]::Round(($values | Measure-Object -Maximum).Maximum, 4)
    }
}

function Read-GpuRows {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return @() }
    return @(Get-Content -LiteralPath $Path | ForEach-Object {
        $columns = $_ -split ','
        if ($columns.Count -ge 11) {
            [pscustomobject]@{
                timestamp = [DateTimeOffset]::ParseExact($columns[0].Trim(), 'yyyy/MM/dd HH:mm:ss.fff', $null)
                utilization = [double]$columns[1].Trim()
                memory_mib = [double]$columns[2].Trim()
                power_w = [double]$columns[3].Trim()
                graphics_clock_mhz = [double]$columns[4].Trim()
                sm_clock_mhz = [double]$columns[5].Trim()
                temperature_c = [double]$columns[6].Trim()
                pstate = $columns[7].Trim()
                power_limit_w = [double]$columns[8].Trim()
                enforced_power_limit_w = [double]$columns[9].Trim()
                perf_cap_reason = $columns[10].Trim()
            }
        }
    })
}

function Assert-NoKitProcess {
    $kit = Join-Path $release "kit\kit.exe"
    $running = @(Get-CimInstance Win32_Process -Filter "Name='kit.exe'" -ErrorAction SilentlyContinue | Where-Object {
        $_.ExecutablePath -and ([IO.Path]::GetFullPath($_.ExecutablePath) -eq [IO.Path]::GetFullPath($kit))
    })
    if ($running.Count) { throw "Phase V3T-R refuses overlapping Kit: $($running.ProcessId -join ',')" }
}

$nvidiaSmi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
for ($runIndex = 0; $runIndex -lt $orders.Count; $runIndex++) {
    $order = @($orders[$runIndex])
    for ($orderIndex = 0; $orderIndex -lt $order.Count; $orderIndex++) {
        $condition = $order[$orderIndex]
        Assert-NoKitProcess
        $name = "{0}_r{1}_o{2}" -f $condition, ($runIndex + 1), ($orderIndex + 1)
        $dir = Join-Path $OutputDir $name
        if (Test-Path -LiteralPath $dir) { throw "Phase V3T-R run already exists: $dir" }
        New-Item -ItemType Directory -Path $dir | Out-Null
        $kitLog = Join-Path $dir "kit.log"
        $diagnostic = Join-Path $dir "runtime_diagnostic.json"
        $gpuCsv = Join-Path $dir "gpu.csv"
        $monitor = $null
        if ($nvidiaSmi) {
            $monitorArgs = @(
                "--query-gpu=timestamp,utilization.gpu,memory.used,power.draw,clocks.current.graphics,clocks.current.sm,temperature.gpu,pstate,power.limit,enforced.power.limit,clocks_event_reasons.active",
                "--format=csv,noheader,nounits", "--loop-ms=250"
            )
            $monitor = Start-Process $nvidiaSmi.Source -ArgumentList $monitorArgs -RedirectStandardOutput $gpuCsv -PassThru -WindowStyle Hidden
        }
        $started = [DateTimeOffset]::UtcNow
        $timer = [Diagnostics.Stopwatch]::StartNew()
        try {
            $additional = @(
                "--ext-folder", $candidateApps,
                "--ext-folder", (Join-Path $release "apps"),
                "--ext-folder", $diagnosticExtensionRoot,
                "--enable", "omni.campfire.phasev3tq.diagnostic",
                "--/phasev3tq/output=$diagnostic",
                "--/phasev3tq/condition=$condition"
            )
            & $phase3Runner -OutputDir $dir -AppKind $(if ($condition -eq "benchmark") { "benchmark" } else { "normal" }) `
                -AppPath $apps[$condition] -InheritProductionV3Defaults -DisableMilestoneFrames `
                -IsolatedCrashSafety -KitLog $kitLog -CrashDumpDir (Join-Path $dir "sensitive-crash-dumps") `
                -AdditionalKitArguments $additional -AllowDebugExtensions:($condition -eq "developer") `
                -VisibleWindow:$VisibleWindow.IsPresent
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
        finally {
            $timer.Stop()
            if ($monitor -and -not $monitor.HasExited) {
                Stop-Process -Id $monitor.Id -Force
                Wait-Process -Id $monitor.Id -Timeout 5 -ErrorAction SilentlyContinue
            }
        }
        $summary = Get-Content -LiteralPath (Join-Path $dir "summary.json") -Raw -Encoding UTF8 | ConvertFrom-Json
        $runtime = Get-Content -LiteralPath $diagnostic -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($runtime.status -ne "ok") { throw "Runtime diagnostic did not close cleanly: $name" }
        $logLines = @(Get-Content -LiteralPath $kitLog)
        $startupOrder = @($logLines | ForEach-Object { if ($_ -match '\[ext:\s*([^\]]+)\]\s+startup') { $Matches[1] } })
        $enabledNames = @($startupOrder | ForEach-Object { $_ -replace '-\d.*$', '' } | Sort-Object -Unique)
        $developerPresent = @($developerExtensions | Where-Object { $enabledNames -contains $_ })
        $listenLines = @($logLines | Where-Object { $_ -match '\[omni\.kit\.debug\.python\] Listening python debugger on:' })
        if ($condition -eq "developer") {
            if ($developerPresent.Count -ne $developerExtensions.Count) { throw "Developer app lacks expected extensions: $name" }
            if ($listenLines.Count -ne 1 -or $listenLines[0] -notmatch "127\.0\.0\.1.*3000") { throw "Developer localhost listen gate failed: $name" }
        }
        elseif ($developerPresent.Count -or $listenLines.Count -or -not $summary.scenario.debugger_free) {
            throw "Debugger-free gate failed: $name"
        }
        if (-not $summary.scenario.wood_visual_v3.enabled -or $summary.flow.active_blocks_peak -le 0) {
            throw "V3/Flow production gate failed: $name"
        }
        if ($summary.wood.dry.mass_balance_error_kg -ne 0 -or $summary.wood.wet.mass_balance_error_kg -ne 0) {
            throw "Mass-balance gate failed: $name"
        }
    }
}

$appsUnchanged = $true
$appHashes = [ordered]@{}
foreach ($condition in @("normal", "developer", "benchmark")) {
    $after = (Get-FileHash -LiteralPath $apps[$condition] -Algorithm SHA256).Hash
    $changed = $hashesBefore[$condition] -ne $after
    if ($changed) { $appsUnchanged = $false }
    $appHashes[$condition] = [ordered]@{ path = $apps[$condition]; before = $hashesBefore[$condition]; after = $after; changed = $changed }
}
if (-not $appsUnchanged) { throw "Phase V3T-R changed a built app during measurement." }
$collectorArgs = @("--input", $OutputDir, "--candidate-apps", $candidateApps, "--output", (Join-Path $OutputDir "manifest.json"))
if ($VisibleWindow.IsPresent) { $collectorArgs += "--visible-window" }
python $collector @collectorArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Phase V3T-R complete: $((Get-ChildItem $OutputDir -Directory).Count) isolated process(es)."
