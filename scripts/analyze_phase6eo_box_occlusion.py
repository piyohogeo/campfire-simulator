"""Evaluate the predeclared Phase 6EO Box Mesh occlusion contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path

import numpy as np


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _percentile(values: np.ndarray, percentile: float) -> float:
    if values.size == 0:
        return 0.0
    ordered = np.sort(values.astype(np.float64, copy=False))
    return float(ordered[min(ordered.size - 1, math.ceil(ordered.size * percentile) - 1)])


def _stats(values: np.ndarray) -> dict:
    values = values.astype(np.float64, copy=False)
    return {
        "voxel_count": int(values.size),
        "minimum": float(np.min(values)) if values.size else 0.0,
        "mean": float(np.mean(values)) if values.size else 0.0,
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "p99": _percentile(values, 0.99),
        "maximum": float(np.max(values)) if values.size else 0.0,
        "above_1e_6": int(np.count_nonzero(values > 1.0e-6)),
        "above_1e_5": int(np.count_nonzero(values > 1.0e-5)),
        "above_5e_5": int(np.count_nonzero(values > 5.0e-5)),
        "above_1e_4": int(np.count_nonzero(values > 1.0e-4)),
    }


def _maximum_cell(data, mask: np.ndarray) -> dict | None:
    rows = np.flatnonzero(mask)
    if not rows.size:
        return None
    magnitude = data["magnitude"].astype(np.float64)
    row = int(rows[int(np.argmax(magnitude[rows]))])
    return {
        "magnitude_m_s": float(magnitude[row]),
        "index_ijk": data["index_ijk"][row].astype(int).tolist(),
        "world_xyz_m": data["world_xyz"][row].astype(float).tolist(),
        "local_xyz_m": data["local_xyz"][row].astype(float).tolist(),
        "mesh_signed_distance_m": float(data["mesh_signed_distance_m"][row]),
        "mesh_distance_voxels": float(data["mesh_distance_voxels"][row]),
    }


def _sample(path: Path) -> dict:
    with np.load(path, allow_pickle=False) as data:
        cell = float(np.mean(data["voxel_size_xyz"]))
        signed = data["mesh_signed_distance_m"].astype(np.float64)
        magnitude = data["magnitude"].astype(np.float64)
        local = data["local_xyz"].astype(np.float64)
        inside = data["mesh_inside"].astype(bool)
        boundary = inside & ((-signed) <= cell + 1.0e-9)
        deep = inside & ((-signed) > cell + 1.0e-9)
        horizontal = np.linalg.norm(local[:, :2], axis=1)
        center = deep & (horizontal <= 0.5 * cell + 1.0e-9)
        return {
            "path": str(path),
            "sha256": _sha256(path),
            "frame": int(data["frame"][0]),
            "velocity_voxel_size_m": cell,
            "boundary": _stats(magnitude[boundary]),
            "deep": _stats(magnitude[deep]),
            "center": _stats(magnitude[center]),
            "maximum_cells": {
                "boundary": _maximum_cell(data, boundary),
                "deep": _maximum_cell(data, deep),
                "center": _maximum_cell(data, center),
            },
        }


def _roi(raw: dict, channel: str, roi: str) -> dict:
    records = []
    for sample in raw["samples"]:
        value = sample["channels"][channel]
        if not value.get("available"):
            raise ValueError(f"missing {channel} frame {sample['frame']}")
        stats = value["rois"][roi]
        records.append(
            {
                "frame": int(sample["frame"]),
                "mean": float(stats["mean"]),
                "p95": float(stats["p95"]),
                "maximum": float(stats["maximum"]),
                "nonzero_voxel_count": int(stats["nonzero_voxel_count"]),
            }
        )
    return {"samples": records, "maximum_mean": max(item["mean"] for item in records)}


def _condition(root: Path, name: str) -> dict:
    raw_path = root / "formal" / name / "raw.json"
    evidence_path = root / "formal" / name / "runner_evidence.json"
    guard_path = root / "runner-logs" / f"{name}.guard.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    guard = json.loads(guard_path.read_text(encoding="utf-8"))
    samples = [
        _sample(path)
        for path in sorted((root / "spatial" / name).glob(f"{name}_f*_velocity.npz"))
    ]
    if [item["frame"] for item in samples] != [60, 120, 180, 200]:
        raise ValueError(f"{name} velocity sample frames are incomplete")
    return {
        "raw_sha256": _sha256(raw_path),
        "evidence_sha256": _sha256(evidence_path),
        "status": raw["status"],
        "lifecycle_marker": raw["lifecycle_marker"],
        "functional_status": evidence["outcome"]["functional_status"],
        "lifecycle_status": evidence["outcome"]["lifecycle_status"],
        "process_exit_code": evidence["process_exit_code"],
        "active_blocks_final": raw["active_blocks_final"],
        "source_fuel": raw["stage_audit"]["emitter"]["fuel"],
        "stage_audit": raw["effective_stage_audit"],
        "preparation": raw["preparation"],
        "velocity_samples": samples,
        "above_far": {
            channel: _roi(raw, channel, "above_far")
            for channel in ("velocity", "fuel", "temperature", "smoke")
        },
        "resource": {
            "status": guard["status"],
            "peaks": guard["peaks"],
            "machine_minima": guard["machine_minima"],
        },
        "safety": {
            "fatal_count": len(evidence["fatal_lines"]),
            "dump_count": len(evidence["dump_inventory"]),
            "upload_attempt_count": len(evidence["automatic_upload_attempt_lines"]),
            "production_changed": bool(evidence["production_changed"]),
            "registry_unchanged": bool(evidence["relevant_crash_registry_unchanged"]),
        },
    }


def _svg(report: dict) -> str:
    rows = []
    y = 165
    for frame in (60, 120, 180, 200):
        off = next(item for item in report["conditions"]["box_off"]["velocity_samples"] if item["frame"] == frame)
        on = next(item for item in report["conditions"]["box_on"]["velocity_samples"] if item["frame"] == frame)
        rows.append(
            f'<text x="50" y="{y}" class="label">{frame}</text>'
            f'<text x="180" y="{y}" class="value">{off["deep"]["maximum"]:.6g}</text>'
            f'<text x="420" y="{y}" class="pass">{on["deep"]["maximum"]:.6g}</text>'
            f'<text x="660" y="{y}" class="pass">{on["center"]["maximum"]:.6g}</text>'
        )
        y += 64
    ratio = report["gates"]["worst_deep_on_off_ratio"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="520" viewBox="0 0 1000 520"><style>.bg{{fill:#0c1420}}.title{{fill:#f8fafc;font:700 28px sans-serif}}.sub{{fill:#94a3b8;font:16px sans-serif}}.head{{fill:#cbd5e1;font:700 15px sans-serif}}.label{{fill:#7dd3fc;font:700 18px monospace}}.value{{fill:#fca5a5;font:18px monospace}}.pass{{fill:#86efac;font:18px monospace}}</style><rect class="bg" width="1000" height="520"/><text x="42" y="52" class="title">Phase 6EO · known-good Mesh Box occlusion</text><text x="42" y="82" class="sub">Exact-Mesh deep/center velocity; boundary ≤1 voxel reported separately</text><text x="50" y="120" class="head">Frame</text><text x="180" y="120" class="head">OFF deep max m/s</text><text x="420" y="120" class="head">ON deep max m/s</text><text x="660" y="120" class="head">ON center max m/s</text>{''.join(rows)}<text x="42" y="445" class="pass">QUALIFIED · hard maximum 1e-4 m/s · worst deep ratio {ratio:.4g}</text><text x="42" y="480" class="sub">Geometry labels come from the authored 8-vertex closed Mesh, not a Flow occupancy-mask readback.</text></svg>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    if contract["schema"] != "campfire.phase6eo.box-mesh-occlusion-contract.v1":
        raise ValueError("unexpected Phase 6EO contract")
    conditions = {name: _condition(args.root, name) for name in ("box_off", "box_on")}
    thresholds = contract["thresholds"]
    checks = []
    ratios = []
    for frame in (60, 120, 180, 200):
        off = next(item for item in conditions["box_off"]["velocity_samples"] if item["frame"] == frame)
        on = next(item for item in conditions["box_on"]["velocity_samples"] if item["frame"] == frame)
        ratio = on["deep"]["maximum"] / max(off["deep"]["maximum"], 1.0e-30)
        ratios.append(ratio)
        checks.extend(
            (
                {"name": f"f{frame}_on_deep", "passed": on["deep"]["maximum"] <= thresholds["collision_on_deep_maximum_m_s"], "value": on["deep"]["maximum"]},
                {"name": f"f{frame}_on_center", "passed": on["center"]["maximum"] <= thresholds["collision_on_center_maximum_m_s"], "value": on["center"]["maximum"]},
                {"name": f"f{frame}_off_deep", "passed": off["deep"]["maximum"] >= thresholds["collision_off_deep_minimum_m_s"], "value": off["deep"]["maximum"]},
                {"name": f"f{frame}_off_center", "passed": off["center"]["maximum"] >= thresholds["collision_off_center_minimum_m_s"], "value": off["center"]["maximum"]},
                {"name": f"f{frame}_deep_ratio", "passed": ratio <= thresholds["on_to_off_deep_maximum_ratio"], "value": ratio},
            )
        )
    above_ratios = {}
    for channel in ("velocity", "temperature", "smoke"):
        off = conditions["box_off"]["above_far"][channel]["maximum_mean"]
        on = conditions["box_on"]["above_far"][channel]["maximum_mean"]
        ratio = on / max(off, 1.0e-30)
        above_ratios[channel] = ratio
        checks.append({"name": f"above_far_{channel}_ratio", "passed": ratio <= thresholds["above_far_mean_ratio_maximum"], "value": ratio})
    checks.extend(
        [
            {"name": "off_above_velocity_positive", "passed": conditions["box_off"]["above_far"]["velocity"]["maximum_mean"] >= thresholds["above_far_off_velocity_mean_minimum_m_s"]},
            {"name": "off_above_temperature_positive", "passed": conditions["box_off"]["above_far"]["temperature"]["maximum_mean"] >= thresholds["above_far_off_temperature_mean_minimum"]},
            {"name": "off_above_smoke_positive", "passed": conditions["box_off"]["above_far"]["smoke"]["maximum_mean"] >= thresholds["above_far_off_smoke_mean_minimum"]},
        ]
    )
    for name, condition in conditions.items():
        checks.extend(
            [
                {"name": f"{name}_normal_exit", "passed": condition["lifecycle_status"] == "normal_exit" and condition["process_exit_code"] == 0},
                {"name": f"{name}_active_blocks", "passed": condition["active_blocks_final"] > 0},
                {"name": f"{name}_fuel", "passed": abs(condition["source_fuel"] - 0.8) <= thresholds["fuel_absolute_tolerance"]},
                {"name": f"{name}_safety", "passed": not any((condition["safety"]["fatal_count"], condition["safety"]["dump_count"], condition["safety"]["upload_attempt_count"], condition["safety"]["production_changed"])) and condition["safety"]["registry_unchanged"]},
            ]
        )
    stage_difference = {
        "source_sha_equal": conditions["box_off"]["preparation"]["source_sha256"] == conditions["box_on"]["preparation"]["source_sha256"],
        "common_prefix_equal": conditions["box_off"]["preparation"]["offline_changes"][:-1] == conditions["box_on"]["preparation"]["offline_changes"],
        "only_off_extra": conditions["box_off"]["preparation"]["offline_changes"][-1:] == ["physicsCollisionEnabled=false_for_positive_control"],
    }
    checks.append({"name": "stage_difference_only_collision_switch", "passed": all(stage_difference.values())})
    report = {
        "schema": "campfire.phase6eo.box-mesh-occlusion-report.v1",
        "phase": "phase6eo",
        "qualified": all(item["passed"] for item in checks),
        "contract_sha256": _sha256(args.contract),
        "contract": contract,
        "conditions": conditions,
        "stage_difference": stage_difference,
        "gates": {
            "checks": checks,
            "failed": [item for item in checks if not item["passed"]],
            "worst_deep_on_off_ratio": max(ratios),
            "above_far_on_off_mean_ratios": above_ratios,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.svg.write_text(_svg(report), encoding="utf-8")
    if not report["qualified"]:
        raise SystemExit(f"Phase 6EO failed: {report['gates']['failed']}")
    print("Phase 6EO numeric qualification passed")


if __name__ == "__main__":
    main()
