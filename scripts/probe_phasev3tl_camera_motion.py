"""Visual-gate-only camera orbit for Phase V3T-L captures."""

from __future__ import annotations

import asyncio
import math

import omni.kit.app
import omni.timeline
import omni.usd
from pxr import Gf, UsdGeom


async def _orbit() -> None:
    app = omni.kit.app.get_app()
    timeline = omni.timeline.get_timeline_interface()
    context = omni.usd.get_context()
    camera = None
    for _ in range(1200):
        stage = context.get_stage()
        camera = stage.GetPrimAtPath("/World/Camera") if stage else None
        if camera and camera.IsValid() and timeline.is_playing():
            break
        await app.next_update_async()
    if not camera or not camera.IsValid():
        return
    xform = UsdGeom.Xformable(camera)
    attribute = camera.GetAttribute("xformOp:transform")
    if not attribute:
        attribute = xform.MakeMatrixXform().GetAttr()
    while timeline.is_playing():
        phase = max(0.0, min(1.0, float(timeline.get_current_time()) / 200.0))
        angle = math.radians(-46.0 + 18.0 * phase)
        radius = 10.8
        eye = Gf.Vec3d(radius * math.cos(angle), radius * math.sin(angle), 5.8 + 0.45 * math.sin(phase * math.pi))
        view = Gf.Matrix4d(1.0)
        view.SetLookAt(eye, Gf.Vec3d(0.0, 0.0, 1.15), Gf.Vec3d(0.0, 0.0, 1.0))
        attribute.Set(view.GetInverse())
        for _ in range(4):
            await app.next_update_async()


asyncio.ensure_future(_orbit())
