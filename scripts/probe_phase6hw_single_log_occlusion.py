"""Run one readback-free Phase 6HW end-on diagnostic Flow process."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).absolute().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import carb
import omni.kit.app
import omni.kit.viewport.utility
import omni.timeline
import omni.usd
from omni.flowusd import _flowusd
from pxr import Sdf

import probe_phase6ds_flow_collision as known_good
from phase6hu_atomic_report import atomic_write_json
from phase6hu_runtime_report import DurableOperationReporter
from phase6hw_stage_contract import validate_stage


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _run() -> None:
    settings = carb.settings.get_settings()
    output = Path(settings.get_as_string("/phase6hs/output")).resolve()
    markers = Path(settings.get_as_string("/phase6hs/markers")).resolve()
    attempt_id = settings.get_as_string("/phase6hs/attemptId")
    condition = settings.get_as_string("/phase6hw/condition")
    stage_path = Path(settings.get_as_string("/phase6hw/stage")).resolve()
    contract_path = Path(settings.get_as_string("/phase6hw/contract")).resolve()
    if condition not in ("collision_off", "collision_on"):
        raise RuntimeError("Phase 6HW condition invalid")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    scene = contract["fixed_scene"]
    report = {
        "schema": "campfire.phase6hw.single-log-end-on-run.v1",
        "phase": "phase6hw",
        "status": "running",
        "attempt_id": attempt_id,
        "condition": condition,
        "collision_enabled": condition == "collision_on",
        "timestamp_utc": _utc(),
        "readback_calls": 0,
        "timeline_play_calls": 0,
        "flow_interface_calls": 0,
        "capture_calls": 0,
        "production_code_changed": False,
        "latest_demo_changed": False,
        "lifecycle": {},
    }
    atomic_markers = output.parent / "atomic_report_markers.jsonl"
    reporter = DurableOperationReporter(output, markers, atomic_markers, report, attempt_id)
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    held: dict[str, object] = {}
    flow = None
    exit_code = 1

    def mark(name: str, **values) -> None:
        reporter.mark(name, **values)

    try:
        mark("contract_started", condition=condition)
        stage_contract = validate_stage(stage_path, contract, condition)
        report["stage_contract"] = stage_contract
        mark("stage_contract_complete", passed=stage_contract["passed"], stage_sha256=stage_contract["evidence"]["stage_sha256"], settings_sha256=stage_contract["evidence"]["settings_sha256"])
        if not stage_contract["passed"]:
            raise RuntimeError(f"Phase 6HW stage contract failed: {stage_contract['gates']}")
        await context.open_stage_async(str(stage_path))
        held["stage"] = context.get_stage()
        if held["stage"] is None:
            raise RuntimeError("Phase 6HW stage did not open")
        mark("stage_open_complete", stage_identity=id(held["stage"]))
        viewport = None
        for _ in range(120):
            viewport = omni.kit.viewport.utility.get_active_viewport()
            if viewport is not None:
                break
            await app.next_update_async()
        if viewport is None:
            raise RuntimeError("Phase 6HW active viewport unavailable")
        held["viewport"] = viewport
        viewport.camera_path = Sdf.Path(scene["camera_path"])
        viewport.resolution = tuple(scene["capture_resolution"])
        for _ in range(30):
            await app.next_update_async()
            if tuple(viewport.resolution) == tuple(scene["capture_resolution"]):
                break
        if tuple(viewport.resolution) != tuple(scene["capture_resolution"]):
            raise RuntimeError("Phase 6HW viewport resolution did not settle")
        flow = _flowusd.acquire_flowusd_interface()
        report["flow_interface_calls"] += 1
        held["flow"] = flow
        timeline.stop()
        timeline.set_current_time(0.0)
        for _ in range(scene["preplay_updates"]):
            await app.next_update_async()
        captures = output.parent / "captures"
        captures.mkdir(parents=True, exist_ok=False)
        baseline = await known_good._capture(viewport, captures / "flow_only_baseline.png")
        report["capture_calls"] += 1
        mark("baseline_capture_complete", capture_bytes=baseline["bytes"])
        active_blocks = []
        captured = []
        stable_frames = set(scene["stable_capture_frames"])
        active_frames = set(scene["active_block_frames"])
        timeline.play()
        report["timeline_play_calls"] += 1
        for frame in range(1, scene["simulation_updates"] + 1):
            await app.next_update_async()
            if frame in active_frames:
                blocks = int(flow.get_active_block_count())
                active_blocks.append({"frame": frame, "active_blocks": blocks})
                mark("active_block_sample", frame=frame, active_blocks=blocks)
            if frame in stable_frames:
                timeline.stop()
                mark("stable_capture_started", frame=frame)
                capture = await known_good._capture(viewport, captures / f"flow_only_f{frame:04d}.png")
                report["capture_calls"] += 1
                captured.append({"frame": frame, **capture})
                mark("stable_capture_complete", frame=frame, capture_bytes=capture["bytes"])
                if frame != scene["simulation_updates"]:
                    timeline.play()
                    report["timeline_play_calls"] += 1
        timeline.stop()
        for index in range(scene["renderer_drain_updates"]):
            await app.next_update_async()
            if index in (0, scene["renderer_drain_updates"] - 1):
                mark("post_simulation_drain", index=index + 1)
        report["runtime"] = {
            "simulation_updates": scene["simulation_updates"],
            "preplay_updates": scene["preplay_updates"],
            "renderer_drain_updates": scene["renderer_drain_updates"],
            "active_blocks": active_blocks,
            "stable_captures": captured,
            "baseline_capture": baseline,
            "timeline_playing_at_operation_complete": bool(timeline.is_playing()),
            "flow_identity": id(flow),
            "stage_identity": id(held["stage"]),
            "viewport_identity": id(viewport),
            "camera_path": scene["camera_path"],
            "resolution": scene["capture_resolution"],
            "source_center_m": scene["source_center_m"],
            "source_radius_m": scene["source_radius_m"],
            "source_surface_gap_m": scene["source_surface_gap_m"],
            "end_clearance_m": scene["source_to_nearest_end_clearance_m"],
            "display": scene["display"],
        }
        if bool(timeline.is_playing()):
            raise RuntimeError("Phase 6HW timeline still playing")
        if [item["frame"] for item in active_blocks] != scene["active_block_frames"]:
            raise RuntimeError("Phase 6HW active-block sample mismatch")
        if [item["frame"] for item in captured] != scene["stable_capture_frames"]:
            raise RuntimeError("Phase 6HW stable capture mismatch")
        if report["capture_calls"] != 1 + len(scene["stable_capture_frames"]):
            raise RuntimeError("Phase 6HW capture count mismatch")
        mark("operation_complete", condition=condition, active_blocks=active_blocks[-1]["active_blocks"], stable_capture_count=len(captured))
        report["status"] = "operation_pass"
        exit_code = 0
    except Exception as error:
        report["status"] = "error"
        report["error"] = f"{type(error).__name__}: {error}"
        report["traceback"] = traceback.format_exc()
    finally:
        reporter.enter_cleanup()
        try:
            mark("timeline_stop_started")
            timeline.stop()
            mark("timeline_stop_complete")
            for index in range(8):
                await app.next_update_async()
                mark("renderer_drain_update", index=index + 1)
            mark("stage_close_started", held_references=sorted(held))
            await asyncio.wait_for(context.close_stage_async(), timeout=180.0)
            if context.get_stage() is not None:
                raise RuntimeError("USD context still exposes a stage after close")
            mark("stage_close_complete")
            for index in range(scene["post_close_updates"]):
                await app.next_update_async()
                mark("post_close_update", index=index + 1)
            if flow is not None:
                _flowusd.release_flowusd_interface(flow)
                flow = None
            held.clear()
            mark("references_released")
            report["lifecycle"] = {"stage_close_complete": True, "shutdown_complete": True}
            if report["status"] == "operation_pass":
                report["status"] = "qualified"
            mark("shutdown_complete")
        except Exception as shutdown_error:
            report["lifecycle"] = {"stage_close_complete": False, "shutdown_complete": False}
            report["shutdown_error"] = f"{type(shutdown_error).__name__}: {shutdown_error}"
            report["status"] = "error"
            exit_code = 1
            reporter.try_final_write()
        app.post_uncancellable_quit(exit_code)


asyncio.ensure_future(_run())
