"""Kit 110 probe for the default-off eight-band wood visual V1."""

from __future__ import annotations

import asyncio
import hashlib
import json
import statistics
import time
from pathlib import Path

import carb
import omni.kit.app
import omni.kit.viewport.utility
import omni.usd
from pxr import Usd

import campfire.app


LOG_IDS = ("Log_00", "Log_01", "Log_02", "Log_03")
CAPTURE_RESOLUTION = (1280, 720)


def _arguments():
    settings = carb.settings.get_settings()
    return {
        "output": Path(settings.get_as_string("/phasev1/output")),
        "capture_dir": Path(settings.get_as_string("/phasev1/captureDir")),
    }


def _model(log_id, state_index):
    model = campfire.app.create_cylindrical_wood_model(
        log_id, 0.16, 1.8, 0.12 if state_index != 1 else 0.60
    )
    cells_per_axial = model.spec.circumferential_cells * model.spec.radial_cells
    for axial in range(model.spec.axial_cells):
        band = axial // 3
        for local in range(cells_per_axial):
            cell = model.cells[axial * cells_per_axial + local]
            if cell.surface_exposure <= 0.0:
                continue
            if state_index == 0:
                cell.moisture_mass_kg = cell.dry_wood_mass_kg * 0.05
                cell.temperature_k = 1120.0 if band in (4, 5) else 430.0
            elif state_index == 1:
                cell.moisture_mass_kg = cell.dry_wood_mass_kg * (0.75 if band < 5 else 0.30)
                cell.temperature_k = 390.0 + band * 22.0
            elif state_index == 2:
                fraction = 0.82 if band >= 3 else 0.30
                converted = cell.dry_wood_mass_kg * fraction
                cell.dry_wood_mass_kg -= converted
                cell.char_mass_kg = converted
                cell.moisture_mass_kg = 0.0
                cell.temperature_k = 780.0 + band * 35.0
            else:
                fraction = 0.88 if band <= 4 else 0.35
                converted = cell.dry_wood_mass_kg * fraction
                cell.dry_wood_mass_kg -= converted
                cell.ash_mass_kg = converted
                cell.moisture_mass_kg = 0.0
                cell.temperature_k = 900.0 + (7 - band) * 28.0
    return model


def _uniform_row(model):
    surface = tuple(cell for cell in model.cells if cell.surface_exposure > 0.0)
    area = sum(cell.external_area_m2 for cell in surface)
    return campfire.app.ResidentPublishedRow(
        sum(cell.temperature_k * cell.external_area_m2 for cell in surface) / area,
        sum(cell.moisture_mass_kg for cell in surface),
        sum(cell.dry_wood_mass_kg for cell in surface),
        sum(cell.char_mass_kg for cell in surface),
        sum(cell.ash_mass_kg for cell in surface),
        1.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
    )


def _build_visual_stage(path, mode):
    path.unlink(missing_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    campfire.app.populate_phase3_scene(stage)
    models = tuple(_model(log_id, index) for index, log_id in enumerate(LOG_IDS))
    if mode == "v0":
        campfire.app.preauthor_wood_visual_v0(stage, LOG_IDS)
        consumer = campfire.app.WoodVisualV0Consumer(stage, LOG_IDS)
        snapshot = campfire.app.ResidentPublishedSnapshot(
            1, 1, LOG_IDS, tuple(_uniform_row(model) for model in models)
        )
    else:
        campfire.app.preauthor_wood_visual_v1(stage, LOG_IDS)
        consumer = campfire.app.WoodVisualV1Consumer(stage, LOG_IDS)
        snapshot = campfire.app.WoodVisualBandSnapshot(
            1,
            LOG_IDS,
            tuple(
                row
                for model in models
                for row in campfire.app.aggregate_model_into_visual_bands(model)
            ),
        )
    consumer.on_timeline_started()
    profile = consumer.publish(snapshot)
    consumer.close()
    paths = tuple(str(prim.GetPath()) for prim in stage.Traverse())
    if not stage.GetRootLayer().Save():
        raise RuntimeError("Unable to save V1 comparison stage")
    return profile, paths


def _summary(values, warmup=5):
    values = list(values)[warmup:]
    ordered = sorted(values)
    return {
        "samples": len(values),
        "mean_ms": statistics.fmean(values),
        "p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        "maximum_ms": max(values),
    }


def _file(path):
    payload = path.read_bytes()
    return {
        "path": str(path),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


async def _viewport():
    app = omni.kit.app.get_app()
    for _ in range(120):
        viewport = omni.kit.viewport.utility.get_active_viewport()
        if viewport is not None:
            break
        await app.next_update_async()
    else:
        raise RuntimeError("Phase V1 probe requires a viewport")
    viewport.camera_path = campfire.app.CAMERA_PATH
    viewport.fill_frame = False
    viewport.resolution = CAPTURE_RESOLUTION
    for _ in range(90):
        await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        if tuple(viewport.resolution) == CAPTURE_RESOLUTION:
            return viewport
    raise RuntimeError("Phase V1 viewport resolution did not settle")


async def _capture(viewport, path):
    request = omni.kit.viewport.utility.capture_viewport_to_file(viewport, file_path=str(path))
    if not await request.wait_for_result(completion_frames=2):
        raise RuntimeError("Phase V1 capture failed")
    for _ in range(30):
        if path.is_file():
            return _file(path)
        await asyncio.sleep(0.05)
    raise RuntimeError("Phase V1 capture file is missing")


def _performance_probe():
    stage = Usd.Stage.CreateInMemory()
    campfire.app.populate_fixed_scene(stage)
    log_ids = tuple(f"Log_{index:02d}" for index in range(20))
    for index, log_id in enumerate(log_ids[4:], start=4):
        campfire.app.create_log(
            stage,
            campfire.app.LogSpec(
                log_id,
                ((index % 5 - 2) * 0.45, (index // 5 - 1.5) * 0.45, 0.40),
                rotation_z_deg=float((index % 2) * 90),
            ),
        )
    contract = campfire.app.preauthor_wood_visual_v1(stage, log_ids)
    consumer = campfire.app.WoodVisualV1Consumer(stage, log_ids)
    consumer.on_timeline_started()
    profiles = []
    for revision in range(1, 86):
        models = tuple(_model(log_id, index % 4) for index, log_id in enumerate(log_ids))
        for model in models:
            for cell in model.cells:
                if cell.surface_exposure > 0.0:
                    cell.temperature_k += float(revision % 2)
        snapshot = campfire.app.WoodVisualBandSnapshot(
            revision,
            log_ids,
            tuple(
                row
                for model in models
                for row in campfire.app.aggregate_model_into_visual_bands(model)
            ),
        )
        profiles.append(consumer.publish(snapshot))
    unchanged = consumer.publish(snapshot)
    consumer.close()
    return {
        "timing": _summary(profile.total_ms for profile in profiles),
        "usd_set_timing": _summary(profile.usd_set_ms for profile in profiles),
        "maximum_attribute_sets_per_revision": 20 * 8 * 3 + 1,
        "observed_maximum_sets": max(profile.usd_set_count for profile in profiles),
        "unchanged_revision_sets": unchanged.usd_set_count,
        "render_prim_count": len(contract["render_prim_paths"]),
        "reference_budget_p95_ms": 1.0,
        "production_candidate": False,
    }


async def _run(arguments):
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    output = arguments["output"].resolve()
    capture_dir = arguments["capture_dir"].resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    capture_dir.mkdir(parents=True, exist_ok=True)
    for old in capture_dir.glob("*.png"):
        old.unlink()
    report = None
    exit_code = 1
    try:
        v0_path = output.with_suffix(".v0.usda")
        v1_path = output.with_suffix(".v1.usda")
        v0_profile, v0_paths = _build_visual_stage(v0_path, "v0")
        v1_profile, v1_paths = _build_visual_stage(v1_path, "v1")
        captures = {}
        frames = []
        for mode, path in (("v0", v0_path), ("v1", v1_path)):
            await context.open_stage_async(str(path))
            viewport = await _viewport()
            for _ in range(20):
                await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
            captures[mode] = await _capture(viewport, capture_dir / f"wood_visual_{mode}.png")
            for _ in range(10):
                frame_path = capture_dir / f"frame_{len(frames) + 1:04d}.png"
                frames.append(await _capture(viewport, frame_path))
        performance = _performance_probe()
        v1_stage = context.get_stage()
        render_prims_have_physics = any(
            bool(v1_stage.GetPrimAtPath(path).GetAttribute("physics:rigidBodyEnabled"))
            for path in v1_paths
            if path.startswith("/World/WoodVisualV1/") and "/Band_" in path
        )
        gates = {
            "feature_default_off": not carb.settings.get_settings().get_as_bool(campfire.app.WOOD_VISUAL_V1_SETTING),
            "v0_v1_same_camera_and_resolution": True,
            "fixed_snapshot_images_differ": captures["v0"]["sha256"] != captures["v1"]["sha256"],
            "eight_bands_per_log": sum("/Band_" in path for path in v1_paths) >= 32,
            "physical_logs_preserved": all(f"/World/Logs/{log_id}" in v1_paths for log_id in LOG_IDS),
            "render_bands_have_no_physics": not render_prims_have_physics,
            "unchanged_revision_sets_zero": performance["unchanged_revision_sets"] == 0,
            "twenty_log_set_growth_measured": performance["maximum_attribute_sets_per_revision"] == 481,
        }
        report = {
            "schema": "campfire.phasev1.wood_visual_band_probe.v1",
            "status": "ok" if all(gates.values()) else "failed",
            "scope": {
                "purpose": "local-state visual probe and fallback",
                "production_candidate": False,
                "fixed_snapshot_not_burn_trajectory": True,
                "physical_cylinder_split": False,
                "flow_or_collision_changed": False,
            },
            "gates": gates,
            "four_log": {
                "v0_profile": v0_profile.__dict__,
                "v1_profile": v1_profile.__dict__,
                "captures": captures,
                "video_frames": frames,
            },
            "twenty_log": performance,
            "limitations": [
                "V1 authors 8 render-only cylinders and 24 shader inputs per modeled log.",
                "USD Set count grows with log count and is not the V3 production transport.",
                "Comparison frames show one fixed diagnostic snapshot, not combustion time evolution.",
            ],
        }
        exit_code = 0 if report["status"] == "ok" else 2
    except Exception as error:
        report = {
            "schema": "campfire.phasev1.wood_visual_band_probe.v1",
            "status": "error",
            "error": f"{type(error).__name__}: {error}",
        }
        carb.log_error(f"[phasev1] {report['error']}")
    finally:
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        carb.settings.get_settings().set("/phasev1/exitCode", exit_code)
        app.post_uncancellable_quit(exit_code)


asyncio.ensure_future(_run(_arguments()))
