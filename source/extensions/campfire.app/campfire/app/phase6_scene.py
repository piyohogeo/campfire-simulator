"""Phase 6 calibration result scene."""

from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom

from .calibration import load_nist_plywood_reference
from .scene import CAMERA_PATH, export_stage, populate_fixed_scene


PHASE6_BAR_ROOT = "/World/CalibrationChart"
PHASE6_FLUXES = (35, 70)
PHASE6_SERIES = ("Observed", "Baseline", "Calibrated")
_COLORS = {
    "Observed": Gf.Vec3f(0.95, 0.72, 0.39),
    "Baseline": Gf.Vec3f(0.87, 0.25, 0.16),
    "Calibrated": Gf.Vec3f(0.18, 0.68, 0.40),
}


def _set_bar_height(bar: Usd.Prim, value_seconds: float) -> None:
    height = max(0.08, min(value_seconds / 80.0 * 6.0, 6.0))
    bar.GetAttribute("xformOp:scale").Set(Gf.Vec3f(0.42, 0.42, height / 2.0))
    translate = bar.GetAttribute("xformOp:translate").Get()
    bar.GetAttribute("xformOp:translate").Set(
        Gf.Vec3d(translate[0], translate[1], height / 2.0)
    )
    bar.GetAttribute("campfire:valueSeconds").Set(float(value_seconds))


def populate_phase6_scene(stage: Usd.Stage) -> Usd.Stage:
    populate_fixed_scene(stage)
    for path in ("/World/Logs", "/World/Stones", "/World/IgnitionSource"):
        stage.RemovePrim(path)
    stage.GetPrimAtPath("/World/Ground").GetAttribute("radius").Set(7.0)
    UsdGeom.Xform.Define(stage, PHASE6_BAR_ROOT)
    reference = load_nist_plywood_reference()

    observed = {
        int(target["incident_heat_flux_kw_m2"]): float(
            target["time_to_sustained_ignition_s"]
        )
        for target in reference["targets"]
    }
    for flux_index, flux in enumerate(PHASE6_FLUXES):
        group_path = f"{PHASE6_BAR_ROOT}/Flux{flux}"
        UsdGeom.Xform.Define(stage, group_path)
        for series_index, series in enumerate(PHASE6_SERIES):
            cube = UsdGeom.Cube.Define(stage, f"{group_path}/{series}")
            cube.CreateSizeAttr(1.0)
            x = -2.1 + flux_index * 4.2
            y = -1.15 + series_index * 1.15
            cube.AddTranslateOp().Set(Gf.Vec3d(x, y, 0.025))
            cube.AddScaleOp().Set(Gf.Vec3f(0.42, 0.42, 0.025))
            cube.CreateDisplayColorAttr([_COLORS[series]])
            prim = cube.GetPrim()
            prim.CreateAttribute("campfire:heatFluxKwM2", Sdf.ValueTypeNames.Int).Set(flux)
            prim.CreateAttribute("campfire:series", Sdf.ValueTypeNames.String).Set(series.lower())
            prim.CreateAttribute("campfire:valueSeconds", Sdf.ValueTypeNames.Double).Set(0.0)
            if series == "Observed":
                _set_bar_height(prim, observed[flux])

    camera = UsdGeom.Camera.Get(stage, CAMERA_PATH)
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(
        Gf.Vec3d(14.0, -18.0, 10.0),
        Gf.Vec3d(0.0, 0.0, 2.15),
        Gf.Vec3d(0.0, 0.0, 1.0),
    )
    camera.GetPrim().GetAttribute("xformOp:transform").Set(view.GetInverse())
    stage.GetRootLayer().customLayerData = {
        **stage.GetRootLayer().customLayerData,
        "campfire:phase": "phase6",
        "campfire:scene": "nist_plywood_calibration",
        "campfire:metric": "time_to_ignition_seconds",
    }
    return stage


def apply_phase6_calibration(stage: Usd.Stage, calibration: dict) -> None:
    for case_index, flux in enumerate(PHASE6_FLUXES):
        for series, result_key in (("Baseline", "baseline"), ("Calibrated", "best")):
            value = calibration[result_key]["cases"][case_index][
                "predicted_ignition_seconds"
            ]
            _set_bar_height(
                stage.GetPrimAtPath(f"{PHASE6_BAR_ROOT}/Flux{flux}/{series}"),
                float(value or 0.0),
            )
    stage.GetRootLayer().customLayerData = {
        **stage.GetRootLayer().customLayerData,
        "campfire:baselineScore": calibration["baseline"]["score_rmse_relative"],
        "campfire:calibratedScore": calibration["best"]["score_rmse_relative"],
        "campfire:improvementFraction": calibration["improvement_fraction"],
    }


def export_phase6_stage(stage: Usd.Stage, destination: Path) -> Path:
    return export_stage(stage, destination)
