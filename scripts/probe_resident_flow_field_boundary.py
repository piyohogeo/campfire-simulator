"""Sample Flow readback around the existing Phase 6CO layout boundary.

This default-off probe observes the production-but-disabled Resident Point
qualification from outside the extension.  It does not own the scenario,
modify the production stage schema, or claim that NanoVDB hashes checkpoint
the complete Flow solver state.
"""

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


CHANNEL_NAMES = (
    "temperature",
    "fuel",
    "burn",
    "smoke",
    "velocity",
    "divergence",
)
REQUIRED_NONEMPTY_CHANNELS = CHANNEL_NAMES[:-1]
POINTS_PER_LOG = 360


def _write_report(path: Path, report: dict) -> None:
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _distance(left, right) -> float:
    return math.sqrt(
        sum((float(left[index]) - float(right[index])) ** 2 for index in range(3))
    )


def _buffer_snapshot(flow_interface) -> dict:
    raw = flow_interface.get_latest_nanovdb_readback()
    channels = {}
    for index, name in enumerate(CHANNEL_NAMES):
        value = raw[index] if index < len(raw) else []
        array = np.asarray(value)
        channels[name] = {
            "dtype": str(array.dtype),
            "shape": list(array.shape),
            "word_count": int(array.size),
            "byte_count": int(array.nbytes),
            "sha256": hashlib.sha256(array.tobytes()).hexdigest(),
        }
    return channels


def _stage_sample(stage, timeline, flow_interface) -> dict:
    point = stage.GetPrimAtPath(campfire.app.RESIDENT_POINT_EMITTER_PATH)
    revision_attribute = point.GetAttribute("campfire:residentRevision")
    revision = int(revision_attribute.Get())
    positions = point.GetAttribute("pointPositions").Get()
    alignment = campfire.app.measure_resident_point_log_alignment(
        stage,
        (campfire.app.PHASE3_DRY_LOG_ID, campfire.app.PHASE3_WET_LOG_ID),
        positions,
        points_per_log=POINTS_PER_LOG,
    )
    origin = campfire.app.get_log_world_position(
        stage, campfire.app.PHASE3_DRY_LOG_ID
    )
    return {
        "revision": revision,
        "timeline_time_s": float(timeline.get_current_time()),
        "timeline_playing": bool(timeline.is_playing()),
        "timeline_stopped": bool(timeline.is_stopped()),
        "active_blocks": int(flow_interface.get_active_block_count()),
        "dry_log_origin_m": [float(component) for component in origin],
        "point_count": int(alignment["point_count"]),
        "dry_log_point_centroid_m": [
            float(component) for component in alignment["point_centroids_m"][0]
        ],
        "maximum_alignment_error_m": float(alignment["max_error_m"]),
        "root_layer": str(stage.GetRootLayer().identifier),
    }


async def _wait_for_stage(context):
    for _ in range(3000):
        await omni.kit.app.get_app().next_update_async()
        stage = context.get_stage()
        if stage is None:
            continue
        point = stage.GetPrimAtPath(campfire.app.RESIDENT_POINT_EMITTER_PATH)
        revision = point.GetAttribute("campfire:residentRevision") if point else None
        if revision is not None and revision.IsValid():
            return stage
    raise RuntimeError("Phase 6CZ Resident Point stage did not become ready")


async def _run() -> None:
    settings = carb.settings.get_settings()
    output = Path(settings.get_as_string("/phase6cz/output")).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "phase": "phase6cz",
        "status": "running",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "default_off": True,
            "production_code_changed": False,
            "observes_existing_phase6co_scenario": True,
            "flow_version": "110.0.0",
            "point_emitter_default_enabled": False,
            "flow_solver_state_checkpointed": False,
        },
        "samples": [],
        "field_snapshots": {},
    }
    _write_report(output, report)
    flow_interface = None
    try:
        context = omni.usd.get_context()
        stage = await _wait_for_stage(context)
        timeline = omni.timeline.get_timeline_interface()
        flow_interface = _flowusd.acquire_flowusd_interface()
        initial = _stage_sample(stage, timeline, flow_interface)
        roots = {initial["root_layer"]}
        recorded_revisions = set()
        pre_layout_sample = None
        post_layout_sample = None

        for _ in range(30000):
            await omni.kit.app.get_app().next_update_async()
            stage = context.get_stage()
            if stage is None:
                continue
            point = stage.GetPrimAtPath(campfire.app.RESIDENT_POINT_EMITTER_PATH)
            if not point or not point.IsValid():
                continue
            sample = _stage_sample(stage, timeline, flow_interface)
            revision = sample["revision"]
            roots.add(sample["root_layer"])

            revision_is_new = revision not in recorded_revisions
            if 335 <= revision <= 405 and revision_is_new:
                sample["sample"] = len(report["samples"]) + 1
                report["samples"].append(sample)
                recorded_revisions.add(revision)

            if revision == 350 and pre_layout_sample is None:
                pre_layout_sample = sample
                if "pre_layout_revision_350" not in report["field_snapshots"]:
                    report["field_snapshots"]["pre_layout_revision_350"] = {
                        "sample": sample,
                        "channels": _buffer_snapshot(flow_interface),
                    }
            if revision == 351 and post_layout_sample is None:
                post_layout_sample = sample
                if "post_first_publication_revision_351" not in report["field_snapshots"]:
                    report["field_snapshots"]["post_first_publication_revision_351"] = {
                        "sample": sample,
                        "channels": _buffer_snapshot(flow_interface),
                    }
            if revision_is_new:
                _write_report(output, report)

            if revision >= 400 and pre_layout_sample and post_layout_sample:
                break

        snapshots = report["field_snapshots"]
        named_boundary = {
            name: snapshots.get(name)
            for name in (
                "pre_layout_revision_350",
                "post_first_publication_revision_351",
            )
        }
        required_nonempty = {
            name: bool(
                snapshot
                and all(
                    snapshot["channels"][channel]["word_count"] > 0
                    for channel in REQUIRED_NONEMPTY_CHANNELS
                )
            )
            for name, snapshot in named_boundary.items()
        }
        boundary_active = {
            name: int(snapshot["sample"]["active_blocks"])
            if snapshot is not None
            else 0
            for name, snapshot in named_boundary.items()
        }
        log_displacement = (
            _distance(
                pre_layout_sample["dry_log_origin_m"],
                post_layout_sample["dry_log_origin_m"],
            )
            if pre_layout_sample and post_layout_sample
            else 0.0
        )
        point_delta = (
            [
                float(post_layout_sample["dry_log_point_centroid_m"][index])
                - float(pre_layout_sample["dry_log_point_centroid_m"][index])
                for index in range(3)
            ]
            if pre_layout_sample and post_layout_sample
            else [0.0, 0.0, 0.0]
        )
        point_displacement = math.sqrt(sum(value * value for value in point_delta))
        roots_observed = sorted(roots)
        gates = {
            "pre_layout_revision_350_captured": pre_layout_sample is not None,
            "post_first_publication_revision_351_captured": post_layout_sample
            is not None,
            "expected_40_mm_lateral_point_centroid_edit": abs(
                point_delta[1] - 0.04
            ) <= 0.001,
            "required_fields_nonempty_at_both_samples": all(
                required_nonempty.values()
            ),
            "active_blocks_nonzero_at_both_samples": all(
                value > 0 for value in boundary_active.values()
            ),
            "single_root_layer_observed": len(roots_observed) == 1,
            "revision_400_observed": any(
                sample["revision"] >= 400 for sample in report["samples"]
            ),
        }
        report.update(
            {
                "status": "ok" if all(gates.values()) else "failed",
                "layout_boundary": {
                    "log_displacement_m": log_displacement,
                    "point_centroid_delta_m": point_delta,
                    "point_centroid_displacement_m": point_displacement,
                    "pre_layout_sample": pre_layout_sample,
                    "post_first_publication_sample": post_layout_sample,
                },
                "observation": {
                    "required_nonempty_channels": list(REQUIRED_NONEMPTY_CHANNELS),
                    "required_fields_nonempty": required_nonempty,
                    "active_blocks": boundary_active,
                    "no_sampled_zero_field_transition": all(
                        required_nonempty.values()
                    )
                    and all(value > 0 for value in boundary_active.values()),
                    "flow_solver_state_checkpointed": False,
                    "within_update_reset_can_be_excluded": False,
                    "dynamic_log_point_tracking_implemented": False,
                    "post_publication_alignment_within_2_mm": bool(
                        post_layout_sample
                        and post_layout_sample["maximum_alignment_error_m"] <= 0.002
                    ),
                    "root_layers": roots_observed,
                },
                "gates": gates,
            }
        )
    except asyncio.CancelledError:
        raise
    except Exception as error:
        report["status"] = "error"
        report["error"] = f"{type(error).__name__}: {error}"
        carb.log_error(f"[phase6cz] {type(error).__name__}: {error}")
    finally:
        # The fixed Flow 110 Python binding exposes a process-global interface.
        # The observed Campfire extension owns the corresponding release at the
        # end of this scenario, so the external observer must not release it
        # early and invalidate the owner's handle.
        _write_report(output, report)


asyncio.ensure_future(_run())
