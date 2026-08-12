"""Aggregate Phase 6ER scalar calibration without inventing a qualification gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def _summary(values: np.ndarray) -> dict:
    values = np.asarray(values, dtype=np.float64)
    if not values.size:
        return {"count": 0, "mean": 0.0, "p50": 0.0, "p95": 0.0, "maximum": 0.0, "sum": 0.0}
    return {
        "count": int(values.size), "mean": float(values.mean()),
        "p50": float(np.quantile(values, 0.50)), "p95": float(np.quantile(values, 0.95)),
        "maximum": float(values.max()), "sum": float(values.sum()),
    }


def _spatial(case: Path, channel: str) -> list[dict]:
    rows = []
    for path in sorted((case / "spatial" / "collider_1").glob(f"*_{channel}.npz")):
        with np.load(path) as data:
            values = data["magnitude"].astype(np.float64)
            depth = data["mesh_distance_voxels"].astype(np.float64)
            inside = depth < 0.0
            deep = depth < -1.0
            boundary = inside & ~deep
            center = deep & (data["axis_radial_distance_m"].astype(np.float64) <= 0.5 * float(np.max(data["voxel_size_xyz"])))
            rows.append({
                "frame": int(data["frame"][0]), "voxel_size_xyz": data["voxel_size_xyz"].astype(float).tolist(),
                "boundary": _summary(values[boundary]), "deep": _summary(values[deep]),
                "center_axis": _summary(values[center]), "archive": str(path),
                "archive_sha256": hashlib.sha256(path.read_bytes()).hexdigest().upper(),
            })
    return rows


def _roi_series(raw: dict, channel: str, roi: str) -> list[dict]:
    rows = []
    for sample in raw.get("samples", []):
        value = sample.get("channels", {}).get(channel, {})
        if value.get("available") and roi in value.get("rois", {}):
            rows.append({"frame": sample["frame"], **value["rois"][roi]})
    return rows


def _metric_max(entry: dict, channel: str, band: str, metric: str) -> float:
    return max((frame[band][metric] for frame in entry["channels"][channel]["spatial"]), default=0.0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    entries = []
    failures = []
    for definition in contract["conditions"]:
        case = args.root / "calibration" / definition["name"]
        raw_path, evidence_path = case / "raw.json", case / "runner_evidence.json"
        if not raw_path.is_file() or not evidence_path.is_file():
            failures.append(f"missing:{definition['name']}")
            continue
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        lifecycle_ok = bool(
            raw.get("status") == "ok" and raw.get("lifecycle_marker") == "shutdown_complete"
            and evidence.get("outcome", {}).get("lifecycle_status") == "normal_exit"
        )
        if not lifecycle_ok:
            failures.append(f"lifecycle:{definition['name']}")
        channels = {}
        for channel in ("velocity", "temperature", "smoke"):
            channels[channel] = {
                "spatial": _spatial(case, channel),
                "rois": {roi: _roi_series(raw, channel, roi) for roi in contract["roi_contract"] if roi not in ("boundary_band", "deep_interior", "center_axis")},
            }
        entries.append({
            "name": definition["name"], "definition": definition, "lifecycle_ok": lifecycle_ok,
            "active_blocks": raw.get("active_blocks_final", 0), "source_sums": raw.get("source_sums", {}),
            "channels": channels,
        })
    by_name = {entry["name"]: entry for entry in entries}
    comparisons = []
    for prefix in ("normal", "temperature_only", "smoke_only"):
        off, on = by_name.get(prefix + "_off"), by_name.get(prefix + "_on")
        if not off or not on:
            continue
        for channel in ("temperature", "smoke"):
            for band in ("boundary", "deep", "center_axis"):
                off_sum = _metric_max(off, channel, band, "sum")
                on_sum = _metric_max(on, channel, band, "sum")
                off_mean = _metric_max(off, channel, band, "mean")
                on_mean = _metric_max(on, channel, band, "mean")
                comparisons.append({
                    "source_mode": prefix, "channel": channel, "band": band,
                    "off_sum_max": off_sum, "on_sum_max": on_sum,
                    "on_to_off_sum_ratio": on_sum / max(off_sum, 1.0e-30),
                    "off_mean_max": off_mean, "on_mean_max": on_mean,
                    "on_to_off_mean_ratio": on_mean / max(off_mean, 1.0e-30),
                })
    ambient = by_name.get("emitterless_on")
    baseline = {
        channel: {
            band: _metric_max(ambient, channel, band, "maximum") if ambient else None
            for band in ("boundary", "deep", "center_axis")
        }
        for channel in ("temperature", "smoke")
    }
    report = {
        "schema": "campfire.phase6er.scalar-calibration-report.v1", "phase": "phase6er",
        "contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest().upper(),
        "status": "complete" if not failures else "failed", "failed_gates": failures,
        "entries": entries, "emitterless_baseline": baseline, "on_off_comparisons": comparisons,
        "observations_are_not_formal_thresholds": True,
        "phase6eq_reclassified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Phase 6ER scalar calibration complete={not failures} cases={len(entries)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
