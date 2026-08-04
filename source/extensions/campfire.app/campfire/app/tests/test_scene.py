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
