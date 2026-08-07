import json
import math
import threading
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import campfire.app
import omni.kit.test
from pxr import Gf, Usd, UsdGeom, UsdPhysics


class TestScene(omni.kit.test.AsyncTestCase):
    async def test_timing_summary_excludes_warmup_and_reports_tail(self):
        summary = campfire.app.summarize_timing_ms([99.0, 1.0, 2.0, 3.0], 1)
        self.assertEqual(summary["sample_count"], 3)
        self.assertEqual(summary["warmup_samples_excluded"], 1)
        self.assertEqual(summary["total_ms"], 6.0)
        self.assertEqual(summary["mean_ms"], 2.0)
        self.assertEqual(summary["p95_ms"], 3.0)
        self.assertEqual(summary["max_ms"], 3.0)

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

    async def test_scalar_and_uniform_cell_heat_flux_are_equivalent(self):
        scalar = campfire.app.create_cylindrical_wood_model(
            "scalar_flux",
            radius_m=0.16,
            length_m=1.8,
            moisture_ratio_dry_basis=0.12,
        )
        per_cell = campfire.app.WoodThermalModel.from_dict(scalar.to_dict())
        uniform_fluxes = [150_000.0] * len(per_cell.cells)
        for _ in range(20):
            scalar_result = scalar.step(0.2, 150_000.0)
            per_cell_result = per_cell.step(0.2, uniform_fluxes)
        self.assertEqual(scalar_result, per_cell_result)
        self.assertEqual(scalar.to_dict(), per_cell.to_dict())
        self.assertEqual(scalar.metrics(), per_cell.metrics())

    async def test_numpy_backend_matches_python_for_complete_steps(self):
        python_model = campfire.app.create_cylindrical_wood_model(
            "python_backend",
            radius_m=0.04,
            length_m=0.20,
            moisture_ratio_dry_basis=0.12,
            axial_cells=4,
            circumferential_cells=6,
            radial_cells=3,
        )
        numpy_model = campfire.app.WoodThermalModel.from_dict(
            python_model.to_dict()
        )
        heat_fluxes = [
            150_000.0 if cell.surface_exposure > 0.0 else 0.0
            for cell in python_model.cells
        ]

        for _ in range(400):
            python_result = python_model.step(0.2, heat_fluxes)
            numpy_result = numpy_model.step(
                0.2,
                heat_fluxes,
                array_backend=campfire.app.NUMPY_ARRAY_BACKEND,
            )
            self.assertEqual(numpy_result, python_result)

        self.assertEqual(numpy_model.to_dict(), python_model.to_dict())
        self.assertEqual(numpy_model.metrics(), python_model.metrics())

        eager_numpy_phases = campfire.app.WoodThermalModel.from_dict(
            numpy_model.to_dict()
        )
        deferred_numpy_phases = campfire.app.WoodThermalModel.from_dict(
            numpy_model.to_dict()
        )
        for _ in range(20):
            eager_result = eager_numpy_phases.step(
                0.2, 70_000.0, array_backend=campfire.app.NUMPY_ARRAY_BACKEND
            )
            deferred_result = deferred_numpy_phases.step(
                0.2,
                70_000.0,
                array_backend=campfire.app.NUMPY_ARRAY_BACKEND,
                update_cell_phases=False,
            )
            self.assertEqual(deferred_result, eager_result)
            self.assertEqual(
                deferred_numpy_phases.metrics(), eager_numpy_phases.metrics()
            )
        deferred_numpy_phases.refresh_cell_phases()
        self.assertEqual(
            deferred_numpy_phases.to_dict(), eager_numpy_phases.to_dict()
        )

        arrhenius_python = campfire.app.create_cylindrical_wood_model(
            "arrhenius_python",
            radius_m=0.04,
            length_m=0.20,
            moisture_ratio_dry_basis=0.12,
            initial_temperature_k=650.0,
            axial_cells=2,
            circumferential_cells=4,
            radial_cells=2,
            parameters=campfire.app.parallel_arrhenius_baseline_parameters(),
        )
        for cell in arrhenius_python.cells:
            cell.dry_wood_specific_heat_j_kg_k = 1214.0
            cell.dry_wood_specific_heat_model = (
                campfire.app.USDA_FPL_NORMALIZED_DRY_WOOD_SPECIFIC_HEAT_MODEL
            )
        arrhenius_numpy = campfire.app.WoodThermalModel.from_dict(
            arrhenius_python.to_dict()
        )
        for _ in range(120):
            python_result = arrhenius_python.step(0.2, 70_000.0)
            numpy_result = arrhenius_numpy.step(
                0.2,
                70_000.0,
                array_backend=campfire.app.NUMPY_ARRAY_BACKEND,
            )
            self.assertEqual(numpy_result, python_result)
        self.assertEqual(arrhenius_numpy.to_dict(), arrhenius_python.to_dict())
        self.assertEqual(arrhenius_numpy.metrics(), arrhenius_python.metrics())

        original_heat_capacity = campfire.app.create_cylindrical_wood_model(
            "original_heat_capacity",
            radius_m=0.04,
            length_m=0.20,
            moisture_ratio_dry_basis=0.12,
            axial_cells=4,
            circumferential_cells=6,
            radial_cells=3,
        )
        fast_heat_capacity = campfire.app.WoodThermalModel.from_dict(
            original_heat_capacity.to_dict()
        )
        homogeneous_heat_capacity = campfire.app.WoodThermalModel.from_dict(
            original_heat_capacity.to_dict()
        )
        inline_heat_capacity = campfire.app.WoodThermalModel.from_dict(
            original_heat_capacity.to_dict()
        )
        slotted_heat_capacity = campfire.app.WoodThermalModel.from_dict(
            original_heat_capacity.to_dict()
        )
        slotted_heat_capacity.use_slotted_cell_storage()
        self.assertFalse(hasattr(slotted_heat_capacity.cells[0], "__dict__"))
        self.assertEqual(
            slotted_heat_capacity.to_dict(), original_heat_capacity.to_dict()
        )
        homogeneous, specific_heat_j_kg_k = (
            homogeneous_heat_capacity._homogeneous_constant_dry_wood_specific_heat_j_kg_k()
        )
        self.assertTrue(homogeneous)
        self.assertEqual(
            specific_heat_j_kg_k,
            homogeneous_heat_capacity.parameters.wood_specific_heat_j_kg_k,
        )
        for step_index in range(120):
            if step_index == 20:
                original_heat_capacity.cells[0].dry_wood_specific_heat_j_kg_k = 1214.0
                fast_heat_capacity.cells[0].dry_wood_specific_heat_j_kg_k = 1214.0
                homogeneous_heat_capacity.cells[
                    0
                ].dry_wood_specific_heat_j_kg_k = 1214.0
                inline_heat_capacity.cells[0].dry_wood_specific_heat_j_kg_k = 1214.0
                slotted_heat_capacity.cells[
                    0
                ].dry_wood_specific_heat_j_kg_k = 1214.0
            elif step_index == 40:
                original_heat_capacity.cells[0].dry_wood_specific_heat_j_kg_k = None
                fast_heat_capacity.cells[0].dry_wood_specific_heat_j_kg_k = None
                homogeneous_heat_capacity.cells[
                    0
                ].dry_wood_specific_heat_j_kg_k = None
                inline_heat_capacity.cells[0].dry_wood_specific_heat_j_kg_k = None
                slotted_heat_capacity.cells[
                    0
                ].dry_wood_specific_heat_j_kg_k = None
                original_heat_capacity.parameters = replace(
                    original_heat_capacity.parameters,
                    wood_specific_heat_j_kg_k=1600.0,
                )
                fast_heat_capacity.parameters = replace(
                    fast_heat_capacity.parameters,
                    wood_specific_heat_j_kg_k=1600.0,
                )
                homogeneous_heat_capacity.parameters = replace(
                    homogeneous_heat_capacity.parameters,
                    wood_specific_heat_j_kg_k=1600.0,
                )
                inline_heat_capacity.parameters = replace(
                    inline_heat_capacity.parameters,
                    wood_specific_heat_j_kg_k=1600.0,
                )
                slotted_heat_capacity.parameters = replace(
                    slotted_heat_capacity.parameters,
                    wood_specific_heat_j_kg_k=1600.0,
                )
            elif step_index == 60:
                for model in (
                    original_heat_capacity,
                    fast_heat_capacity,
                    homogeneous_heat_capacity,
                    inline_heat_capacity,
                    slotted_heat_capacity,
                ):
                    model.cells[0].dry_wood_specific_heat_j_kg_k = 1214.0
                    model.cells[0].dry_wood_specific_heat_model = (
                        campfire.app.USDA_FPL_NORMALIZED_DRY_WOOD_SPECIFIC_HEAT_MODEL
                    )
            heat_flux = 150_000.0 if step_index < 80 else 0.0
            original_result = original_heat_capacity.step(0.2, heat_flux)
            fast_result = fast_heat_capacity.step(
                0.2,
                heat_flux,
                python_constant_heat_capacity_fast_path=True,
            )
            homogeneous_result = homogeneous_heat_capacity.step(
                0.2,
                heat_flux,
                python_constant_heat_capacity_fast_path=True,
                python_homogeneous_heat_capacity_fast_path=True,
            )
            inline_result = inline_heat_capacity.step(
                0.2,
                heat_flux,
                python_constant_heat_capacity_fast_path=True,
                python_homogeneous_heat_capacity_fast_path=True,
                python_inline_homogeneous_sensible_heat_capacity_fast_path=True,
            )
            slotted_result = slotted_heat_capacity.step(
                0.2,
                heat_flux,
                python_constant_heat_capacity_fast_path=True,
                python_homogeneous_heat_capacity_fast_path=True,
                python_inline_homogeneous_sensible_heat_capacity_fast_path=True,
            )
            self.assertEqual(fast_result, original_result)
            self.assertEqual(homogeneous_result, original_result)
            self.assertEqual(inline_result, original_result)
            self.assertEqual(slotted_result, original_result)
        self.assertEqual(
            fast_heat_capacity.to_dict(), original_heat_capacity.to_dict()
        )
        self.assertEqual(
            homogeneous_heat_capacity.to_dict(), original_heat_capacity.to_dict()
        )
        self.assertEqual(
            inline_heat_capacity.to_dict(), original_heat_capacity.to_dict()
        )
        self.assertEqual(
            slotted_heat_capacity.to_dict(), original_heat_capacity.to_dict()
        )
        self.assertEqual(
            fast_heat_capacity.metrics(), original_heat_capacity.metrics()
        )
        self.assertEqual(
            homogeneous_heat_capacity.metrics(), original_heat_capacity.metrics()
        )
        self.assertEqual(
            inline_heat_capacity.metrics(), original_heat_capacity.metrics()
        )
        self.assertEqual(
            slotted_heat_capacity.metrics(), original_heat_capacity.metrics()
        )

        for field_name, invalid_value, expected_message in (
            (
                "dry_wood_specific_heat_j_kg_k",
                math.nan,
                "reference_specific_heat_j_kg_k must be finite and positive",
            ),
            ("temperature_k", 0.0, "temperature_k must be finite and positive"),
        ):
            invalid_model = campfire.app.create_cylindrical_wood_model(
                f"invalid_{field_name}",
                radius_m=0.04,
                length_m=0.20,
                moisture_ratio_dry_basis=0.12,
                axial_cells=2,
                circumferential_cells=4,
                radial_cells=2,
            )
            setattr(invalid_model.cells[0], field_name, invalid_value)
            with self.assertRaisesRegex(ValueError, expected_message):
                invalid_model.step(
                    0.2,
                    0.0,
                    python_constant_heat_capacity_fast_path=True,
                    python_homogeneous_heat_capacity_fast_path=True,
                    python_inline_homogeneous_sensible_heat_capacity_fast_path=True,
                )

        with self.assertRaisesRegex(
            ValueError, "Constant heat-capacity fast path requires the Python backend"
        ):
            numpy_model.step(
                0.2,
                0.0,
                array_backend=campfire.app.NUMPY_ARRAY_BACKEND,
                python_constant_heat_capacity_fast_path=True,
            )

        with self.assertRaisesRegex(
            ValueError,
            "Homogeneous heat-capacity fast path requires the constant-model fast path",
        ):
            original_heat_capacity.step(
                0.2,
                0.0,
                python_homogeneous_heat_capacity_fast_path=True,
            )

        with self.assertRaisesRegex(
            ValueError,
            "Inline homogeneous sensible heat-capacity fast path requires the homogeneous heat-capacity fast path",
        ):
            original_heat_capacity.step(
                0.2,
                0.0,
                python_constant_heat_capacity_fast_path=True,
                python_inline_homogeneous_sensible_heat_capacity_fast_path=True,
            )

        original_boundary = campfire.app.create_cylindrical_wood_model(
            "original_surface_boundary",
            radius_m=0.04,
            length_m=0.20,
            moisture_ratio_dry_basis=0.12,
            axial_cells=4,
            circumferential_cells=6,
            radial_cells=3,
        )
        fast_surface_boundary = campfire.app.WoodThermalModel.from_dict(
            original_boundary.to_dict()
        )
        self.assertGreater(
            sum(
                cell.external_area_m2 * cell.surface_exposure == 0.0
                for cell in original_boundary.cells
            ),
            0,
        )
        for step_index in range(120):
            heat_flux = (
                150_000.0
                if step_index < 60
                else [
                    150_000.0 if cell.surface_exposure > 0.0 else 0.0
                    for cell in original_boundary.cells
                ]
            )
            original_result = original_boundary.step(
                0.2,
                heat_flux,
                python_surface_boundary_fast_path=False,
            )
            fast_result = fast_surface_boundary.step(
                0.2,
                heat_flux,
                python_surface_boundary_fast_path=True,
            )
            self.assertEqual(fast_result, original_result)
        self.assertEqual(
            fast_surface_boundary.to_dict(), original_boundary.to_dict()
        )
        self.assertEqual(
            fast_surface_boundary.metrics(), original_boundary.metrics()
        )

        original_clamp = campfire.app.create_cylindrical_wood_model(
            "original_state_clamp",
            radius_m=0.04,
            length_m=0.20,
            moisture_ratio_dry_basis=0.12,
            axial_cells=4,
            circumferential_cells=6,
            radial_cells=3,
        )
        fast_state_clamp = campfire.app.WoodThermalModel.from_dict(
            original_clamp.to_dict()
        )
        for model in (original_clamp, fast_state_clamp):
            model.cells[0].moisture_mass_kg = -0.0
            model.cells[0].char_mass_kg = -0.0
        for step_index in range(120):
            heat_flux = 150_000.0 if step_index < 60 else 0.0
            original_result = original_clamp.step(
                0.2,
                heat_flux,
                python_state_clamp_fast_path=False,
            )
            fast_result = fast_state_clamp.step(
                0.2,
                heat_flux,
                python_state_clamp_fast_path=True,
            )
            self.assertEqual(fast_result, original_result)
            if step_index == 0:
                self.assertEqual(
                    math.copysign(
                        1.0, fast_state_clamp.cells[0].moisture_mass_kg
                    ),
                    1.0,
                )
                self.assertEqual(
                    math.copysign(1.0, fast_state_clamp.cells[0].char_mass_kg),
                    1.0,
                )
        self.assertEqual(fast_state_clamp.to_dict(), original_clamp.to_dict())
        self.assertEqual(fast_state_clamp.metrics(), original_clamp.metrics())
        full_metrics = fast_state_clamp.metrics()
        self.assertEqual(
            fast_state_clamp.runtime_metrics(),
            {
                name: full_metrics[name]
                for name in (
                    "surface_mean_temperature_k",
                    "moisture_mass_kg",
                    "dry_wood_mass_kg",
                    "char_mass_kg",
                    "ash_mass_kg",
                )
            },
        )
        topology = fast_state_clamp.capture_runtime_topology()
        self.assertEqual(
            fast_state_clamp.runtime_metrics(topology),
            fast_state_clamp.runtime_metrics(),
        )
        self.assertEqual(
            topology.initial_dry_mass_kg,
            sum(
                cell.dry_wood_mass_kg + cell.char_mass_kg + cell.ash_mass_kg
                for cell in fast_state_clamp.cells
            )
            + fast_state_clamp.emitted_pyrolysis_gas_kg
            + fast_state_clamp.emitted_char_gas_kg,
        )
        first_surface = topology.surface_cells[0]
        first_surface.temperature_k += 100.0
        first_surface.surface_exposure = 0.0
        self.assertNotEqual(
            fast_state_clamp.runtime_metrics(topology)[
                "surface_mean_temperature_k"
            ],
            fast_state_clamp.runtime_metrics()["surface_mean_temperature_k"],
        )

        eager_phases = campfire.app.create_cylindrical_wood_model(
            "eager_phases",
            radius_m=0.04,
            length_m=0.20,
            moisture_ratio_dry_basis=0.12,
            axial_cells=4,
            circumferential_cells=6,
            radial_cells=3,
        )
        deferred_phases = campfire.app.WoodThermalModel.from_dict(
            eager_phases.to_dict()
        )
        initial_deferred_phases = tuple(
            cell.phase for cell in deferred_phases.cells
        )
        for step_index in range(120):
            heat_flux = 150_000.0 if step_index < 60 else 0.0
            eager_result = eager_phases.step(0.2, heat_flux)
            deferred_result = deferred_phases.step(
                0.2, heat_flux, update_cell_phases=False
            )
            self.assertEqual(deferred_result, eager_result)
            self.assertEqual(deferred_phases.metrics(), eager_phases.metrics())
        self.assertEqual(
            tuple(cell.phase for cell in deferred_phases.cells),
            initial_deferred_phases,
        )
        deferred_phases.refresh_cell_phases()
        self.assertEqual(deferred_phases.to_dict(), eager_phases.to_dict())

        with self.assertRaisesRegex(ValueError, "Unsupported wood-step array backend"):
            numpy_model.step(0.2, 0.0, array_backend="unknown")

    async def test_wood_step_internal_timing_is_opt_in_and_state_neutral(self):
        unprofiled = campfire.app.create_cylindrical_wood_model(
            "unprofiled",
            radius_m=0.04,
            length_m=0.20,
            moisture_ratio_dry_basis=0.12,
            axial_cells=2,
            circumferential_cells=4,
            radial_cells=2,
        )
        profiled = campfire.app.WoodThermalModel.from_dict(unprofiled.to_dict())
        diagnosed = campfire.app.WoodThermalModel.from_dict(unprofiled.to_dict())
        timing_ms = {}
        state_diagnostics = {}

        unprofiled_result = unprofiled.step(0.2, 150_000.0)
        profiled_result = profiled.step(0.2, 150_000.0, timing_ms=timing_ms)
        diagnosed_result = diagnosed.step(
            0.2,
            150_000.0,
            state_diagnostics=state_diagnostics,
        )
        with self.assertRaisesRegex(
            ValueError, "diagnostics require cell phase updates"
        ):
            diagnosed.step(
                0.2,
                150_000.0,
                state_diagnostics={},
                update_cell_phases=False,
            )

        self.assertEqual(profiled_result, unprofiled_result)
        self.assertEqual(profiled.to_dict(), unprofiled.to_dict())
        self.assertEqual(diagnosed_result, unprofiled_result)
        self.assertEqual(diagnosed.to_dict(), unprofiled.to_dict())
        self.assertEqual(state_diagnostics["cells_evaluated"], len(diagnosed.cells))
        self.assertEqual(
            sum(
                count
                for name, count in state_diagnostics.items()
                if name.startswith("phase_") and name != "phase_changes"
            ),
            len(diagnosed.cells),
        )
        self.assertEqual(
            set(timing_ms),
            {
                "input_validation",
                "conduction",
                "sensible_heat",
                "evaporation",
                "pyrolysis",
                "char_oxidation",
                "state_finalize",
                "result_aggregation",
            },
        )
        for elapsed_ms in timing_ms.values():
            self.assertTrue(math.isfinite(elapsed_ms))
            self.assertGreaterEqual(elapsed_ms, 0.0)

        detailed_baseline = campfire.app.WoodThermalModel.from_dict(
            unprofiled.to_dict()
        )
        detailed_profile = campfire.app.WoodThermalModel.from_dict(
            unprofiled.to_dict()
        )
        detailed_timing_ms = {}
        detailed_sensible_heat_ms = {}
        baseline_result = detailed_baseline.step(0.2, 150_000.0)
        detailed_result = detailed_profile.step(
            0.2,
            150_000.0,
            timing_ms=detailed_timing_ms,
            sensible_heat_timing_ms=detailed_sensible_heat_ms,
        )
        self.assertEqual(detailed_result, baseline_result)
        self.assertEqual(detailed_profile.to_dict(), detailed_baseline.to_dict())
        self.assertEqual(
            set(detailed_sensible_heat_ms),
            {
                "heat_capacity_evaluation",
                "interior_conduction_update",
                "surface_boundary_update",
                "loop_and_timer_overhead",
            },
        )
        for elapsed_ms in detailed_sensible_heat_ms.values():
            self.assertTrue(math.isfinite(elapsed_ms))
            self.assertGreaterEqual(elapsed_ms, 0.0)
        with self.assertRaisesRegex(
            ValueError, "requires wood-step timing"
        ):
            detailed_baseline.step(
                0.2,
                150_000.0,
                sensible_heat_timing_ms={},
            )

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
            dry_result = dry.step(
                0.1,
                100_000.0,
                python_constant_heat_capacity_fast_path=True,
            )
            wet_result = wet.step(
                0.1,
                100_000.0,
                python_constant_heat_capacity_fast_path=True,
            )
            if dry_ignition is None and dry_result.pyrolysis_gas_rate_kg_s > 1.0e-6:
                dry_ignition = step_index * 0.1
            if wet_ignition is None and wet_result.pyrolysis_gas_rate_kg_s > 1.0e-6:
                wet_ignition = step_index * 0.1
            if dry_ignition is not None and wet_ignition is not None:
                break

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

    async def test_resident_snapshot_adapter_commits_one_revision_to_all_consumers(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(stage)
        log_ids = (campfire.app.PHASE3_DRY_LOG_ID, campfire.app.PHASE3_WET_LOG_ID)
        initial_dry_mass = {
            log_id: sum(
                cell.dry_wood_mass_kg + cell.char_mass_kg + cell.ash_mass_kg
                for cell in campfire.app.load_model_from_prim(
                    stage.GetPrimAtPath(f"/World/Logs/{log_id}")
                ).cells
            )
            for log_id in log_ids
        }
        rows = (
            campfire.app.ResidentPublishedRow(
                820.0, 1.0, 8.0, 1.5, 0.1, 0.72, 0.64, 0.4, 0.7, 0.2, 0.008
            ),
            campfire.app.ResidentPublishedRow(
                430.0, 3.0, 9.0, 0.4, 0.05, 0.88, 0.82, 0.0, 0.0, 0.1, 0.0
            ),
        )
        rounded = campfire.app.ResidentPublishedRow(
            600.0,
            1.0,
            1.0,
            0.0,
            0.0,
            1.0 + 5.0e-16,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
        )
        self.assertEqual(rounded.remaining_mass_ratio, 1.0)
        snapshot = campfire.app.ResidentPublishedSnapshot(1, 0, log_ids, rows)
        adapter = campfire.app.UsdResidentSnapshotAdapter(
            stage,
            log_ids,
            initial_dry_mass,
            profile_transactions=True,
        )
        with self.assertRaisesRegex(RuntimeError, "active timeline"):
            adapter.publish(snapshot)
        adapter.on_timeline_started()
        adapter.publish(snapshot)

        emitter = stage.GetPrimAtPath(campfire.app.FLOW_EMITTER_PATH)
        self.assertAlmostEqual(emitter.GetAttribute("fuel").Get(), 0.4)
        self.assertAlmostEqual(emitter.GetAttribute("temperature").Get(), 0.7)
        self.assertEqual(
            emitter.GetAttribute("campfire:residentRevision").Get(), 1
        )
        for log_id, row in zip(log_ids, rows):
            prim = stage.GetPrimAtPath(f"/World/Logs/{log_id}")
            self.assertEqual(prim.GetAttribute("campfire:residentRevision").Get(), 1)
            self.assertAlmostEqual(
                prim.GetAttribute("campfire:surfaceTemperatureK").Get(),
                row.surface_mean_temperature_k,
            )
            self.assertAlmostEqual(
                prim.GetAttribute("campfire:charFraction").Get(),
                min(
                    1.0,
                    (row.char_mass_kg + row.ash_mass_kg)
                    / initial_dry_mass[log_id],
                ),
            )
            self.assertAlmostEqual(
                prim.GetAttribute("campfire:remainingMassRatio").Get(),
                row.remaining_mass_ratio,
            )
            self.assertAlmostEqual(
                prim.GetAttribute("campfire:weakestSupportRatio").Get(),
                row.weakest_support_ratio,
            )
        status = adapter.status()
        self.assertEqual(status["revision"], 1)
        self.assertEqual(status["publish_count"], 1)
        self.assertEqual(status["start_count"], 1)
        self.assertTrue(status["transaction_profiling_enabled"])
        self.assertEqual(status["transaction_profile_count"], 1)
        profile = adapter.transaction_profiles()[0]
        self.assertIsInstance(profile, campfire.app.ResidentUsdTransactionProfile)
        self.assertEqual(profile.status, "committed")
        self.assertEqual(profile.write_count, 19)
        self.assertEqual(
            profile.existing_property_count + profile.created_property_count,
            19,
        )
        self.assertLessEqual(profile.authored_old_value_count, 19)
        self.assertEqual(
            {name for name, _elapsed_ms in profile.group_ms},
            {"emitter_payload", "visual_payload", "diagnostic_payload", "revision"},
        )
        self.assertEqual(len(profile.attribute_ms), 19)
        self.assertEqual(
            profile.changed_write_count + profile.unchanged_write_count,
            19,
        )
        self.assertGreater(profile.total_ms, 0.0)
        self.assertGreaterEqual(profile.unattributed_ms, 0.0)
        repeated_snapshot = campfire.app.ResidentPublishedSnapshot(
            2, 0, log_ids, rows
        )
        adapter.publish(repeated_snapshot)
        repeated_profile = adapter.transaction_profiles()[1]
        self.assertEqual(repeated_profile.changed_write_count, 3)
        self.assertEqual(repeated_profile.unchanged_write_count, 16)
        self.assertEqual(
            dict(repeated_profile.attribute_write_disposition)[
                "Emitter.campfire:residentRevision"
            ],
            "changed",
        )
        self.assertEqual(
            dict(repeated_profile.attribute_write_disposition)["Emitter.temperature"],
            "unchanged",
        )
        with self.assertRaisesRegex(RuntimeError, "increase monotonically"):
            adapter.publish(snapshot)
        status = adapter.status()
        self.assertEqual(status["revision"], 2)
        self.assertEqual(status["publish_count"], 2)
        self.assertEqual(status["transaction_profile_count"], 2)
        adapter.on_timeline_stopped()
        self.assertTrue(adapter.close())
        self.assertFalse(adapter.close())

    async def test_resident_snapshot_adapter_rolls_back_and_rejects_other_threads(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(stage)
        log_ids = (campfire.app.PHASE3_DRY_LOG_ID, campfire.app.PHASE3_WET_LOG_ID)
        initial_dry_mass = {
            log_id: 1.0
            for log_id in log_ids
        }
        rows = tuple(
            campfire.app.ResidentPublishedRow(
                600.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.3, 0.4, 0.2, 0.006
            )
            for _ in log_ids
        )
        snapshot = campfire.app.ResidentPublishedSnapshot(1, 0, log_ids, rows)

        def fail_fourth_write(write_count, _name):
            if write_count == 4:
                raise RuntimeError("injected USD write failure")

        adapter = campfire.app.UsdResidentSnapshotAdapter(
            stage,
            log_ids,
            initial_dry_mass,
            write_observer=fail_fourth_write,
            profile_transactions=True,
        )
        adapter.on_timeline_started()
        emitter = stage.GetPrimAtPath(campfire.app.FLOW_EMITTER_PATH)
        original_fuel = emitter.GetAttribute("fuel").Get()
        with self.assertRaisesRegex(RuntimeError, "injected USD write failure"):
            adapter.publish(snapshot)
        self.assertEqual(emitter.GetAttribute("fuel").Get(), original_fuel)
        self.assertFalse(emitter.GetAttribute("campfire:residentRevision"))
        self.assertEqual(adapter.status()["revision"], 0)
        self.assertEqual(adapter.status()["publish_count"], 0)
        self.assertEqual(adapter.status()["transaction_profile_count"], 1)
        failed_profile = adapter.transaction_profiles()[0]
        self.assertEqual(failed_profile.status, "rolled_back")
        self.assertEqual(failed_profile.write_count, 4)
        self.assertEqual(
            failed_profile.changed_write_count + failed_profile.unchanged_write_count,
            4,
        )
        self.assertGreater(failed_profile.rollback_ms, 0.0)

        thread_errors = []

        def read_status_from_other_thread():
            try:
                adapter.status()
            except Exception as exc:
                thread_errors.append(exc)

        worker = threading.Thread(target=read_status_from_other_thread)
        worker.start()
        worker.join()
        self.assertEqual(len(thread_errors), 1)
        self.assertRegex(str(thread_errors[0]), "owner thread")
        adapter.close()

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

    async def test_fixed_grid_reaction_depth_does_not_claim_physical_char_thickness(self):
        reference = campfire.app.load_nist_plywood_reference()
        model = campfire.app.create_layered_coupon(
            reference["targets"][0], reference, campfire.app.WoodModelParameters()
        )
        conversions = (1.0, 0.75, 0.5, 0.25, 0.0)
        char_fractions = (0.2, 0.15, 0.1, 0.05, 0.0)
        for cell, conversion, char_fraction in zip(
            model.cells, conversions, char_fractions
        ):
            initial_dry_mass_kg = (
                model.spec.effective_dry_density_kg_m3 * cell.volume_m3
            )
            cell.dry_wood_mass_kg = initial_dry_mass_kg * (1.0 - conversion)
            cell.char_mass_kg = initial_dry_mass_kg * char_fraction

        diagnostic = model.char_geometry_diagnostic()
        self.assertEqual(
            diagnostic.layer_pyrolysis_conversion_fractions, conversions
        )
        self.assertEqual(
            diagnostic.layer_char_mass_fractions_initial_dry, char_fractions
        )
        self.assertAlmostEqual(
            diagnostic.equivalent_unshrunk_pyrolysis_depth_m, 0.00635
        )
        self.assertIsNone(diagnostic.physical_char_layer_thickness_m)
        self.assertIsNone(diagnostic.shrinkage_factor)
        self.assertFalse(diagnostic.ready_for_darcy_layer_thickness)

    async def test_external_char_depth_benchmark_blocks_cross_material_transfer(self):
        reference = campfire.app.load_nist_plywood_reference()
        benchmark = campfire.app.evaluate_external_plywood_char_depth_benchmark(
            reference,
            {
                "cases": [
                    {
                        "incident_heat_flux_kw_m2": 35.0,
                        "specimen_thickness_m": 0.0127,
                        "effective_dry_density_kg_m3": 471.7,
                        "equivalent_unshrunk_pyrolysis_depth_m": 0.00924,
                        "physical_char_layer_thickness_m": None,
                    }
                ]
            },
        )
        self.assertFalse(benchmark["used_for_parameter_selection"])
        self.assertFalse(benchmark["scored"])
        self.assertFalse(benchmark["ready_for_physical_thickness_transfer"])
        self.assertIsNone(benchmark["comparison_error_metric"])
        self.assertEqual(benchmark["matched_condition_count"], 3)
        self.assertEqual(benchmark["condition_count"], 10)
        self.assertAlmostEqual(
            benchmark["external_observation"]["char_depth_m"], 0.01377
        )
        self.assertAlmostEqual(benchmark["current_model"]["depth_m"], 0.00924)
        self.assertIsNone(
            benchmark["current_model"]["physical_char_layer_thickness_m"]
        )

    async def test_matched_char_depth_gate_requires_all_24_valid_observations(self):
        reference = campfire.app.load_nist_plywood_reference()
        blank = campfire.app.evaluate_matched_char_depth_measurement_readiness(
            reference
        )
        self.assertEqual(blank["required_observation_count"], 24)
        self.assertEqual(blank["scheduled_observation_count"], 24)
        self.assertEqual(blank["complete_observation_count"], 0)
        self.assertEqual(len(blank["incomplete_slots"]), 24)
        self.assertFalse(blank["ready_for_physical_char_thickness_calibration"])

        protocol = reference["matched_char_depth_measurement_protocol"]
        completed = tuple(
            campfire.app.CharDepthMeasurementObservation(
                incident_heat_flux_kw_m2=flux,
                time_s=time_s,
                replicate_id=replicate_id,
                initial_thickness_m=0.0127,
                current_total_thickness_m=0.0120,
                exposed_surface_displacement_m=0.0002,
                optical_char_layer_thickness_m=0.0040,
                isotherm_300c_layer_thickness_m=0.0038,
                thickness_uncertainty_m=0.0001,
                char_front_uncertainty_m=0.0002,
                wood_species_by_ply="Douglas-fir;Douglas-fir;Douglas-fir;Douglas-fir;Douglas-fir",
                adhesive_type="phenol-formaldehyde",
                individual_ply_thickness_m="0.00254;0.00254;0.00254;0.00254;0.00254",
                oven_dry_density_kg_m3=510.0,
                moisture_ratio_dry_basis=0.08,
                grain_orientation_by_ply_deg="0;90;0;90;0",
                mass_history_file=f"flux_{flux:g}_time_{time_s:g}_rep_{replicate_id}.csv",
            )
            for flux in protocol["required_heat_fluxes_kw_m2"]
            for time_s in protocol["required_times_s"]
            for replicate_id in protocol["required_replicate_ids"]
        )
        ready = campfire.app.evaluate_char_depth_measurement_readiness(
            completed,
            required_heat_fluxes_kw_m2=tuple(
                protocol["required_heat_fluxes_kw_m2"]
            ),
            required_times_s=tuple(protocol["required_times_s"]),
            required_replicate_ids=tuple(protocol["required_replicate_ids"]),
        )
        self.assertEqual(ready.complete_observation_count, 24)
        self.assertTrue(ready.ready_for_physical_char_thickness_calibration)

    async def test_char_depth_experiment_plan_is_complete_but_not_authorized(self):
        protocol = campfire.app.load_char_depth_experiment_protocol()
        schedule = campfire.app.load_char_depth_run_schedule()
        readiness = campfire.app.evaluate_char_depth_experiment_plan()

        self.assertEqual(
            protocol["coordinate_frame"]["z_axis"],
            "Positive from the initial exposed surface into the specimen toward the unexposed face.",
        )
        self.assertEqual(len(schedule), 24)
        self.assertEqual(schedule[0].run_id, "CF6O-F035-T0060-R01")
        self.assertEqual(schedule[-1].run_id, "CF6O-F070-T0600-R03")
        self.assertEqual(readiness.unique_slot_count, 24)
        self.assertEqual(readiness.template_file_count, 6)
        self.assertFalse(readiness.missing_template_files)
        self.assertFalse(readiness.invalid_schedule_rows)
        self.assertTrue(readiness.technical_plan_complete)
        self.assertFalse(readiness.authorized_to_execute)
        self.assertEqual(len(readiness.missing_external_approvals), 3)

    async def test_char_depth_offline_dry_run_is_blank_and_not_importable(self):
        with TemporaryDirectory() as temporary_directory:
            run_directory = campfire.app.create_char_depth_dry_run_package(
                "CF6O-F035-T0060-R01", Path(temporary_directory)
            )
            readiness = campfire.app.evaluate_char_depth_dry_run_package(
                run_directory
            )
            self.assertEqual(readiness.run_id, "CF6O-F035-T0060-R01")
            self.assertTrue(readiness.structural_complete)
            self.assertTrue(readiness.dry_run_package_complete)
            self.assertFalse(readiness.contains_measurements)
            self.assertFalse(readiness.authorized_to_execute)
            self.assertFalse(readiness.eligible_for_measurement_import)
            self.assertEqual(len(readiness.missing_runtime_metadata), 9)
            self.assertFalse(readiness.missing_files)
            self.assertFalse(readiness.missing_directories)
            self.assertFalse(readiness.invalid_files)

            repeated_directory = campfire.app.create_char_depth_dry_run_package(
                "CF6O-F035-T0060-R01", Path(temporary_directory)
            )
            self.assertEqual(repeated_directory, run_directory)

            (run_directory / "raw_images" / "unexpected_measurement.png").write_bytes(
                b"presence alone must close the blank-package gate"
            )
            changed = campfire.app.evaluate_char_depth_dry_run_package(
                run_directory
            )
            self.assertTrue(changed.contains_measurements)
            self.assertFalse(changed.dry_run_package_complete)
            self.assertFalse(changed.eligible_for_measurement_import)
            with self.assertRaises(FileExistsError):
                campfire.app.create_char_depth_dry_run_package(
                    "CF6O-F035-T0060-R01", Path(temporary_directory)
                )

    async def test_lab_handoff_cannot_grant_repository_authority(self):
        blank = campfire.app.evaluate_char_depth_lab_handoff()
        self.assertTrue(blank.template_contract_complete)
        self.assertEqual(blank.required_runtime_field_count, 9)
        self.assertEqual(blank.populated_runtime_field_count, 0)
        self.assertEqual(len(blank.missing_runtime_metadata), 9)
        self.assertEqual(blank.required_external_evidence_count, 3)
        self.assertEqual(blank.populated_external_evidence_count, 0)
        self.assertEqual(len(blank.missing_external_evidence), 3)
        self.assertEqual(len(blank.missing_laboratory_review), 4)
        self.assertFalse(blank.ready_for_external_authorization_review)
        self.assertFalse(blank.repository_can_authorize)
        self.assertFalse(blank.authorized_to_execute)

        handoff = campfire.app.load_char_depth_lab_handoff()
        handoff["runtime_metadata"].update(
            {
                "operator_id": "SYNTHETIC-OPERATOR",
                "apparatus_id": "SYNTHETIC-APPARATUS",
                "heat_flux_calibration_record": "SYNTHETIC-CALIBRATION",
                "actual_heat_flux_kw_m2": 35.0,
                "camera_clock_offset_s": 0.0,
                "thermocouple_configuration": "SYNTHETIC-TC-CONFIG",
                "quench_method_approval": "SYNTHETIC-QUENCH-APPROVAL",
                "laboratory_safety_sop_approval": "SYNTHETIC-SOP-APPROVAL",
                "apparatus_owner_approval": "SYNTHETIC-OWNER-APPROVAL",
            }
        )
        for record in handoff["external_evidence"].values():
            record.update(
                {
                    "record_reference": "SYNTHETIC-REFERENCE",
                    "responsible_organization": "SYNTHETIC-LAB",
                    "approved_by": "SYNTHETIC-APPROVER",
                    "approved_at_utc": "2026-08-05T00:00:00Z",
                }
            )
        handoff["responsible_laboratory_review"].update(
            {
                "laboratory_name": "SYNTHETIC-LAB",
                "handoff_prepared_by": "SYNTHETIC-PREPARER",
                "handoff_reviewed_by": "SYNTHETIC-REVIEWER",
                "reviewed_at_utc": "2026-08-05T00:00:00Z",
            }
        )
        with TemporaryDirectory() as temporary_directory:
            handoff_path = Path(temporary_directory) / "handoff.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            complete = campfire.app.evaluate_char_depth_lab_handoff(handoff_path)
            handoff["runtime_metadata"]["actual_heat_flux_kw_m2"] = -1.0
            first_evidence = next(iter(handoff["external_evidence"].values()))
            first_evidence["approved_at_utc"] = "2026-08-05T09:00:00+09:00"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            invalid = campfire.app.evaluate_char_depth_lab_handoff(handoff_path)
        self.assertTrue(complete.ready_for_external_authorization_review)
        self.assertFalse(complete.repository_can_authorize)
        self.assertFalse(complete.authorized_to_execute)
        self.assertFalse(invalid.ready_for_external_authorization_review)
        self.assertIn(
            "runtime_metadata.actual_heat_flux_kw_m2", invalid.invalid_fields
        )
        self.assertTrue(
            any(field.endswith("approved_at_utc") for field in invalid.invalid_fields)
        )

    async def test_plywood_and_osb_use_distinct_sourced_thermal_profiles(self):
        reference = campfire.app.load_nist_plywood_reference()
        parameters = campfire.app.parallel_arrhenius_baseline_parameters(reference)
        plywood = campfire.app.create_layered_coupon(
            reference["targets"][0], reference, parameters, material_kind="plywood"
        )
        osb = campfire.app.create_layered_coupon(
            reference["holdout"]["targets"][0],
            reference,
            parameters,
            material_kind="osb",
        )
        self.assertAlmostEqual(
            plywood.spec.through_thickness_conductivity_w_m_k, 0.115
        )
        self.assertAlmostEqual(plywood.spec.dry_wood_specific_heat_j_kg_k, 1214.0)
        self.assertAlmostEqual(osb.spec.through_thickness_conductivity_w_m_k, 0.118)
        self.assertAlmostEqual(osb.spec.dry_wood_specific_heat_j_kg_k, 1298.0)
        self.assertEqual(
            plywood.spec.dry_wood_specific_heat_model,
            campfire.app.USDA_FPL_NORMALIZED_DRY_WOOD_SPECIFIC_HEAT_MODEL,
        )
        self.assertEqual(
            osb.spec.dry_wood_specific_heat_model,
            campfire.app.USDA_FPL_NORMALIZED_DRY_WOOD_SPECIFIC_HEAT_MODEL,
        )
        self.assertEqual(plywood.spec.adhesive_interface_count, 4)
        self.assertEqual(osb.spec.adhesive_interface_count, 0)
        self.assertFalse(plywood.spec.adhesive_geometry_explicit)
        self.assertFalse(osb.spec.adhesive_geometry_explicit)
        self.assertNotAlmostEqual(
            plywood.spec.effective_dry_density_kg_m3,
            reference["material_property_profiles"]["plywood"][
                "reference_density_kg_m3"
            ],
        )

    async def test_temperature_dependent_heat_capacity_is_normalized_and_clamped(self):
        model = campfire.app.USDA_FPL_NORMALIZED_DRY_WOOD_SPECIFIC_HEAT_MODEL
        reference_cp = 1214.0
        at_reference = campfire.app.temperature_adjusted_dry_wood_specific_heat_j_kg_k(
            reference_cp, 293.15, model
        )
        below_source_range = (
            campfire.app.temperature_adjusted_dry_wood_specific_heat_j_kg_k(
                reference_cp, 200.0, model
            )
        )
        at_source_minimum = (
            campfire.app.temperature_adjusted_dry_wood_specific_heat_j_kg_k(
                reference_cp, 280.0, model
            )
        )
        at_source_maximum = (
            campfire.app.temperature_adjusted_dry_wood_specific_heat_j_kg_k(
                reference_cp, 420.0, model
            )
        )
        above_source_range = (
            campfire.app.temperature_adjusted_dry_wood_specific_heat_j_kg_k(
                reference_cp, 900.0, model
            )
        )
        self.assertAlmostEqual(at_reference, reference_cp, places=9)
        self.assertAlmostEqual(below_source_range, at_source_minimum, places=9)
        self.assertAlmostEqual(above_source_range, at_source_maximum, places=9)
        self.assertLess(at_source_minimum, at_reference)
        self.assertGreater(at_source_maximum, at_reference)
        self.assertAlmostEqual(
            campfire.app.temperature_adjusted_dry_wood_specific_heat_j_kg_k(
                reference_cp,
                900.0,
                campfire.app.CONSTANT_DRY_WOOD_SPECIFIC_HEAT_MODEL,
            ),
            reference_cp,
        )

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

    async def test_parallel_arrhenius_pathways_compete_and_conserve_product_mass(self):
        reference = campfire.app.load_nist_plywood_reference()
        parameters = campfire.app.parallel_arrhenius_baseline_parameters(reference)
        self.assertEqual(
            parameters.pyrolysis_rate_model, "arrhenius_parallel_first_order"
        )
        rates = campfire.app.parallel_arrhenius_rate_constants_s(parameters, 650.0)
        self.assertEqual(set(rates), {"gas", "tar", "char"})
        self.assertTrue(all(rate > 0.0 for rate in rates.values()))

        target = reference["targets"][1]
        model = campfire.app.create_layered_coupon(target, reference, parameters)
        for cell in model.cells:
            cell.temperature_k = 850.0
        result = model.step(0.1, 0.0)
        self.assertGreater(result.primary_gas_kg, 0.0)
        self.assertGreater(result.primary_tar_kg, 0.0)
        self.assertGreater(result.primary_char_kg, 0.0)
        self.assertGreater(result.secondary_tar_cracked_kg, 0.0)
        self.assertGreater(result.uncracked_tar_kg, 0.0)
        self.assertAlmostEqual(
            result.primary_tar_kg,
            result.secondary_tar_cracked_kg + result.uncracked_tar_kg,
            places=12,
        )
        self.assertAlmostEqual(
            result.pyrolysis_gas_kg,
            result.primary_gas_kg + result.primary_tar_kg,
            places=12,
        )
        metrics = model.metrics()
        self.assertAlmostEqual(
            sum(metrics["primary_product_yield_fraction"].values()),
            1.0,
            places=12,
        )
        self.assertAlmostEqual(
            sum(metrics["post_secondary_product_yield_fraction"].values()),
            1.0,
            places=12,
        )
        self.assertGreater(
            metrics["post_secondary_product_yield_fraction"]["gas"],
            metrics["primary_product_yield_fraction"]["gas"],
        )
        self.assertLess(abs(model.mass_balance_error_kg), 1.0e-9)

    async def test_secondary_tar_diagnostic_is_bounded_and_round_trips(self):
        parameters = campfire.app.parallel_arrhenius_baseline_parameters()
        self.assertEqual(
            campfire.app.secondary_tar_conversion_fraction(parameters, 650.0), 0.0
        )
        at_minimum = campfire.app.secondary_tar_conversion_fraction(
            parameters, parameters.secondary_tar_cracking_min_temperature_k
        )
        in_range = campfire.app.secondary_tar_conversion_fraction(parameters, 800.0)
        at_maximum = campfire.app.secondary_tar_conversion_fraction(
            parameters, parameters.secondary_tar_cracking_max_temperature_k
        )
        above_range = campfire.app.secondary_tar_conversion_fraction(
            parameters, 1200.0
        )
        self.assertGreater(at_minimum, 0.0)
        self.assertGreater(in_range, at_minimum)
        self.assertGreater(at_maximum, in_range)
        self.assertAlmostEqual(above_range, at_maximum, places=12)

        model = campfire.app.create_cylindrical_wood_model(
            "SecondaryTar", 0.03, 0.1, 0.0,
            axial_cells=1, circumferential_cells=1, radial_cells=1,
            parameters=parameters,
        )
        model.cells[0].temperature_k = 850.0
        model.step(0.1, 0.0)
        restored = campfire.app.WoodThermalModel.from_dict(model.to_dict())
        self.assertAlmostEqual(
            restored.converted_secondary_tar_kg,
            model.converted_secondary_tar_kg,
            places=12,
        )

    async def test_darcy_gas_transport_requires_complete_explicit_inputs(self):
        inputs = campfire.app.DarcyGasTransportInput(
            layer_thickness_m=0.01,
            porosity_fraction=0.5,
            permeability_m2=1.0e-11,
            dynamic_viscosity_pa_s=4.0e-5,
            pressure_drop_pa=1000.0,
        )
        result = campfire.app.evaluate_darcy_gas_transport(inputs)
        self.assertAlmostEqual(result.pressure_gradient_pa_m, 100000.0)
        self.assertAlmostEqual(result.superficial_velocity_m_s, 0.025)
        self.assertAlmostEqual(result.interstitial_velocity_m_s, 0.05)
        self.assertAlmostEqual(result.residence_time_s, 0.2)
        faster = campfire.app.evaluate_darcy_gas_transport(
            campfire.app.DarcyGasTransportInput(
                layer_thickness_m=inputs.layer_thickness_m,
                porosity_fraction=inputs.porosity_fraction,
                permeability_m2=inputs.permeability_m2,
                dynamic_viscosity_pa_s=inputs.dynamic_viscosity_pa_s,
                pressure_drop_pa=2000.0,
            )
        )
        self.assertLess(faster.residence_time_s, result.residence_time_s)
        with self.assertRaises(ValueError):
            campfire.app.evaluate_darcy_gas_transport(
                campfire.app.DarcyGasTransportInput(
                    layer_thickness_m=0.01,
                    porosity_fraction=0.0,
                    permeability_m2=1.0e-11,
                    dynamic_viscosity_pa_s=4.0e-5,
                    pressure_drop_pa=1000.0,
                )
            )

    async def test_nist_grid_search_improves_baseline_without_hiding_error(self):
        calibration = campfire.app.run_nist_plywood_calibration()
        self.assertEqual(calibration["candidate_count"], 16)
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
            "arrhenius_parallel_first_order",
        )
        self.assertGreater(
            calibration["best"]["parameters"][
                "pyrolysis_parallel_common_scale"
            ],
            0.0,
        )
        for case in calibration["best"]["cases"]:
            self.assertEqual(case["model_kind"], "layered_plywood")
            self.assertEqual(case["layer_count"], 5)
            self.assertEqual(len(case["final_layer_temperatures_k"]), 5)
            self.assertAlmostEqual(
                sum(case["primary_product_yield_fraction"].values()),
                1.0,
                places=9,
            )
            self.assertAlmostEqual(
                sum(case["post_secondary_product_yield_fraction"].values()),
                1.0,
                places=9,
            )
            self.assertGreater(
                case["post_secondary_product_yield_fraction"]["gas"],
                case["primary_product_yield_fraction"]["gas"],
            )
            self.assertEqual(case["material_kind"], "plywood")
            self.assertAlmostEqual(case["through_thickness_conductivity_w_m_k"], 0.115)
            self.assertAlmostEqual(case["dry_wood_specific_heat_j_kg_k"], 1214.0)
            self.assertEqual(
                case["dry_wood_specific_heat_model"],
                campfire.app.USDA_FPL_NORMALIZED_DRY_WOOD_SPECIFIC_HEAT_MODEL,
            )
            self.assertEqual(case["dry_wood_specific_heat_valid_range_k"], [280.0, 420.0])
            self.assertEqual(
                len(case["final_layer_dry_wood_specific_heats_j_kg_k"]), 5
            )
            self.assertEqual(case["adhesive_interface_count"], 4)
            self.assertFalse(case["adhesive_geometry_explicit"])
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
        sensitivity = calibration["secondary_tar_residence_sensitivity"]
        self.assertFalse(sensitivity["used_for_parameter_selection"])
        self.assertEqual(
            [scenario["residence_time_s"] for scenario in sensitivity["scenarios"]],
            [0.9, 1.0, 2.2],
        )
        self.assertEqual(sensitivity["experiment_temperature_range_k"], [773.0, 1073.0])
        self.assertEqual(sensitivity["experiment_residence_time_range_s"], [0.9, 2.2])
        for case_index in range(2):
            gas_yields = [
                scenario["cases"][case_index][
                    "post_secondary_product_yield_fraction"
                ]["gas"]
                for scenario in sensitivity["scenarios"]
            ]
            self.assertLessEqual(gas_yields[0], gas_yields[1])
            self.assertLessEqual(gas_yields[1], gas_yields[2])
            for scenario in sensitivity["scenarios"]:
                self.assertAlmostEqual(
                    scenario["score_rmse_relative"],
                    calibration["best"]["score_rmse_relative"],
                    places=12,
                )
        transport = calibration["gas_transport_readiness"]
        self.assertEqual(transport["model"], "steady_one_dimensional_darcy")
        self.assertFalse(transport["ready_for_secondary_tar_coupling"])
        self.assertFalse(transport["used_for_parameter_selection"])
        self.assertIsNone(transport["predicted_residence_time_s"])
        self.assertEqual(
            set(transport["missing_current_panel_inputs"]),
            {
                "char_layer_thickness_m",
                "through_thickness_porosity_fraction",
                "through_thickness_permeability_m2",
                "gas_dynamic_viscosity_pa_s",
                "char_layer_pressure_drop_pa",
            },
        )
        self.assertEqual(len(transport["fixed_grid_reaction_progress"]), 2)
        char_geometry = calibration["char_geometry_diagnostic"]
        self.assertFalse(char_geometry["shrinkage_applied"])
        self.assertFalse(char_geometry["used_for_parameter_selection"])
        self.assertEqual(len(char_geometry["cases"]), 2)
        for case in char_geometry["cases"]:
            self.assertEqual(len(case["layer_pyrolysis_conversion_fractions"]), 5)
            self.assertEqual(len(case["layer_char_mass_fractions_initial_dry"]), 5)
            self.assertTrue(
                all(
                    0.0 <= fraction <= 1.0
                    for fraction in case["layer_pyrolysis_conversion_fractions"]
                )
            )
            self.assertGreaterEqual(
                case["equivalent_unshrunk_pyrolysis_depth_m"], 0.0
            )
            self.assertLessEqual(
                case["equivalent_unshrunk_pyrolysis_depth_m"], 0.0127
            )
            self.assertIsNone(case["physical_char_layer_thickness_m"])
            self.assertIsNone(case["shrinkage_factor"])
            self.assertFalse(case["ready_for_darcy_layer_thickness"])
        char_benchmark = calibration["external_plywood_char_depth_benchmark"]
        self.assertFalse(char_benchmark["used_for_parameter_selection"])
        self.assertFalse(char_benchmark["scored"])
        self.assertFalse(
            char_benchmark["ready_for_physical_thickness_transfer"]
        )
        self.assertIsNone(char_benchmark["comparison_error_metric"])
        self.assertEqual(char_benchmark["matched_condition_count"], 3)
        self.assertEqual(char_benchmark["condition_count"], 10)
        self.assertAlmostEqual(
            char_benchmark["external_observation"]["char_depth_m"], 0.01377
        )
        self.assertIsNone(
            char_benchmark["current_model"]["physical_char_layer_thickness_m"]
        )
        measurement_gate = calibration[
            "matched_char_depth_measurement_readiness"
        ]
        self.assertEqual(measurement_gate["required_observation_count"], 24)
        self.assertEqual(measurement_gate["scheduled_observation_count"], 24)
        self.assertEqual(measurement_gate["complete_observation_count"], 0)
        self.assertEqual(len(measurement_gate["incomplete_slots"]), 24)
        self.assertFalse(
            measurement_gate[
                "ready_for_physical_char_thickness_calibration"
            ]
        )
        execution_plan = calibration["char_depth_experiment_execution_plan"]
        self.assertEqual(len(execution_plan["schedule"]), 24)
        self.assertTrue(execution_plan["readiness"]["technical_plan_complete"])
        self.assertFalse(execution_plan["readiness"]["authorized_to_execute"])
        self.assertEqual(
            len(execution_plan["readiness"]["missing_external_approvals"]), 3
        )

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
