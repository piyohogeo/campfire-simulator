"""Kit 110 material/capture probe for the default-off wood visual V0."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import statistics
import time
from pathlib import Path

import carb
import omni.kit.app
import omni.kit.viewport.utility
import omni.usd
from pxr import Usd, UsdShade

import campfire.app


CAPTURE_RESOLUTION = (1280, 720)
LOG_IDS = ("Log_00", "Log_01", "Log_02", "Log_03")


def _settings():
    settings = carb.settings.get_settings()
    return {
        "output": Path(settings.get_as_string("/phasev0/output")),
        "capture_dir": Path(settings.get_as_string("/phasev0/captureDir")),
    }


def _row(temperature, moisture, dry, char, ash):
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


def _rows(frame=19, *, performance=False):
    amount = frame / 19.0
    variation = (frame % 2) * 0.02 if performance else 0.0
    return (
        _row(420.0 + 80.0 * amount, 0.05 + variation, 1.0, 0.0, 0.0),
        _row(420.0 + 80.0 * amount, 0.60 - variation, 1.0, 0.0, 0.0),
        _row(720.0 + 300.0 * amount, 0.0, 0.25 - variation, 0.75 + variation, 0.0),
        _row(820.0 + 300.0 * amount, 0.0, 0.05, 0.10 + variation, 0.85 - variation),
    )


def _snapshot(revision, frame=19, *, performance=False):
    return campfire.app.ResidentPublishedSnapshot(
        revision=revision,
        tick=revision,
        log_ids=LOG_IDS,
        rows=_rows(frame, performance=performance),
    )


def _build_stage(path, *, enabled):
    path.unlink(missing_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    campfire.app.populate_phase3_scene(stage)
    if enabled:
        contract = campfire.app.preauthor_wood_visual_v0(stage, LOG_IDS)
    else:
        contract = None
    if not stage.GetRootLayer().Save():
        raise RuntimeError(f"Unable to save wood visual probe stage: {path}")
    return contract


def _summary(values, warmup=0):
    measured = list(values[warmup:])
    ordered = sorted(measured)
    return {
        "samples": len(measured),
        "mean_ms": statistics.fmean(measured),
        "p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        "maximum_ms": max(measured),
    }


def _file(path):
    payload = path.read_bytes()
    return {
        "path": str(path),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


async def _capture(viewport, path):
    request = omni.kit.viewport.utility.capture_viewport_to_file(
        viewport, file_path=str(path)
    )
    if not await request.wait_for_result(completion_frames=2):
        raise RuntimeError(f"Wood visual capture failed: {path}")
    for _ in range(30):
        if path.is_file():
            return _file(path)
        await asyncio.sleep(0.05)
    raise RuntimeError(f"Wood visual capture is missing: {path}")


async def _viewport():
    app = omni.kit.app.get_app()
    viewport = None
    for _ in range(120):
        viewport = omni.kit.viewport.utility.get_active_viewport()
        if viewport is not None:
            break
        await app.next_update_async()
    if viewport is None:
        raise RuntimeError("Wood visual probe requires an active viewport")
    viewport.camera_path = campfire.app.CAMERA_PATH
    viewport.fill_frame = False
    viewport.resolution = CAPTURE_RESOLUTION
    for _ in range(90):
        await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        if tuple(viewport.resolution) == CAPTURE_RESOLUTION:
            break
    if tuple(viewport.resolution) != CAPTURE_RESOLUTION:
        raise RuntimeError(f"Viewport resolution did not settle: {viewport.resolution}")
    return viewport


async def _open(context, path):
    await context.open_stage_async(str(path))
    stage = context.get_stage()
    if stage is None:
        raise RuntimeError(f"Wood visual stage did not open: {path}")
    return stage


async def _run(arguments):
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    output = arguments["output"].resolve()
    capture_dir = arguments["capture_dir"].resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    capture_dir.mkdir(parents=True, exist_ok=True)
    for old in capture_dir.glob("*.png"):
        old.unlink()
    off_path = output.with_suffix(".off.usda")
    on_path = output.with_suffix(".on.usda")
    exit_code = 1
    report = None
    consumer = None
    try:
        off_contract = _build_stage(off_path, enabled=False)
        on_contract = _build_stage(on_path, enabled=True)
        stage = await _open(context, off_path)
        viewport = await _viewport()
        off_paths = {str(prim.GetPath()) for prim in stage.Traverse()}
        off_frame_times = []
        for _ in range(35):
            started = time.perf_counter()
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
            off_frame_times.append((time.perf_counter() - started) * 1000.0)
        off_capture = await _capture(viewport, capture_dir / "wood_visual_off.png")

        stage = await _open(context, on_path)
        viewport = await _viewport()
        paths_before = {str(prim.GetPath()) for prim in stage.Traverse()}
        consumer = campfire.app.WoodVisualV0Consumer(
            stage, LOG_IDS, track_notices=True
        )
        consumer.on_timeline_started()
        initial = consumer.publish(_snapshot(1, 0))
        repeated = consumer.publish(_snapshot(1, 0))
        on_frame_times = []
        performance_profiles = []
        for index in range(2, 82):
            performance_profiles.append(
                consumer.publish(
                    _snapshot(index, (index - 2) % 20, performance=True)
                )
            )
            started = time.perf_counter()
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
            on_frame_times.append((time.perf_counter() - started) * 1000.0)

        final_revision = 100
        consumer.publish(_snapshot(final_revision, 19))
        on_capture = await _capture(viewport, capture_dir / "wood_visual_on.png")
        video_frames = []
        for frame in range(20):
            revision = final_revision + frame + 1
            consumer.publish(_snapshot(revision, frame))
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
            video_frames.append(
                await _capture(
                    viewport, capture_dir / f"frame_{frame + 1:04d}.png"
                )
            )

        paths_after = {str(prim.GetPath()) for prim in stage.Traverse()}
        material_contract = {}
        uniform_records = {}
        finite_and_bounded = True
        for log_id, row in zip(LOG_IDS, _rows()):
            log = stage.GetPrimAtPath(f"/World/Logs/{log_id}")
            shader = UsdShade.Shader.Get(
                stage, f"/World/Looks/WoodVisualV0/{log_id}/Shader"
            )
            material, _ = UsdShade.MaterialBindingAPI(log).ComputeBoundMaterial()
            uniform = campfire.app.wood_visual_uniform_from_row(row)
            values = (
                *uniform.base_color,
                uniform.roughness,
                *uniform.emission_color,
                uniform.moisture_fraction,
                uniform.char_fraction,
                uniform.ash_fraction,
            )
            finite_and_bounded = finite_and_bounded and all(
                math.isfinite(value) for value in values
            )
            uniform_records[log_id] = {
                "base_color": list(uniform.base_color),
                "roughness": uniform.roughness,
                "emission_color": list(uniform.emission_color),
                "moisture_fraction": uniform.moisture_fraction,
                "char_fraction": uniform.char_fraction,
                "ash_fraction": uniform.ash_fraction,
            }
            material_contract[log_id] = {
                "bound_material": str(material.GetPath()) if material else None,
                "physics_binding_preserved": bool(
                    log.GetRelationship("material:binding:physics")
                ),
                "inputs": {
                    name: bool(shader.GetInput(name))
                    for name in campfire.app.WOOD_VISUAL_V0_INPUT_NAMES
                },
            }

        display_color = stage.GetPrimAtPath(
            "/World/Logs/Log_00"
        ).GetAttribute("primvars:displayColor")
        publication_ms = [profile.total_ms for profile in performance_profiles]
        set_ms = [profile.usd_set_ms for profile in performance_profiles]
        distinct_colors = len(
            {tuple(record["base_color"]) for record in uniform_records.values()}
        ) == len(LOG_IDS)
        gates = {
            "feature_default_off": not carb.settings.get_settings().get_as_bool(
                campfire.app.WOOD_VISUAL_V0_SETTING
            ),
            "off_stage_has_no_v0_contract": off_contract is None,
            "display_color_available": bool(display_color),
            "display_color_has_no_roughness_or_emission": not bool(
                stage.GetPrimAtPath("/World/Logs/Log_00").GetAttribute("roughness")
            )
            and not bool(
                stage.GetPrimAtPath("/World/Logs/Log_00").GetAttribute(
                    "emissiveColor"
                )
            ),
            "preview_surface_inputs_available": all(
                all(item["inputs"].values()) for item in material_contract.values()
            ),
            "render_material_bound": all(
                item["bound_material"]
                == f"/World/Looks/WoodVisualV0/{log_id}"
                for log_id, item in material_contract.items()
            ),
            "physics_binding_preserved": all(
                item["physics_binding_preserved"]
                for item in material_contract.values()
            ),
            "offline_preauthor_complete": on_contract["log_ids"] == list(LOG_IDS),
            "finite_visual_values": finite_and_bounded,
            "four_log_colors_distinct": distinct_colors,
            "unchanged_revision_skips_all_sets": repeated.usd_set_count == 0,
            "no_live_prim_creation": paths_before == paths_after,
            "off_on_images_differ": off_capture["sha256"] != on_capture["sha256"],
        }
        report = {
            "schema": "campfire.phasev0.wood_visual_probe.v1",
            "status": "ok" if all(gates.values()) else "failed",
            "kit_flow_version": "110.0.0",
            "selection": {
                "display_color": "insufficient: base color only",
                "selected": "pre-authored UsdPreviewSurface per log",
                "live_prim_redefinition": False,
            },
            "gates": gates,
            "off_stage_prim_count": len(off_paths),
            "on_stage_prim_count": len(paths_after),
            "material_contract": material_contract,
            "uniforms": uniform_records,
            "publication": {
                "initial": initial.__dict__,
                "unchanged_revision": repeated.__dict__,
                "timing": _summary(publication_ms, 5),
                "usd_set_timing": _summary(set_ms, 5),
                "set_count": sum(
                    profile.usd_set_count for profile in performance_profiles
                ),
                "notice_count": sum(
                    profile.notice_count for profile in performance_profiles
                ),
                "consumer_status": consumer.status(),
                "reference_budget_p95_ms": 1.0,
                "reference_budget_met": (
                    _summary(publication_ms, 5)["p95_ms"] <= 1.0
                ),
            },
            "frame_timing": {
                "off": _summary(off_frame_times, 5),
                "on": _summary(on_frame_times, 5),
            },
            "captures": {
                "off": off_capture,
                "on": on_capture,
                "video_frames": video_frames,
                "resolution": list(CAPTURE_RESOLUTION),
                "camera": str(campfire.app.CAMERA_PATH),
            },
        }
        exit_code = 0 if report["status"] == "ok" else 2
    except Exception as error:
        report = {
            "schema": "campfire.phasev0.wood_visual_probe.v1",
            "status": "error",
            "error": f"{type(error).__name__}: {error}",
        }
        carb.log_error(f"[phasev0] {report['error']}")
    finally:
        if consumer is not None:
            try:
                consumer.on_timeline_stopped()
                consumer.close()
            except Exception:
                pass
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        carb.settings.get_settings().set("/phasev0/exitCode", exit_code)
        app.post_uncancellable_quit(exit_code)


asyncio.ensure_future(_run(_settings()))
