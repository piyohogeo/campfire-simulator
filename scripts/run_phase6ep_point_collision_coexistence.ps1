param([string]$OutputRoot = "")

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutputRoot) { $OutputRoot = Join-Path $root "artifacts\phase6ep-point-collision-1" }
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6EP refuses artifact root reuse: $OutputRoot" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
$contractPath = Join-Path $PSScriptRoot "phase6ep_point_collision_contract.json"
$hashPath = Join-Path $PSScriptRoot "phase6ep_point_collision_contract.sha256"
$selector = Join-Path $PSScriptRoot "select_phase6ep_point_offset.py"
$caseRunner = Join-Path $PSScriptRoot "run_phase6ep_point_collision_case.ps1"
$guardTool = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
$incrementalGate = Join-Path $PSScriptRoot "gate_phase6ep_condition.py"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6ep_point_collision.py"
$productionApp = Join-Path $root "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$expectedHash = ((Get-Content -Raw -Encoding ASCII $hashPath).Trim().Split(' ')[0]).ToUpperInvariant()
$contractHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($contractHash -ne $expectedHash) { throw "Phase 6EP contract hash mismatch" }
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
if ($contract.phase -ne "phase6ep" -or -not [bool]$contract.declared_before_runtime_sweep) { throw "Phase 6EP contract is not frozen" }
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "predeclared_contract.json")
$selectionPath = Join-Path $OutputRoot "offline_offset_selection.json"
& python $selector --contract $contractPath --output $selectionPath
if ($LASTEXITCODE -ne 0) { throw "Phase 6EP has no offline-safe offset candidate" }
$selection = Get-Content -Raw -Encoding UTF8 $selectionPath | ConvertFrom-Json
$selectedOffset = [double]$selection.selected_offset_m
if ($selectedOffset -ne 0.075) { throw "Phase 6EP frozen geometry did not select 1.5 velocity voxels" }
$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$powershell = (Get-Process -Id $PID).Path
$limits = [ordered]@{runner=536870912;diagnostic=536870912;kit=15032385536;tree=17179869184;memory=8589934592;commit=8589934592}
$runnerLogs = Join-Path $OutputRoot "runner-logs"
New-Item -ItemType Directory -Path $runnerLogs | Out-Null

function Invoke-Phase6EpCase {
    param([string]$Name,[string]$Scenario,[double]$Offset,[string]$Filtering,[string]$Collision,[int]$RunIndex,[string]$Group,[switch]$Capture)
    $caseOutput = Join-Path $OutputRoot "$Group\$Name"
    $logStem = ($Group -replace '[\\/]','_') + "_" + $Name
    $stdout = Join-Path $runnerLogs "$logStem.stdout.log"
    $stderr = Join-Path $runnerLogs "$logStem.stderr.log"
    $trace = Join-Path $runnerLogs "$logStem.memory.jsonl"
    $summary = Join-Path $runnerLogs "$logStem.guard.json"
    $arguments = @("-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",$caseRunner,"-Scenario",$Scenario,"-OutputDir",$caseOutput,"-OffsetM","$Offset","-SupportRadiusM","0.05","-Filtering",$Filtering,"-Collision",$Collision,"-RunIndex","$RunIndex")
    if ($Capture) { $arguments += @("-Capture","-CaptureStart","21","-CaptureEnd","200") }
    $guardArgs = @(
        $guardTool,"--trace",$trace,"--summary",$summary,"--stdout",$stdout,"--stderr",$stderr,"--timeout-seconds","1200",
        "--runner-private-limit","$($limits.runner)","--diagnostic-private-limit","$($limits.diagnostic)",
        "--kit-private-limit","$($limits.kit)","--tree-private-limit","$($limits.tree)",
        "--available-memory-floor","$($limits.memory)","--commit-headroom-floor","$($limits.commit)",
        "--cpu-telemetry","--lifecycle-path",(Join-Path $caseOutput "raw.json"),
        "--diagnostic-marker-path",((Join-Path $caseOutput "sensitive-shutdown-diagnostics") + ".markers.jsonl"),"--",$powershell
    ) + $arguments
    & python @guardArgs
    if ($LASTEXITCODE -ne 0) { throw "Phase 6EP guard/runner failed for $Group/$Name" }
    $guard = Get-Content -Raw -Encoding UTF8 $summary | ConvertFrom-Json
    $raw = Get-Content -Raw -Encoding UTF8 (Join-Path $caseOutput "raw.json") | ConvertFrom-Json
    $evidence = Get-Content -Raw -Encoding UTF8 (Join-Path $caseOutput "runner_evidence.json") | ConvertFrom-Json
    if ($guard.status -ne "ok" -or -not $guard.process_absent -or $guard.exit_code -ne 0) { throw "Phase 6EP resource gate failed for $Group/$Name" }
    if ($raw.status -ne "ok" -or $raw.lifecycle_marker -ne "shutdown_complete") { throw "Phase 6EP functional gate failed for $Group/$Name" }
    if ($evidence.outcome.lifecycle_status -ne "normal_exit" -or $evidence.outcome.functional_status -ne "pass") { throw "Phase 6EP lifecycle gate failed for $Group/$Name" }
    if (@($evidence.fatal_lines).Count -or @($evidence.dump_inventory).Count -or @($evidence.automatic_upload_attempt_lines).Count -or [bool]$evidence.production_changed) { throw "Phase 6EP safety gate failed for $Group/$Name" }
    return $caseOutput
}

# Runtime sweep uses one fixed critical geometry. The all-scenario selection was frozen offline.
$sweepRows = @()
for ($index = 0; $index -lt @($contract.offset_sweep.values).Count; $index++) {
    $cells = [double]$contract.offset_sweep.values[$index]
    $meters = [double]$contract.offset_sweep.meters[$index]
    $name = "offset_" + ($cells.ToString("0.00",[Globalization.CultureInfo]::InvariantCulture).Replace('.','p'))
    $case = Invoke-Phase6EpCase -Name $name -Scenario "lower_upper" -Offset $meters -Filtering "true" -Collision "true" -RunIndex 1 -Group "sweep"
    $raw = Get-Content -Raw -Encoding UTF8 (Join-Path $case "raw.json") | ConvertFrom-Json
    $sweepRows += [ordered]@{offset_velocity_cells=$cells;offset_m=$meters;active_points=$raw.point_payload.active_point_count;supply_efficiency=$raw.point_payload.supply_efficiency;active_support_intersections=$raw.point_payload.active_support_intersection_count;active_blocks=$raw.active_blocks_final;source_sums=$raw.source_sums}
}
[IO.File]::WriteAllText((Join-Path $OutputRoot "runtime_offset_sweep.json"),([ordered]@{schema="campfire.phase6ep.runtime-offset-sweep.v1";rows=$sweepRows;selected_offset_m=$selectedOffset}|ConvertTo-Json -Depth 10)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))

$conditionMap = @{
    lower_upper_collision_off_filter_off=@{scenario="lower_upper";offset=0.0;filtering="false";collision="false";kind="collision_off"}
    lower_upper_collision_on_filter_off=@{scenario="lower_upper";offset=0.0;filtering="false";collision="true";kind="filter_off"}
    single_candidate=@{scenario="single";offset=$selectedOffset;filtering="true";collision="true";kind="candidate"}
    near_two_candidate=@{scenario="near_two";offset=$selectedOffset;filtering="true";collision="true";kind="candidate"}
    lower_upper_candidate=@{scenario="lower_upper";offset=$selectedOffset;filtering="true";collision="true";kind="candidate"}
    production_four_candidate=@{scenario="production_four";offset=$selectedOffset;filtering="true";collision="true";kind="candidate"}
}
for ($run = 1; $run -le 3; $run++) {
    foreach ($conditionName in @($contract.formal_execution_order_per_run)) {
        $definition = $conditionMap[$conditionName]
        $group = "formal\run_$run"
        $case = Invoke-Phase6EpCase -Name $conditionName -Scenario $definition.scenario -Offset $definition.offset -Filtering $definition.filtering -Collision $definition.collision -RunIndex $run -Group $group
        $gatePath = Join-Path $case "incremental_gate.json"
        $gateArgs = @($incrementalGate,"--condition",$case,"--contract",$contractPath,"--kind",$definition.kind,"--output",$gatePath)
        if ($conditionName -eq "lower_upper_candidate") {
            $gateArgs += @("--pair-positive",(Join-Path $OutputRoot "$group\lower_upper_collision_off_filter_off"))
        }
        & python @gateArgs
        if ($LASTEXITCODE -ne 0) { throw "Phase 6EP incremental numeric gate failed for run $run/$conditionName" }
    }
}

$reportPath = Join-Path $OutputRoot "report.json"
$svgPath = Join-Path $OutputRoot "qualification.svg"
& python $analyzer --root $OutputRoot --contract $contractPath --output $reportPath --svg $svgPath
if ($LASTEXITCODE -ne 0) { throw "Phase 6EP formal aggregation failed" }

# Visual processes are excluded from the formal numeric population.
foreach ($visual in @(
    @{name="collision_off";offset=0.0;filtering="false";collision="false"},
    @{name="collision_on_unfiltered";offset=0.0;filtering="false";collision="true"},
    @{name="collision_on_candidate";offset=$selectedOffset;filtering="true";collision="true"}
)) {
    Invoke-Phase6EpCase -Name $visual.name -Scenario "lower_upper" -Offset $visual.offset -Filtering $visual.filtering -Collision $visual.collision -RunIndex 1 -Group "visual" -Capture | Out-Null
}

$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
if ($productionHashBefore -ne $productionHashAfter) { throw "Phase 6EP changed production app" }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash -ne $contractHash) { throw "Phase 6EP contract changed during execution" }
$complete = [ordered]@{schema="campfire.phase6ep.matrix-complete.v1";phase="phase6ep";qualified=$true;contract_sha256=$contractHash;selected_offset_m=$selectedOffset;formal_process_count=18;sweep_process_count=5;visual_process_count=3;production_app_sha256_before=$productionHashBefore;production_app_sha256_after=$productionHashAfter;production_changed=$false}
[IO.File]::WriteAllText((Join-Path $OutputRoot "matrix_complete.json"),($complete|ConvertTo-Json -Depth 8)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
Write-Host "Phase 6EP complete: 5 sweep + 18 formal + 3 visual processes passed"
