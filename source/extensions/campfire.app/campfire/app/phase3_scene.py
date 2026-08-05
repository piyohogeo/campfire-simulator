"""Phase 3 wood-thermal scene and Flow adapter."""

from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom

from .combustion import (
    FlowSourceState,
    WoodThermalModel,
    create_cylindrical_wood_model,
    save_model_to_prim,
)
from .flow_scene import FLOW_EMITTER_PATH
from .phase2_scene import export_phase2_stage, populate_phase2_scene, set_emitter_follow


PHASE3_DRY_LOG_ID = "Log_00"
PHASE3_WET_LOG_ID = "Log_01"
PHASE3_MODEL_DT_SECONDS = 0.2
PHASE3_TOTAL_STEPS = 1200
PHASE3_CAPTURE_STEPS = (650, PHASE3_TOTAL_STEPS)
PHASE3_FLOW_UPDATE_INTERVAL_STEPS = 5
PHASE3_EXTERNAL_HEAT_FLUX_W_M2 = 150_000.0
PHASE3_DRY_MOISTURE_RATIO_DB = 0.12
PHASE3_WET_MOISTURE_RATIO_DB = 0.60
PHASE3_IGNITION_RATE_KG_S = 1.0e-6


def create_phase3_models(stage: Usd.Stage) -> dict[str, WoodThermalModel]:
    models = {
        PHASE3_DRY_LOG_ID: create_cylindrical_wood_model(
            PHASE3_DRY_LOG_ID,
            radius_m=0.16,
            length_m=1.80,
            moisture_ratio_dry_basis=PHASE3_DRY_MOISTURE_RATIO_DB,
        ),
        PHASE3_WET_LOG_ID: create_cylindrical_wood_model(
            PHASE3_WET_LOG_ID,
            radius_m=0.16,
            length_m=1.80,
            moisture_ratio_dry_basis=PHASE3_WET_MOISTURE_RATIO_DB,
        ),
    }
    for log_id, model in models.items():
        save_model_to_prim(model, stage.GetPrimAtPath(f"/World/Logs/{log_id}"))
    return models


def update_flow_source(
    stage: Usd.Stage, log_id: str, source: FlowSourceState
) -> None:
    """Apply wood-owned mass release to the verified Flow sphere emitter."""

    set_emitter_follow(stage, log_id)
    emitter = stage.GetPrimAtPath(FLOW_EMITTER_PATH)
    values = {
        "fuel": source.fuel,
        "temperature": source.temperature,
        "smoke": source.smoke,
        "coupleRateFuel": 2.0 if source.fuel > 0.0 else 0.0,
        "coupleRateTemperature": 10.0 if source.temperature > 0.0 else 0.0,
        "coupleRateSmoke": 1.0 if source.smoke > 0.0 else 0.0,
    }
    for name, value in values.items():
        attribute = emitter.GetAttribute(name)
        if not attribute or not attribute.Set(value):
            raise RuntimeError(f"Unable to update Flow emitter attribute: {name}")


def apply_model_visual_state(
    prim: Usd.Prim, model: WoodThermalModel, metrics: dict | None = None
) -> None:
    """Expose aggregate drying/char state without changing collision geometry."""

    metrics = model.metrics() if metrics is None else metrics
    initial_dry_mass = sum(
        cell.dry_wood_mass_kg + cell.char_mass_kg + cell.ash_mass_kg
        for cell in model.cells
    ) + model.emitted_pyrolysis_gas_kg + model.emitted_char_gas_kg
    char_fraction = min(
        1.0,
        (metrics["char_mass_kg"] + metrics["ash_mass_kg"])
        / max(initial_dry_mass, 1.0e-12),
    )
    heat_fraction = min(
        1.0,
        max(0.0, (metrics["surface_mean_temperature_k"] - 500.0) / 700.0),
    )
    wood = Gf.Vec3f(0.30, 0.12, 0.045)
    char = Gf.Vec3f(0.035, 0.025, 0.020)
    ember = Gf.Vec3f(0.55, 0.075, 0.015)
    color = wood * (1.0 - char_fraction) + char * char_fraction
    color = color * (1.0 - 0.35 * heat_fraction) + ember * (0.35 * heat_fraction)
    UsdGeom.Gprim(prim).GetDisplayColorAttr().Set([color])
    prim.CreateAttribute("campfire:surfaceTemperatureK", Sdf.ValueTypeNames.Double).Set(
        metrics["surface_mean_temperature_k"]
    )
    prim.CreateAttribute("campfire:charFraction", Sdf.ValueTypeNames.Double).Set(
        char_fraction
    )


def populate_phase3_scene(stage: Usd.Stage) -> Usd.Stage:
    populate_phase2_scene(stage)
    models = create_phase3_models(stage)
    for log_id, model in models.items():
        apply_model_visual_state(stage.GetPrimAtPath(f"/World/Logs/{log_id}"), model)

    emitter = stage.GetPrimAtPath(FLOW_EMITTER_PATH)
    emitter.GetAttribute("fuel").Set(0.0)
    emitter.GetAttribute("temperature").Set(0.0)
    emitter.GetAttribute("smoke").Set(0.0)
    emitter.GetAttribute("coupleRateFuel").Set(0.0)
    emitter.GetAttribute("coupleRateTemperature").Set(0.0)
    emitter.GetAttribute("coupleRateSmoke").Set(0.0)
    set_emitter_follow(stage, PHASE3_DRY_LOG_ID)

    stage.SetEndTimeCode(float(PHASE3_TOTAL_STEPS))
    stage.SetTimeCodesPerSecond(1.0 / PHASE3_MODEL_DT_SECONDS)
    stage.GetRootLayer().customLayerData = {
        "campfire:phase": "phase3",
        "campfire:scene": "wood_thermal_mvp",
        "campfire:modelDtSeconds": PHASE3_MODEL_DT_SECONDS,
        "campfire:flowUpdateIntervalSteps": PHASE3_FLOW_UPDATE_INTERVAL_STEPS,
        "campfire:dryMoistureRatioDryBasis": PHASE3_DRY_MOISTURE_RATIO_DB,
        "campfire:wetMoistureRatioDryBasis": PHASE3_WET_MOISTURE_RATIO_DB,
        "renderSettings": {
            "rtx:flow:enabled": True,
            "rtx:flow:pathTracingEnabled": True,
            "rtx:flow:rayTracedReflectionsEnabled": True,
            "rtx:flow:rayTracedTranslucencyEnabled": True,
        },
    }
    return stage


def export_phase3_stage(stage: Usd.Stage, destination: Path) -> Path:
    return export_phase2_stage(stage, destination)
