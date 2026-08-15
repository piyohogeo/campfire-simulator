"""Derive the readback-free Phase 6HT ON/OFF probe from Phase 6HS."""

from __future__ import annotations

from pathlib import Path

from phase6hs_probe_source import build_probe_source as build_phase6hs_source


def build_probe_source(source_path: Path) -> str:
    source = build_phase6hs_source(source_path)
    replacements = (
        (
            "from pxr import Gf, Usd, UsdGeom, UsdPhysics",
            "from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics",
        ),
        (
            "SEGMENTS = 12",
            '''SEGMENTS = 12
EMITTER_CENTER = (0.0, -0.42, 0.0)
CAMERA_PATH = Sdf.Path("/World/Cameras/FlowOcclusion")
CAMERA_EYE = (0.0, -4.2, 1.2)
CAMERA_TARGET = (0.0, -0.42, 0.58)
CAPTURE_RESOLUTION = (960, 540)
SIMULATION_UPDATES = 240
ACTIVE_BLOCK_FRAMES = (60, 120, 180, 240)''',
        ),
        (
            "def _build(path: Path, add_proxy: bool) -> tuple[Usd.Stage, dict]:",
            "def _build(path: Path, add_proxy: bool, collision_enabled: bool) -> tuple[Usd.Stage, dict]:",
        ),
        (
            "    campfire.app.populate_phase2_scene(stage, render_hierarchy=True)\n    geometry = None",
            '''    campfire.app.populate_phase2_scene(stage, render_hierarchy=True)
    known_good.EMITTER_CENTER = EMITTER_CENTER
    known_good._define_flow(stage, collision_enabled)
    UsdGeom.Xform.Define(stage, "/World/Cameras")
    known_good._define_camera(stage, CAMERA_PATH, CAMERA_EYE, CAMERA_TARGET)
    stage.SetStartTimeCode(0.0)
    stage.SetEndTimeCode(float(SIMULATION_UPDATES))
    stage.SetTimeCodesPerSecond(60.0)
    geometry = None''',
        ),
        (
            '    attempt_id = settings.get_as_string("/phase6hs/attemptId")',
            '    attempt_id = settings.get_as_string("/phase6hs/attemptId")\n    condition = settings.get_as_string("/phase6ht/condition")\n    collision_enabled = condition == "collision_on"\n    if condition not in ("collision_on", "collision_off"):\n        raise RuntimeError("Phase 6HT condition invalid")',
        ),
        (
            '        "flow_interface_calls": 0,',
            '        "flow_interface_calls": 0,\n        "diagnostic_phase": "phase6ht",\n        "condition": condition,\n        "collision_enabled": collision_enabled,\n        "capture_calls": 0,',
        ),
        (
            '        baseline, baseline_info = _build(stage_dir / "baseline.usda", False)\n        candidate, candidate_info = _build(stage_dir / "candidate.usda", True)',
            '        baseline, baseline_info = _build(stage_dir / "baseline.usda", False, collision_enabled)\n        candidate, candidate_info = _build(stage_dir / "candidate.usda", True, collision_enabled)',
        ),
        (
            '''        for index in range(30):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
            if index in (0, 29):
                mark("renderer_update", index=index + 1)
        flow = _flowusd.acquire_flowusd_interface()
        report["flow_interface_calls"] += 1
        held["flow"] = flow
        report["runtime"] = {
            "renderer_updates": 30,
            "timeline_playing": bool(timeline.is_playing()),
            "active_blocks_stopped": int(flow.get_active_block_count()),
            "flow_identity": id(flow),
            "stage_identity": id(held["stage"]),
            "viewport_identity": id(viewport),
        }
        if timeline.is_playing():
            raise RuntimeError("Phase 6HS timeline must remain stopped")
        mark("operation_complete", active_blocks=report["runtime"]["active_blocks_stopped"])
        report["status"] = "operation_pass"
        exit_code = 0''',
            '''        viewport.camera_path = CAMERA_PATH
        viewport.resolution = CAPTURE_RESOLUTION
        for _ in range(30):
            await app.next_update_async()
            if tuple(viewport.resolution) == CAPTURE_RESOLUTION:
                break
        if tuple(viewport.resolution) != CAPTURE_RESOLUTION:
            raise RuntimeError("Phase 6HT viewport resolution did not settle")
        flow = _flowusd.acquire_flowusd_interface()
        report["flow_interface_calls"] += 1
        held["flow"] = flow
        timeline.stop()
        timeline.set_current_time(0.0)
        for _ in range(12):
            await app.next_update_async()
        captures = output.parent / "captures"
        captures.mkdir(parents=True, exist_ok=False)
        baseline_capture = await known_good._capture(viewport, captures / "baseline.png")
        report["capture_calls"] += 1
        mark("baseline_capture_complete", capture_bytes=baseline_capture["bytes"])
        timeline.play()
        report["timeline_play_calls"] += 1
        active_blocks = []
        for frame in range(1, SIMULATION_UPDATES + 1):
            await app.next_update_async()
            if frame in ACTIVE_BLOCK_FRAMES:
                blocks = int(flow.get_active_block_count())
                active_blocks.append({"frame": frame, "active_blocks": blocks})
                mark("active_block_sample", frame=frame, active_blocks=blocks)
        timeline.stop()
        for index in range(8):
            await app.next_update_async()
            if index in (0, 7):
                mark("post_simulation_drain", index=index + 1)
        final_capture = await known_good._capture(viewport, captures / "final.png")
        report["capture_calls"] += 1
        mark("final_capture_complete", capture_bytes=final_capture["bytes"])
        report["runtime"] = {
            "simulation_updates": SIMULATION_UPDATES,
            "preplay_updates": 12,
            "renderer_drain_updates": 8,
            "timeline_playing_during_simulation": True,
            "timeline_playing_at_operation_complete": bool(timeline.is_playing()),
            "active_blocks": active_blocks,
            "flow_identity": id(flow),
            "stage_identity": id(held["stage"]),
            "viewport_identity": id(viewport),
            "captures": {"baseline": baseline_capture, "final": final_capture},
            "camera_path": str(CAMERA_PATH),
            "resolution": list(CAPTURE_RESOLUTION),
            "source_center_m": list(EMITTER_CENTER),
        }
        if timeline.is_playing():
            raise RuntimeError("Phase 6HT timeline must be stopped before operation completion")
        if len(active_blocks) != len(ACTIVE_BLOCK_FRAMES):
            raise RuntimeError("Phase 6HT active block sample count mismatch")
        mark("operation_complete", active_blocks=active_blocks[-1]["active_blocks"], condition=condition)
        report["status"] = "operation_pass"
        exit_code = 0''',
        ),
    )
    for before, after in replacements:
        if source.count(before) != 1:
            raise RuntimeError("Phase 6HT probe replacement cardinality mismatch")
        source = source.replace(before, after)
    return source
