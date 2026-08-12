"""Incremental non-pair gate for one Phase 6ER formal process."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np


def _maximum(condition: Path, colliders: list[int], channel: str, band: str) -> float:
    result = 0.0
    for collider in colliders:
        for path in (condition / "spatial" / f"collider_{collider}").glob(f"*_{channel}.npz"):
            with np.load(path) as data:
                values = data["magnitude"].astype(np.float64)
                depth = data["mesh_distance_voxels"].astype(np.float64)
                mask = depth < -1.0
                if band == "center":
                    voxel = float(np.max(data["voxel_size_xyz"]))
                    mask &= data["axis_radial_distance_m"].astype(np.float64) <= 0.5 * voxel
                if mask.any():
                    result = max(result, float(values[mask].max()))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    threshold = contract["thresholds"]
    raw = json.loads((args.condition / "raw.json").read_text(encoding="utf-8"))
    evidence = json.loads((args.condition / "runner_evidence.json").read_text(encoding="utf-8"))
    point = raw["point_payload"]
    scenario = raw["arguments"]["scenario"]
    collision = bool(raw["arguments"]["collision"])
    failures = []
    lifecycle = bool(
        raw.get("status") == "ok" and raw.get("lifecycle_marker") == "shutdown_complete"
        and evidence.get("outcome", {}).get("functional_status") == "pass"
        and evidence.get("outcome", {}).get("lifecycle_status") == "normal_exit"
        and not evidence.get("fatal_lines") and not evidence.get("dump_inventory")
        and not evidence.get("automatic_upload_attempt_lines") and not evidence.get("production_changed")
    )
    if not lifecycle:
        failures.append("lifecycle")
    if int(raw.get("active_blocks_final", 0)) < threshold["minimum_active_blocks"]:
        failures.append("active_blocks")
    if int(raw.get("revision", -1)) != contract["point_payload"]["revision"]:
        failures.append("revision")
    if collision:
        if int(point["active_other_support_intersection_count"]) != threshold["maximum_active_other_support_intersections"]:
            failures.append("active_other_support_intersection")
        for channel in ("fuel", "temperature", "smoke"):
            if float(point["weighted_supply"][channel]["retention"]) < threshold["minimum_weighted_supply_retention"]:
                failures.append(f"weighted_{channel}_retention")
    active = int(point["active_point_count"])
    scale = raw["arguments"]
    expected = {
        "fuel": active * 0.8 * float(scale["fuel_scale"]),
        "temperature": active * 2.0 * float(scale["temperature_scale"]),
        "smoke": active * 0.08 * float(scale["smoke_scale"]),
    }
    for channel, expected_value in expected.items():
        if not math.isclose(float(raw["source_sums"][channel]), expected_value, rel_tol=threshold["source_channel_sum_relative_tolerance"], abs_tol=1.0e-5):
            failures.append(f"source_sum_{channel}")
    colliders = [1] if scenario == "lower_upper" else list(range(len(point["poses"])))
    deep_velocity = _maximum(args.condition, colliders, "velocity", "deep")
    center_velocity = _maximum(args.condition, colliders, "velocity", "center")
    if collision and max(deep_velocity, center_velocity) > threshold["other_or_self_deep_velocity_maximum_m_s"]:
        failures.append("deep_velocity")
    ignition_frames = []
    for sample in raw.get("samples", []):
        profile = sample.get("channels", {}).get("temperature", {}).get("field_profile", {})
        if float(profile.get("maximum_value", 0.0)) >= threshold["external_temperature_profile_threshold"]:
            ignition_frames.append(int(sample["frame"]))
    ignition = min(ignition_frames) if ignition_frames else None
    extent = max((float(sample.get("channels", {}).get("temperature", {}).get("field_profile", {}).get("vertical_extent_m", 0.0)) for sample in raw.get("samples", [])), default=0.0)
    if collision and (ignition is None or ignition > threshold["latest_external_ignition_frame"]):
        failures.append("external_ignition")
    if collision and extent < threshold["minimum_external_vertical_extent_m"]:
        failures.append("external_vertical_extent")
    report = {
        "schema":"campfire.phase6er.incremental-condition-gate.v1","phase":"phase6er",
        "scenario":scenario,"collision":collision,"policy":raw["arguments"]["policy"],
        "passed":not failures,"failed_gates":failures,"lifecycle_passed":lifecycle,
        "point_retention":point["supply_efficiency"],"weighted_supply":point["weighted_supply"],
        "active_other_support_intersections":point["active_other_support_intersection_count"],
        "deep_velocity_maximum_m_s":deep_velocity,"center_velocity_maximum_m_s":center_velocity,
        "external_ignition_frame":ignition,"external_vertical_extent_m":extent,
        "active_blocks":raw.get("active_blocks_final",0),"source_sums":raw["source_sums"],
    }
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(f"Phase 6ER incremental {scenario}/{report['policy']} passed={not failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
