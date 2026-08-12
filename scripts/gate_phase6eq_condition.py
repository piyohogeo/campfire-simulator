"""Fail-closed incremental gate for one Phase 6EQ process."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np


def _stats(path: Path) -> dict:
    with np.load(path) as data:
        channel = str(data["channel"][0])
        frame = int(data["frame"][0])
        values = data["magnitude"].astype(np.float64)
        depth = data["mesh_distance_voxels"].astype(np.float64)
        deep = depth < -1.0
        halo = (depth >= 0.0) & (depth <= 3.0)
        return {
            "channel": channel,
            "frame": frame,
            "deep_maximum": float(values[deep].max()) if deep.any() else 0.0,
            "deep_mean": float(values[deep].mean()) if deep.any() else 0.0,
            "deep_count": int(deep.sum()),
            "halo_maximum": float(values[halo].max()) if halo.any() else 0.0,
            "halo_count": int(halo.sum()),
        }


def _spatial(condition: Path) -> dict[int, list[dict]]:
    result = {}
    for folder in sorted((condition / "spatial").glob("collider_*")):
        index = int(folder.name.split("_")[-1])
        result[index] = [_stats(path) for path in sorted(folder.glob("*.npz"))]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    thresholds = contract["thresholds"]
    raw = json.loads((args.condition / "raw.json").read_text(encoding="utf-8"))
    evidence = json.loads((args.condition / "runner_evidence.json").read_text(encoding="utf-8"))
    spatial = _spatial(args.condition)
    policy = raw["arguments"]["policy"]
    collision = bool(raw["arguments"]["collision"])
    scenario = raw["arguments"]["scenario"]
    point = raw["point_payload"]
    failures = []
    lifecycle = (
        raw.get("status") == "ok"
        and raw.get("lifecycle_marker") == "shutdown_complete"
        and evidence.get("outcome", {}).get("functional_status") == "pass"
        and evidence.get("outcome", {}).get("lifecycle_status") == "normal_exit"
        and not evidence.get("fatal_lines")
        and not evidence.get("dump_inventory")
        and not evidence.get("automatic_upload_attempt_lines")
        and not evidence.get("production_changed")
    )
    if not lifecycle:
        failures.append("lifecycle")
    if int(raw.get("active_blocks_final", 0)) < thresholds["minimum_active_blocks"]:
        failures.append("active_blocks")
    if int(raw.get("revision", -1)) != contract["point_payload"]["revision"]:
        failures.append("revision")
    if collision:
        if int(point["active_other_support_intersection_count"]) != thresholds["maximum_active_other_support_intersections"]:
            failures.append("other_support_intersection")
        for channel in ("fuel", "temperature", "smoke"):
            if float(point["weighted_supply"][channel]["retention"]) < thresholds["minimum_weighted_supply_retention"]:
                failures.append(f"weighted_{channel}_retention")
    active = int(point["active_point_count"])
    expected = {"fuel": active * 0.8, "temperature": active * 2.0, "smoke": active * 0.08}
    for channel, value in expected.items():
        if not math.isclose(float(raw["source_sums"][channel]), value, rel_tol=1.0e-6, abs_tol=1.0e-5):
            failures.append(f"source_sum_{channel}")
    other_indices = [1] if scenario == "lower_upper" else sorted(spatial)
    channel_limits = {
        "velocity": thresholds["other_collider_deep_velocity_maximum_m_s"],
        "temperature": thresholds["other_collider_deep_temperature_maximum"],
        "smoke": thresholds["other_collider_deep_smoke_maximum"],
    }
    deep_maxima = {channel: 0.0 for channel in channel_limits}
    if collision:
        for collider in other_indices:
            for row in spatial.get(collider, []):
                if row["channel"] in deep_maxima:
                    deep_maxima[row["channel"]] = max(deep_maxima[row["channel"]], row["deep_maximum"])
        for channel, maximum in deep_maxima.items():
            if maximum > channel_limits[channel]:
                failures.append(f"other_deep_{channel}")
    self_indices = [0] if scenario == "lower_upper" else sorted(spatial)
    temperature_halo_frames = []
    for collider in self_indices:
        for row in spatial.get(collider, []):
            if row["channel"] == "temperature" and row["halo_maximum"] >= thresholds["external_temperature_profile_threshold"]:
                temperature_halo_frames.append(row["frame"])
    ignition_frame = min(temperature_halo_frames) if temperature_halo_frames else None
    if collision and (ignition_frame is None or ignition_frame > thresholds["latest_external_ignition_frame"]):
        failures.append("external_ignition")
    vertical_extent = max(
        (
            float(sample["channels"].get("temperature", {}).get("field_profile", {}).get("vertical_extent_m", 0.0))
            for sample in raw.get("samples", [])
        ),
        default=0.0,
    )
    if collision and vertical_extent < thresholds["minimum_external_vertical_extent_m"]:
        failures.append("external_vertical_extent")
    report = {
        "schema": "campfire.phase6eq.incremental-condition-gate.v1",
        "phase": "phase6eq",
        "scenario": scenario,
        "policy": policy,
        "collision": collision,
        "passed": not failures,
        "failed_gates": failures,
        "point_retention": point["supply_efficiency"],
        "weighted_supply": point["weighted_supply"],
        "active_other_support_intersections": point["active_other_support_intersection_count"],
        "source_sums": raw["source_sums"],
        "other_deep_maximum": deep_maxima,
        "external_ignition_frame": ignition_frame,
        "external_vertical_extent_m": vertical_extent,
        "active_blocks": raw.get("active_blocks_final", 0),
        "lifecycle_passed": lifecycle,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Phase 6EQ gate {scenario}/{policy} passed={not failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
