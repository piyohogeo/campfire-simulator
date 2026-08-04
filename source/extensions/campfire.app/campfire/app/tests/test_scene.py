import math

import campfire.app
import omni.kit.test
from pxr import Gf, Usd, UsdGeom, UsdPhysics


class TestScene(omni.kit.test.AsyncTestCase):
    async def test_fixed_scene_has_expected_structure(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_fixed_scene(stage)

        self.assertEqual(UsdGeom.GetStageUpAxis(stage), UsdGeom.Tokens.z)
        self.assertAlmostEqual(UsdGeom.GetStageMetersPerUnit(stage), 1.0)
        self.assertTrue(stage.GetPrimAtPath("/World/Ground"))
        self.assertTrue(stage.GetPrimAtPath("/World/Camera"))
        self.assertTrue(stage.GetPrimAtPath("/World/IgnitionSource"))
        self.assertEqual(
            len(list(stage.GetPrimAtPath("/World/Logs").GetChildren())), 4
        )
        self.assertEqual(
            len(list(stage.GetPrimAtPath("/World/Stones").GetChildren())), 12
        )

    async def test_repopulation_is_idempotent(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_fixed_scene(stage)
        campfire.app.populate_fixed_scene(stage)

        self.assertEqual(
            len(list(stage.GetPrimAtPath("/World/Logs").GetChildren())), 4
        )

    async def test_flow_scene_has_emitter_simulation_and_colliders(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_flow_scene(stage)

        emitter = stage.GetPrimAtPath(campfire.app.FLOW_EMITTER_PATH)
        simulate = stage.GetPrimAtPath(campfire.app.FLOW_SIMULATE_PATH)
        self.assertEqual(emitter.GetTypeName(), "FlowEmitterSphere")
        self.assertEqual(simulate.GetTypeName(), "FlowSimulate")
        self.assertAlmostEqual(simulate.GetAttribute("densityCellSize").Get(), 0.025)
        self.assertTrue(simulate.GetAttribute("physicsCollisionEnabled").Get())
        self.assertTrue(simulate.GetAttribute("forceSimulate").Get())
        self.assertTrue(simulate.GetAttribute("simulateWhenPaused").Get())
        self.assertTrue(
            stage.GetPrimAtPath("/World/Flow/Simulate/nanoVdbExport")
            .GetAttribute("readbackEnabled")
            .Get()
        )
        self.assertEqual(
            sum(
                1
                for log in stage.GetPrimAtPath("/World/Logs").GetChildren()
                if log.HasAPI(UsdPhysics.CollisionAPI)
            ),
            4,
        )
        self.assertFalse(stage.GetPrimAtPath("/World/IgnitionSource"))

    async def test_flow_emitter_motion_reaches_expected_positions(self):
        self.assertTrue(
            Gf.IsClose(
                campfire.app.emitter_position_for_frame(1),
                Gf.Vec3f(-0.18, 0.0, 0.48),
                1e-5,
            )
        )
        midpoint = campfire.app.emitter_position_for_frame(105)
        self.assertAlmostEqual(midpoint[0], 0.0, places=5)
        self.assertTrue(
            Gf.IsClose(
                campfire.app.emitter_position_for_frame(220),
                Gf.Vec3f(0.18, 0.0, 0.48),
                1e-5,
            )
        )

    async def test_phase2_scene_has_dynamic_logs_with_persistent_ids(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase2_scene(stage)

        self.assertEqual(campfire.app.list_log_ids(stage), [
            "Log_00", "Log_01", "Log_02", "Log_03"
        ])
        for log_id in campfire.app.list_log_ids(stage):
            log = stage.GetPrimAtPath(f"/World/Logs/{log_id}")
            self.assertTrue(log.HasAPI(UsdPhysics.CollisionAPI))
            self.assertTrue(log.HasAPI(UsdPhysics.RigidBodyAPI))
            self.assertTrue(log.HasAPI(UsdPhysics.MassAPI))
            self.assertGreater(log.GetAttribute("physics:mass").Get(), 0.0)
            self.assertEqual(log.GetAttribute("campfire:logId").Get(), log_id)

        self.assertEqual(
            sum(
                1
                for stone in stage.GetPrimAtPath("/World/Stones").GetChildren()
                if stone.HasAPI(UsdPhysics.CollisionAPI)
            ),
            12,
        )

    async def test_add_move_and_emitter_follow_share_log_identity(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase2_scene(stage)
        campfire.app.add_scenario_log(stage)
        self.assertEqual(len(campfire.app.list_log_ids(stage)), 5)

        campfire.app.move_log(stage, "Log_04", (0.25, -0.10, 2.0), 15.0)
        log_position = campfire.app.get_log_world_position(stage, "Log_04")
        emitter_position = campfire.app.set_emitter_follow(stage, "Log_04")
        self.assertTrue(Gf.IsClose(log_position, Gf.Vec3d(0.25, -0.10, 2.0), 1e-6))
        self.assertTrue(
            Gf.IsClose(emitter_position, Gf.Vec3f(0.25, -0.10, 2.12), 1e-5)
        )

        with self.assertRaises(ValueError):
            campfire.app.add_scenario_log(stage)

    async def test_wood_grid_uses_dry_basis_moisture_and_si_mass(self):
        model = campfire.app.create_cylindrical_wood_model(
            "TestLog", 0.16, 1.8, moisture_ratio_dry_basis=0.20
        )
        metrics = model.metrics()
        expected_dry_mass = math.pi * 0.16**2 * 1.8 * 520.0
        self.assertEqual(metrics["cell_count"], 24 * 12 * 4)
        self.assertAlmostEqual(metrics["dry_wood_mass_kg"], expected_dry_mass, places=9)
        self.assertAlmostEqual(
            metrics["moisture_mass_kg"] / metrics["dry_wood_mass_kg"],
            0.20,
            places=9,
        )
        self.assertAlmostEqual(model.mass_balance_error_kg, 0.0, places=10)

    async def test_heat_conduction_alone_conserves_sensible_energy(self):
        parameters = campfire.app.WoodModelParameters(
            convection_w_m2_k=0.0,
            emissivity=0.0,
            evaporation_start_temperature_k=5000.0,
            pyrolysis_start_temperature_k=5000.0,
            pyrolysis_full_temperature_k=5100.0,
            char_oxidation_start_temperature_k=5000.0,
        )
        model = campfire.app.create_cylindrical_wood_model(
            "ConductionLog",
            0.04,
            0.20,
            0.0,
            axial_cells=2,
            circumferential_cells=4,
            radial_cells=2,
            parameters=parameters,
        )
        model.cells[0].temperature_k = 500.0

        def sensible_energy():
            return sum(
                cell.temperature_k
                * cell.dry_wood_mass_kg
                * parameters.wood_specific_heat_j_kg_k
                for cell in model.cells
            )

        energy_before = sensible_energy()
        model.step(0.1, 0.0)
        self.assertAlmostEqual(sensible_energy(), energy_before, places=7)
        self.assertLess(model.cells[0].temperature_k, 500.0)
        self.assertGreater(max(cell.temperature_k for cell in model.cells[1:]), 293.15)

    async def test_wet_kindling_evaporates_and_ignites_after_dry_kindling(self):
        dry = campfire.app.create_cylindrical_wood_model(
            "DryKindling", 0.03, 0.35, 0.0,
            axial_cells=6, circumferential_cells=6, radial_cells=3
        )
        wet = campfire.app.create_cylindrical_wood_model(
            "WetKindling", 0.03, 0.35, 0.40,
            axial_cells=6, circumferential_cells=6, radial_cells=3
        )
        dry_ignition = None
        wet_ignition = None
        for step_index in range(1, 2401):
            dry_result = dry.step(0.1, 100_000.0)
            wet_result = wet.step(0.1, 100_000.0)
            if dry_ignition is None and dry_result.pyrolysis_gas_rate_kg_s > 1.0e-6:
                dry_ignition = step_index * 0.1
            if wet_ignition is None and wet_result.pyrolysis_gas_rate_kg_s > 1.0e-6:
                wet_ignition = step_index * 0.1

        self.assertIsNotNone(dry_ignition)
        self.assertIsNotNone(wet_ignition)
        self.assertGreater(wet_ignition, dry_ignition)
        self.assertGreater(wet.emitted_water_kg, 0.0)
        for model in (dry, wet):
            self.assertLess(abs(model.mass_balance_error_kg), 1.0e-9)
            for cell in model.cells:
                self.assertTrue(math.isfinite(cell.temperature_k))
                self.assertGreaterEqual(cell.moisture_mass_kg, 0.0)
                self.assertGreaterEqual(cell.dry_wood_mass_kg, 0.0)
                self.assertGreaterEqual(cell.char_mass_kg, 0.0)
                self.assertGreaterEqual(cell.ash_mass_kg, 0.0)

    async def test_wood_state_round_trips_on_log_prim_and_maps_to_flow(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase2_scene(stage)
        prim = stage.GetPrimAtPath("/World/Logs/Log_00")
        model = campfire.app.create_cylindrical_wood_model(
            "Log_00", 0.16, 1.8, 0.12, axial_cells=3,
            circumferential_cells=4, radial_cells=2
        )
        result = model.step(0.1, 150_000.0)
        campfire.app.save_model_to_prim(model, prim)
        restored = campfire.app.load_model_from_prim(prim)
        self.assertEqual(restored.spec.log_id, "Log_00")
        self.assertEqual(len(restored.cells), len(model.cells))
        self.assertAlmostEqual(restored.elapsed_seconds, model.elapsed_seconds)
        self.assertAlmostEqual(restored.current_mass_kg, model.current_mass_kg)
        source = campfire.app.flow_source_from_model(restored, result)
        self.assertGreaterEqual(source.fuel, 0.0)
        self.assertLessEqual(source.fuel, 1.0)
        self.assertGreaterEqual(source.temperature, 0.0)

    async def test_phase3_scene_persists_dry_and_wet_authoritative_states(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(stage)
        dry_prim = stage.GetPrimAtPath("/World/Logs/Log_00")
        wet_prim = stage.GetPrimAtPath("/World/Logs/Log_01")
        dry = campfire.app.load_model_from_prim(dry_prim)
        wet = campfire.app.load_model_from_prim(wet_prim)
        self.assertEqual(len(dry.cells), 1152)
        self.assertEqual(len(wet.cells), 1152)
        self.assertAlmostEqual(
            dry.metrics()["moisture_mass_kg"]
            / dry.metrics()["dry_wood_mass_kg"],
            0.12,
        )
        self.assertAlmostEqual(
            wet.metrics()["moisture_mass_kg"]
            / wet.metrics()["dry_wood_mass_kg"],
            0.60,
        )
        emitter = stage.GetPrimAtPath(campfire.app.FLOW_EMITTER_PATH)
        self.assertEqual(emitter.GetAttribute("fuel").Get(), 0.0)
        self.assertEqual(
            stage.GetRootLayer().customLayerData["campfire:phase"], "phase3"
        )

    async def test_log_cabin_has_more_air_than_dense_parallel_stack(self):
        dense = campfire.app.estimate_air_supply(
            campfire.app.dense_stack_placements()
        )
        cabin = campfire.app.estimate_air_supply(
            campfire.app.log_cabin_placements()
        )
        self.assertGreater(dense.contact_pairs, 0)
        self.assertGreater(cabin.orientation_diversity, dense.orientation_diversity)
        self.assertGreater(cabin.ventilation_factor, dense.ventilation_factor)
        self.assertGreater(cabin.mean_oxygen_factor, dense.mean_oxygen_factor)
        for oxygen in (*dense.oxygen_by_log.values(), *cabin.oxygen_by_log.values()):
            self.assertGreaterEqual(oxygen, 0.05)
            self.assertLessEqual(oxygen, 1.0)

    async def test_crosswind_increases_bounded_dense_stack_oxygen(self):
        placements = campfire.app.dense_stack_placements()
        calm = campfire.app.estimate_air_supply(placements)
        wind = campfire.app.estimate_air_supply(placements, (3.0, 0.0, 0.0))
        self.assertGreater(wind.mean_oxygen_factor, calm.mean_oxygen_factor)
        self.assertEqual(wind.wind_factor, 1.0)
        self.assertLessEqual(max(wind.oxygen_by_log.values()), 1.0)

    async def test_air_supply_updates_surface_cells_and_heat_feedback(self):
        model = campfire.app.create_cylindrical_wood_model(
            "AirLog", 0.03, 0.35, 0.12,
            axial_cells=4, circumferential_cells=4, radial_cells=2
        )
        campfire.app.apply_oxygen_to_model(model, 0.42)
        surface = [cell for cell in model.cells if cell.surface_exposure > 0.0]
        interior = [cell for cell in model.cells if cell.surface_exposure == 0.0]
        self.assertTrue(all(cell.oxygen_factor == 0.42 for cell in surface))
        self.assertTrue(all(cell.oxygen_factor == 0.0 for cell in interior))
        self.assertLess(
            campfire.app.heat_feedback_factor(0.42),
            campfire.app.heat_feedback_factor(0.80),
        )

    async def test_log_cabin_air_feedback_ignites_before_dense_stack(self):
        comparison = campfire.app.run_stack_air_comparison()
        dense = comparison["dense"]
        cabin = comparison["cabin"]
        self.assertIsNotNone(dense["ignition_seconds"])
        self.assertIsNotNone(cabin["ignition_seconds"])
        self.assertLess(cabin["ignition_seconds"], dense["ignition_seconds"])
        self.assertGreater(cabin["oxygen_factor"], dense["oxygen_factor"])
        self.assertGreater(
            cabin["emitted_pyrolysis_gas_kg"],
            dense["emitted_pyrolysis_gas_kg"],
        )
        self.assertLess(abs(dense["mass_balance_error_kg"]), 1.0e-9)
        self.assertLess(abs(cabin["mass_balance_error_kg"]), 1.0e-9)

    async def test_phase4_scene_contains_both_oxygen_annotated_stacks(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase4_scene(stage)
        logs = list(stage.GetPrimAtPath("/World/Logs").GetChildren())
        dense = [log for log in logs if log.GetAttribute("campfire:stackScenario").Get() == "dense"]
        cabin = [log for log in logs if log.GetAttribute("campfire:stackScenario").Get() == "cabin"]
        self.assertEqual(len(dense), 6)
        self.assertEqual(len(cabin), 4)
        self.assertTrue(all(log.GetAttribute("campfire:oxygenFactor").Get() > 0.0 for log in logs))
        self.assertFalse(
            stage.GetPrimAtPath(campfire.app.FLOW_EMITTER_PATH)
            .GetAttribute("enabled")
            .Get()
        )
        self.assertEqual(stage.GetRootLayer().customLayerData["campfire:phase"], "phase4")

    async def test_local_heat_flux_sequence_targets_selected_cells(self):
        model = campfire.app.create_cylindrical_wood_model(
            "LocalHeat", 0.04, 0.20, 0.0,
            axial_cells=2, circumferential_cells=4, radial_cells=2
        )
        fluxes = [0.0] * len(model.cells)
        target = next(
            index for index, cell in enumerate(model.cells)
            if cell.surface_exposure > 0.0
        )
        fluxes[target] = 50_000.0
        initial = [cell.temperature_k for cell in model.cells]
        model.step(0.1, fluxes)
        self.assertGreater(model.cells[target].temperature_k, initial[target])
        with self.assertRaises(ValueError):
            model.step(0.1, fluxes[:-1])

    async def test_cross_section_support_selects_burned_failure_location(self):
        model = campfire.app.create_phase5_model()
        initial = campfire.app.assess_cross_section_support(model)
        self.assertAlmostEqual(initial.weakest_support_ratio, 1.0, places=9)
        cells_per_section = (
            model.spec.circumferential_cells * model.spec.radial_cells
        )
        failed_index = 5
        start = failed_index * cells_per_section
        for cell in model.cells[start : start + cells_per_section]:
            original = cell.dry_wood_mass_kg
            cell.dry_wood_mass_kg = original * 0.20
            cell.char_mass_kg = original * 0.08
        assessment = campfire.app.assess_cross_section_support(model)
        self.assertTrue(assessment.failed)
        self.assertEqual(assessment.weakest_section, failed_index)
        self.assertEqual(assessment.split_index, failed_index + 1)
        self.assertLess(
            assessment.weakest_support_ratio,
            assessment.failure_threshold,
        )

    async def test_phase5_release_removes_joint_and_updates_segment_physics(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase5_scene(stage)
        model = campfire.app.create_phase5_model()
        cells_per_section = (
            model.spec.circumferential_cells * model.spec.radial_cells
        )
        for cell in model.cells[5 * cells_per_section : 6 * cells_per_section]:
            cell.dry_wood_mass_kg *= 0.15
        assessment = campfire.app.assess_cross_section_support(model)
        updates = campfire.app.release_phase5_structure(stage, model, assessment)
        self.assertFalse(stage.GetPrimAtPath(campfire.app.PHASE5_JOINT_PATH))
        self.assertEqual(len(updates), 2)
        self.assertAlmostEqual(
            sum(update.mass_kg for update in updates),
            model.current_mass_kg,
            places=9,
        )
        for update in updates:
            prim = stage.GetPrimAtPath(update.path)
            self.assertTrue(prim.GetAttribute("campfire:constraintReleased").Get())
            self.assertAlmostEqual(
                prim.GetAttribute("physics:mass").Get(), update.mass_kg, places=6
            )
            self.assertLessEqual(update.collider_radius_m, model.spec.radius_m)

    async def test_collapse_scenario_releases_and_reignites_with_mass_balance(self):
        result = campfire.app.run_collapse_reignition_scenario()
        self.assertGreater(result["initial_support_ratio"], result["failure_threshold"])
        self.assertLessEqual(
            result["support_ratio_at_release"], result["failure_threshold"]
        )
        self.assertGreater(
            result["post_collapse_oxygen_factor"],
            result["pre_collapse_oxygen_factor"],
        )
        self.assertTrue(result["reignited"], result)
        self.assertGreater(result["reignition_gain"], 1.05)
        self.assertAlmostEqual(
            result["segment_mass_sum_kg"], result["remaining_mass_kg"], places=9
        )
        self.assertLess(abs(result["mass_balance_error_kg"]), 1.0e-9)
        self.assertTrue(result["all_values_finite"])

    async def test_nist_reference_is_fixed_and_higher_flux_ignites_first(self):
        reference = campfire.app.load_nist_plywood_reference()
        self.assertEqual(reference["report"], "NISTIR 7094")
        self.assertEqual(reference["method"]["replicates_per_flux"], 3)
        self.assertAlmostEqual(reference["panel_model"]["nominal_thickness_m"], 0.0127)
        self.assertEqual(reference["panel_model"]["plywood_layer_count"], 5)
        self.assertFalse(reference["panel_model"]["adhesive_layers_explicit"])
        self.assertEqual(reference["arrhenius_model"]["reaction_order"], 1.0)
        self.assertEqual(len(reference["arrhenius_model"]["source_pathways"]), 3)
        for pathway in reference["arrhenius_model"]["source_pathways"]:
            self.assertAlmostEqual(
                pathway["preexponential_per_min"] / 60.0,
                pathway["preexponential_s"],
            )
        self.assertEqual(
            reference["holdout"]["material"], "External Oriented Strandboard"
        )
        self.assertFalse(reference["holdout"]["used_for_parameter_selection"])
        self.assertEqual(
            [target["time_to_sustained_ignition_s"] for target in reference["holdout"]["targets"]],
            [39.7, 10.6],
        )
        selection, validation = campfire.app.build_replicate_split_targets(reference)
        self.assertEqual(selection[0]["sample_ids"], ["SAMP.1", "SAMP.2"])
        self.assertEqual(validation[0]["sample_ids"], ["SAMP.3"])
        self.assertAlmostEqual(selection[0]["time_to_sustained_ignition_s"], 43.515)
        self.assertAlmostEqual(selection[1]["time_to_sustained_ignition_s"], 8.245)
        self.assertAlmostEqual(validation[0]["time_to_sustained_ignition_s"], 54.23)
        self.assertAlmostEqual(validation[1]["time_to_sustained_ignition_s"], 6.69)
        parameters = campfire.app.WoodModelParameters()
        results = [
            campfire.app.simulate_layered_coupon(target, reference, parameters)
            for target in reference["targets"]
        ]
        self.assertIsNotNone(results[0].ignition_seconds)
        self.assertIsNotNone(results[1].ignition_seconds)
        self.assertGreater(results[0].ignition_seconds, results[1].ignition_seconds)
        for result in results:
            self.assertLess(abs(result.mass_balance_error_kg), 1.0e-9)
            self.assertTrue(result.all_values_finite)
            self.assertEqual(result.model_kind, "layered_plywood")
            self.assertEqual(result.layer_count, 5)
            self.assertEqual(len(result.final_layer_temperatures_k), 5)

    async def test_layered_panel_preserves_mass_and_heats_through_five_plies(self):
        reference = campfire.app.load_nist_plywood_reference()
        target = reference["targets"][0]
        model = campfire.app.create_layered_coupon(
            target, reference, campfire.app.WoodModelParameters()
        )
        self.assertEqual(model.spec.layer_count, 5)
        self.assertAlmostEqual(model.spec.thickness_m, 0.0127)
        self.assertEqual(model.spec.layer_orientations_deg, (0.0, 90.0, 0.0, 90.0, 0.0))
        self.assertAlmostEqual(model.initial_mass_kg, 0.0647, places=9)
        self.assertEqual(
            [cell.surface_exposure for cell in model.cells],
            [1.0, 0.0, 0.0, 0.0, 0.0],
        )
        for _ in range(20):
            model.step(0.1, 35_000.0)
        self.assertGreater(model.cells[0].temperature_k, model.cells[1].temperature_k)
        self.assertGreater(model.cells[1].temperature_k, model.cells[2].temperature_k)
        self.assertLess(abs(model.mass_balance_error_kg), 1.0e-9)

    async def test_arrhenius_rate_is_first_order_and_increases_with_temperature(self):
        parameters = campfire.app.arrhenius_baseline_parameters()
        self.assertEqual(parameters.pyrolysis_rate_model, "arrhenius_first_order")
        rates = [
            campfire.app.arrhenius_pyrolysis_rate_constant_s(parameters, temperature)
            for temperature in (500.0, 600.0, 700.0)
        ]
        self.assertGreater(rates[1], rates[0])
        self.assertGreater(rates[2], rates[1])
        with self.assertRaises(ValueError):
            campfire.app.arrhenius_pyrolysis_rate_constant_s(parameters, 0.0)

    async def test_nist_grid_search_improves_baseline_without_hiding_error(self):
        calibration = campfire.app.run_nist_plywood_calibration()
        self.assertEqual(calibration["candidate_count"], 48)
        self.assertTrue(calibration["improved"])
        self.assertGreater(calibration["improvement_fraction"], 0.0)
        self.assertLess(
            calibration["best"]["score_rmse_relative"],
            calibration["baseline"]["score_rmse_relative"],
        )
        self.assertEqual(len(calibration["best"]["cases"]), 2)
        self.assertEqual(calibration["panel_model"]["plywood_layer_count"], 5)
        self.assertEqual(
            calibration["best"]["parameters"]["pyrolysis_rate_model"],
            "arrhenius_first_order",
        )
        self.assertGreater(
            calibration["best"]["parameters"][
                "pyrolysis_arrhenius_preexponential_s"
            ],
            0.0,
        )
        for case in calibration["best"]["cases"]:
            self.assertEqual(case["model_kind"], "layered_plywood")
            self.assertEqual(case["layer_count"], 5)
            self.assertEqual(len(case["final_layer_temperatures_k"]), 5)
        selection = calibration["selection"]
        self.assertTrue(selection["improved"])
        self.assertEqual(selection["sample_ids"], ["SAMP.1", "SAMP.2"])
        self.assertEqual(selection["best"]["parameters"], calibration["best"]["parameters"])
        replicate_holdout = calibration["replicate_holdout"]
        self.assertFalse(replicate_holdout["used_for_parameter_selection"])
        self.assertEqual(replicate_holdout["sample_ids"], ["SAMP.3"])
        self.assertEqual(
            replicate_holdout["calibrated"]["parameters"],
            calibration["best"]["parameters"],
        )
        for case in replicate_holdout["calibrated"]["cases"]:
            self.assertTrue(case["all_values_finite"])
            self.assertLess(abs(case["mass_balance_error_kg"]), 1.0e-9)
        holdout = calibration["holdout"]
        self.assertFalse(holdout["used_for_parameter_selection"])
        self.assertEqual(holdout["calibrated"]["parameters"], calibration["best"]["parameters"])
        self.assertEqual(len(holdout["calibrated"]["cases"]), 2)
        for case in holdout["calibrated"]["cases"]:
            self.assertTrue(case["all_values_finite"])
            self.assertLess(abs(case["mass_balance_error_kg"]), 1.0e-9)
            self.assertEqual(case["model_kind"], "layered_osb")
            self.assertEqual(case["layer_count"], 1)

    async def test_phase6_scene_visualizes_observed_baseline_and_calibrated_values(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase6_scene(stage)
        calibration = {
            "baseline": {
                "score_rmse_relative": 0.8,
                "cases": [
                    {"predicted_ignition_seconds": 25.0},
                    {"predicted_ignition_seconds": 12.0},
                ],
            },
            "best": {
                "score_rmse_relative": 0.4,
                "cases": [
                    {"predicted_ignition_seconds": 44.0},
                    {"predicted_ignition_seconds": 8.0},
                ],
            },
            "improvement_fraction": 0.5,
        }
        campfire.app.apply_phase6_calibration(stage, calibration)
        bars = []
        for flux in campfire.app.PHASE6_FLUXES:
            bars.extend(
                stage.GetPrimAtPath(
                    f"{campfire.app.PHASE6_BAR_ROOT}/Flux{flux}"
                ).GetChildren()
            )
        self.assertEqual(len(bars), 6)
        self.assertEqual(
            {bar.GetAttribute("campfire:series").Get() for bar in bars},
            {"observed", "baseline", "calibrated"},
        )
        self.assertTrue(
            all(bar.GetAttribute("campfire:valueSeconds").Get() > 0.0 for bar in bars)
        )
        metadata = stage.GetRootLayer().customLayerData
        self.assertEqual(metadata["campfire:phase"], "phase6")
        self.assertAlmostEqual(metadata["campfire:improvementFraction"], 0.5)
