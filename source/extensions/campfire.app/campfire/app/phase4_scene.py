"""Phase 4 side-by-side stack ventilation scene."""

from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom

from .air_supply import (
    LogPlacement,
    dense_stack_placements,
    estimate_air_supply,
    log_cabin_placements,
)
from .flow_scene import FLOW_EMITTER_PATH
from .phase2_scene import populate_phase2_scene
from .scene import CAMERA_PATH, export_stage
from .wood import LogSpec, create_log


PHASE4_DENSE_OFFSET_X_M = -2.15
PHASE4_CABIN_OFFSET_X_M = 2.15


def _offset_and_prefix(
    placements: list[LogPlacement], prefix: str, offset_x_m: float
) -> list[LogPlacement]:
    return [
        LogPlacement(
            log_id=f"{prefix}_{index:02d}",
            center_m=(
                placement.center_m[0] + offset_x_m,
                placement.center_m[1],
                placement.center_m[2],
            ),
            rotation_z_deg=placement.rotation_z_deg,
            radius_m=placement.radius_m,
            length_m=placement.length_m,
        )
        for index, placement in enumerate(placements)
    ]


def phase4_placements() -> dict[str, list[LogPlacement]]:
    return {
        "dense": _offset_and_prefix(
            dense_stack_placements(), "Dense", PHASE4_DENSE_OFFSET_X_M
        ),
        "cabin": _offset_and_prefix(
            log_cabin_placements(), "Cabin", PHASE4_CABIN_OFFSET_X_M
        ),
    }


def populate_phase4_scene(stage: Usd.Stage) -> Usd.Stage:
    populate_phase2_scene(stage)
    stage.RemovePrim("/World/Logs")
    stage.RemovePrim("/World/Stones")
    stage.RemovePrim("/World/Lights/Key")
    stage.GetPrimAtPath("/World/Lights/Dome").GetAttribute("inputs:intensity").Set(1200.0)
    UsdGeom.Xform.Define(stage, "/World/Logs")
    placements = phase4_placements()

    for scenario_name, scenario_placements in placements.items():
        local_placements = [
            LogPlacement(
                placement.log_id,
                (
                    placement.center_m[0]
                    - (PHASE4_DENSE_OFFSET_X_M if scenario_name == "dense" else PHASE4_CABIN_OFFSET_X_M),
                    placement.center_m[1],
                    placement.center_m[2],
                ),
                placement.rotation_z_deg,
                placement.radius_m,
                placement.length_m,
            )
            for placement in scenario_placements
        ]
        air = estimate_air_supply(local_placements)
        for placement in scenario_placements:
            prim = create_log(
                stage,
                LogSpec(
                    placement.log_id,
                    placement.center_m,
                    placement.rotation_z_deg,
                    placement.radius_m,
                    placement.length_m,
                ),
            )
            oxygen = air.oxygen_by_log[placement.log_id]
            prim.CreateAttribute("campfire:stackScenario", Sdf.ValueTypeNames.String).Set(
                scenario_name
            )
            prim.CreateAttribute("campfire:oxygenFactor", Sdf.ValueTypeNames.Double).Set(
                oxygen
            )
            color = Gf.Vec3f(0.38 - 0.18 * oxygen, 0.07 + 0.28 * oxygen, 0.035)
            UsdGeom.Gprim(prim).GetDisplayColorAttr().Set([color])

    emitter = stage.GetPrimAtPath(FLOW_EMITTER_PATH)
    emitter.GetAttribute("enabled").Set(False)
    camera = UsdGeom.Camera.Get(stage, CAMERA_PATH)
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(
        Gf.Vec3d(9.5, -12.5, 8.5),
        Gf.Vec3d(0.0, 0.0, 0.35),
        Gf.Vec3d(0.0, 0.0, 1.0),
    )
    camera.GetPrim().GetAttribute("xformOp:transform").Set(view.GetInverse())
    stage.GetRootLayer().customLayerData = {
        **stage.GetRootLayer().customLayerData,
        "campfire:phase": "phase4",
        "campfire:scene": "stack_air_comparison",
    }
    return stage


def export_phase4_stage(stage: Usd.Stage, destination: Path) -> Path:
    return export_stage(stage, destination)
