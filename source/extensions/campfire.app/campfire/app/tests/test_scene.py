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
