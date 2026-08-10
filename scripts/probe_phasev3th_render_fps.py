"""Phase V3T-H visible-viewport FPS probe without an additional render path."""

from __future__ import annotations

import asyncio
import ctypes
import json
import time
from pathlib import Path

import carb
import numpy as np
import omni.kit.app
import omni.kit.viewport.utility
import omni.timeline
import omni.usd
from pxr import Gf, Usd, UsdGeom


RESOLUTION = (1280, 720)
MAX_READS = 40000
MAX_PUBLICATIONS = 2000


def _args():
    settings = carb.settings.get_settings()
    return {
        "output": Path(settings.get_as_string("/phasev3th/output")).resolve(),
        "condition": settings.get_as_string("/phasev3th/condition"),
        "read_mode": settings.get_as_string("/phasev3th/readMode"),
        "warmup_seconds": settings.get_as_float("/phasev3th/warmupSeconds"),
        "measure_seconds": settings.get_as_float("/phasev3th/measureSeconds"),
        "run": settings.get_as_int("/phasev3th/run"),
        "native_library": Path(settings.get_as_string("/phasev3th/nativeLibrary")).resolve(),
    }


def _build_stage(path, flow_enabled):
    path.unlink(missing_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    import campfire.app
    from campfire.app.flow_scene import populate_flow_scene

    populate_flow_scene(stage)
    stage.RemovePrim("/World/Logs")
    UsdGeom.Xform.Define(stage, "/World/Logs")
    for slot in range(20):
        row, column = divmod(slot, 5)
        campfire.app.create_log(
            stage,
            campfire.app.LogSpec(
                f"Log_{slot:02d}", ((column - 2) * 1.15, (row - 1.5) * 1.05, 0.42),
                0.0 if row % 2 == 0 else 90.0, 0.22, 0.92,
            ),
            render_hierarchy=True,
            render_log_slot=slot,
        )
    log_ids = tuple(campfire.app.list_log_ids(stage))
    visual_contract = campfire.app.preauthor_wood_visual_v3(stage, log_ids)
    if not flow_enabled:
        emitter = stage.GetPrimAtPath("/World/Flow/Emitter")
        if emitter and emitter.GetAttribute("enabled"):
            emitter.GetAttribute("enabled").Set(False)
    camera = UsdGeom.Camera.Get(stage, "/World/Camera")
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(Gf.Vec3d(7.8, -7.8, 5.8), Gf.Vec3d(0.0, 0.0, 1.15), Gf.Vec3d(0, 0, 1))
    camera.GetPrim().GetAttribute("xformOp:transform").Set(view.GetInverse())
    stage.SetEndTimeCode(1000000.0)
    if not stage.GetRootLayer().Save():
        raise RuntimeError("unable to save Phase V3T-H stage")
    return log_ids, visual_contract, [str(prim.GetPath()) for prim in stage.Traverse()]


def _payload_factory(log_ids):
    from campfire.app.wood_visual_surface import ImmutableWoodVisualSurfacePayload

    points_per_log = 360
    count = len(log_ids) * points_per_log
    indices = np.tile(np.arange(points_per_log, dtype=np.uint32), len(log_ids)).tobytes()
    x = np.arange(count, dtype=np.float32)
    states = []
    for state in (0, 1):
        states.append((
            (680.0 + state * 360.0 + (x % 37.0) * 2.0).astype(np.float32).tobytes(),
            (0.004 + state * 0.018 + (x % 11.0) * 0.0002).astype(np.float32).tobytes(),
            (0.003 + state * 0.010 + (x % 13.0) * 0.0001).astype(np.float32).tobytes(),
            (0.0002 + state * 0.0008 + (x % 7.0) * 0.00002).astype(np.float32).tobytes(),
        ))

    def make(revision):
        temperature, moisture, char, ash = states[revision & 1]
        return ImmutableWoodVisualSurfacePayload(
            revision, revision, tuple(log_ids), points_per_log, indices,
            temperature, moisture, char, ash,
        )

    return make


def _frame_snapshot(viewport):
    info = viewport.frame_info
    return {
        "fps": float(info.get("fps", 0.0)),
        "frame_number": int(info.get("frame_number", -1)),
        "swh_frame_number": int(info.get("swh_frame_number", -1)),
        "subframe_count": int(info.get("subframe_count", 1)),
        "status": int(info.get("status", -1)),
        "resolution": list(info.get("resolution", ())),
    }


async def _run_period(app, timeline, viewport, duration, read_enabled, consumer, payload_factory, revision_start):
    read_times = np.empty(MAX_READS, dtype=np.int64)
    fps_values = np.empty(MAX_READS, dtype=np.float64)
    frame_numbers = np.empty(MAX_READS, dtype=np.int64)
    swh_frame_numbers = np.empty(MAX_READS, dtype=np.int64)
    publication_starts = np.empty(MAX_PUBLICATIONS, dtype=np.int64)
    publication_ends = np.empty(MAX_PUBLICATIONS, dtype=np.int64)
    publication_profiles = []
    read_count = 0
    read_overflow = 0
    update_count = 0
    publication_count = 0
    revision = revision_start
    initial = _frame_snapshot(viewport)
    started_wall_ns = time.time_ns()
    started = time.perf_counter_ns()
    deadline = started + int(duration * 1e9)
    next_publication = started
    while time.perf_counter_ns() < deadline:
        await app.next_update_async()
        update_count += 1
        now = time.perf_counter_ns()
        if read_enabled:
            if read_count >= MAX_READS:
                read_overflow += 1
            else:
                info = viewport.frame_info
                read_times[read_count] = now
                fps_values[read_count] = float(info.get("fps", 0.0))
                frame_numbers[read_count] = int(info.get("frame_number", -1))
                swh_frame_numbers[read_count] = int(info.get("swh_frame_number", -1))
                read_count += 1
        if consumer is not None and now >= next_publication:
            revision += 1
            begin = time.perf_counter_ns()
            profile = consumer.publish(payload_factory(revision))
            end = time.perf_counter_ns()
            if publication_count < MAX_PUBLICATIONS:
                publication_starts[publication_count] = begin
                publication_ends[publication_count] = end
                publication_profiles.append({
                    "revision": profile.revision,
                    "status": profile.status,
                    "total_ms": profile.total_ms,
                    "beauty_pack_ms": profile.beauty_pack_ms,
                    "cpu_provider_setter_ms": profile.cpu_upload_ms,
                    "revision_commit_ms": profile.revision_commit_ms,
                    "upload_count": profile.upload_count,
                })
                publication_count += 1
            next_publication += 200_000_000
            if next_publication < now - 200_000_000:
                next_publication = now + 200_000_000
    ended = time.perf_counter_ns()
    ended_wall_ns = time.time_ns()
    final = _frame_snapshot(viewport)
    return {
        "started_ns": started,
        "ended_ns": ended,
        "started_wall_ns": started_wall_ns,
        "ended_wall_ns": ended_wall_ns,
        "wall_seconds": (ended - started) / 1e9,
        "kit_update_count": update_count,
        "read_timestamps_ns": read_times[:read_count].tolist(),
        "hud_fps_values": fps_values[:read_count].tolist(),
        "frame_numbers": frame_numbers[:read_count].tolist(),
        "swh_frame_numbers": swh_frame_numbers[:read_count].tolist(),
        "read_overflow": read_overflow,
        "initial_frame_info": initial,
        "final_frame_info": final,
        "publication_starts_ns": publication_starts[:publication_count].tolist(),
        "publication_ends_ns": publication_ends[:publication_count].tolist(),
        "publication_profiles": publication_profiles,
        "revision_end": revision,
        "timeline_seconds_end": float(timeline.get_current_time()),
    }


async def _run(arguments):
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    report = {"schema": "campfire.phasev3th.visible-viewport-process.v2", "status": "error"}
    consumer = None
    try:
        if arguments["condition"] not in ("flow_off_v3_off", "flow_on_v3_off", "flow_on_v3_cpu"):
            raise ValueError("invalid condition")
        if arguments["read_mode"] not in ("on", "off"):
            raise ValueError("invalid read mode")
        flow_enabled = arguments["condition"] != "flow_off_v3_off"
        v3_enabled = arguments["condition"] == "flow_on_v3_cpu"
        stage_path = arguments["output"].with_suffix(".usda")
        log_ids, visual_contract, prim_paths = _build_stage(stage_path, flow_enabled)
        await context.open_stage_async(str(stage_path))
        viewport = None
        for _ in range(240):
            viewport = omni.kit.viewport.utility.get_active_viewport()
            if viewport is not None:
                break
            await app.next_update_async()
        if viewport is None:
            raise RuntimeError("active viewport unavailable")
        viewport.camera_path = "/World/Camera"
        viewport.fill_frame = False
        viewport.resolution = RESOLUTION
        payload_factory = _payload_factory(log_ids)
        if v3_enabled:
            from campfire.app.wood_visual_v3 import WoodVisualV3Consumer

            library = ctypes.CDLL(str(arguments["native_library"]))
            consumer = WoodVisualV3Consumer(context.get_stage(), log_ids, native_library=library)
            consumer.on_timeline_started()
        import omni.flowusd._flowusd as _flowusd

        flow_interface = _flowusd.acquire_flowusd_interface()
        timeline.set_current_time(0.0)
        timeline.play()
        warmup = await _run_period(
            app, timeline, viewport, arguments["warmup_seconds"], False,
            consumer, payload_factory, 0,
        )
        timeline_start = float(timeline.get_current_time())
        measured = await _run_period(
            app, timeline, viewport, arguments["measure_seconds"],
            arguments["read_mode"] == "on", consumer, payload_factory, warmup["revision_end"],
        )
        report = {
            "schema": "campfire.phasev3th.visible-viewport-process.v2",
            "status": "ok",
            "condition": arguments["condition"],
            "run": arguments["run"] + 1,
            "read_mode": arguments["read_mode"],
            "kit": "110.2",
            "flow": "110.0.0",
            "resolution": list(RESOLUTION),
            "log_count": 20,
            "v3_cadence_hz": 5.0 if v3_enabled else 0.0,
            "metric_contract": {
                "average_fps": "visible ViewportAPI.frame_info frame_number delta divided by measurement wall time",
                "hud_fps": "public ViewportAPI.fps/frame_info['fps']; exact source used by the bundled upper-right FPS HUD",
                "hud_frame_time": "HUD derives 1000 / rounded FPS; it is not a raw per-frame duration",
                "raw_visible_frame_timestamp_available": False,
                "frame_pacing_percentiles_measured": False,
                "additional_render_product_created": False,
                "omni_stats_match": False,
            },
            "warmup": {"wall_seconds": warmup["wall_seconds"], "timeline_seconds_end": warmup["timeline_seconds_end"]},
            "measurement": {**measured, "timeline_seconds_start": timeline_start, "flow_active_blocks_final": int(flow_interface.get_active_block_count())},
            "stage": {
                "prim_count": len(prim_paths),
                "prim_paths_sha256": __import__("hashlib").sha256("\n".join(prim_paths).encode()).hexdigest(),
                "visual_contract": visual_contract,
                "topology_changed_during_measurement": False,
            },
            "consumer_status": consumer.status() if consumer is not None else None,
            "gpu_condition_skipped": True,
            "gpu_skip_reason": "Phase V3T-G did not establish the required repeated final lifecycle safety gate.",
            "production_changed": False,
        }
    except Exception as error:
        report = {
            "schema": "campfire.phasev3th.visible-viewport-process.v2",
            "status": "error",
            "error": f"{type(error).__name__}: {error}",
            "condition": arguments.get("condition"),
        }
    finally:
        timeline.stop()
        if consumer is not None:
            consumer.close()
        arguments["output"].parent.mkdir(parents=True, exist_ok=True)
        arguments["output"].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        app.post_uncancellable_quit(0 if report["status"] == "ok" else 1)


asyncio.ensure_future(_run(_args()))
