param(
    [string]$OutputDir = "",
    [int]$Warmup = 20,
    [int]$Updates = 120,
    [int]$BaselineRuns = 10,
    [int]$ResourceRuns = 3,
    [int]$SequenceRuns = 10,
    [int]$TimeoutSeconds = 180,
    [switch]$Quick,
    [switch]$Resume,
    [switch]$SkipAnalyze
)

$ErrorActionPreference = "Stop"
$processPath = $env:Path
$pathKeys = @([Environment]::GetEnvironmentVariables().Keys | Where-Object { $_ -ieq "path" })
if ($pathKeys.Count -gt 1) {
    [Environment]::SetEnvironmentVariable("Path", $null, [EnvironmentVariableTarget]::Process)
    [Environment]::SetEnvironmentVariable("Path", $processPath, [EnvironmentVariableTarget]::Process)
}
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$probe = Join-Path $PSScriptRoot "probe_phasev3tg_shutdown.py"
$extension = Join-Path $PSScriptRoot "phasev3tg_extension"
$analyzer = Join-Path $PSScriptRoot "analyze_phasev3tg_shutdown.py"
$kitPython = Join-Path $releaseRoot "kit\python\python.exe"
if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phasev3tg" }
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
if ($Quick) {
    $BaselineRuns = 1
    $ResourceRuns = 1
    $SequenceRuns = 1
    $Warmup = [Math]::Max(2, [Math]::Min(4, $Warmup))
    $Updates = [Math]::Max(8, [Math]::Min(12, $Updates))
}

$nvidiaSmi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
$entries = [System.Collections.Generic.List[object]]::new()

function Assert-NoIsolatedKit {
    $existing = @(Get-CimInstance Win32_Process -Filter "Name='kit.exe'" -ErrorAction SilentlyContinue | Where-Object {
        $_.ExecutablePath -and ([IO.Path]::GetFullPath($_.ExecutablePath) -eq [IO.Path]::GetFullPath($kit))
    })
    if ($existing.Count -gt 0) {
        throw "Phase V3T-G refuses to start while isolated Kit is alive: $($existing.ProcessId -join ',')"
    }
}

function Invoke-IsolatedRun {
    param([string]$Mode, [string]$Sequence, [int]$RunIndex, [string]$Group)
    Assert-NoIsolatedKit
    $name = "{0}_{1}_{2}_r{3:d2}" -f $Group,$Mode,$Sequence,($RunIndex + 1)
    $runDir = Join-Path $OutputDir $name
    New-Item -ItemType Directory -Path $runDir -Force | Out-Null
    $resultPath = Join-Path $runDir "probe.json"
    $markerPath = Join-Path $runDir "markers.jsonl"
    $processPath = Join-Path $runDir "process.json"
    $kitLog = Join-Path $runDir "kit.log"
    $gpuCsv = Join-Path $runDir "gpu.csv"
    if ($Resume -and (Test-Path -LiteralPath $processPath)) {
        return (Get-Content -Raw -LiteralPath $processPath | ConvertFrom-Json)
    }
    Remove-Item -LiteralPath $resultPath,$markerPath,$processPath,$kitLog,$gpuCsv -Force -ErrorAction SilentlyContinue
    $monitor = $null
    if ($nvidiaSmi) {
        $monitor = Start-Process -FilePath $nvidiaSmi.Source -ArgumentList @(
            "--query-gpu=timestamp,utilization.gpu,memory.used", "--format=csv,noheader,nounits", "--loop-ms=250"
        ) -RedirectStandardOutput $gpuCsv -PassThru -WindowStyle Hidden
    }
    $started = [DateTimeOffset]::UtcNow
    $process = $null
    try {
        $arguments = @(
            $app, "--no-window", "--/app/file/ignoreUnsavedOnExit=true", "--/app/quitAfter=30000",
            "--/app/settings/persistent=0", "--/app/settings/loadUserConfig=0", "--/app/window/hideUi=true",
            "--/app/viewport/defaults/fillViewport=false", "--/renderer/multiGpu/enabled=false", "--/rtx/flow/enabled=true",
            "--/exts/campfire.app/autoCreateScene=false", "--/exts/campfire.app/residentPointApplicationEnabled=false",
            "--/exts/campfire.app/residentPointRigidLayoutEnabled=false", "--/exts/campfire.app/woodVisualV3Enabled=false",
            "--ext-folder", $extension, "--enable", "omni.campfire.phasev3tg_shutdown", "--/log/file=$kitLog",
            "--/phasev3tg/output=$resultPath", "--/phasev3tg/markers=$markerPath", "--/phasev3tg/mode=$Mode",
            "--/phasev3tg/sequence=$Sequence", "--/phasev3tg/warmup=$Warmup", "--/phasev3tg/updates=$Updates",
            "--/phasev3tg/run=$RunIndex", "--exec", $probe
        )
        $process = Start-Process -FilePath $kit -ArgumentList $arguments -PassThru -WindowStyle Hidden
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            Stop-Process -Id $process.Id -Force
            $classification = "timeout"
            $exitCode = $null
        } else {
            $process.WaitForExit()
            $process.Refresh()
            $exitCode = $process.ExitCode
            $exitHex = '0x{0:X8}' -f ([int32]$exitCode)
            $classification = if ($exitHex -eq "0xC0000005") { "access_violation_0xC0000005" } elseif ($exitCode -eq 0) { "normal" } else { "nonzero_exit" }
        }
    }
    finally {
        if ($monitor -and -not $monitor.HasExited) { Stop-Process -Id $monitor.Id -Force; Wait-Process -Id $monitor.Id -Timeout 5 -ErrorAction SilentlyContinue }
    }
    $ended = [DateTimeOffset]::UtcNow
    $markers = @()
    if (Test-Path -LiteralPath $markerPath) {
        $markers = @(Get-Content -LiteralPath $markerPath | Where-Object { $_ } | ForEach-Object { $_ | ConvertFrom-Json })
    }
    $shutdown = @($markers | Where-Object { $_.name -eq "shutdown_begin" } | Select-Object -Last 1)
    $crashPatterns = '0xC0000005|access violation|illegal address|device lost|invalid pointer|unregisterViewOverride|ComputeExtent'
    $excerpt = @()
    foreach ($path in @($kitLog)) {
        if (Test-Path -LiteralPath $path) { $excerpt += @(Select-String -LiteralPath $path -Pattern $crashPatterns -Context 2,6 | ForEach-Object { $_.ToString() }) }
    }
    $last = @($markers | Select-Object -Last 1)
    $gpuMemory = @()
    if (Test-Path -LiteralPath $gpuCsv) {
        $gpuMemory = @(Get-Content $gpuCsv | ForEach-Object { $parts=$_ -split ','; if($parts.Count -ge 3){ [double]$parts[2].Trim() } })
    }
    $record = [ordered]@{
        schema = "campfire.phasev3tg.process-result.v1"; name=$name; group=$Group; mode=$Mode; sequence=$Sequence; run=$RunIndex+1
        started_utc=$started.ToString('o'); ended_utc=$ended.ToString('o'); elapsed_ms=[Math]::Round(($ended-$started).TotalMilliseconds,3)
        shutdown_to_exit_ms=if($shutdown.Count){[Math]::Round(($ended.ToUnixTimeMilliseconds()-[long]($shutdown[0].wall_ns/1000000)),3)}else{$null}
        exit_code=$exitCode; exit_hex=if($null -ne $exitCode){'0x{0:X8}' -f ([int32]$exitCode)}else{$null}
        classification=$classification; last_marker=if($last.Count){$last[0].name}else{$null}; marker_count=$markers.Count
        crash_excerpt=$excerpt; cuda_illegal_address=[bool]($excerpt -match 'illegal address'); device_lost=[bool]($excerpt -match 'device lost'); invalid_pointer=[bool]($excerpt -match 'invalid pointer')
        gpu_memory_mib_min=if($gpuMemory.Count){($gpuMemory|Measure-Object -Minimum).Minimum}else{$null}; gpu_memory_mib_max=if($gpuMemory.Count){($gpuMemory|Measure-Object -Maximum).Maximum}else{$null}
        probe_json=if(Test-Path $resultPath){$resultPath}else{$null}; markers=$markerPath; kit_log=$kitLog; gpu_csv=if(Test-Path $gpuCsv){$gpuCsv}else{$null}
    }
    [IO.File]::WriteAllText($processPath, ($record | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    return [pscustomobject]$record
}

# Mandatory reproduction controls, rotated every run.
for ($run=0; $run -lt $BaselineRuns; $run++) {
    $order = if (($run % 2) -eq 0) { @("cpu_reference","gpu_ring3_normal") } else { @("gpu_ring3_normal","cpu_reference") }
    foreach($mode in $order){ $entries.Add((Invoke-IsolatedRun $mode "A" $run "baseline")) }
}
# Remaining resource boundaries use the same scene/publication count.
$resourceModes = @(
    @{mode="provider_only"; sequence="A"}, @{mode="warp_only"; sequence="A"}, @{mode="gpu_single_sync"; sequence="A"},
    @{mode="gpu_ring3_keep_allocations"; sequence="E"}, @{mode="gpu_ring3_keep_providers"; sequence="E"}, @{mode="gpu_ring3_stage_first"; sequence="D"}
)
for($run=0;$run -lt $ResourceRuns;$run++){
    $offset = $run % $resourceModes.Count
    if($offset -eq 0){
        $rotated=$resourceModes
    } else {
        $rotated=@($resourceModes[$offset..($resourceModes.Count-1)] + $resourceModes[0..($offset-1)])
    }
    foreach($item in $rotated){$entries.Add((Invoke-IsolatedRun $item.mode $item.sequence $run "resource"))}
}
# A was already covered by the mandatory GPU baseline; exercise B-E ten times.
for($run=0;$run -lt $SequenceRuns;$run++){
    $sequences=@("B","C","D","E"); $offset=$run%$sequences.Count
    $ordered=@($sequences[$offset..($sequences.Count-1)] + $(if($offset){$sequences[0..($offset-1)]}else{@()}))
    foreach($sequence in $ordered){$entries.Add((Invoke-IsolatedRun "gpu_ring3_normal" $sequence $run "sequence"))}
}

$manifest=[ordered]@{
    schema="campfire.phasev3tg.manifest.v1"; kit="110.2"; flow="110.0.0"; atlas=@{width=120;height=60;textures=2;bytes=57600}; logs=20
    warmup=$Warmup; updates=$Updates; baseline_runs=$BaselineRuns; resource_runs=$ResourceRuns; sequence_runs=$SequenceRuns
    production_changed=$false; entries=$entries
}
$manifestPath=Join-Path $OutputDir "manifest.json"
[IO.File]::WriteAllText($manifestPath,($manifest|ConvertTo-Json -Depth 10)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
if(-not $SkipAnalyze){& $kitPython $analyzer --manifest $manifestPath; if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}}
