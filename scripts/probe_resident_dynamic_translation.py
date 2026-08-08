"""Inject and measure one running log translation in the default-off Point path."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import carb
import numpy as np
import omni.flowusd._flowusd as _flowusd
import omni.kit.app
import omni.timeline
import omni.usd

import campfire.app


CHANNEL_NAMES = ("temperature", "fuel", "burn", "smoke", "velocity", "divergence")
REQUIRED_NONEMPTY_CHANNELS = CHANNEL_NAMES[:-1]
POINTS_PER_LOG = 360
TRIGGER_REVISION = 344


def _write(path: Path, report: dict) -> None:
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _distance(left, right) -> float:
    return math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(left, right)))


def _fields(flow_interface) -> dict:
    raw = flow_interface.get_latest_nanovdb_readback()
    result = {}
    for index, name in enumerate(CHANNEL_NAMES):
        array = np.asarray(raw[index] if index < len(raw) else [])
        result[name] = {
            "word_count": int(array.size),
            "byte_count": int(array.nbytes),
            "sha256": hashlib.sha256(array.tobytes()).hexdigest(),
        }
    return result


def _sample(stage, timeline, flow_interface) -> dict:
    emitter = stage.GetPrimAtPath(campfire.app.RESIDENT_POINT_EMITTER_PATH)
    positions = emitter.GetAttribute("pointPositions").Get()
    alignment = campfire.app.measure_resident_point_log_alignment(
        stage,
        (campfire.app.PHASE3_DRY_LOG_ID, campfire.app.PHASE3_WET_LOG_ID),
        positions,
        points_per_log=POINTS_PER_LOG,
    )
    origin = campfire.app.get_log_world_position(stage, campfire.app.PHASE3_DRY_LOG_ID)
    return {
        "revision": int(emitter.GetAttribute("campfire:residentRevision").Get()),
        "layout_revision": int(
            emitter.GetAttribute("campfire:layoutRevision").Get()
        ),
        "timeline_time_s": float(timeline.get_current_time()),
        "timeline_playing": bool(timeline.is_playing()),
        "active_blocks": int(flow_interface.get_active_block_count()),
        "dry_log_origin_m": [float(value) for value in origin],
        "dry_log_point_centroid_m": [
            float(value) for value in alignment["point_centroids_m"][0]
        ],
        "maximum_alignment_error_m": float(alignment["max_error_m"]),
        "root_layer": str(stage.GetRootLayer().identifier),
    }


async def _wait_for_stage(context):
    for _ in range(3000):
        await omni.kit.app.get_app().next_update_async()
        stage = context.get_stage()
        point = (
            stage.GetPrimAtPath(campfire.app.RESIDENT_POINT_EMITTER_PATH)
            if stage is not None
            else None
        )
        if point and point.GetAttribute("campfire:residentRevision"):
            return stage
    raise RuntimeError("Phase 6DA Resident Point stage did not become ready")


async def _run() -> None:
    settings = carb.settings.get_settings()
    output = Path(settings.get_as_string("/phase6da/output")).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "phase": "phase6da",
        "status": "running",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "default_off": True,
            "flow_version": "110.0.0",
            "translation_only": True,
            "rotation_tracking_qualified": False,
            "flow_solver_state_checkpointed": False,
        },
        "samples": [],
    }
    _write(output, report)
    try:
        context = omni.usd.get_context()
        stage = await _wait_for_stage(context)
        timeline = omni.timeline.get_timeline_interface()
        flow_interface = _flowusd.acquire_flowusd_interface()
        pre = None
        post = None
        moved_target = None
        pre_fields = None
        post_fields = None
        roots = set()

        for _ in range(30000):
            await omni.kit.app.get_app().next_update_async()
            stage = context.get_stage()
            if stage is None:
                continue
            emitter = stage.GetPrimAtPath(campfire.app.RESIDENT_POINT_EMITTER_PATH)
            if not emitter or not emitter.IsValid():
                continue
            sample = _sample(stage, timeline, flow_interface)
            roots.add(sample["root_layer"])
            revision = sample["revision"]
            if 338 <= revision <= 352 and (
                not report["samples"]
                or report["samples"][-1]["revision"] != revision
            ):
                report["samples"].append(sample)

            if revision >= TRIGGER_REVISION and pre is None:
                pre = sample
                pre_fields = _fields(flow_interface)
                origin = sample["dry_log_origin_m"]
                moved_target = (origin[0], origin[1] + 0.02, origin[2])
                campfire.app.move_log(
                    stage, campfire.app.PHASE3_DRY_LOG_ID, moved_target, 0.0
                )
            elif pre is not None and revision > pre["revision"] and post is None:
                post = sample
                post_fields = _fields(flow_interface)

            if post is not None and revision >= post["revision"] + 6:
                break
            if revision >= 365 and post is None:
                break
            _write(output, report)

        displacement = (
            _distance(pre["dry_log_origin_m"], post["dry_log_origin_m"])
            if pre and post
            else 0.0
        )
        point_displacement = (
            _distance(
                pre["dry_log_point_centroid_m"],
                post["dry_log_point_centroid_m"],
            )
            if pre and post
            else 0.0
        )
        required_nonempty = bool(
            pre_fields
            and post_fields
            and all(pre_fields[name]["word_count"] > 0 for name in REQUIRED_NONEMPTY_CHANNELS)
            and all(post_fields[name]["word_count"] > 0 for name in REQUIRED_NONEMPTY_CHANNELS)
        )
        gates = {
            "running_pre_sample_captured": pre is not None and pre["timeline_playing"],
            "next_revision_post_sample_captured": post is not None and post["timeline_playing"],
            "layout_revision_advanced_with_snapshot": bool(
                pre and post and post["layout_revision"] > pre["layout_revision"]
            ),
            "post_alignment_within_2_mm": bool(
                post and post["maximum_alignment_error_m"] <= 0.002
            ),
            "point_and_log_displacement_agree_within_2_mm": abs(
                point_displacement - displacement
            )
            <= 0.002,
            "required_flow_fields_nonempty": required_nonempty,
            "active_blocks_nonzero": bool(
                pre and post and pre["active_blocks"] > 0 and post["active_blocks"] > 0
            ),
            "single_root_layer_observed": len(roots) == 1,
        }
        report.update(
            {
                "status": "ok" if all(gates.values()) else "failed",
                "boundary": {
                    "trigger_revision": TRIGGER_REVISION,
                    "requested_target_m": list(moved_target) if moved_target else None,
                    "pre": pre,
                    "post": post,
                    "log_displacement_m": displacement,
                    "point_centroid_displacement_m": point_displacement,
                    "displacement_difference_m": abs(point_displacement - displacement),
                },
                "fields": {"pre": pre_fields, "post": post_fields},
                "observation": {
                    "dynamic_log_point_translation_implemented": True,
                    "rotation_tracking_implemented": False,
                    "seamless_visual_continuity_qualified": False,
                    "flow_solver_state_checkpointed": False,
                    "within_update_reset_can_be_excluded": False,
                    "root_layers": sorted(roots),
                },
                "gates": gates,
            }
        )
    except asyncio.CancelledError:
        raise
    except Exception as error:
        report["status"] = "error"
        report["error"] = f"{type(error).__name__}: {error}"
        carb.log_error(f"[phase6da] {type(error).__name__}: {error}")
    finally:
        _write(output, report)


asyncio.ensure_future(_run())
