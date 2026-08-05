param(
    [string]$OutputDir = "",
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repoRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
if (-not $ValidateOnly -and (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app))) {
    throw "Application is not built. Run .\repo.bat build first."
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $repoRoot "artifacts\phase6\latest"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
if (-not $ValidateOnly) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

    & $kit @(
        $app,
        "--no-window",
        "--/app/quitAfter=600",
        "--/app/settings/persistent=0",
        "--/app/settings/loadUserConfig=0",
        "--/exts/campfire.app/autoCreateScene=true",
        "--/exts/campfire.app/phase=phase6",
        "--/exts/campfire.app/captureOnStartup=true",
        "--/exts/campfire.app/quitAfterCapture=true",
        "--/exts/campfire.app/outputDir=$OutputDir",
        "--/app/viewport/grid/enabled=false",
        "--/persistent/app/viewport/displayOptions=1152"
    )
    if ($LASTEXITCODE -ne 0) {
        throw "Phase 6 application failed with exit code $LASTEXITCODE."
    }
}

$summaryPath = Join-Path $OutputDir "summary.json"
if (-not (Test-Path -LiteralPath $summaryPath)) {
    throw "Phase 6 summary was not produced."
}
$result = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json
if ($result.status -ne "ok" -or $result.phase -ne "phase6") {
    throw "Phase 6 summary reported failure."
}
$calibration = $result.calibration
if ($calibration.arrhenius_model.source_pathways.Count -ne 3 -or $calibration.arrhenius_model.reaction_order -ne 1.0) {
    throw "Phase 6 Arrhenius source definition is invalid."
}
if ([math]::Abs($calibration.panel_model.nominal_thickness_m - 0.0127) -gt 0.0000001 -or $calibration.panel_model.plywood_layer_count -ne 5) {
    throw "Phase 6 layered plywood geometry is invalid."
}
if ($calibration.panel_model.adhesive_layers_explicit) {
    throw "Phase 6 must not invent unreported adhesive-layer geometry."
}
$plywoodProfile = $calibration.material_property_profiles.plywood
$osbProfile = $calibration.material_property_profiles.osb
$heatCapacityModel = $calibration.temperature_dependent_heat_capacity
$secondaryTar = $calibration.secondary_tar_cracking
if ([math]::Abs($plywoodProfile.thermal_conductivity_w_m_k - 0.115) -gt 0.0000001 -or [math]::Abs($plywoodProfile.specific_heat_j_kg_k - 1214.0) -gt 0.0000001) {
    throw "Phase 6 plywood thermal profile changed."
}
if ([math]::Abs($osbProfile.thermal_conductivity_w_m_k - 0.118) -gt 0.0000001 -or [math]::Abs($osbProfile.specific_heat_j_kg_k - 1298.0) -gt 0.0000001) {
    throw "Phase 6 OSB thermal profile changed."
}
if ($heatCapacityModel.model -ne "usda_fpl_normalized_linear_280_420_k" -or $heatCapacityModel.source_valid_temperature_range_k.Count -ne 2 -or [math]::Abs($heatCapacityModel.source_valid_temperature_range_k[0] - 280.0) -gt 0.0000001 -or [math]::Abs($heatCapacityModel.source_valid_temperature_range_k[1] - 420.0) -gt 0.0000001 -or [math]::Abs($heatCapacityModel.reference_temperature_k - 293.15) -gt 0.0000001) {
    throw "Phase 6 bounded temperature-dependent heat-capacity model changed."
}
if ([math]::Abs($secondaryTar.preexponential_s - 4280000.0) -gt 0.0000001 -or [math]::Abs($secondaryTar.activation_energy_j_mol - 108000.0) -gt 0.0000001 -or [math]::Abs($secondaryTar.residence_time_s - 1.0) -gt 0.0000001 -or $secondaryTar.application_temperature_range_k.Count -ne 2 -or [math]::Abs($secondaryTar.application_temperature_range_k[0] - 773.0) -gt 0.0000001 -or [math]::Abs($secondaryTar.application_temperature_range_k[1] - 1073.0) -gt 0.0000001) {
    throw "Phase 6 secondary-tar diagnostic definition changed."
}
if ($plywoodProfile.adhesive_interface_count -ne 4 -or $plywoodProfile.adhesive_geometry_explicit -or $plywoodProfile.adhesive_additional_resistance_applied) {
    throw "Phase 6 plywood adhesive-interface assumptions changed."
}
if (-not $calibration.improved -or $calibration.improvement_fraction -le 0.0) {
    throw "Phase 6 search did not improve the baseline."
}
if ($calibration.best.score_rmse_relative -ge $calibration.baseline.score_rmse_relative) {
    throw "Phase 6 best score is not lower than the baseline."
}
$selection = $calibration.selection
if (-not $selection.improved -or $selection.sample_ids.Count -ne 2) {
    throw "Phase 6 replicate selection set is invalid."
}
if (($selection.sample_ids -join ",") -ne "SAMP.1,SAMP.2") {
    throw "Phase 6 replicate selection IDs changed."
}
if (($selection.best.parameters | ConvertTo-Json -Compress) -ne ($calibration.best.parameters | ConvertTo-Json -Compress)) {
    throw "Phase 6 reported parameters do not match replicate selection."
}
if ($calibration.candidate_count -ne 16 -or $calibration.best.cases.Count -ne 2) {
    throw "Phase 6 did not evaluate the expected fixed search space."
}
if ($calibration.baseline.parameters.pyrolysis_rate_model -ne "arrhenius_parallel_first_order" -or $calibration.best.parameters.pyrolysis_rate_model -ne "arrhenius_parallel_first_order") {
    throw "Phase 6 did not use three-pathway first-order Arrhenius pyrolysis."
}
if ($calibration.best.parameters.pyrolysis_parallel_common_scale -le 0.0) {
    throw "Phase 6 selected an invalid common Arrhenius scale."
}
if (-not $calibration.best.parameters.secondary_tar_cracking_enabled -or [math]::Abs($calibration.best.parameters.secondary_tar_cracking_residence_time_s - 1.0) -gt 0.0000001) {
    throw "Phase 6 secondary-tar diagnostic is not enabled with the fixed scenario."
}
foreach ($product in @("gas", "tar", "char")) {
    $aName = "pyrolysis_parallel_${product}_preexponential_s"
    $eName = "pyrolysis_parallel_${product}_activation_energy_j_mol"
    if ($calibration.best.parameters.$aName -le 0.0 -or $calibration.best.parameters.$eName -le 0.0) {
        throw "Phase 6 selected invalid $product Arrhenius coefficients."
    }
}
foreach ($case in $calibration.best.cases) {
    if (-not $case.all_values_finite) {
        throw "Phase 6 calibration produced non-finite state."
    }
    if ([math]::Abs($case.mass_balance_error_kg) -gt 0.000001) {
        throw "Phase 6 calibration violated mass conservation."
    }
    if ($null -eq $case.predicted_ignition_seconds) {
        throw "Phase 6 calibration did not predict ignition."
    }
    if ($case.model_kind -ne "layered_plywood" -or $case.layer_count -ne 5 -or $case.final_layer_temperatures_k.Count -ne 5) {
        throw "Phase 6 calibration did not use the explicit five-ply model."
    }
    if ([math]::Abs($case.specimen_thickness_m - 0.0127) -gt 0.0000001) {
        throw "Phase 6 calibration specimen thickness changed."
    }
    if ($case.material_kind -ne "plywood" -or [math]::Abs($case.through_thickness_conductivity_w_m_k - 0.115) -gt 0.0000001 -or [math]::Abs($case.dry_wood_specific_heat_j_kg_k - 1214.0) -gt 0.0000001) {
        throw "Phase 6 calibration did not use the sourced plywood profile."
    }
    if ($case.dry_wood_specific_heat_model -ne "usda_fpl_normalized_linear_280_420_k" -or $case.dry_wood_specific_heat_valid_range_k.Count -ne 2 -or [math]::Abs($case.dry_wood_specific_heat_valid_range_k[0] - 280.0) -gt 0.0000001 -or [math]::Abs($case.dry_wood_specific_heat_valid_range_k[1] - 420.0) -gt 0.0000001 -or $case.final_layer_dry_wood_specific_heats_j_kg_k.Count -ne 5) {
        throw "Phase 6 calibration did not use bounded temperature-dependent plywood cp."
    }
    if ($case.adhesive_interface_count -ne 4 -or $case.adhesive_geometry_explicit) {
        throw "Phase 6 calibration invented adhesive geometry."
    }
    $yieldSum = $case.primary_product_yield_fraction.gas + $case.primary_product_yield_fraction.tar + $case.primary_product_yield_fraction.char
    if ([math]::Abs($yieldSum - 1.0) -gt 0.000001) {
        throw "Phase 6 primary-product yields do not close to one."
    }
    $postSecondaryYieldSum = $case.post_secondary_product_yield_fraction.gas + $case.post_secondary_product_yield_fraction.tar + $case.post_secondary_product_yield_fraction.char
    if ([math]::Abs($postSecondaryYieldSum - 1.0) -gt 0.000001 -or $case.post_secondary_product_yield_fraction.gas -le $case.primary_product_yield_fraction.gas -or $case.post_secondary_product_yield_fraction.tar -ge $case.primary_product_yield_fraction.tar) {
        throw "Phase 6 post-secondary product yields are invalid."
    }
}
if ($calibration.best.cases[0].predicted_ignition_seconds -le $calibration.best.cases[1].predicted_ignition_seconds) {
    throw "Phase 6 lost the expected heat-flux ignition ordering."
}
$holdout = $calibration.holdout
if ($holdout.used_for_parameter_selection) {
    throw "Phase 6 holdout leaked into parameter selection."
}
if ($holdout.material -ne "External Oriented Strandboard" -or $holdout.calibrated.cases.Count -ne 2) {
    throw "Phase 6 external-material holdout is incomplete."
}
if ($holdout.baseline.score_rmse_relative -lt 0.0 -or $holdout.calibrated.score_rmse_relative -lt 0.0) {
    throw "Phase 6 holdout score is invalid."
}
foreach ($case in $holdout.calibrated.cases) {
    if (-not $case.all_values_finite -or $null -eq $case.predicted_ignition_seconds) {
        throw "Phase 6 holdout produced an invalid prediction."
    }
    if ([math]::Abs($case.mass_balance_error_kg) -gt 0.000001) {
        throw "Phase 6 holdout violated mass conservation."
    }
    if ($case.model_kind -ne "layered_osb" -or $case.layer_count -ne 1) {
        throw "Phase 6 OSB holdout did not use the planar single-layer adapter."
    }
    if ($case.material_kind -ne "osb" -or [math]::Abs($case.through_thickness_conductivity_w_m_k - 0.118) -gt 0.0000001 -or [math]::Abs($case.dry_wood_specific_heat_j_kg_k - 1298.0) -gt 0.0000001) {
        throw "Phase 6 holdout did not use the sourced OSB profile."
    }
    if ($case.dry_wood_specific_heat_model -ne "usda_fpl_normalized_linear_280_420_k" -or $case.dry_wood_specific_heat_valid_range_k.Count -ne 2 -or [math]::Abs($case.dry_wood_specific_heat_valid_range_k[0] - 280.0) -gt 0.0000001 -or [math]::Abs($case.dry_wood_specific_heat_valid_range_k[1] - 420.0) -gt 0.0000001 -or $case.final_layer_dry_wood_specific_heats_j_kg_k.Count -ne 1) {
        throw "Phase 6 holdout did not use bounded temperature-dependent OSB cp."
    }
}
if ($holdout.calibrated.cases[0].predicted_ignition_seconds -le $holdout.calibrated.cases[1].predicted_ignition_seconds) {
    throw "Phase 6 holdout lost the expected heat-flux ignition ordering."
}
$replicateHoldout = $calibration.replicate_holdout
if ($replicateHoldout.used_for_parameter_selection -or ($replicateHoldout.sample_ids -join ",") -ne "SAMP.3") {
    throw "Phase 6 same-material holdout leaked into parameter selection."
}
if (($replicateHoldout.calibrated.parameters | ConvertTo-Json -Compress) -ne ($calibration.best.parameters | ConvertTo-Json -Compress)) {
    throw "Phase 6 same-material holdout was refitted."
}
foreach ($case in $replicateHoldout.calibrated.cases) {
    if (-not $case.all_values_finite -or $null -eq $case.predicted_ignition_seconds) {
        throw "Phase 6 same-material holdout produced an invalid prediction."
    }
    if ([math]::Abs($case.mass_balance_error_kg) -gt 0.000001) {
        throw "Phase 6 same-material holdout violated mass conservation."
    }
}
if ($replicateHoldout.calibrated.cases[0].predicted_ignition_seconds -le $replicateHoldout.calibrated.cases[1].predicted_ignition_seconds) {
    throw "Phase 6 same-material holdout lost the expected heat-flux ignition ordering."
}
$tarSensitivity = $calibration.secondary_tar_residence_sensitivity
if ($tarSensitivity.used_for_parameter_selection -or $tarSensitivity.scenarios.Count -ne 3) {
    throw "Phase 6 secondary-tar residence sensitivity definition is invalid."
}
$expectedResidenceTimes = @(0.9, 1.0, 2.2)
for ($scenarioIndex = 0; $scenarioIndex -lt $expectedResidenceTimes.Count; $scenarioIndex++) {
    if ([math]::Abs([double]$tarSensitivity.scenarios[$scenarioIndex].residence_time_s - $expectedResidenceTimes[$scenarioIndex]) -gt 0.000000000001) {
        throw "Phase 6 secondary-tar residence sensitivity definition is invalid."
    }
}
foreach ($scenario in $tarSensitivity.scenarios) {
    if ($scenario.used_for_parameter_selection -or [math]::Abs($scenario.score_rmse_relative - $calibration.best.score_rmse_relative) -gt 0.000000000001) {
        throw "Phase 6 secondary-tar residence scenario changed the selected score."
    }
    foreach ($case in $scenario.cases) {
        $yieldSum = $case.post_secondary_product_yield_fraction.gas + $case.post_secondary_product_yield_fraction.tar + $case.post_secondary_product_yield_fraction.char
        if ([math]::Abs($yieldSum - 1.0) -gt 0.000001) {
            throw "Phase 6 secondary-tar residence scenario does not conserve product mass."
        }
    }
}
for ($caseIndex = 0; $caseIndex -lt 2; $caseIndex++) {
    if ($tarSensitivity.scenarios[0].cases[$caseIndex].post_secondary_product_yield_fraction.gas -gt $tarSensitivity.scenarios[1].cases[$caseIndex].post_secondary_product_yield_fraction.gas -or $tarSensitivity.scenarios[1].cases[$caseIndex].post_secondary_product_yield_fraction.gas -gt $tarSensitivity.scenarios[2].cases[$caseIndex].post_secondary_product_yield_fraction.gas) {
        throw "Phase 6 secondary gas yield is not monotonic with residence time."
    }
}
$gasTransport = $calibration.gas_transport_readiness
$expectedMissingTransportInputs = @(
    "char_layer_pressure_drop_pa",
    "char_layer_thickness_m",
    "gas_dynamic_viscosity_pa_s",
    "through_thickness_permeability_m2",
    "through_thickness_porosity_fraction"
)
$actualMissingTransportInputs = @($gasTransport.missing_current_panel_inputs | Sort-Object)
if ($gasTransport.ready_for_secondary_tar_coupling -or $gasTransport.used_for_parameter_selection -or $null -ne $gasTransport.predicted_residence_time_s -or ($actualMissingTransportInputs -join ",") -ne ($expectedMissingTransportInputs -join ",")) {
    throw "Phase 6 gas-transport coupling gate changed."
}
$transportContext = $gasTransport.source_context
if ([math]::Abs($transportContext.wood_porosity_fraction - 0.51) -gt 0.0000001 -or [math]::Abs($transportContext.char_porosity_fraction - 0.85) -gt 0.0000001 -or [math]::Abs($transportContext.wood_permeability_m2 - 0.000000000000752) -gt 1.0e-20 -or [math]::Abs($transportContext.char_permeability_m2 - 0.00000000001) -gt 1.0e-20 -or [math]::Abs($transportContext.reported_reference_pressure_drop_pa - 30000.0) -gt 0.0000001) {
    throw "Phase 6 gas-transport source context changed."
}
$charGeometry = $calibration.char_geometry_diagnostic
if ($charGeometry.used_for_parameter_selection -or $charGeometry.shrinkage_applied -or $charGeometry.cases.Count -ne 2) {
    throw "Phase 6 char-geometry diagnostic definition is invalid."
}
foreach ($case in $charGeometry.cases) {
    if ($case.layer_pyrolysis_conversion_fractions.Count -ne 5 -or $case.layer_char_mass_fractions_initial_dry.Count -ne 5) {
        throw "Phase 6 char-geometry diagnostic lost the five-ply state."
    }
    foreach ($fraction in $case.layer_pyrolysis_conversion_fractions) {
        if ($fraction -lt 0.0 -or $fraction -gt 1.0) {
            throw "Phase 6 char-geometry conversion fraction is outside [0, 1]."
        }
    }
    if ($case.equivalent_unshrunk_pyrolysis_depth_m -lt 0.0 -or $case.equivalent_unshrunk_pyrolysis_depth_m -gt 0.0127 -or $null -ne $case.physical_char_layer_thickness_m -or $null -ne $case.shrinkage_factor -or $case.ready_for_darcy_layer_thickness) {
        throw "Phase 6 char-geometry physical-thickness gate changed."
    }
}
if ($gasTransport.fixed_grid_reaction_progress.Count -ne 2) {
    throw "Phase 6 gas-transport report lost fixed-grid reaction progress."
}
$charBenchmark = $calibration.external_plywood_char_depth_benchmark
if ($charBenchmark.used_for_parameter_selection -or $charBenchmark.scored -or $charBenchmark.ready_for_physical_thickness_transfer -or $null -ne $charBenchmark.comparison_error_metric) {
    throw "Phase 6 external char-depth benchmark gate changed."
}
if ($charBenchmark.matched_condition_count -ne 3 -or $charBenchmark.condition_count -ne 10) {
    throw "Phase 6 external char-depth comparability matrix changed."
}
if ([math]::Abs($charBenchmark.external_observation.char_depth_m - 0.01377) -gt 0.000000001 -or [math]::Abs($charBenchmark.external_observation.char_depth_95_percent_interval_half_width_m - 0.00060) -gt 0.000000001) {
    throw "Phase 6 external char-depth observation changed."
}
if ($null -ne $charBenchmark.current_model.physical_char_layer_thickness_m -or $charBenchmark.current_model.depth_m -le 0.0 -or $charBenchmark.current_model.depth_m -gt 0.0127) {
    throw "Phase 6 external char-depth benchmark used an invalid current quantity."
}
$measurementReadiness = $calibration.matched_char_depth_measurement_readiness
if ($measurementReadiness.status -ne "awaiting_matched_experiments" -or $measurementReadiness.used_for_parameter_selection) {
    throw "Phase 6 matched char-depth measurement protocol changed."
}
if ($measurementReadiness.required_observation_count -ne 24 -or $measurementReadiness.scheduled_observation_count -ne 24 -or $measurementReadiness.complete_observation_count -ne 0 -or $measurementReadiness.incomplete_slots.Count -ne 24 -or $measurementReadiness.missing_slots.Count -ne 0 -or $measurementReadiness.invalid_slots.Count -ne 0 -or $measurementReadiness.duplicate_slots.Count -ne 0 -or $measurementReadiness.unexpected_slots.Count -ne 0 -or $measurementReadiness.ready_for_physical_char_thickness_calibration) {
    throw "Phase 6 matched char-depth data gate changed."
}
$experimentPlan = $calibration.char_depth_experiment_execution_plan
$experimentReadiness = $experimentPlan.readiness
if ($experimentPlan.schedule.Count -ne 24 -or $experimentReadiness.scheduled_run_count -ne 24 -or $experimentReadiness.unique_slot_count -ne 24 -or $experimentReadiness.template_file_count -ne 6 -or $experimentReadiness.missing_template_files.Count -ne 0 -or $experimentReadiness.invalid_schedule_rows.Count -ne 0 -or -not $experimentReadiness.technical_plan_complete -or $experimentReadiness.authorized_to_execute -or $experimentReadiness.missing_external_approvals.Count -ne 3) {
    throw "Phase 6 char-depth experiment execution plan gate changed."
}
if ($experimentPlan.schedule[0].run_id -ne "CF6O-F035-T0060-R01" -or $experimentPlan.schedule[23].run_id -ne "CF6O-F070-T0600-R03") {
    throw "Phase 6 char-depth run schedule changed."
}
foreach ($path in @($result.image, $result.report, $result.holdout_report, $result.replicate_holdout_report, $result.layer_profile_report, $result.kinetics_report, $result.tar_residence_sensitivity_report, $result.gas_transport_readiness_report, $result.char_geometry_report, $result.char_depth_benchmark_report, $result.char_depth_measurement_protocol_report, $result.char_depth_experiment_plan_report, $measurementReadiness.template_path, $result.top_candidates_csv, $result.final_stage)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Phase 6 artifact was not produced: $path"
    }
}
Add-Type -AssemblyName System.Drawing
$image = [System.Drawing.Image]::FromFile($result.image)
try {
    if ($image.Width -ne 1280 -or $image.Height -ne 720) {
        throw "Phase 6 PNG has an unexpected resolution."
    }
}
finally {
    $image.Dispose()
}
Write-Host "Phase 6 calibration validation succeeded: $OutputDir"
