"""Aggregate the frozen Phase 6EQ self-Collider tolerance population."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np


POLICIES = ("collision_off", "strict_all", "allow_self_support", "allow_self_center")


def _summary(values) -> dict:
    data = np.asarray(list(values), dtype=np.float64)
    if not data.size:
        return {"count": 0, "minimum": 0.0, "mean": 0.0, "p50": 0.0, "p95": 0.0, "maximum": 0.0}
    return {
        "count": int(data.size), "minimum": float(data.min()), "mean": float(data.mean()),
        "p50": float(np.quantile(data, 0.5)), "p95": float(np.quantile(data, 0.95)),
        "maximum": float(data.max()),
    }


def _spatial_rows(directory: Path) -> list[dict]:
    rows = []
    for folder in sorted((directory / "spatial").glob("collider_*")):
        collider = int(folder.name.split("_")[-1])
        for path in sorted(folder.glob("*.npz")):
            with np.load(path) as data:
                values = data["magnitude"].astype(np.float64)
                depth = data["mesh_distance_voxels"].astype(np.float64)
                deep = depth < -1.0
                boundary = (depth < 0.0) & (depth >= -1.0)
                halo = (depth >= 0.0) & (depth <= 3.0)
                rows.append({
                    "collider": collider,
                    "channel": str(data["channel"][0]),
                    "frame": int(data["frame"][0]),
                    "deep": _summary(values[deep]),
                    "boundary": _summary(values[boundary]),
                    "halo": _summary(values[halo]),
                    "path": str(path),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest().upper(),
                    "bytes": path.stat().st_size,
                })
    return rows


def _load_condition(root: Path, directory: Path) -> dict:
    raw = json.loads((directory / "raw.json").read_text(encoding="utf-8"))
    evidence = json.loads((directory / "runner_evidence.json").read_text(encoding="utf-8"))
    gate = json.loads((directory / "incremental_gate.json").read_text(encoding="utf-8"))
    relative = directory.relative_to(root)
    guard_path = root / "runner-logs" / ("_".join(relative.parts) + ".guard.json")
    guard = json.loads(guard_path.read_text(encoding="utf-8")) if guard_path.is_file() else None
    return {"raw": raw, "evidence": evidence, "gate": gate, "spatial": _spatial_rows(directory), "guard": guard}


def _field(raw: dict, channel: str, key: str) -> list[float]:
    return [
        float(sample["channels"].get(channel, {}).get("field_profile", {}).get(key, 0.0))
        for sample in raw.get("samples", [])
    ]


def _scene_sum(raw: dict, channel: str) -> list[float]:
    return [
        float(sample["channels"].get(channel, {}).get("rois", {}).get("scene", {}).get("sum", 0.0))
        for sample in raw.get("samples", [])
    ]


def _deep_maximum(entry: dict, channel: str, other_only: bool) -> float:
    scenario = entry["raw"]["arguments"]["scenario"]
    rows = entry["spatial"]
    if other_only and scenario == "lower_upper":
        rows = [row for row in rows if row["collider"] == 1]
    return max((row["deep"]["maximum"] for row in rows if row["channel"] == channel), default=0.0)


def _make_svg(report: dict, path: Path) -> None:
    rows = report["condition_summary"]
    width, height = 1480, 170 + 62 * len(rows)
    body = []
    colors = {"collision_off": "#ef4444", "strict_all": "#3b82f6", "allow_self_support": "#f59e0b", "allow_self_center": "#22c55e"}
    for index, row in enumerate(rows):
        y = 145 + index * 62
        retention = row["weighted_fuel_retention"]["mean"]
        deep = row["other_deep_velocity_maximum_m_s"]
        body.append(f'<text x="35" y="{y}" class="label">{row["scenario"]} / {row["policy"]}</text>')
        body.append(f'<rect x="520" y="{y-22}" width="{460*retention:.1f}" height="22" rx="4" fill="{colors[row["policy"]]}"/>')
        body.append(f'<text x="1000" y="{y-4}" class="value">supply {retention*100:.2f}% · other deep v {deep:.3e}</text>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><style>.title{{font:700 30px system-ui;fill:#f8fafc}}.sub{{font:17px system-ui;fill:#94a3b8}}.label,.value{{font:15px ui-monospace;fill:#dbeafe}}</style><rect width="100%" height="100%" fill="#08111f"/><text x="35" y="48" class="title">Phase 6EQ — self-Collider tolerance</text><text x="35" y="82" class="sub">bar = weighted fuel retention · other-Collider deep velocity remains a separate hard gate</text>{''.join(body)}</svg>'''
    path.write_text(svg, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    entries = []
    failures = []
    for directory in sorted((args.root / "formal").glob("run_*/*/*")):
        if not directory.is_dir() or not (directory / "raw.json").is_file():
            continue
        loaded = _load_condition(args.root, directory)
        raw, gate = loaded["raw"], loaded["gate"]
        policy = raw["arguments"]["policy"] if raw["arguments"]["collision"] else "collision_off"
        scenario = raw["arguments"]["scenario"]
        run = directory.parents[1].name
        if not gate["passed"]:
            failures.append(f"{run}/{scenario}/{policy}:incremental")
        entry = {
            "run": run, "scenario": scenario, "policy": policy,
            "offset_m": float(raw["arguments"]["offset_m"]),
            "point_retention": float(raw["point_payload"]["supply_efficiency"]),
            "weighted_supply": raw["point_payload"]["weighted_supply"],
            "active_point_count": int(raw["point_payload"]["active_point_count"]),
            "point_count": int(raw["point_payload"]["original_point_count"]),
            "active_other_support_intersections": int(raw["point_payload"]["active_other_support_intersection_count"]),
            "disable_reason_counts": raw["point_payload"]["disable_reason_counts"],
            "source_sums": raw["source_sums"],
            "active_blocks": int(raw["active_blocks_final"]),
            "external_ignition_frame": gate["external_ignition_frame"],
            "external_vertical_extent_m": gate["external_vertical_extent_m"],
            "other_deep": {channel: _deep_maximum(loaded, channel, True) for channel in ("velocity", "temperature", "smoke")},
            "self_deep": {channel: _deep_maximum(loaded, channel, False) for channel in ("velocity", "temperature", "smoke")},
            "field_profiles": {
                "temperature_height_m": _field(raw, "temperature", "vertical_extent_m"),
                "temperature_spread_x_m": _field(raw, "temperature", "horizontal_extent_x_m"),
                "temperature_spread_y_m": _field(raw, "temperature", "horizontal_extent_y_m"),
                "velocity_mean_positive_z_m_s": _field(raw, "velocity", "mean_positive_vertical_velocity_m_s"),
            },
            "scene_channel_sums": {channel: _scene_sum(raw, channel) for channel in ("fuel", "temperature", "smoke")},
            "spatial": loaded["spatial"],
            "incremental_gate": gate,
            "resource": loaded["guard"],
        }
        entries.append(entry)
    expected = int(contract["formal_process_count"])
    if len(entries) != expected:
        failures.append(f"process_count:{len(entries)}:{expected}")
    pair_results = []
    for run in ("run_1", "run_2", "run_3"):
        for scenario in contract["formal_scenarios"]:
            off = next((item for item in entries if item["run"] == run and item["scenario"] == scenario and item["policy"] == "collision_off"), None)
            for policy in ("strict_all", "allow_self_support", "allow_self_center"):
                candidate = next((item for item in entries if item["run"] == run and item["scenario"] == scenario and item["policy"] == policy), None)
                if off is None or candidate is None:
                    failures.append(f"pair_missing:{run}:{scenario}:{policy}")
                    continue
                off_value = off["other_deep"]["velocity"]
                ratio = candidate["other_deep"]["velocity"] / max(off_value, 1.0e-30)
                passed = (
                    off_value >= contract["thresholds"]["collision_off_other_deep_velocity_minimum_m_s"]
                    and ratio <= contract["thresholds"]["collision_on_to_off_other_deep_velocity_ratio"]
                )
                if not passed:
                    failures.append(f"pair:{run}:{scenario}:{policy}")
                pair_results.append({"run": run, "scenario": scenario, "policy": policy, "off_deep_velocity_m_s": off_value, "ratio": ratio, "passed": passed})
    summaries = []
    for scenario in contract["formal_scenarios"]:
        for policy in POLICIES:
            selected = [item for item in entries if item["scenario"] == scenario and item["policy"] == policy]
            fuel_retention = [item["weighted_supply"]["fuel"]["retention"] for item in selected]
            ignition = [item["external_ignition_frame"] for item in selected if item["external_ignition_frame"] is not None]
            variation_source = [max(item["scene_channel_sums"]["temperature"], default=0.0) for item in selected]
            relative_variation = (max(variation_source) - min(variation_source)) / max(np.mean(variation_source), 1.0e-30) if variation_source else math.inf
            if len(selected) == 3 and relative_variation > contract["thresholds"]["maximum_run_relative_variation"]:
                failures.append(f"variation:{scenario}:{policy}")
            summaries.append({
                "scenario": scenario, "policy": policy, "run_count": len(selected),
                "weighted_fuel_retention": _summary(fuel_retention),
                "other_deep_velocity_maximum_m_s": max((item["other_deep"]["velocity"] for item in selected), default=0.0),
                "other_deep_temperature_maximum": max((item["other_deep"]["temperature"] for item in selected), default=0.0),
                "other_deep_smoke_maximum": max((item["other_deep"]["smoke"] for item in selected), default=0.0),
                "external_ignition_frame": _summary(ignition),
                "temperature_vertical_extent_m": _summary(max(item["field_profiles"]["temperature_height_m"], default=0.0) for item in selected),
                "temperature_spread_x_m": _summary(max(item["field_profiles"]["temperature_spread_x_m"], default=0.0) for item in selected),
                "temperature_spread_y_m": _summary(max(item["field_profiles"]["temperature_spread_y_m"], default=0.0) for item in selected),
                "upward_velocity_m_s": _summary(max(item["field_profiles"]["velocity_mean_positive_z_m_s"], default=0.0) for item in selected),
                "active_blocks": _summary(item["active_blocks"] for item in selected),
                "run_relative_variation": relative_variation,
            })
    report = {
        "schema": "campfire.phase6eq.self-collider-tolerance-report.v1",
        "phase": "phase6eq",
        "contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest().upper(),
        "qualified_numeric": not failures,
        "overall_qualified": False,
        "overall_reason": "visual review is a separate post-numeric gate",
        "formal_process_count": len(entries),
        "entries": entries,
        "pair_results": pair_results,
        "condition_summary": summaries,
        "failed_gates": failures,
        "phase6ep_evidence_reused": False,
        "production_connected": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    _make_svg(report, args.svg)
    print(f"Phase 6EQ numeric qualified={not failures} processes={len(entries)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
