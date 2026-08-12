param([string]$OutputRoot = "")

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutputRoot) { $OutputRoot = Join-Path $root "artifacts\phase6eq-self-collider-1" }
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Phase 6EQ refuses artifact root reuse: $OutputRoot" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
$contractPath = Join-Path $PSScriptRoot "phase6eq_self_collider_contract.json"
$hashPath = Join-Path $PSScriptRoot "phase6eq_self_collider_contract.sha256"
$caseRunner = Join-Path $PSScriptRoot "run_phase6ep_point_collision_case.ps1"
$guardTool = Join-Path $PSScriptRoot "phase6eg_resource_guard.py"
$offline = Join-Path $PSScriptRoot "phase6eq_offline_geometry.py"
$gate = Join-Path $PSScriptRoot "gate_phase6eq_condition.py"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6eq_self_collider.py"
$productionApp = Join-Path $root "_build\windows-x86_64\release\apps\campfire.simulator.kit"
$expectedHash = ((Get-Content -Raw -Encoding ASCII $hashPath).Trim().Split(' ')[0]).ToUpperInvariant()
$contractHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash
if ($contractHash -ne $expectedHash) { throw "Phase 6EQ contract hash mismatch" }
$contract = Get-Content -Raw -Encoding UTF8 $contractPath | ConvertFrom-Json
if ($contract.phase -ne "phase6eq" -or -not [bool]$contract.declared_before_runtime) { throw "Phase 6EQ contract is not frozen" }
Copy-Item -LiteralPath $contractPath -Destination (Join-Path $OutputRoot "predeclared_contract.json")
& python $offline --contract $contractPath --output (Join-Path $OutputRoot "offline_geometry.json") --archive (Join-Path $OutputRoot "offline_point_classification.npz")
if ($LASTEXITCODE -ne 0) { throw "Phase 6EQ offline geometry gate failed" }

$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
$powershell = (Get-Process -Id $PID).Path
$limits = $contract.safety
$runnerLogs = Join-Path $OutputRoot "runner-logs"
New-Item -ItemType Directory -Path $runnerLogs | Out-Null

function Invoke-Phase6EqCase {
    param(
        [string]$Group,[string]$Name,[string]$Scenario,[string]$Policy,
        [double]$Offset,[string]$Filtering,[string]$Collision,[int]$RunIndex,[switch]$Capture
    )
    $caseOutput = Join-Path $OutputRoot "$Group\$Name"
    $logStem = (($Group + "_" + $Name) -replace '[\\/]','_')
    $stdout = Join-Path $runnerLogs "$logStem.stdout.log"
    $stderr = Join-Path $runnerLogs "$logStem.stderr.log"
    $trace = Join-Path $runnerLogs "$logStem.memory.jsonl"
    $summary = Join-Path $runnerLogs "$logStem.guard.json"
    $arguments = @(
        "-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",$caseRunner,
        "-Scenario",$Scenario,"-OutputDir",$caseOutput,"-OffsetM","$Offset","-SupportRadiusM","0.05",
        "-Filtering",$Filtering,"-Collision",$Collision,"-Policy",$Policy,"-ReportPhase","phase6eq",
        "-SampleFrames","30,60,90,120,150,180,200","-SpatialAllChannels","-RunIndex","$RunIndex"
    )
    if ($Capture) { $arguments += @("-Capture","-CaptureStart","21","-CaptureEnd","200") }
    $guardArgs = @(
        $guardTool,"--trace",$trace,"--summary",$summary,"--stdout",$stdout,"--stderr",$stderr,
        "--timeout-seconds","1200","--runner-private-limit","$($limits.runner_private_limit_bytes)",
        "--diagnostic-private-limit","$($limits.diagnostic_private_limit_bytes)",
        "--kit-private-limit","$($limits.kit_private_limit_bytes)","--tree-private-limit","$($limits.unique_tree_private_limit_bytes)",
        "--available-memory-floor","$($limits.physical_memory_floor_bytes)","--commit-headroom-floor","$($limits.commit_headroom_floor_bytes)",
        "--cpu-telemetry","--lifecycle-path",(Join-Path $caseOutput "raw.json"),
        "--diagnostic-marker-path",((Join-Path $caseOutput "sensitive-shutdown-diagnostics") + ".markers.jsonl"),"--",$powershell
    ) + $arguments
    & python @guardArgs
    if ($LASTEXITCODE -ne 0) { throw "Phase 6EQ guard/runner failed for $Group/$Name" }
    $guard = Get-Content -Raw -Encoding UTF8 $summary | ConvertFrom-Json
    $raw = Get-Content -Raw -Encoding UTF8 (Join-Path $caseOutput "raw.json") | ConvertFrom-Json
    $evidence = Get-Content -Raw -Encoding UTF8 (Join-Path $caseOutput "runner_evidence.json") | ConvertFrom-Json
    if ($guard.status -ne "ok" -or -not $guard.process_absent -or $guard.exit_code -ne 0) { throw "Phase 6EQ resource gate failed for $Group/$Name" }
    if ($raw.status -ne "ok" -or $raw.lifecycle_marker -ne "shutdown_complete") { throw "Phase 6EQ functional gate failed for $Group/$Name" }
    if ($evidence.outcome.lifecycle_status -ne "normal_exit" -or $evidence.outcome.functional_status -ne "pass") { throw "Phase 6EQ lifecycle gate failed for $Group/$Name" }
    if (@($evidence.fatal_lines).Count -or @($evidence.dump_inventory).Count -or @($evidence.automatic_upload_attempt_lines).Count -or [bool]$evidence.production_changed) { throw "Phase 6EQ safety gate failed for $Group/$Name" }
    return $caseOutput
}

# The runtime sweep is diagnostic, one run per predeclared offset and policy.
$runtimeSweep = @()
foreach ($policy in @("strict_all","allow_self_support","allow_self_center")) {
    foreach ($offset in @($contract.offline_offset_sweep_m)) {
        $token = ([double]$offset).ToString("+0.0000;-0.0000;0.0000",[Globalization.CultureInfo]::InvariantCulture).Replace('+','p').Replace('-','m').Replace('.','p')
        $name = "${policy}_$token"
        $case = Invoke-Phase6EqCase -Group "runtime_sweep" -Name $name -Scenario $contract.runtime_offset_sweep_scenario -Policy $policy -Offset ([double]$offset) -Filtering "true" -Collision "true" -RunIndex 1
        $raw = Get-Content -Raw -Encoding UTF8 (Join-Path $case "raw.json") | ConvertFrom-Json
        $runtimeSweep += [ordered]@{
            policy=$policy;offset_m=[double]$offset;active_points=$raw.point_payload.active_point_count;
            point_retention=$raw.point_payload.supply_efficiency;weighted_supply=$raw.point_payload.weighted_supply;
            active_other_support_intersections=$raw.point_payload.active_other_support_intersection_count;
            active_blocks=$raw.active_blocks_final;source_sums=$raw.source_sums
        }
    }
}
[IO.File]::WriteAllText((Join-Path $OutputRoot "runtime_offset_sweep.json"),([ordered]@{schema="campfire.phase6eq.runtime-offset-sweep.v1";rows=$runtimeSweep}|ConvertTo-Json -Depth 12)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))

for ($run = 1; $run -le 3; $run++) {
    $order = @($contract.formal_orders[$run - 1])
    foreach ($scenario in @($contract.formal_scenarios)) {
        foreach ($policy in $order) {
            $definition = $contract.policies.$policy
            $collision = if ($policy -eq "collision_off") { "false" } else { "true" }
            $filtering = if ($policy -eq "collision_off") { "false" } else { "true" }
            $effectivePolicy = if ($policy -eq "collision_off") { "strict_all" } else { $policy }
            $group = "formal\run_$run\$scenario"
            $case = Invoke-Phase6EqCase -Group $group -Name $policy -Scenario $scenario -Policy $effectivePolicy -Offset ([double]$definition.selected_offset_m) -Filtering $filtering -Collision $collision -RunIndex $run
            & python $gate --condition $case --contract $contractPath --output (Join-Path $case "incremental_gate.json")
            if ($LASTEXITCODE -ne 0) { throw "Phase 6EQ incremental gate failed for run $run/$scenario/$policy" }
        }
    }
}

$reportPath = Join-Path $OutputRoot "report.json"
$svgPath = Join-Path $OutputRoot "qualification.svg"
& python $analyzer --root $OutputRoot --contract $contractPath --output $reportPath --svg $svgPath
if ($LASTEXITCODE -ne 0) { throw "Phase 6EQ formal aggregate failed" }

# Visual conditions are outside the numeric population and remain fail-closed.
foreach ($policy in @($contract.visual_conditions)) {
    $definition = $contract.policies.$policy
    $collision = if ($policy -eq "collision_off") { "false" } else { "true" }
    $filtering = if ($policy -eq "collision_off") { "false" } else { "true" }
    $effectivePolicy = if ($policy -eq "collision_off") { "strict_all" } else { $policy }
    Invoke-Phase6EqCase -Group "visual" -Name $policy -Scenario $contract.visual_scenario -Policy $effectivePolicy -Offset ([double]$definition.selected_offset_m) -Filtering $filtering -Collision $collision -RunIndex 1 -Capture | Out-Null
}

$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $productionApp).Hash
if ($productionHashBefore -ne $productionHashAfter) { throw "Phase 6EQ changed production app" }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $contractPath).Hash -ne $contractHash) { throw "Phase 6EQ contract changed during execution" }
$complete = [ordered]@{
    schema="campfire.phase6eq.matrix-complete.v1";phase="phase6eq";numeric_qualified=$true;
    contract_sha256=$contractHash;runtime_sweep_process_count=18;formal_process_count=24;visual_process_count=4;
    production_app_sha256_before=$productionHashBefore;production_app_sha256_after=$productionHashAfter;production_changed=$false
}
[IO.File]::WriteAllText((Join-Path $OutputRoot "matrix_complete.json"),($complete|ConvertTo-Json -Depth 8)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
Write-Host "Phase 6EQ matrix complete: 18 runtime sweep + 24 formal + 4 visual processes"
