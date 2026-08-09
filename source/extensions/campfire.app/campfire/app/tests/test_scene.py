import json
import math
import threading
from array import array
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import campfire.app
import numpy as np
import omni.kit.test
from pxr import Gf, Sdf, Tf, Usd, UsdGeom, UsdPhysics, UsdShade


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

    async def test_default_off_wood_render_hierarchy_preserves_legacy_cylinders(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase2_scene(stage)
        for log_id in campfire.app.list_log_ids(stage):
            root = campfire.app.get_log_root(stage, log_id)
            self.assertTrue(root.IsA(UsdGeom.Cylinder))
            self.assertEqual(campfire.app.get_log_collider(stage, log_id), root)
            self.assertEqual(campfire.app.get_log_render_surface(stage, log_id), root)
            self.assertTrue(root.HasAPI(UsdPhysics.CollisionAPI))

    async def test_wood_render_hierarchy_has_stable_360_cell_mesh_and_roles(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase2_scene(stage, render_hierarchy=True)
        self.assertTrue(stage.GetRootLayer().customLayerData["campfire:woodRenderHierarchy"])
        for slot, log_id in enumerate(campfire.app.list_log_ids(stage)):
            root = campfire.app.get_log_root(stage, log_id)
            collider = campfire.app.get_log_collider(stage, log_id)
            render = campfire.app.get_log_render_surface(stage, log_id)
            self.assertTrue(root.IsA(UsdGeom.Xform))
            self.assertTrue(root.HasAPI(UsdPhysics.RigidBodyAPI))
            self.assertTrue(root.HasAPI(UsdPhysics.MassAPI))
            self.assertFalse(root.HasAPI(UsdPhysics.CollisionAPI))
            self.assertTrue(collider.IsA(UsdGeom.Cylinder))
            self.assertTrue(collider.HasAPI(UsdPhysics.CollisionAPI))
            self.assertFalse(collider.HasAPI(UsdPhysics.RigidBodyAPI))
            self.assertEqual(
                UsdGeom.Imageable(collider).GetVisibilityAttr().Get(),
                UsdGeom.Tokens.invisible,
            )
            self.assertTrue(render.IsA(UsdGeom.Mesh))
            self.assertFalse(render.HasAPI(UsdPhysics.CollisionAPI))
            self.assertFalse(render.HasAPI(UsdPhysics.RigidBodyAPI))
            self.assertEqual(root.GetAttribute("campfire:renderAtlasSlot").Get(), slot)
            mesh = UsdGeom.Mesh(render)
            counts = tuple(mesh.GetFaceVertexCountsAttr().Get())
            self.assertEqual(len(mesh.GetPointsAttr().Get()), 431)
            self.assertEqual(len(counts), 384)
            self.assertEqual(counts.count(3), 24)
            self.assertEqual(counts.count(4), 360)
            surface = tuple(
                UsdGeom.PrimvarsAPI(render)
                .GetPrimvar("surfaceIndex")
                .Get()
            )
            self.assertEqual(len(surface), 384)
            self.assertEqual(set(surface), set(range(360)))
            for circumferential in range(12):
                self.assertEqual(
                    surface[circumferential], surface[324 + circumferential]
                )
                self.assertEqual(
                    surface[276 + circumferential], surface[372 + circumferential]
                )
            st = tuple(UsdGeom.PrimvarsAPI(render).GetPrimvar("st").Get())
            self.assertEqual(len(st), sum(counts))
            cursor = 0
            for count in counts:
                self.assertEqual(len(set(st[cursor : cursor + count])), 1)
                cursor += count

    async def test_wood_render_hierarchy_preserves_physics_and_point_layout_contract(self):
        legacy = Usd.Stage.CreateInMemory()
        hierarchy = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase2_scene(legacy)
        campfire.app.populate_phase2_scene(hierarchy, render_hierarchy=True)
        log_ids = campfire.app.list_log_ids(legacy)
        self.assertEqual(log_ids, campfire.app.list_log_ids(hierarchy))
        for log_id in log_ids:
            legacy_root = campfire.app.get_log_root(legacy, log_id)
            hierarchy_root = campfire.app.get_log_root(hierarchy, log_id)
            self.assertEqual(
                campfire.app.get_log_dimensions(legacy, log_id),
                campfire.app.get_log_dimensions(hierarchy, log_id),
            )
            for name in (
                "campfire:initialMassKg",
                "physics:mass",
                "physxRigidBody:linearDamping",
                "physxRigidBody:angularDamping",
                "physics:rigidBodyEnabled",
                "physics:kinematicEnabled",
            ):
                self.assertEqual(
                    legacy_root.GetAttribute(name).Get(),
                    hierarchy_root.GetAttribute(name).Get(),
                )
            self.assertTrue(
                Gf.IsClose(
                    campfire.app.get_log_physics_transform(legacy, log_id),
                    campfire.app.get_log_physics_transform(hierarchy, log_id),
                    1.0e-9,
                )
            )
        self.assertEqual(
            campfire.app.resident_point_layout_for_logs(legacy, log_ids),
            campfire.app.resident_point_layout_for_logs(hierarchy, log_ids),
        )
        campfire.app.add_scenario_log(hierarchy)
        added = campfire.app.get_log_root(hierarchy, campfire.app.PHASE2_ADDED_LOG_ID)
        self.assertTrue(added.IsA(UsdGeom.Xform))
        self.assertEqual(added.GetAttribute("campfire:renderAtlasSlot").Get(), 4)

    async def test_wood_render_atlas_uses_one_texel_centres(self):
        self.assertEqual(campfire.app.WOOD_ATLAS_WIDTH_PX, 120)
        self.assertEqual(campfire.app.WOOD_ATLAS_HEIGHT_PX, 60)
        samples = {
            campfire.app.atlas_uv(log_slot, surface_index)
            for log_slot in range(20)
            for surface_index in range(360)
        }
        self.assertEqual(len(samples), 7200)
        self.assertEqual(campfire.app.atlas_uv(0, 0), Gf.Vec2f(0.5 / 120.0, 0.5 / 60.0))
        four_logs = campfire.app.compact_atlas_descriptor(4)
        self.assertEqual((four_logs.width_px, four_logs.height_px), (96, 15))
        self.assertEqual(2 * four_logs.bytes_per_rgba8_atlas, 11_520)
        with self.assertRaises(ValueError):
            campfire.app.atlas_uv(20, 0)
        with self.assertRaises(ValueError):
            campfire.app.atlas_uv(0, 360)

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

    async def test_wood_visual_v0_mapping_is_deterministic_finite_and_readable(self):
        def row(temperature, moisture, dry, char, ash):
            return campfire.app.ResidentPublishedRow(
                temperature,
                moisture,
                dry,
                char,
                ash,
                1.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
            )

        dry = campfire.app.wood_visual_uniform_from_row(
            row(420.0, 0.05, 1.0, 0.0, 0.0)
        )
        wet = campfire.app.wood_visual_uniform_from_row(
            row(420.0, 0.60, 1.0, 0.0, 0.0)
        )
        charred = campfire.app.wood_visual_uniform_from_row(
            row(900.0, 0.0, 0.25, 0.75, 0.0)
        )
        ash = campfire.app.wood_visual_uniform_from_row(
            row(1100.0, 0.0, 0.05, 0.10, 0.85)
        )
        self.assertEqual(
            dry,
            campfire.app.wood_visual_uniform_from_row(
                row(420.0, 0.05, 1.0, 0.0, 0.0)
            ),
        )
        self.assertLess(sum(wet.base_color), sum(dry.base_color))
        self.assertLess(sum(charred.base_color), sum(dry.base_color))
        self.assertGreater(sum(ash.base_color), sum(charred.base_color))
        self.assertLess(wet.roughness, dry.roughness)
        self.assertGreater(charred.roughness, dry.roughness)
        self.assertGreater(ash.roughness, charred.roughness)
        self.assertEqual(dry.emission_color, (0.0, 0.0, 0.0))
        self.assertGreater(sum(charred.emission_color), 0.0)
        for visual in (dry, wet, charred, ash):
            values = (
                *visual.base_color,
                visual.roughness,
                *visual.emission_color,
                visual.moisture_fraction,
                visual.char_fraction,
                visual.ash_fraction,
            )
            self.assertTrue(all(math.isfinite(value) for value in values))
        for temperature in (1.0, 649.999, 650.0, 800.0, 1000.0, 1300.0, 5000.0):
            for masses in (
                (0.0, 0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0, 0.0),
                (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            ):
                boundary = campfire.app.wood_visual_uniform_from_row(
                    row(temperature, *masses)
                )
                self.assertTrue(
                    all(
                        math.isfinite(value)
                        for value in (
                            *boundary.base_color,
                            boundary.roughness,
                            *boundary.emission_color,
                            boundary.moisture_fraction,
                            boundary.char_fraction,
                            boundary.ash_fraction,
                        )
                    )
                )
        with self.assertRaisesRegex(ValueError, "mass values must be non-negative"):
            campfire.app.wood_visual_uniform_from_row(
                row(420.0, -0.01, 1.0, 0.0, 0.0)
            )
        with self.assertRaisesRegex(ValueError, "resident values must be finite"):
            campfire.app.wood_visual_uniform_from_row(
                row(float("nan"), 0.0, 1.0, 0.0, 0.0)
            )

    async def test_wood_visual_v0_is_pre_authored_and_skips_unchanged_revision(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(stage)
        log_ids = ("Log_00", "Log_01", "Log_02", "Log_03")
        contract = campfire.app.preauthor_wood_visual_v0(stage, log_ids)
        self.assertEqual(contract["log_ids"], list(log_ids))
        for log_id in log_ids:
            prim = stage.GetPrimAtPath(f"/World/Logs/{log_id}")
            self.assertTrue(prim.GetRelationship("material:binding:physics"))
            bound, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
            self.assertEqual(
                str(bound.GetPath()), f"/World/Looks/WoodVisualV0/{log_id}"
            )

        rows = tuple(
            campfire.app.ResidentPublishedRow(
                temperature,
                moisture,
                dry,
                char,
                ash,
                1.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
            )
            for temperature, moisture, dry, char, ash in (
                (420.0, 0.05, 1.0, 0.0, 0.0),
                (420.0, 0.60, 1.0, 0.0, 0.0),
                (900.0, 0.0, 0.25, 0.75, 0.0),
                (1100.0, 0.0, 0.05, 0.10, 0.85),
            )
        )
        snapshot = campfire.app.ResidentPublishedSnapshot(1, 1, log_ids, rows)
        consumer = campfire.app.WoodVisualV0Consumer(stage, log_ids)
        consumer.on_timeline_started()
        first = consumer.publish(snapshot)
        repeated = consumer.publish(snapshot)
        self.assertEqual(first.status, "committed")
        self.assertGreaterEqual(first.usd_set_count, 5)
        self.assertEqual(repeated.status, "unchanged_revision")
        self.assertEqual(repeated.usd_set_count, 0)
        self.assertEqual(consumer.status()["revision"], 1)
        self.assertEqual(consumer.status()["skip_count"], 1)
        consumer.close()

    async def test_wood_visual_v0_failure_restores_visual_without_touching_snapshot(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(stage)
        log_ids = ("Log_00", "Log_01")
        campfire.app.preauthor_wood_visual_v0(stage, log_ids)

        def fail_first_write(index, _log_id, _name):
            if index == 1:
                raise RuntimeError("injected visual failure")

        consumer = campfire.app.WoodVisualV0Consumer(
            stage, log_ids, write_observer=fail_first_write
        )
        consumer.on_timeline_started()
        row = campfire.app.ResidentPublishedRow(
            900.0, 0.0, 0.25, 0.75, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0
        )
        snapshot = campfire.app.ResidentPublishedSnapshot(
            1, 1, log_ids, (row, row)
        )
        before = UsdShade.Shader.Get(
            stage, "/World/Looks/WoodVisualV0/Log_00/Shader"
        ).GetInput("diffuseColor").Get()
        with self.assertRaisesRegex(RuntimeError, "injected visual failure"):
            consumer.publish(snapshot)
        after = UsdShade.Shader.Get(
            stage, "/World/Looks/WoodVisualV0/Log_00/Shader"
        ).GetInput("diffuseColor").Get()
        self.assertTrue(Gf.IsClose(before, after, 1.0e-7))
        self.assertEqual(consumer.status()["revision"], 0)
        self.assertEqual(consumer.status()["failure_count"], 1)
        self.assertEqual(snapshot.revision, 1)
        consumer.close()

    async def test_wood_visual_v1_uses_stable_eight_band_identity(self):
        model = campfire.app.create_cylindrical_wood_model(
            "Log_00", 0.16, 1.8, 0.12
        )
        cells_per_axial = (
            model.spec.circumferential_cells * model.spec.radial_cells
        )
        for axial in range(model.spec.axial_cells):
            for local in range(cells_per_axial):
                cell = model.cells[axial * cells_per_axial + local]
                if cell.surface_exposure > 0.0:
                    cell.temperature_k = 400.0 + axial * 20.0
                    cell.char_mass_kg = cell.dry_wood_mass_kg * axial / 24.0
        first = campfire.app.aggregate_model_into_visual_bands(model)
        second = campfire.app.aggregate_model_into_visual_bands(model)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 8)
        self.assertLess(
            first[0].surface_mean_temperature_k,
            first[-1].surface_mean_temperature_k,
        )
        self.assertLess(first[0].char_mass_kg, first[-1].char_mass_kg)

    async def test_wood_visual_v1_is_render_only_and_skips_same_revision(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(stage)
        log_ids = ("Log_00", "Log_01", "Log_02", "Log_03")
        physical_paths = tuple(f"/World/Logs/{value}" for value in log_ids)
        before = {
            path: (
                stage.GetPrimAtPath(path).HasAPI(UsdPhysics.CollisionAPI),
                stage.GetPrimAtPath(path).HasAPI(UsdPhysics.RigidBodyAPI),
            )
            for path in physical_paths
        }
        contract = campfire.app.preauthor_wood_visual_v1(stage, log_ids)
        self.assertFalse(contract["physical_cylinder_split"])
        self.assertEqual(len(contract["render_prim_paths"]), 32)
        self.assertEqual(
            before,
            {
                path: (
                    stage.GetPrimAtPath(path).HasAPI(UsdPhysics.CollisionAPI),
                    stage.GetPrimAtPath(path).HasAPI(UsdPhysics.RigidBodyAPI),
                )
                for path in physical_paths
            },
        )
        for path in contract["render_prim_paths"]:
            prim = stage.GetPrimAtPath(path)
            self.assertFalse(prim.HasAPI(UsdPhysics.CollisionAPI))
            self.assertTrue(prim.GetAttribute("campfire:renderOnly").Get())
        models = tuple(
            campfire.app.create_cylindrical_wood_model(log_id, 0.16, 1.8, 0.12)
            for log_id in log_ids
        )
        rows = tuple(
            row
            for model in models
            for row in campfire.app.aggregate_model_into_visual_bands(model)
        )
        snapshot = campfire.app.WoodVisualBandSnapshot(1, log_ids, rows)
        consumer = campfire.app.WoodVisualV1Consumer(stage, log_ids)
        consumer.on_timeline_started()
        first = consumer.publish(snapshot)
        repeated = consumer.publish(snapshot)
        self.assertEqual(first.status, "committed")
        self.assertEqual(repeated.status, "unchanged_revision")
        self.assertEqual(repeated.usd_set_count, 0)
        consumer.close()

    async def test_wood_visual_surface_payload_is_immutable_and_ordered(self):
        log_ids = ("Log_00", "Log_01")
        indices = array("I", (0, 1, 2, 0, 1, 2)).tobytes()
        temperatures = array("f", (300.0, 301.0, 302.0, 400.0, 401.0, 402.0)).tobytes()
        masses = array("f", (0.0, 0.1, 0.2, 0.3, 0.4, 0.5)).tobytes()
        payload = campfire.app.ImmutableWoodVisualSurfacePayload(
            7,
            9,
            log_ids,
            3,
            indices,
            temperatures,
            masses,
            masses,
            masses,
        )
        self.assertEqual(payload.point_count, 6)
        self.assertEqual(payload.digest(), payload.digest())
        self.assertIs(type(payload.temperatures), bytes)
        with self.assertRaisesRegex(ValueError, "identity order"):
            campfire.app.ImmutableWoodVisualSurfacePayload(
                7,
                9,
                log_ids,
                3,
                array("I", (0, 2, 1, 0, 1, 2)).tobytes(),
                temperatures,
                masses,
                masses,
                masses,
            )

    async def test_wood_visual_surface_permutation_is_not_hidden_by_mean(self):
        values = np.arange(7200, dtype=np.float32)
        permuted = values.copy()
        permuted[[123, 4567]] = permuted[[4567, 123]]
        self.assertTrue(np.array_equal(np.sort(values), np.sort(permuted)))
        self.assertFalse(np.array_equal(values, permuted))
        self.assertNotEqual(values.tobytes(), permuted.tobytes())

    async def test_wood_visual_v3_preauthors_fixed_mesh_material(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(stage, render_hierarchy=True)
        log_ids = tuple(campfire.app.list_log_ids(stage))
        contract = campfire.app.preauthor_wood_visual_v3(stage, log_ids)
        self.assertEqual(contract["atlas"], [96, 15])
        self.assertEqual(contract["atlas_descriptor"]["cell_stride_px"], 1)
        self.assertEqual(contract["atlas_descriptor"]["render_log_count"], 4)
        self.assertEqual(contract["atlas_descriptor"]["bytes_per_rgba8_atlas"], 5_760)
        self.assertEqual(contract["upload_count_per_revision"], 2)
        self.assertEqual(
            contract["base_uri"], campfire.app.WOOD_VISUAL_V3_BASE_TEXTURE_URI
        )
        self.assertEqual(
            contract["emission_uri"],
            campfire.app.WOOD_VISUAL_V3_EMISSION_TEXTURE_URI,
        )
        for log_id in log_ids:
            render = campfire.app.get_log_render_surface(stage, log_id)
            self.assertTrue(render.IsA(UsdGeom.Mesh))
            material, _ = UsdShade.MaterialBindingAPI(render).ComputeBoundMaterial()
            self.assertEqual(material.GetPath(), campfire.app.WOOD_VISUAL_V3_ROOT)

    async def test_wood_visual_v3_vectorized_atlas_maps_local_states(self):
        log_ids = tuple(f"Log_{index:02d}" for index in range(20))
        count = len(log_ids) * 360
        temperature = np.full(count, 300.0, dtype=np.float32)
        moisture = np.zeros(count, dtype=np.float32)
        char = np.zeros(count, dtype=np.float32)
        ash = np.zeros(count, dtype=np.float32)
        moisture[0] = 0.03
        char[1] = 0.015
        ash[2] = 0.0015
        temperature[3] = 1200.0
        payload = campfire.app.ImmutableWoodVisualSurfacePayload(
            1,
            1,
            log_ids,
            360,
            np.tile(np.arange(360, dtype=np.uint32), 20).tobytes(),
            temperature.tobytes(),
            moisture.tobytes(),
            char.tobytes(),
            ash.tobytes(),
        )
        packed = campfire.app.WoodVisualV3AtlasPacker(log_ids).pack(payload)
        self.assertEqual(packed.base_rgba8.shape, (60, 120, 4))
        self.assertEqual(packed.emission_rgba8.shape, (60, 120, 4))
        self.assertEqual(packed.base_rgba8.nbytes + packed.emission_rgba8.nbytes, 57_600)
        self.assertTrue(packed.base_rgba8.flags.c_contiguous)
        self.assertTrue(packed.emission_rgba8.flags.c_contiguous)
        wet = packed.base_rgba8[0, 0, :3]
        charred = packed.base_rgba8[0, 1, :3]
        ashed = packed.base_rgba8[0, 2, :3]
        hot = packed.emission_rgba8[0, 3, :3]
        self.assertLess(int(wet.sum()), int(np.array((77, 31, 11)).sum()))
        self.assertLess(int(charred.max()), 10)
        self.assertGreater(int(ashed.min()), 150)
        self.assertGreater(int(hot[0]), 200)
        self.assertGreater(int(hot[1]), 80)

    async def test_wood_visual_v3_adaptive_scheduler_bounds_delay_and_keeps_heat(self):
        log_ids = ("Log_00",)

        def payload(revision, temperature):
            count = 360
            zero = np.zeros(count, dtype=np.float32).tobytes()
            return campfire.app.ImmutableWoodVisualSurfacePayload(
                revision,
                revision,
                log_ids,
                360,
                np.arange(360, dtype=np.uint32).tobytes(),
                np.full(count, temperature, dtype=np.float32).tobytes(),
                zero,
                zero,
                zero,
            )

        scheduler = campfire.app.WoodVisualV3AdaptiveScheduler()
        decisions = []
        for tick in range(5):
            current = payload(tick + 1, 400.0 + tick)
            decision = scheduler.decide(current, tick * 0.2)
            decisions.append(decision)
            if decision.publish:
                scheduler.committed(current, tick * 0.2)
        self.assertEqual([value.publish for value in decisions], [True, False, True, False, True])
        self.assertLessEqual(
            max(value.elapsed_since_publish_seconds for value in decisions if value.publish),
            0.5,
        )
        rapid = scheduler.decide(payload(6, 700.0), 1.0)
        self.assertTrue(rapid.publish)
        self.assertEqual(rapid.reason, "rapid_heat")

    async def test_wood_visual_v3_revision_failure_reload_and_close_lifecycle(self):
        providers = []

        class FakeProvider:
            def __init__(self, name):
                self.name = name
                self.uploads = 0
                self.destroyed = False
                providers.append(self)

            def set_raw_bytes_data(self, _capsule, sizes, _format, strict=False):
                self.assert_sizes = tuple(sizes)
                self.assert_strict = strict
                self.uploads += 1

            def destroy(self):
                self.destroyed = True

        failure = {"point": None}

        def inject(point, _revision):
            if point == failure["point"]:
                raise RuntimeError("injected visual failure")

        def payload(revision, state=1):
            count = len(log_ids) * 360
            zero = np.zeros(count, dtype=np.float32)
            moisture = np.full(count, 0.01 * state, dtype=np.float32)
            return campfire.app.ImmutableWoodVisualSurfacePayload(
                revision,
                revision,
                log_ids,
                360,
                np.tile(
                    np.arange(360, dtype=np.uint32), len(log_ids)
                ).tobytes(),
                np.full(count, 650.0 + 100.0 * state, dtype=np.float32).tobytes(),
                moisture.tobytes(),
                zero.tobytes(),
                zero.tobytes(),
            )

        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(stage, render_hierarchy=True)
        log_ids = tuple(campfire.app.list_log_ids(stage))
        campfire.app.preauthor_wood_visual_v3(stage, log_ids)
        consumer = campfire.app.WoodVisualV3Consumer(
            stage,
            log_ids,
            provider_factory=FakeProvider,
            texture_format=object(),
            failure_injector=inject,
        )
        consumer.on_timeline_started()
        first = consumer.publish(payload(1))
        repeated = consumer.publish(payload(1))
        self.assertEqual(first.upload_count, 2)
        self.assertEqual(first.usd_set_count, 1)
        self.assertEqual(repeated.status, "unchanged_revision")
        self.assertEqual(repeated.upload_count, 0)
        self.assertEqual(repeated.usd_set_count, 0)
        self.assertEqual(consumer.status()["atlas"], [96, 15])
        self.assertEqual(consumer.status()["bytes_per_revision"], 11_520)
        unchanged = consumer.publish(payload(2))
        self.assertEqual(unchanged.status, "unchanged_quantized")
        self.assertEqual(unchanged.upload_count, 0)
        self.assertEqual(unchanged.usd_set_count, 0)
        self.assertEqual(consumer.status()["revision"], 1)
        self.assertEqual(consumer.status()["processed_revision"], 2)
        capture = consumer.publish_for_capture(payload(2))
        self.assertEqual(capture.status, "capture_republish")
        self.assertEqual(capture.upload_count, 2)
        self.assertEqual(capture.usd_set_count, 1)
        self.assertEqual(consumer.status()["revision"], 2)
        self.assertEqual(consumer.status()["processed_revision"], 2)
        failure["point"] = "after_base"
        with self.assertRaisesRegex(RuntimeError, "injected"):
            consumer.publish(payload(3, state=2))
        self.assertEqual(consumer.status()["revision"], 2)
        self.assertEqual(consumer.status()["processed_revision"], 2)
        self.assertEqual(consumer.status()["failure_count"], 1)
        self.assertEqual(consumer.status()["recovery_count"], 1)
        failure["point"] = None
        consumer.publish(payload(3, state=2))

        reloaded = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(reloaded, render_hierarchy=True)
        campfire.app.preauthor_wood_visual_v3(reloaded, log_ids)
        profile = consumer.on_stage_reloaded(reloaded, payload(3, state=2))
        self.assertEqual(profile.status, "reloaded")
        self.assertEqual(
            reloaded.GetPrimAtPath(campfire.app.WOOD_VISUAL_V3_ROOT)
            .GetAttribute("campfire:committedRevision")
            .Get(),
            3,
        )
        with self.assertRaisesRegex(RuntimeError, "monotonically"):
            consumer.publish(payload(2))
        consumer.on_timeline_stopped()
        with self.assertRaisesRegex(RuntimeError, "active timeline"):
            consumer.publish(payload(4, state=3))
        self.assertTrue(consumer.close())
        self.assertFalse(consumer.close())
        self.assertTrue(all(provider.destroyed for provider in providers))

    async def test_resident_point_application_scene_is_explicit_and_pre_authored(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(stage)
        points = (
            Gf.Vec3f(-0.05, 0.0, 0.4),
            Gf.Vec3f(0.05, 0.0, 0.4),
            Gf.Vec3f(0.0, 0.05, 0.45),
            Gf.Vec3f(0.0, -0.05, 0.45),
        )

        result = campfire.app.configure_resident_point_application_scene(
            stage, points
        )
        log_ids = (campfire.app.PHASE3_DRY_LOG_ID, campfire.app.PHASE3_WET_LOG_ID)
        campfire.app.preauthor_resident_snapshot_consumers(stage, log_ids)

        self.assertEqual(result["point_count"], 4)
        sphere = stage.GetPrimAtPath(campfire.app.FLOW_EMITTER_PATH)
        emitter = stage.GetPrimAtPath(campfire.app.RESIDENT_POINT_EMITTER_PATH)
        source = stage.GetPrimAtPath(campfire.app.RESIDENT_POINT_SOURCE_PATH)
        self.assertEqual(sphere.GetTypeName(), "FlowEmitterSphere")
        self.assertFalse(sphere.GetAttribute("enabled").Get())
        self.assertEqual(emitter.GetTypeName(), "FlowEmitterPoint")
        self.assertEqual(
            emitter.GetRelationship("pointsPrim").GetTargets(),
            [campfire.app.RESIDENT_POINT_SOURCE_PATH],
        )
        for name in (
            "pointPositions",
            "pointFuels",
            "pointTemperatures",
            "pointSmokes",
            "campfire:residentRevision",
            "campfire:layoutRevision",
        ):
            self.assertTrue(emitter.GetAttribute(name))
        self.assertEqual(len(emitter.GetAttribute("pointPositions").Get()), 4)
        self.assertEqual(len(UsdGeom.Points(source).GetPointsAttr().Get()), 4)
        self.assertEqual(emitter.GetAttribute("campfire:residentRevision").Get(), 0)
        self.assertEqual(emitter.GetAttribute("campfire:layoutRevision").Get(), 1)
        sphere = stage.GetPrimAtPath(campfire.app.FLOW_EMITTER_PATH)
        self.assertEqual(sphere.GetAttribute("campfire:residentRevision").Get(), 0)
        for log_id in log_ids:
            prim = stage.GetPrimAtPath(f"/World/Logs/{log_id}")
            for name in (
                "campfire:surfaceTemperatureK",
                "campfire:charFraction",
                "campfire:remainingMassRatio",
                "campfire:weakestSupportRatio",
                "campfire:residentRevision",
            ):
                self.assertTrue(prim.GetAttribute(name).HasAuthoredValueOpinion())
        layer_data = stage.GetRootLayer().customLayerData
        self.assertTrue(layer_data["campfire:residentPointApplication"])
        self.assertEqual(layer_data["campfire:residentPointEmitterCount"], 1)

    async def test_resident_point_layout_transaction_updates_and_rolls_back(self):
        class Producer:
            def __init__(self):
                self.np = np
                self.origins = np.asarray(
                    ((0.0, -0.3, 0.18), (0.0, 0.3, 0.18)), dtype=np.float64
                )
                self.axes = np.asarray((0, 0), dtype=np.uint32)
                self.positions = np.empty((2, 3), dtype=np.float32)
                self.build_layout()

            def build_layout(self):
                self.positions[:] = self.origins

        class Attribute:
            def __init__(self, value):
                self.value = value
                self.fail_once = False

            def Get(self):
                return self.value

            def Set(self, value):
                if self.fail_once:
                    self.fail_once = False
                    return False
                self.value = value
                return True

        producer = Producer()
        old_positions = producer.positions.tobytes(order="C")
        sidecar = object.__new__(campfire.app.ResidentPointSidecar)
        sidecar._producer = producer
        sidecar._positions = old_positions
        sidecar._layout_revision = 1
        sidecar._committed_layout_revision = 1
        sidecar._layout_replace_count = 0
        sidecar._last_undo = object()
        sidecar._attributes = {
            "positions": Attribute(
                tuple(
                    Gf.Vec3f(*(float(component) for component in position))
                    for position in producer.positions
                )
            ),
            "layout_revision": Attribute(1),
        }
        candidate = {
            "revision": 2,
            "origins": ((0.0, -0.26, 0.18), (0.0, 0.3, 0.18)),
            "axes": (0, 0),
        }

        sidecar._attributes["layout_revision"].fail_once = True
        with self.assertRaisesRegex(RuntimeError, "layout revision Set failed"):
            sidecar.replace_layout(candidate)
        self.assertEqual(
            producer.origins.tolist(),
            [[0.0, -0.3, 0.18], [0.0, 0.3, 0.18]],
        )
        self.assertEqual(sidecar._positions, old_positions)
        self.assertEqual(sidecar._layout_revision, 1)
        self.assertEqual(sidecar._committed_layout_revision, 1)
        self.assertEqual(sidecar._attributes["layout_revision"].Get(), 1)
        self.assertEqual(sidecar._layout_replace_count, 0)

        self.assertEqual(sidecar.replace_layout(candidate), 2)
        self.assertEqual(sidecar._layout_revision, 2)
        self.assertEqual(sidecar._committed_layout_revision, 2)
        self.assertEqual(sidecar._attributes["layout_revision"].Get(), 2)
        self.assertEqual(sidecar._layout_replace_count, 1)
        self.assertIsNone(sidecar._last_undo)
        self.assertNotEqual(sidecar._positions, old_positions)

    async def test_resident_point_live_translation_commits_with_snapshot_and_rolls_back(self):
        class Producer:
            def __init__(self):
                self.np = np
                self.origins = np.asarray(
                    ((0.0, -0.3, 0.18), (0.0, 0.3, 0.18)), dtype=np.float64
                )
                self.axes = np.asarray((0, 0), dtype=np.uint32)
                self.positions = self.origins.astype(np.float32)
                self.point_count = 2
                self.fuels = np.asarray((0.1, 0.2), dtype=np.float32)
                self.temperatures = np.asarray((0.3, 0.4), dtype=np.float32)
                self.smokes = np.asarray((0.5, 0.6), dtype=np.float32)
                self.layout_candidate_count = 0

            def build_channels(self):
                return self.point_count

            def build_layout_candidate(self, origins, axes):
                self.layout_candidate_count += 1
                origins = np.asarray(origins, dtype=np.float64)
                axes = np.asarray(axes, dtype=np.uint32)
                return {
                    "origins": tuple(tuple(float(value) for value in row) for row in origins),
                    "axes": tuple(int(value) for value in axes),
                    "positions": origins.astype(np.float32).tobytes(order="C"),
                }

            def layout_origins_changed(self, origins, tolerance=1.0e-9):
                origins = np.asarray(origins, dtype=np.float64)
                return bool(np.any(np.abs(origins - self.origins) > tolerance))

            def commit_layout_candidate(self, origins, axes, positions):
                self.origins[:] = np.asarray(origins, dtype=np.float64)
                self.axes[:] = np.asarray(axes, dtype=np.uint32)
                self.positions[:] = np.frombuffer(
                    positions, dtype=np.float32
                ).reshape(self.positions.shape)

        class Attribute:
            def __init__(self, value):
                self.value = value

            def Get(self):
                return self.value

            def Set(self, value):
                self.value = value
                return True

        class Backend:
            revision = 2

        class Snapshot:
            revision = 2
            tick = 2

        producer = Producer()
        old_positions = producer.positions.tobytes(order="C")
        stage = object()
        layout_state = {
            "revision": 1,
            "origins": tuple(tuple(value for value in row) for row in producer.origins),
            "axes": (0, 0),
        }
        sidecar = object.__new__(campfire.app.ResidentPointSidecar)
        sidecar._producer = producer
        sidecar._backend = Backend()
        sidecar._translation_provider = lambda: (
            (0.0, -0.26, 0.16),
            (0.0, 0.3, 0.18),
        )
        sidecar._skip_unchanged_translation_layout = True
        sidecar._layout_state = layout_state
        sidecar._positions = old_positions
        sidecar._layout_revision = 1
        sidecar._committed_layout_revision = 1
        sidecar._revision = 1
        sidecar._last_snapshot = None
        sidecar._last_undo = None
        sidecar._prepare_count = 0
        sidecar._publish_count = 0
        sidecar._rollback_count = 0
        sidecar._failure_count = 0
        sidecar._layout_replace_count = 0
        sidecar._live_translation_prepare_count = 0
        sidecar._live_translation_publish_count = 0
        sidecar._live_translation_unchanged_count = 0
        sidecar._live_translation_timing_ms = {
            "provider": [],
            "candidate_build": [],
            "fuel_vt_conversion": [],
            "temperature_vt_conversion": [],
            "smoke_vt_conversion": [],
            "position_vt_conversion": [],
            "previous_value_snapshot": [],
            "change_block_enter": [],
            "position_usd_set": [],
            "fuel_usd_set": [],
            "temperature_usd_set": [],
            "smoke_usd_set": [],
            "layout_revision_usd_set": [],
            "resident_revision_usd_set": [],
            "change_block_exit": [],
            "publish_transaction": [],
            "producer_commit": [],
            "channel_only_change_block_exit": [],
            "channel_only_publish_transaction": [],
        }
        sidecar._closed = False
        sidecar._stage = stage
        sidecar._stage_provider = lambda: stage
        sidecar._write_observer = None
        sidecar.attempt_payload_ids = []
        sidecar.attempt_payload_digests = []
        sidecar.published_payload_ids = []
        sidecar.published_payload_digests = []
        sidecar._attributes = {
            "positions": Attribute(old_positions),
            "fuels": Attribute(None),
            "temperatures": Attribute(None),
            "smokes": Attribute(None),
            "revision": Attribute(1),
            "layout_revision": Attribute(1),
        }

        payload = sidecar.prepare(Snapshot())
        self.assertEqual(producer.layout_candidate_count, 1)
        self.assertEqual(payload.layout_revision, 2)
        self.assertEqual(payload.layout_origins[0], (0.0, -0.26, 0.16))
        self.assertEqual(sidecar._layout_revision, 1)
        self.assertEqual(producer.origins[0].tolist(), [0.0, -0.3, 0.18])

        sidecar.publish(payload)
        self.assertEqual(sidecar._attributes["layout_revision"].Get(), 2)
        self.assertEqual(sidecar._attributes["revision"].Get(), 2)
        self.assertEqual(sidecar._layout_revision, 2)
        self.assertEqual(producer.origins[0].tolist(), [0.0, -0.26, 0.16])
        self.assertEqual(layout_state["revision"], 2)
        self.assertEqual(layout_state["origins"][0], (0.0, -0.26, 0.16))

        sidecar.rollback_last_commit(2)
        self.assertEqual(sidecar._attributes["layout_revision"].Get(), 1)
        self.assertEqual(sidecar._attributes["revision"].Get(), 1)
        self.assertEqual(sidecar._layout_revision, 1)
        self.assertEqual(producer.origins[0].tolist(), [0.0, -0.3, 0.18])
        self.assertEqual(sidecar._positions, old_positions)
        self.assertEqual(layout_state["revision"], 1)

        sidecar._backend.revision = 3
        Snapshot.revision = 3
        Snapshot.tick = 3
        sidecar._translation_provider = lambda: tuple(
            tuple(float(value) for value in row) for row in producer.origins
        )
        unchanged = sidecar.prepare(Snapshot())
        self.assertEqual(producer.layout_candidate_count, 1)
        self.assertEqual(unchanged.layout_revision, 1)
        self.assertEqual(sidecar._live_translation_unchanged_count, 1)
        sidecar.publish(unchanged)
        timing = sidecar.status()["live_translation_timing_ms"]
        self.assertEqual(timing["provider"]["sample_count"], 2)
        self.assertEqual(timing["candidate_build"]["sample_count"], 1)
        self.assertEqual(timing["position_usd_set"]["sample_count"], 1)
        self.assertEqual(
            timing["channel_only_change_block_exit"]["sample_count"], 1
        )
        self.assertEqual(
            timing["channel_only_publish_transaction"]["sample_count"], 1
        )
        for timing_name in (
            "fuel_vt_conversion",
            "temperature_vt_conversion",
            "smoke_vt_conversion",
            "position_vt_conversion",
            "previous_value_snapshot",
            "change_block_enter",
            "fuel_usd_set",
            "temperature_usd_set",
            "smoke_usd_set",
            "layout_revision_usd_set",
            "resident_revision_usd_set",
            "change_block_exit",
            "publish_transaction",
            "producer_commit",
        ):
            self.assertEqual(timing[timing_name]["sample_count"], 1)

    async def test_resident_point_layout_accepts_only_cardinal_horizontal_logs(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(stage)
        log_ids = (campfire.app.PHASE3_DRY_LOG_ID, campfire.app.PHASE3_WET_LOG_ID)

        initial = campfire.app.resident_point_layout_for_logs(stage, log_ids)
        self.assertEqual(initial["revision"], 1)
        self.assertEqual(initial["axes"], (0, 0))
        campfire.app.move_log(stage, log_ids[0], (0.1, -0.2, 0.3), 90.0)
        rotated = campfire.app.resident_point_layout_for_logs(stage, log_ids)
        self.assertEqual(rotated["axes"], (1, 0))
        self.assertEqual(rotated["origins"][0], (0.1, -0.2, 0.3))
        campfire.app.move_log(stage, log_ids[0], (0.1, -0.2, 0.3), 45.0)
        with self.assertRaisesRegex(ValueError, "cardinal XY"):
            campfire.app.resident_point_layout_for_logs(stage, log_ids)

    async def test_resident_point_continuity_measures_complete_log_groups(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(stage)
        log_ids = (campfire.app.PHASE3_DRY_LOG_ID, campfire.app.PHASE3_WET_LOG_ID)
        origins = tuple(
            tuple(
                float(value)
                for value in campfire.app.get_log_world_position(stage, log_id)
            )
            for log_id in log_ids
        )
        points = tuple(
            Gf.Vec3f(origin[0] + offset, origin[1], origin[2])
            for origin in origins
            for offset in (-0.01, 0.01)
        )

        measurement = campfire.app.measure_resident_point_log_alignment(
            stage, log_ids, points, points_per_log=2
        )

        self.assertEqual(measurement["point_count"], 4)
        self.assertAlmostEqual(measurement["max_error_m"], 0.0, places=6)
        campfire.app.move_log(
            stage,
            log_ids[0],
            (origins[0][0], origins[0][1] + 0.04, origins[0][2]),
        )
        moved = campfire.app.measure_resident_point_log_alignment(
            stage, log_ids, points, points_per_log=2
        )
        self.assertAlmostEqual(moved["error_m"][0], 0.04, places=6)
        with self.assertRaisesRegex(ValueError, "complete per-log groups"):
            campfire.app.resident_point_group_centroids(points[:-1], 2)

    async def test_resident_point_application_owner_assigns_ticks_and_delegates(self):
        class FakeSession:
            def __init__(self):
                self.state = "ready"
                self.tick = -1
                self.steps = []
                self.closed = False

            def status(self):
                return {"state": self.state, "backend": {"tick": self.tick}}

            def start(self):
                self.state = "running"

            def stop(self):
                self.state = "stopped"
                return True

            def step(self, *, tick):
                self.tick = tick
                self.steps.append(tick)
                return tick

            def replace_sidecar_layout(self, layout):
                if self.state not in ("ready", "stopped"):
                    raise RuntimeError("layout replacement requires stopped state")
                return layout["revision"]

            def close(self, *, discard_pending=False):
                self.state = "closed"
                self.closed = True
                return {"pending_discarded": discard_pending}

        class FakeOrchestrator:
            def __init__(self):
                self.events = []

            def observe_stage_event(self, name):
                self.events.append(name)

            def status(self):
                return {"state": "idle", "observed_events": tuple(self.events)}

        session = FakeSession()
        orchestrator = FakeOrchestrator()
        owner = campfire.app.ResidentPointApplicationOwner(session, orchestrator)
        self.assertTrue(owner.start())
        self.assertFalse(owner.start())
        self.assertEqual(owner.step(), 0)
        self.assertEqual(owner.step(), 1)
        owner.observe_stage_event("opening")
        self.assertTrue(owner.stop())
        self.assertFalse(owner.stop())
        status = owner.status()
        self.assertEqual(session.steps, [0, 1])
        self.assertEqual(status["start_count"], 1)
        self.assertEqual(status["stop_count"], 1)
        self.assertEqual(status["step_count"], 2)
        self.assertEqual(status["orchestrator"]["observed_events"], ("opening",))
        self.assertFalse(owner.close()["already_closed"])
        self.assertTrue(owner.close()["already_closed"])

        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(stage)
        log_ids = (campfire.app.PHASE3_DRY_LOG_ID, campfire.app.PHASE3_WET_LOG_ID)
        layout_state = campfire.app.resident_point_layout_for_logs(stage, log_ids)
        layout_owner = campfire.app.ResidentPointApplicationOwner(
            FakeSession(),
            FakeOrchestrator(),
            layout_state=layout_state,
            log_ids=log_ids,
        )
        self.assertFalse(layout_owner.refresh_layout(stage)["changed"])
        shared_state_identity = id(layout_owner._layout_state)
        campfire.app.move_log(stage, log_ids[0], (0.03, 0.0, 0.2), 90.0)
        refreshed = layout_owner.refresh_layout(stage)
        self.assertTrue(refreshed["changed"])
        self.assertEqual(refreshed["revision"], 2)
        self.assertEqual(refreshed["axes"], (1, 0))
        self.assertEqual(id(layout_owner._layout_state), shared_state_identity)
        self.assertEqual(layout_owner.status()["layout_replace_count"], 1)

        command_queue = campfire.app.ResidentPointCommandQueue(
            layout_owner, lambda: stage
        )
        campfire.app.move_log(stage, log_ids[0], (0.03, 0.0, 0.2), 45.0)
        rejected_sequence = command_queue.submit_refresh_layout(source="headless")
        rejected = command_queue.drain()
        self.assertEqual(rejected[0].sequence, rejected_sequence)
        self.assertFalse(rejected[0].accepted)
        self.assertEqual(rejected[0].code, "unsupported_layout")
        self.assertIn("cardinal XY", rejected[0].message)
        self.assertEqual(layout_owner.status()["layout_revision"], 2)
        self.assertEqual(layout_owner.status()["layout_replace_count"], 1)

        campfire.app.move_log(stage, log_ids[0], (0.05, 0.0, 0.2), 0.0)
        accepted_sequence = command_queue.submit_refresh_layout(source="ui")
        accepted = command_queue.drain()
        self.assertEqual(accepted[0].sequence, accepted_sequence)
        self.assertTrue(accepted[0].accepted)
        self.assertEqual(accepted[0].code, "layout_replaced")
        self.assertEqual(accepted[0].layout_revision, 3)
        self.assertEqual(layout_owner.status()["layout_replace_count"], 2)
        self.assertIn(
            "Applied", campfire.app.format_resident_point_command_result(accepted[0])
        )

        worker_sequences = []
        worker = threading.Thread(
            target=lambda: worker_sequences.append(
                command_queue.submit_refresh_layout(source="worker")
            )
        )
        worker.start()
        worker.join()
        self.assertEqual(len(worker_sequences), 1)
        wrong_thread_errors = []

        def drain_on_worker():
            try:
                command_queue.drain()
            except Exception as exc:
                wrong_thread_errors.append(exc)

        wrong_thread = threading.Thread(target=drain_on_worker)
        wrong_thread.start()
        wrong_thread.join()
        self.assertEqual(len(wrong_thread_errors), 1)
        self.assertIn("owner thread", str(wrong_thread_errors[0]))
        unchanged = command_queue.drain()
        self.assertTrue(unchanged[0].accepted)
        self.assertEqual(unchanged[0].code, "layout_unchanged")
        self.assertEqual(command_queue.status()["rejected_count"], 1)
        command_queue.close()

        class FakeNotice:
            def __init__(self, *paths):
                self._paths = paths

            def GetChangedInfoOnlyPaths(self):
                return self._paths

        coalescing_queue = campfire.app.ResidentPointCommandQueue(
            layout_owner, lambda: stage, max_pending=1
        )
        transform_observer = campfire.app.ResidentPointTransformObserver(
            coalescing_queue,
            (f"/World/Logs/{log_id}" for log_id in log_ids),
            lambda: layout_owner.status()["session"]["state"],
        )
        observed_sequences = []
        for index in range(5):
            campfire.app.move_log(
                stage,
                log_ids[0],
                (0.06 + 0.01 * index, 0.0, 0.2),
                0.0,
            )
            observed_sequences.append(
                transform_observer.observe(
                    FakeNotice(f"/World/Logs/{log_ids[0]}.xformOp:translate")
                )
            )
        self.assertEqual(len(set(observed_sequences)), 1)
        queued_status = coalescing_queue.status()
        self.assertEqual(queued_status["request_count"], 5)
        self.assertEqual(queued_status["submitted_count"], 1)
        self.assertEqual(queued_status["coalesced_submission_count"], 4)
        self.assertEqual(queued_status["pending_count"], 1)
        coalesced = coalescing_queue.drain()
        self.assertEqual(len(coalesced), 1)
        self.assertTrue(coalesced[0].accepted)
        self.assertEqual(coalesced[0].layout_revision, 4)
        self.assertEqual(layout_owner.status()["layout_replace_count"], 3)

        self.assertIsNone(
            transform_observer.observe(
                FakeNotice(f"/World/Logs/{log_ids[0]}.displayColor")
            )
        )
        layout_owner._session.state = "running"
        self.assertIsNone(
            transform_observer.observe(
                FakeNotice(f"/World/Logs/{log_ids[0]}.xformOp:orient")
            )
        )
        layout_owner._session.state = "stopped"
        observer_status = transform_observer.status()
        self.assertEqual(observer_status["matched_notice_count"], 6)
        self.assertEqual(observer_status["submitted_request_count"], 5)
        self.assertEqual(observer_status["ignored_running_count"], 1)
        self.assertEqual(observer_status["ignored_non_transform_count"], 1)
        transform_observer.close()
        coalescing_queue.close()
        layout_owner.close()

    async def test_phase3_default_keeps_sphere_without_point_structure(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(stage)

        sphere = stage.GetPrimAtPath(campfire.app.FLOW_EMITTER_PATH)
        self.assertEqual(sphere.GetTypeName(), "FlowEmitterSphere")
        self.assertTrue(sphere.GetAttribute("enabled").Get())
        self.assertFalse(stage.GetPrimAtPath(campfire.app.RESIDENT_POINT_EMITTER_PATH))
        self.assertFalse(stage.GetPrimAtPath(campfire.app.RESIDENT_POINT_SOURCE_PATH))

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
            cache_usd_handles=True,
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
        log_00 = stage.GetPrimAtPath(f"/World/Logs/{log_ids[0]}")
        self.assertTrue(log_00.RemoveProperty("campfire:surfaceTemperatureK"))
        recreated_snapshot = campfire.app.ResidentPublishedSnapshot(
            3, 0, log_ids, rows
        )
        adapter.publish(recreated_snapshot)
        self.assertAlmostEqual(
            log_00.GetAttribute("campfire:surfaceTemperatureK").Get(),
            rows[0].surface_mean_temperature_k,
        )
        recreated_profile = adapter.transaction_profiles()[2]
        self.assertEqual(recreated_profile.changed_write_count, 4)
        self.assertEqual(recreated_profile.unchanged_write_count, 15)
        with self.assertRaisesRegex(RuntimeError, "increase monotonically"):
            adapter.publish(snapshot)
        status = adapter.status()
        self.assertEqual(status["revision"], 3)
        self.assertEqual(status["publish_count"], 3)
        self.assertEqual(status["transaction_profile_count"], 3)
        self.assertTrue(status["handle_cache_enabled"])
        self.assertEqual(status["cached_attribute_count"], 19)
        self.assertEqual(status["prim_cache_miss_count"], 1)
        self.assertEqual(status["prim_cache_hit_count"], 2)
        self.assertEqual(status["attribute_cache_miss_count"], 20)
        self.assertEqual(status["attribute_cache_hit_count"], 37)
        adapter.on_timeline_stopped()
        self.assertTrue(adapter.close())
        self.assertEqual(adapter.status()["cached_attribute_count"], 0)
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
            cache_usd_handles=True,
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
        self.assertAlmostEqual(emitter.GetAttribute("fuel").Get(), original_fuel)
        emitter.GetAttribute("fuel").Set(0.125)
        with self.assertRaisesRegex(RuntimeError, "injected USD write failure"):
            adapter.publish(snapshot)
        self.assertAlmostEqual(emitter.GetAttribute("fuel").Get(), 0.125)
        self.assertEqual(adapter.status()["revision"], 0)
        self.assertEqual(adapter.status()["publish_count"], 0)
        self.assertEqual(adapter.status()["prim_cache_hit_count"], 1)
        self.assertEqual(adapter.status()["attribute_cache_hit_count"], 4)

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

    async def test_resident_application_session_owns_pending_retry_and_close(self):
        class Snapshot:
            def __init__(self, revision, tick):
                self.revision = revision
                self.tick = tick

        class Step:
            def __init__(self, revision, tick):
                self.snapshot = Snapshot(revision, tick)

        class Backend:
            def __init__(self):
                self.revision = 0
                self.tick = -1
                self.closed = False

            def step(self, *, tick):
                if self.closed:
                    raise RuntimeError("closed backend")
                self.revision += 1
                self.tick = tick
                return Step(self.revision, tick)

            def status(self):
                return {
                    "active": not self.closed,
                    "revision": self.revision,
                    "tick": self.tick,
                }

            def close(self):
                already_closed = self.closed
                self.closed = True
                return {"already_closed": already_closed, **self.status()}

        class Adapter:
            def __init__(self):
                self.active = False
                self.closed = False
                self.revision = 0
                self.fail_revision = None

            def on_timeline_started(self):
                self.active = True

            def on_timeline_stopped(self):
                self.active = False

            def publish(self, snapshot):
                if snapshot.revision == self.fail_revision:
                    self.fail_revision = None
                    raise RuntimeError("injected publication failure")
                self.revision = snapshot.revision

            def status(self):
                return {
                    "active": self.active,
                    "revision": self.revision,
                    "closed": self.closed,
                }

            def close(self):
                self.active = False
                already_closed = self.closed
                self.closed = True
                return not already_closed

        backend = Backend()
        adapter = Adapter()
        session = campfire.app.ResidentApplicationSession(backend, adapter)
        self.assertEqual(session.status()["state"], "ready")
        with self.assertRaisesRegex(RuntimeError, "state running"):
            session.step(tick=1)

        session.start()
        first = session.step(tick=1)
        self.assertEqual(first.snapshot.revision, 1)
        adapter.fail_revision = 2
        with self.assertRaisesRegex(RuntimeError, "injected publication failure"):
            session.step(tick=2)
        failed = session.status()
        self.assertEqual(failed["pending_revision"], 2)
        self.assertEqual(failed["backend"]["revision"], 2)
        self.assertEqual(failed["adapter"]["revision"], 1)
        with self.assertRaisesRegex(RuntimeError, "pending snapshot retry"):
            session.step(tick=3)
        with self.assertRaisesRegex(RuntimeError, "refuses to close"):
            session.close()

        self.assertTrue(session.stop())
        self.assertFalse(session.stop())
        session.start()
        retried = session.retry_pending()
        self.assertEqual(retried.snapshot.revision, 2)
        third = session.step(tick=3)
        self.assertEqual(third.snapshot.revision, 3)
        status = session.status()
        self.assertIsNone(status["pending_revision"])
        self.assertEqual(status["step_count"], 3)
        self.assertEqual(status["publish_count"], 3)
        self.assertEqual(status["publish_failure_count"], 1)
        self.assertEqual(status["retry_count"], 1)

        thread_errors = []

        def read_status_from_other_thread():
            try:
                session.status()
            except Exception as error:
                thread_errors.append(error)

        worker = threading.Thread(target=read_status_from_other_thread)
        worker.start()
        worker.join()
        self.assertEqual(len(thread_errors), 1)
        self.assertRegex(str(thread_errors[0]), "owner thread")

        closed = session.close()
        self.assertFalse(closed["already_closed"])
        self.assertFalse(closed["pending_discarded"])
        self.assertTrue(session.close()["already_closed"])

    async def test_resident_application_session_retries_sidecar_with_snapshot(self):
        class Payload:
            def __init__(self, revision):
                self.revision = revision

        class Snapshot:
            def __init__(self, revision, tick):
                self.revision = revision
                self.tick = tick

        class Step:
            def __init__(self, revision, tick):
                self.snapshot = Snapshot(revision, tick)

        class Backend:
            def __init__(self):
                self.revision = 0
                self.closed = False

            def step(self, *, tick):
                self.revision += 1
                return Step(self.revision, tick)

            def status(self):
                return {"revision": self.revision, "active": not self.closed}

            def close(self):
                self.closed = True
                return {"revision": self.revision, "active": False}

        class Adapter:
            def __init__(self):
                self.revision = 0
                self.fail_revision = None
                self.active = False
                self.closed = False

            def on_timeline_started(self):
                self.active = True

            def on_timeline_stopped(self):
                self.active = False

            def publish(self, snapshot):
                if snapshot.revision == self.fail_revision:
                    self.fail_revision = None
                    raise RuntimeError("injected primary failure")
                self.revision = snapshot.revision

            def status(self):
                return {
                    "revision": self.revision,
                    "active": self.active,
                    "closed": self.closed,
                }

            def close(self):
                self.active = False
                self.closed = True
                return True

        class Sidecar:
            def __init__(self):
                self.revision = 0
                self.fail_revision = None
                self.prepared = []
                self.published = []
                self.rollback_count = 0
                self.layout = None
                self.closed = False

            def prepare(self, snapshot):
                payload = Payload(snapshot.revision)
                self.prepared.append(payload)
                return payload

            def publish(self, payload):
                self.published.append(payload)
                if payload.revision == self.fail_revision:
                    self.fail_revision = None
                    raise RuntimeError("injected sidecar failure")
                self.revision = payload.revision

            def rollback_last_commit(self, revision):
                self.assert_revision = revision
                self.revision = revision - 1
                self.rollback_count += 1

            def status(self):
                return {"revision": self.revision, "closed": self.closed}

            def replace_layout(self, layout):
                self.layout = layout
                return layout

            def close(self):
                self.closed = True
                return True

        backend = Backend()
        adapter = Adapter()
        sidecar = Sidecar()
        session = campfire.app.ResidentApplicationSession(
            backend, adapter, sidecar=sidecar
        )
        session.start()
        session.step(tick=1)
        with self.assertRaisesRegex(RuntimeError, "ready or stopped"):
            session.replace_sidecar_layout("moving")

        sidecar.fail_revision = 2
        with self.assertRaisesRegex(RuntimeError, "injected sidecar failure"):
            session.step(tick=2)
        self.assertEqual(adapter.revision, 1)
        self.assertEqual(sidecar.revision, 1)
        pending_payload = sidecar.prepared[-1]
        session.retry_pending()
        self.assertIs(sidecar.published[-1], pending_payload)
        self.assertEqual(adapter.revision, 2)
        self.assertEqual(sidecar.revision, 2)

        adapter.fail_revision = 3
        with self.assertRaisesRegex(RuntimeError, "injected primary failure"):
            session.step(tick=3)
        self.assertEqual(adapter.revision, 2)
        self.assertEqual(sidecar.revision, 2)
        self.assertEqual(sidecar.rollback_count, 1)
        self.assertEqual(session.status()["pending_sidecar_revision"], 3)
        session.retry_pending()
        self.assertEqual(adapter.revision, 3)
        self.assertEqual(sidecar.revision, 3)
        self.assertIsNone(session.status()["pending_sidecar_revision"])

        sidecar.fail_revision = 4
        with self.assertRaisesRegex(RuntimeError, "injected sidecar failure"):
            session.step(tick=4)
        replacement_payload = sidecar.prepared[-1]
        with self.assertRaisesRegex(RuntimeError, "stopped state"):
            session.replace_consumers(Adapter(), sidecar=Sidecar())
        session.stop()
        mismatched_adapter = Adapter()
        mismatched_adapter.revision = 2
        mismatched_sidecar = Sidecar()
        mismatched_sidecar.revision = 3
        with self.assertRaisesRegex(ValueError, "adapter revision does not match"):
            session.replace_consumers(
                mismatched_adapter, sidecar=mismatched_sidecar
            )
        self.assertFalse(adapter.closed)
        self.assertFalse(sidecar.closed)
        self.assertEqual(session.status()["pending_revision"], 4)
        replacement_adapter = Adapter()
        replacement_adapter.revision = 3
        replacement_sidecar = Sidecar()
        replacement_sidecar.revision = 3
        replacement = session.replace_consumers(
            replacement_adapter, sidecar=replacement_sidecar
        )
        self.assertEqual(replacement["revision"], 3)
        self.assertEqual(replacement["pending_revision"], 4)
        self.assertTrue(adapter.closed)
        self.assertTrue(sidecar.closed)
        session.start()
        session.retry_pending()
        self.assertIs(replacement_sidecar.published[-1], replacement_payload)
        self.assertEqual(replacement_adapter.revision, 4)
        self.assertEqual(replacement_sidecar.revision, 4)
        session.stop()
        self.assertEqual(session.replace_sidecar_layout("moving"), "moving")
        self.assertEqual(replacement_sidecar.layout, "moving")
        session.close()

    async def test_resident_stage_recovery_retries_factory_without_losing_pending(self):
        class Session:
            def __init__(self):
                self.state = "running"
                self.pending_revision = 3
                self.revision = 2
                self.replace_count = 0
                self.retry_count = 0

            def status(self):
                return {
                    "state": self.state,
                    "pending_revision": self.pending_revision,
                    "adapter": {"revision": self.revision},
                }

            def stop(self):
                self.state = "stopped"

            def start(self):
                self.state = "running"

            def replace_consumers(self, adapter, *, sidecar=None):
                self.asserted_pair = (adapter, sidecar)
                self.replace_count += 1
                return {
                    "revision": self.revision,
                    "pending_revision": self.pending_revision,
                    "consumer_replace_count": self.replace_count,
                }

            def retry_pending(self):
                self.retry_count += 1
                self.revision = self.pending_revision
                self.pending_revision = None

        class Timeline:
            def __init__(self):
                self.stop_count = 0

            def stop(self):
                self.stop_count += 1

        class Context:
            def __init__(self):
                self.stage = "original"
                self.orchestrator = None

            async def close_stage_async(self):
                self.orchestrator.observe_stage_event("closing")
                self.orchestrator.observe_stage_event("closed")
                self.stage = None
                return True, ""

            async def attach_stage_async(self, stage):
                self.orchestrator.observe_stage_event("opening")
                self.stage = stage
                self.orchestrator.observe_stage_event("opened")
                return True, ""

            def get_stage(self):
                return self.stage

        session = Session()
        timeline = Timeline()
        context = Context()
        factory_calls = []
        fail_factory = {"value": True}

        def factory(stage, revision):
            factory_calls.append((stage, revision))
            if fail_factory["value"]:
                raise RuntimeError("injected factory failure")
            return "replacement adapter", "replacement sidecar"

        drain_count = {"value": 0}

        async def next_update():
            drain_count["value"] += 1

        orchestrator = campfire.app.ResidentStageRecoveryOrchestrator(
            session,
            context,
            timeline,
            factory,
            next_update,
            drain_updates=4,
        )
        context.orchestrator = orchestrator
        replacement_stage = object()
        with self.assertRaisesRegex(RuntimeError, "injected factory failure"):
            await orchestrator.replace_stage(replacement_stage)
        failed = orchestrator.status()
        self.assertEqual(failed["state"], "faulted")
        self.assertEqual(failed["observed_events"], ("closing", "closed", "opening", "opened"))
        self.assertEqual(session.state, "stopped")
        self.assertEqual(session.pending_revision, 3)
        self.assertEqual(session.replace_count, 0)
        self.assertEqual(timeline.stop_count, 1)
        self.assertEqual(drain_count["value"], 8)

        fail_factory["value"] = False
        recovered = orchestrator.retry_recovery()
        self.assertTrue(recovered["pending_retried"])
        self.assertEqual(recovered["pending_revision"], 3)
        self.assertEqual(recovered["session_state"], "running")
        self.assertEqual(session.revision, 3)
        self.assertIsNone(session.pending_revision)
        self.assertEqual(session.replace_count, 1)
        self.assertEqual(session.retry_count, 1)
        self.assertEqual(factory_calls, [(replacement_stage, 2)] * 2)
        status = orchestrator.status()
        self.assertEqual(status["state"], "running")
        self.assertEqual(status["attempt_count"], 1)
        self.assertEqual(status["success_count"], 1)
        self.assertEqual(status["failure_count"], 1)
        self.assertEqual(status["recovery_retry_count"], 1)
        with self.assertRaisesRegex(RuntimeError, "no retryable attached stage"):
            orchestrator.retry_recovery()

    async def test_resident_surface_payload_is_immutable_and_byte_exact(self):
        payload = campfire.app.ImmutableSurfacePayload(
            revision=4,
            tick=7,
            layout_revision=2,
            point_count=2,
            positions=bytes(range(24)),
            fuels=bytes(range(8)),
            temperatures=bytes(range(8, 16)),
            smokes=bytes(range(16, 24)),
        )
        duplicate = replace(payload)
        self.assertEqual(payload, duplicate)
        self.assertEqual(payload.digest(), duplicate.digest())
        with self.assertRaises((AttributeError, TypeError)):
            payload.revision = 5
        with self.assertRaisesRegex(ValueError, "position byte count"):
            replace(payload, positions=b"short")
        with self.assertRaisesRegex(ValueError, "channel byte count"):
            replace(payload, fuels=b"short")
        with self.assertRaisesRegex(ValueError, "revisions and tick"):
            replace(payload, layout_revision=0)
        with self.assertRaisesRegex(ValueError, "metadata must use integers"):
            replace(payload, revision=True)
        with self.assertRaisesRegex(TypeError, "immutable bytes"):
            replace(payload, smokes=bytearray(payload.smokes))
        moved = replace(
            payload,
            layout_origins=((0.0, 0.0, 0.1),),
            layout_axes=(0,),
        )
        self.assertNotEqual(payload.digest(), moved.digest())
        with self.assertRaisesRegex(ValueError, "metadata must be paired"):
            replace(payload, layout_origins=((0.0, 0.0, 0.1),))
        with self.assertRaisesRegex(ValueError, "layout axes are invalid"):
            replace(
                payload,
                layout_origins=((0.0, 0.0, 0.1),),
                layout_axes=(True,),
            )
        with self.assertRaisesRegex(TypeError, "immutable tuples"):
            replace(
                payload,
                layout_origins=[[0.0, 0.0, 0.1]],
                layout_axes=[0],
            )

    async def test_resident_snapshot_adapter_resumes_only_matching_consumer_revision(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(stage)
        log_ids = (campfire.app.PHASE3_DRY_LOG_ID, campfire.app.PHASE3_WET_LOG_ID)
        initial_dry_mass = {log_id: 1.0 for log_id in log_ids}
        consumers = [
            stage.GetPrimAtPath(f"/World/Logs/{log_id}") for log_id in log_ids
        ] + [stage.GetPrimAtPath(campfire.app.FLOW_EMITTER_PATH)]
        for prim in consumers:
            prim.CreateAttribute(
                "campfire:residentRevision", Sdf.ValueTypeNames.Int64
            ).Set(5)

        adapter = campfire.app.UsdResidentSnapshotAdapter(
            stage,
            log_ids,
            initial_dry_mass,
            cache_usd_handles=True,
            lightweight_commits=True,
            initial_revision=5,
        )
        self.assertEqual(adapter.status()["initial_revision"], 5)
        self.assertEqual(adapter.status()["revision"], 5)
        rows = tuple(
            campfire.app.ResidentPublishedRow(
                600.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.3, 0.4, 0.2, 0.006
            )
            for _ in log_ids
        )
        adapter.on_timeline_started()
        adapter.publish(campfire.app.ResidentPublishedSnapshot(6, 6, log_ids, rows))
        self.assertEqual(adapter.status()["revision"], 6)
        self.assertEqual(adapter.status()["publish_count"], 1)
        adapter.close()

        consumers[0].GetAttribute("campfire:residentRevision").Set(4)
        with self.assertRaisesRegex(ValueError, "matching consumer revisions"):
            campfire.app.UsdResidentSnapshotAdapter(
                stage,
                log_ids,
                initial_dry_mass,
                initial_revision=5,
            )
        with self.assertRaisesRegex(ValueError, "non-negative integer"):
            campfire.app.UsdResidentSnapshotAdapter(
                stage,
                log_ids,
                initial_dry_mass,
                initial_revision=True,
            )

    async def test_resident_snapshot_lightweight_commit_recovers_last_snapshot(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(stage)
        log_ids = (campfire.app.PHASE3_DRY_LOG_ID, campfire.app.PHASE3_WET_LOG_ID)
        initial_dry_mass = {log_id: 2.0 for log_id in log_ids}
        first_rows = tuple(
            campfire.app.ResidentPublishedRow(
                600.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.3, 0.4, 0.2, 0.006
            )
            for _ in log_ids
        )
        second_rows = tuple(
            campfire.app.ResidentPublishedRow(
                760.0, 0.8, 0.7, 0.4, 0.1, 0.75, 0.6, 0.8, 1.2, 0.7, 0.02
            )
            for _ in log_ids
        )
        observer_calls = 0

        def fail_second_publish_fourth_write(_write_count, _name):
            nonlocal observer_calls
            observer_calls += 1
            if observer_calls == 23:
                raise RuntimeError("injected lightweight write failure")

        adapter = campfire.app.UsdResidentSnapshotAdapter(
            stage,
            log_ids,
            initial_dry_mass,
            write_observer=fail_second_publish_fourth_write,
            cache_usd_handles=True,
            lightweight_commits=True,
            profile_lightweight_tails=True,
        )
        with self.assertRaisesRegex(ValueError, "transactional detail profiling"):
            campfire.app.UsdResidentSnapshotAdapter(
                stage,
                log_ids,
                initial_dry_mass,
                profile_transactions=True,
                lightweight_commits=True,
            )
        adapter.on_timeline_started()
        first = campfire.app.ResidentPublishedSnapshot(1, 0, log_ids, first_rows)
        adapter.publish(first)

        emitter = stage.GetPrimAtPath(campfire.app.FLOW_EMITTER_PATH)

        def usd_signature():
            values = [
                emitter.GetAttribute(name).Get()
                for name in (
                    "fuel",
                    "temperature",
                    "smoke",
                    "coupleRateFuel",
                    "coupleRateTemperature",
                    "coupleRateSmoke",
                    "campfire:residentRevision",
                )
            ]
            for log_id in log_ids:
                prim = stage.GetPrimAtPath(f"/World/Logs/{log_id}")
                values.extend(
                    [
                        tuple(UsdGeom.Gprim(prim).GetDisplayColorAttr().Get()),
                        prim.GetAttribute("campfire:surfaceTemperatureK").Get(),
                        prim.GetAttribute("campfire:charFraction").Get(),
                        prim.GetAttribute("campfire:remainingMassRatio").Get(),
                        prim.GetAttribute("campfire:weakestSupportRatio").Get(),
                        prim.GetAttribute("campfire:residentRevision").Get(),
                    ]
                )
            return tuple(values)

        committed_signature = usd_signature()
        second = campfire.app.ResidentPublishedSnapshot(2, 1, log_ids, second_rows)
        with self.assertRaisesRegex(RuntimeError, "injected lightweight write failure"):
            adapter.publish(second)
        self.assertEqual(usd_signature(), committed_signature)
        status = adapter.status()
        self.assertEqual(status["revision"], 1)
        self.assertEqual(status["publish_count"], 1)
        self.assertEqual(status["lightweight_commit_count"], 0)
        self.assertEqual(status["lightweight_failure_count"], 1)
        self.assertEqual(status["lightweight_recovery_count"], 1)
        failed_tail_profile = adapter.lightweight_tail_profiles()[0]
        self.assertIsInstance(
            failed_tail_profile, campfire.app.ResidentUsdLightweightTailProfile
        )
        self.assertEqual(failed_tail_profile.status, "recovered")
        self.assertEqual(failed_tail_profile.revision, 2)
        self.assertGreater(failed_tail_profile.recovery_ms, 0.0)
        self.assertFalse(status["faulted"])

        third = campfire.app.ResidentPublishedSnapshot(3, 2, log_ids, second_rows)
        adapter.publish(third)
        status = adapter.status()
        self.assertEqual(status["revision"], 3)
        self.assertEqual(status["publish_count"], 2)
        self.assertEqual(status["lightweight_commit_count"], 1)
        self.assertEqual(status["lightweight_recovery_count"], 1)
        committed_tail_profile = adapter.lightweight_tail_profiles()[1]
        self.assertEqual(committed_tail_profile.status, "committed")
        self.assertEqual(committed_tail_profile.revision, 3)
        self.assertEqual(status["lightweight_tail_profile_count"], 2)
        self.assertEqual(
            emitter.GetAttribute("campfire:residentRevision").Get(), 3
        )
        for log_id in log_ids:
            self.assertEqual(
                stage.GetPrimAtPath(f"/World/Logs/{log_id}")
                .GetAttribute("campfire:residentRevision")
                .Get(),
                3,
            )
        adapter.close()

        fault_stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(fault_stage)
        fault_observer_calls = 0

        def remove_emitter_during_second_publish(_write_count, _name):
            nonlocal fault_observer_calls
            fault_observer_calls += 1
            if fault_observer_calls == 23:
                fault_stage.RemovePrim(campfire.app.FLOW_EMITTER_PATH)
                raise RuntimeError("injected unrecoverable write failure")

        fault_adapter = campfire.app.UsdResidentSnapshotAdapter(
            fault_stage,
            log_ids,
            initial_dry_mass,
            write_observer=remove_emitter_during_second_publish,
            cache_usd_handles=True,
            lightweight_commits=True,
        )
        fault_adapter.on_timeline_started()
        fault_adapter.publish(first)
        with self.assertRaisesRegex(RuntimeError, "snapshot recovery failed"):
            fault_adapter.publish(second)
        self.assertTrue(fault_adapter.status()["faulted"])
        self.assertEqual(fault_adapter.status()["revision"], 1)
        with self.assertRaisesRegex(RuntimeError, "explicit reconstruction"):
            fault_adapter.publish(third)
        fault_adapter.close()

    async def test_resident_snapshot_change_block_coalesces_commit_and_recovery(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(stage)
        log_ids = (campfire.app.PHASE3_DRY_LOG_ID, campfire.app.PHASE3_WET_LOG_ID)
        rows = tuple(
            campfire.app.ResidentPublishedRow(
                720.0, 0.9, 0.8, 0.2, 0.05, 0.85, 0.7, 0.6, 0.9, 0.4, 0.012
            )
            for _ in log_ids
        )
        observer_calls = 0
        fail_on_call = None

        def fail_selected_write(_write_count, _name):
            nonlocal observer_calls
            observer_calls += 1
            if observer_calls == fail_on_call:
                raise RuntimeError("injected revision-last publication failure")

        with self.assertRaisesRegex(ValueError, "requires lightweight commits"):
            campfire.app.UsdResidentSnapshotAdapter(
                stage,
                log_ids,
                {log_id: 2.0 for log_id in log_ids},
                coalesce_lightweight_notices=True,
            )
        with self.assertRaisesRegex(ValueError, "requires lightweight commits and handle cache"):
            campfire.app.UsdResidentSnapshotAdapter(
                stage,
                log_ids,
                {log_id: 2.0 for log_id in log_ids},
                lightweight_commits=True,
                track_lightweight_notices=True,
            )

        adapter = campfire.app.UsdResidentSnapshotAdapter(
            stage,
            log_ids,
            {log_id: 2.0 for log_id in log_ids},
            write_observer=fail_selected_write,
            cache_usd_handles=True,
            lightweight_commits=True,
            coalesce_lightweight_notices=True,
            track_lightweight_notices=True,
        )
        adapter.on_timeline_started()
        adapter.publish(campfire.app.ResidentPublishedSnapshot(1, 0, log_ids, rows))

        emitter = stage.GetPrimAtPath(campfire.app.FLOW_EMITTER_PATH)

        def revisions():
            return tuple(
                [
                    stage.GetPrimAtPath(f"/World/Logs/{log_id}")
                    .GetAttribute("campfire:residentRevision")
                    .Get()
                    for log_id in log_ids
                ]
                + [emitter.GetAttribute("campfire:residentRevision").Get()]
            )

        def usd_signature():
            values = [
                emitter.GetAttribute(name).Get()
                for name in (
                    "fuel",
                    "temperature",
                    "smoke",
                    "coupleRateFuel",
                    "coupleRateTemperature",
                    "coupleRateSmoke",
                    "campfire:residentRevision",
                )
            ]
            for log_id in log_ids:
                prim = stage.GetPrimAtPath(f"/World/Logs/{log_id}")
                values.extend(
                    [
                        tuple(UsdGeom.Gprim(prim).GetDisplayColorAttr().Get()),
                        prim.GetAttribute("campfire:surfaceTemperatureK").Get(),
                        prim.GetAttribute("campfire:charFraction").Get(),
                        prim.GetAttribute("campfire:remainingMassRatio").Get(),
                        prim.GetAttribute("campfire:weakestSupportRatio").Get(),
                        prim.GetAttribute("campfire:residentRevision").Get(),
                    ]
                )
            return tuple(values)

        observed_revisions = []

        def observe_change(_notice, _sender):
            observed_revisions.append(revisions())

        listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, observe_change, stage)
        adapter.publish(campfire.app.ResidentPublishedSnapshot(2, 1, log_ids, rows))
        self.assertEqual(observed_revisions, [(2, 2, 2)])
        committed_signature = usd_signature()

        observed_revisions.clear()
        fail_on_call = observer_calls + 19
        with self.assertRaisesRegex(
            RuntimeError, "injected revision-last publication failure"
        ):
            adapter.publish(campfire.app.ResidentPublishedSnapshot(3, 2, log_ids, rows))
        self.assertEqual(observed_revisions, [(2, 2, 2)])
        self.assertEqual(usd_signature(), committed_signature)
        status = adapter.status()
        self.assertTrue(status["lightweight_notice_coalescing_enabled"])
        self.assertEqual(status["revision"], 2)
        self.assertEqual(status["publish_count"], 2)
        self.assertEqual(status["lightweight_failure_count"], 1)
        self.assertEqual(status["lightweight_recovery_count"], 1)
        self.assertTrue(status["lightweight_notice_tracking_enabled"])
        self.assertEqual(status["lightweight_notice_count"], 2)
        self.assertEqual(status["lightweight_notice_accepted_revision_count"], 1)
        self.assertEqual(status["lightweight_notice_rejected_count"], 1)
        self.assertEqual(status["lightweight_notice_publication_count"], 2)
        self.assertEqual(status["lightweight_notices_per_publication_minimum"], 1)
        self.assertEqual(status["lightweight_notices_per_publication_maximum"], 1)
        listener.Revoke()
        adapter.on_timeline_stopped()
        adapter.close()

    async def test_resident_snapshot_skips_only_unchanged_derived_payloads(self):
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(stage)
        log_ids = (campfire.app.PHASE3_DRY_LOG_ID, campfire.app.PHASE3_WET_LOG_ID)
        initial_dry_mass = {log_id: 2.0 for log_id in log_ids}
        rows = tuple(
            campfire.app.ResidentPublishedRow(
                600.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.3, 0.4, 0.2, 0.006
            )
            for _ in log_ids
        )
        observer_calls = 0

        def count_writes(_write_count, _name):
            nonlocal observer_calls
            observer_calls += 1

        with self.assertRaisesRegex(ValueError, "requires lightweight commits"):
            campfire.app.UsdResidentSnapshotAdapter(
                stage,
                log_ids,
                initial_dry_mass,
                skip_unchanged_derived=True,
            )
        with self.assertRaisesRegex(ValueError, "requires lightweight commits"):
            campfire.app.UsdResidentSnapshotAdapter(
                stage,
                log_ids,
                initial_dry_mass,
                profile_lightweight_tails=True,
            )
        adapter = campfire.app.UsdResidentSnapshotAdapter(
            stage,
            log_ids,
            initial_dry_mass,
            write_observer=count_writes,
            cache_usd_handles=True,
            lightweight_commits=True,
            skip_unchanged_derived=True,
            profile_lightweight_tails=True,
        )
        adapter.on_timeline_started()
        adapter.publish(campfire.app.ResidentPublishedSnapshot(1, 0, log_ids, rows))
        adapter.publish(campfire.app.ResidentPublishedSnapshot(2, 1, log_ids, rows))
        status = adapter.status()
        self.assertEqual(status["lightweight_write_count"], 3)
        self.assertEqual(status["skipped_unchanged_write_count"], 16)
        self.assertEqual(observer_calls, 22)

        changed_rows = (
            campfire.app.ResidentPublishedRow(
                601.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.3, 0.4, 0.2, 0.006
            ),
            rows[1],
        )
        adapter.publish(
            campfire.app.ResidentPublishedSnapshot(3, 2, log_ids, changed_rows)
        )
        status = adapter.status()
        self.assertEqual(status["lightweight_write_count"], 8)
        self.assertEqual(status["skipped_unchanged_write_count"], 30)
        self.assertEqual(observer_calls, 27)
        self.assertEqual(status["revision"], 3)
        self.assertTrue(status["lightweight_tail_profiling_enabled"])
        self.assertEqual(status["lightweight_tail_profile_count"], 2)
        unchanged_profile, changed_profile = adapter.lightweight_tail_profiles()
        self.assertEqual(
            (
                unchanged_profile.write_count,
                unchanged_profile.skipped_write_count,
            ),
            (3, 16),
        )
        self.assertEqual(
            (changed_profile.write_count, changed_profile.skipped_write_count),
            (5, 14),
        )
        self.assertEqual(
            dict(
                (name, (written, skipped))
                for name, written, skipped in unchanged_profile.group_write_disposition
            )["revision"],
            (3, 0),
        )
        emitter = stage.GetPrimAtPath(campfire.app.FLOW_EMITTER_PATH)
        self.assertEqual(
            emitter.GetAttribute("campfire:residentRevision").Get(), 3
        )
        for log_id in log_ids:
            self.assertEqual(
                stage.GetPrimAtPath(f"/World/Logs/{log_id}")
                .GetAttribute("campfire:residentRevision")
                .Get(),
                3,
            )
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

    async def test_native_snapshot_producer_freezes_contiguous_rows(self):
        log_ids = ("log_00", "log_01")
        values = array(
            "d",
            (
                820.0,
                1.0,
                8.0,
                1.5,
                0.1,
                0.72,
                0.64,
                0.4,
                0.7,
                0.2,
                0.008,
                430.0,
                3.0,
                9.0,
                0.4,
                0.05,
                0.88,
                0.82,
                0.0,
                0.0,
                0.1,
                0.0,
            ),
        )
        producer = campfire.app.ResidentNativeSnapshotProducer(log_ids)
        snapshot = producer.build(revision=7, tick=6, values=values)

        self.assertIsInstance(snapshot, campfire.app.ResidentPublishedSnapshot)
        self.assertEqual(snapshot.revision, 7)
        self.assertEqual(snapshot.tick, 6)
        self.assertEqual(snapshot.log_ids, log_ids)
        self.assertEqual(
            producer.field_names, campfire.app.RESIDENT_PUBLISHED_FIELD_NAMES
        )
        self.assertEqual(snapshot.rows[0].surface_mean_temperature_k, 820.0)
        self.assertEqual(snapshot.rows[1].pyrolysis_gas_rate_kg_s, 0.0)

        values[0] = 999.0
        self.assertEqual(snapshot.rows[0].surface_mean_temperature_k, 820.0)
        with self.assertRaisesRegex(ValueError, "expected 22"):
            producer.build(revision=8, tick=7, values=array("d", values[:-1]))
        with self.assertRaisesRegex(ValueError, "64-bit"):
            producer.build(revision=8, tick=7, values=array("f", [0.0] * 22))
        invalid = array("d", values)
        invalid[0] = math.nan
        with self.assertRaisesRegex(ValueError, "finite"):
            producer.build(revision=8, tick=7, values=invalid)
