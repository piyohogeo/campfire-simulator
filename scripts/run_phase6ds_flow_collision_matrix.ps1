param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$root = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $PSScriptRoot "run_phase6ds_flow_collision_case.ps1"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6ds_flow_collision.py"
$python = Join-Path $root "_build\windows-x86_64\release\kit\python\python.exe"
if (-not $OutputDir) { $OutputDir = Join-Path $root "artifacts\phase6ds-flow-collision" }
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $OutputDir) { throw "Phase 6DS matrix refuses to reuse output: $OutputDir" }
New-Item -ItemType Directory -Path $OutputDir | Out-Null

# Establish the effective velocity spacing before defining half/one-cell shifts.
& $runner -Condition box_aligned -RunIndex 1 -BoxShiftM 0.0 -OutputDir (Join-Path $OutputDir "box_aligned\run-1") -Capture
$aligned = Get-Content -Raw -Encoding UTF8 (Join-Path $OutputDir "box_aligned\run-1\raw.json") | ConvertFrom-Json
$velocityCell = [double]$aligned.flow_settings.velocity_cell_size_m
if ([double]::IsNaN($velocityCell) -or [double]::IsInfinity($velocityCell) -or $velocityCell -le 0.0) { throw "Phase 6DS did not obtain an effective velocity cell size" }
$conditions = @(
    [pscustomobject]@{ Name = "collision_off"; Shift = 0.0 },
    [pscustomobject]@{ Name = "box_aligned"; Shift = 0.0 },
    [pscustomobject]@{ Name = "box_shift_half"; Shift = 0.5 * $velocityCell },
    [pscustomobject]@{ Name = "box_shift_one"; Shift = $velocityCell }
)
foreach ($condition in $conditions) {
    $firstRun = if ($condition.Name -eq "box_aligned") { 2 } else { 1 }
    for ($run = $firstRun; $run -le 3; $run++) {
        $capture = ($run -eq 1 -and $condition.Name -eq "collision_off")
        $parameters = @{
            Condition = $condition.Name
            RunIndex = $run
            BoxShiftM = $condition.Shift
            OutputDir = Join-Path $OutputDir ("{0}\run-{1}" -f $condition.Name, $run)
        }
        if ($capture) { $parameters.Capture = $true }
        & $runner @parameters
    }
}

$report = Join-Path $root "docs\devlog\assets\phase6\flow_collision_occlusion_report.json"
$raw = Join-Path $root "docs\devlog\assets\phase6\flow_collision_occlusion_raw.json"
$svg = Join-Path $root "docs\devlog\assets\phase6\flow_collision_occlusion_report.svg"
& $python $analyzer --input $OutputDir --raw $raw --report $report --svg $svg
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Phase 6DS matrix completed: $report"
