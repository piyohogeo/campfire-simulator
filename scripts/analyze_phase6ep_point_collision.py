"""Aggregate Phase 6EP runtime evidence and enforce the frozen gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np


def summary(values):
    values = np.asarray(values, dtype=np.float64)
    if not values.size:
        return {"count": 0, "minimum": 0.0, "mean": 0.0, "p50": 0.0, "p95": 0.0, "maximum": 0.0}
    return {
        "count": int(values.size), "minimum": float(values.min()), "mean": float(values.mean()),
        "p50": float(np.quantile(values, 0.5)), "p95": float(np.quantile(values, 0.95)),
        "p99": float(np.quantile(values, 0.99)),
        "maximum": float(values.max()),
    }


def spatial_stats(path):
    with np.load(path) as data:
        magnitude = data["magnitude"].astype(np.float64)
        depth = data["mesh_distance_voxels"].astype(np.float64)
        radial = data["axis_radial_distance_m"].astype(np.float64)
        voxel = float(np.mean(data["voxel_size_xyz"]))
        inside = depth <= 0.0
        boundary = inside & (depth >= -1.0)
        deep = depth < -1.0
        center = deep & (radial <= 0.5 * voxel)
        return {
            "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest().upper(),
            "frame": int(data["frame"][0]), "voxel_size_m": voxel,
            "boundary": summary(magnitude[boundary]), "deep": summary(magnitude[deep]),
            "center": summary(magnitude[center]),
        }


def load_condition(directory):
    raw = json.loads((directory / "raw.json").read_text(encoding="utf-8"))
    evidence = json.loads((directory / "runner_evidence.json").read_text(encoding="utf-8"))
    spatial = []
    for collider_dir in sorted((directory / "spatial").glob("collider_*")):
        spatial.append([spatial_stats(path) for path in sorted(collider_dir.glob("*.npz"))])
    return {"raw": raw, "evidence": evidence, "spatial": spatial}


def load_guard(root: Path, directory: Path):
    relative = directory.relative_to(root)
    stem = "_".join(relative.parts)
    path = root / "runner-logs" / f"{stem}.guard.json"
    if not path.is_file():
        return {"available": False, "path": str(path)}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "available": True,
        "path": str(path),
        "status": payload.get("status"),
        "duration_seconds": payload.get("duration_seconds"),
        "peaks_private_bytes": payload.get("peaks", {}),
        "machine_minima": payload.get("machine_minima", {}),
        "peak_cpu_percent_of_logical_total_by_role": payload.get("cpu_telemetry", {}).get("peak_percent_of_logical_total_by_role", {}),
        "gpu_sampling": payload.get("cpu_telemetry", {}).get("gpu_sampling"),
        "process_absent": payload.get("process_absent"),
    }


def _upper_maximum(entry, channel):
    rows = entry["upper_roi"].get(channel, [])
    return max((float(item.get("maximum", 0.0)) for item in rows), default=0.0)


def point_distribution(raw):
    path = Path(raw["point_payload"]["payload_path"])
    if not path.is_file():
        return {"available": False, "path": str(path)}
    with np.load(path) as payload:
        owners = payload["owner_index"].astype(np.int64)
        active = payload["active"].astype(bool)
        rows = []
        for owner in sorted(set(owners.tolist())):
            selected = owners == owner
            count = int(selected.sum())
            active_count = int((selected & active).sum())
            rows.append({
                "owner_index": int(owner), "point_count": count,
                "active_point_count": active_count,
                "supply_efficiency": active_count / count if count else 0.0,
            })
    return {"available": True, "path": str(path), "per_owner": rows}


def make_svg(report, path):
    rows = report["formal_summary"]
    labels = [item["condition"] for item in rows]
    width, height = 1400, 180 + 62 * len(rows)
    body = []
    for index, item in enumerate(rows):
        y = 150 + 62 * index
        supply = item["minimum_supply_efficiency"]
        deep = item["worst_deep_maximum_m_s"]
        body.append(f'<text x="40" y="{y}" class="label">{labels[index]}</text>')
        body.append(f'<rect x="500" y="{y-22}" width="{500*supply:.1f}" height="22" rx="5" fill="#22c55e"/>')
        body.append(f'<text x="1020" y="{y-4}" class="value">supply {supply*100:.1f}% · deep {deep:.3e} m/s</text>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><style>.title{{font:700 30px system-ui;fill:#f8fafc}}.sub{{font:18px system-ui;fill:#94a3b8}}.label{{font:16px ui-monospace;fill:#e2e8f0}}.value{{font:16px ui-monospace;fill:#cbd5e1}}</style><rect width="100%" height="100%" fill="#08111f"/><text x="40" y="50" class="title">Phase 6EP PointEmitter–CollisionProxy coexistence</text><text x="40" y="84" class="sub">Frozen 1.5 velocity-voxel offset · three runs · green bar = retained source supply</text>{''.join(body)}</svg>'''
    path.write_text(svg, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    thresholds = contract["thresholds"]
    entries = []
    failures = []
    for directory in sorted((args.root / "formal").glob("run_*/*")):
        if not directory.is_dir():
            continue
        condition = load_condition(directory)
        guard = load_guard(args.root, directory)
        raw, evidence = condition["raw"], condition["evidence"]
        name = directory.name
        candidate = name.endswith("_candidate")
        collision = bool(raw["arguments"]["collision"])
        filtering = bool(raw["arguments"]["filtering"])
        samples = [item for collider in condition["spatial"] for item in collider]
        worst_deep = max((item["deep"]["maximum"] for item in samples), default=0.0)
        worst_center = max((item["center"]["maximum"] for item in samples), default=0.0)
        supply = float(raw["point_payload"]["supply_efficiency"])
        active_support = int(raw["point_payload"]["active_support_intersection_count"])
        lifecycle_ok = (
            raw["status"] == "ok" and raw["lifecycle_marker"] == "shutdown_complete"
            and evidence["outcome"]["functional_status"] == "pass"
            and evidence["outcome"]["lifecycle_status"] == "normal_exit"
            and not evidence["fatal_lines"] and not evidence["dump_inventory"]
            and not evidence["automatic_upload_attempt_lines"] and not evidence["production_changed"]
        )
        gates = {"lifecycle": lifecycle_ok, "active_blocks": int(raw["active_blocks_final"]) > 0, "revision": int(raw["revision"]) == 1}
        if candidate:
            gates.update({
                "supply": supply >= thresholds["minimum_supply_efficiency"],
                "active_support_clear": active_support == 0,
                "deep": worst_deep <= thresholds["collision_on_deep_maximum_m_s"],
                "center": worst_center <= thresholds["collision_on_center_maximum_m_s"],
            })
        for gate, passed in gates.items():
            if not passed:
                failures.append(f"{directory.parent.name}/{name}:{gate}")
        upper = {}
        for channel in ("velocity", "fuel", "temperature", "smoke"):
            values = []
            for sample in raw["samples"]:
                details = sample["channels"].get(channel, {})
                if details.get("available") and details.get("rois", {}).get("upper", {}).get("available"):
                    values.append(details["rois"]["upper"])
            upper[channel] = values
        entries.append({
            "run": directory.parent.name, "condition": name, "candidate": candidate,
            "collision": collision, "filtering": filtering, "supply_efficiency": supply,
            "active_point_count": raw["point_payload"]["active_point_count"],
            "original_point_count": raw["point_payload"]["original_point_count"],
            "disabled_point_count": raw["point_payload"]["disabled_point_count"],
            "self_inside_point_count": raw["point_payload"]["self_inside_count"],
            "other_inside_point_count": raw["point_payload"]["other_inside_count"],
            "support_intersection_count": raw["point_payload"]["support_intersection_count"],
            "active_support_intersection_count": active_support,
            "minimum_active_support_clearance_m": raw["point_payload"]["minimum_active_support_clearance_m"],
            "planning_ms": raw["point_payload"]["planning_ms"],
            "usd_publication_ms": raw["point_payload"]["usd_publication_ms"],
            "source_sums": raw["source_sums"], "active_blocks": raw["active_blocks_final"],
            "payload_revision": int(raw["revision"]),
            "point_distribution": point_distribution(raw),
            "public_point_support_attribute_audit": raw["public_point_support_attribute_audit"],
            "worst_deep_maximum_m_s": worst_deep, "worst_center_maximum_m_s": worst_center,
            "spatial": condition["spatial"], "upper_roi": upper, "resource": guard,
            "gates": gates,
        })
    if len(entries) != 18:
        failures.append(f"formal_process_count:{len(entries)}")
    # Pair gate: use each run's lower/upper candidate against collision-OFF control.
    pair_results = []
    for run in ("run_1", "run_2", "run_3"):
        candidate = next((item for item in entries if item["run"] == run and item["condition"] == "lower_upper_candidate"), None)
        positive = next((item for item in entries if item["run"] == run and item["condition"] == "lower_upper_collision_off_filter_off"), None)
        if candidate is None or positive is None:
            failures.append(f"{run}:pair_missing")
            continue
        ratio = candidate["worst_deep_maximum_m_s"] / max(positive["worst_deep_maximum_m_s"], 1e-30)
        passed = positive["worst_deep_maximum_m_s"] >= thresholds["collision_off_deep_minimum_m_s"] and ratio <= thresholds["on_to_off_deep_maximum_ratio"]
        if not passed:
            failures.append(f"{run}:pair_ratio")
        pair_results.append({"run": run, "deep_ratio": ratio, "off_deep_maximum_m_s": positive["worst_deep_maximum_m_s"], "passed": passed})
    grouped = []
    for name in contract["formal_scenarios"]:
        values = [item for item in entries if item["condition"] == name]
        grouped.append({
            "condition": name, "run_count": len(values),
            "minimum_supply_efficiency": min((item["supply_efficiency"] for item in values), default=0.0),
            "worst_deep_maximum_m_s": max((item["worst_deep_maximum_m_s"] for item in values), default=0.0),
            "worst_center_maximum_m_s": max((item["worst_center_maximum_m_s"] for item in values), default=0.0),
            "active_blocks_minimum": min((item["active_blocks"] for item in values), default=0),
            "planning_ms": summary([item["planning_ms"] for item in values]),
            "usd_publication_ms": summary([item["usd_publication_ms"] for item in values]),
            "source_fuel_sum": summary([item["source_sums"]["fuel"] for item in values]),
            "source_temperature_sum": summary([item["source_sums"]["temperature"] for item in values]),
            "source_smoke_sum": summary([item["source_sums"]["smoke"] for item in values]),
            "upper_roi_maximum": {
                channel: max((_upper_maximum(item, channel) for item in values), default=0.0)
                for channel in ("velocity", "fuel", "temperature", "smoke")
            },
        })
    available_resources = [item["resource"] for item in entries if item["resource"].get("available")]
    resource_summary = {
        "formal_processes_with_resource_evidence": len(available_resources),
        "runner_peak_private_bytes": max((item["peaks_private_bytes"].get("runner", 0) for item in available_resources), default=0),
        "diagnostic_peak_private_bytes": max((item["peaks_private_bytes"].get("diagnostic", 0) for item in available_resources), default=0),
        "kit_peak_private_bytes": max((item["peaks_private_bytes"].get("kit", 0) for item in available_resources), default=0),
        "tree_peak_private_bytes": max((item["peaks_private_bytes"].get("tree", 0) for item in available_resources), default=0),
        "minimum_available_physical_bytes": min((item["machine_minima"].get("available_physical_bytes", math.inf) for item in available_resources), default=0),
        "minimum_commit_headroom_bytes": min((item["machine_minima"].get("estimated_commit_headroom_bytes", math.inf) for item in available_resources), default=0),
        "gpu_sampling": "not collected; the isolated inventory boundary does not provide continuous GPU telemetry",
    }
    report = {
        "schema": "campfire.phase6ep.point-collision-coexistence-report.v1",
        "phase": "phase6ep", "qualified": not failures,
        "contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest().upper(),
        "formal_process_count": len(entries), "entries": entries,
        "pair_results": pair_results, "formal_summary": grouped, "failed_gates": failures,
        "resource_summary": resource_summary,
        "measurement_boundaries": {
            "point_rasterization_cell_size": "not separately exposed by the public FlowEmitterPoint schema in Flow 110.0.0",
            "velocity_voxel_size_m": 0.05,
            "support_radius": "not exposed; conservative 0.05 m evaluation sphere used",
            "gpu_process_metrics": "not collected in the formal population",
        },
        "scope": "default-off production-neutral diagnostic; no production integration",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    make_svg(report, args.svg)
    print(f"Phase 6EP qualified={report['qualified']} formal={len(entries)} failures={len(failures)}")
    return 0 if report["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
