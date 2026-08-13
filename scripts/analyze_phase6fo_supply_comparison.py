"""Analyze Phase 6FO channel preflight and balanced S93/S100 comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np

from phase6es_directional_transport import FACE_DEFINITIONS, _nearest_velocity, face_transport, world_to_log_local


CHANNELS = ("velocity", "temperature", "smoke", "fuel")


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path) as archive:
        return {key: archive[key] for key in archive.files}


def _summary(values: np.ndarray, mask: np.ndarray, voxel_volume: float, thresholds) -> dict:
    selected = np.asarray(values[mask], dtype=np.float64)
    if selected.size == 0:
        return {"voxel_count": 0, "mean": 0.0, "p50": 0.0, "p95": 0.0, "maximum": 0.0, "sum": 0.0, "voxel_volume_integral": 0.0, "threshold_counts": {str(value): 0 for value in thresholds}}
    return {
        "voxel_count": int(selected.size),
        "mean": float(np.mean(selected)),
        "p50": float(np.percentile(selected, 50)),
        "p95": float(np.percentile(selected, 95)),
        "maximum": float(np.max(selected)),
        "sum": float(np.sum(selected, dtype=np.float64)),
        "voxel_volume_integral": float(np.sum(selected, dtype=np.float64) * voxel_volume),
        "threshold_counts": {str(value): int(np.count_nonzero(selected > value)) for value in thresholds},
    }


def _stage_close_seconds(markers: Path):
    if not markers.is_file():
        return None
    rows = [json.loads(line) for line in markers.read_text(encoding="utf-8").splitlines() if line.strip()]
    before = next((row for row in rows if row.get("marker") == "stage_close_request_before"), None)
    after = next((row for row in rows if row.get("marker") == "stage_close_request_after"), None)
    if not before or not after:
        return None
    return (int(after["perf_counter_ns"]) - int(before["perf_counter_ns"])) / 1_000_000_000.0


def _guard_summary(case_dir: Path):
    candidates = list(case_dir.parent.glob("runner-logs/*.guard.json")) + list(case_dir.parent.parent.glob("runner-logs/*.guard.json"))
    if not candidates:
        return None
    return _read(candidates[0])


def _find_file(manifest: dict, frame: int, channel: str) -> Path:
    suffix = f"_f{frame:04d}_{channel}.npz"
    matches = [Path(item["path"]) for item in manifest["files"] if Path(item["path"]).name.endswith(suffix)]
    if len(matches) != 1:
        raise ValueError(f"expected one {suffix} in {manifest.get('condition')}, got {len(matches)}")
    return matches[0]


def _spatial_metrics(raw: dict) -> dict:
    manifests = raw.get("spatial_manifests", [])
    indices = raw.get("spatial_manifest_collider_indices", list(range(len(manifests))))
    by_index = dict(zip(indices, manifests))
    frames = [int(frame) for frame in raw["arguments"]["readback_frames"]]
    poses = raw["point_payload"]["poses"]
    colliders = []
    global_deep_max = {channel: 0.0 for channel in CHANNELS}
    global_boundary_max = {channel: 0.0 for channel in CHANNELS}
    global_deep_volume_sum = {channel: 0.0 for channel in CHANNELS}
    transport_totals = {
        channel: {face: 0.0 for face in FACE_DEFINITIONS}
        for channel in ("temperature", "smoke", "fuel")
    }
    for collider_index, manifest in sorted(by_index.items()):
        pose = poses[int(collider_index)]
        per_frame = []
        previous = None
        cumulative = {channel: {face: 0.0 for face in FACE_DEFINITIONS} for channel in transport_totals}
        for frame in frames:
            loaded = {channel: _load_npz(_find_file(manifest, frame, channel)) for channel in CHANNELS}
            velocity = loaded["velocity"]
            channel_rows = {}
            for channel, payload in loaded.items():
                voxel = np.asarray(payload["voxel_size_xyz"], dtype=np.float64)
                voxel_mean = float(np.mean(voxel))
                voxel_volume = float(np.prod(voxel))
                signed = np.asarray(payload["mesh_signed_distance_m"], dtype=np.float64)
                inside = np.asarray(payload["mesh_inside"], dtype=bool)
                deep = signed < -voxel_mean
                boundary = inside & (signed >= -voxel_mean)
                values = np.asarray(payload["magnitude"] if channel == "velocity" else payload["scalar_value"], dtype=np.float64)
                comparison = np.maximum(values - 1.0, 0.0) if channel == "temperature" else np.abs(values)
                thresholds = (1e-6, 1e-5, 1e-4) if channel == "velocity" else (1e-6, 1e-3, 1e-2)
                deep_stats = _summary(comparison, deep, voxel_volume, thresholds)
                boundary_stats = _summary(comparison, boundary, voxel_volume, thresholds)
                channel_rows[channel] = {
                    "voxel_size_xyz_m": voxel.tolist(),
                    "comparison_value": "max(raw-1,0)" if channel == "temperature" else "abs(raw)",
                    "deep": deep_stats,
                    "boundary": boundary_stats,
                    "raw_deep": _summary(values, deep, voxel_volume, thresholds),
                }
                global_deep_max[channel] = max(global_deep_max[channel], deep_stats["maximum"])
                global_boundary_max[channel] = max(global_boundary_max[channel], boundary_stats["maximum"])
                global_deep_volume_sum[channel] += deep_stats["voxel_volume_integral"]
            velocity_world = np.asarray(velocity["world_xyz"], dtype=np.float64)
            velocity_xyz = np.asarray(velocity["velocity_xyz"], dtype=np.float64)
            for channel in transport_totals:
                payload = loaded[channel]
                world = np.asarray(payload["world_xyz"], dtype=np.float64)
                local = world_to_log_local(world, pose["center"], pose["yaw_degrees"])
                scalar = np.asarray(payload["scalar_value"], dtype=np.float64)
                if channel == "temperature":
                    scalar = np.maximum(scalar - 1.0, 0.0)
                mapped_velocity = _nearest_velocity(world, velocity_world, velocity_xyz)
                faces = face_transport(local, mapped_velocity, scalar, np.asarray(payload["voxel_size_xyz"], dtype=np.float64), 0.05)
                channel_rows[channel]["faces"] = faces
            entry = {"frame": frame, "channels": channel_rows}
            if previous is not None:
                dt = (frame - previous["frame"]) / 60.0
                for channel in transport_totals:
                    for face in FACE_DEFINITIONS:
                        left = previous["channels"][channel]["faces"][face]["outward_transport_proxy"]
                        right = channel_rows[channel]["faces"][face]["outward_transport_proxy"]
                        cumulative[channel][face] += 0.5 * dt * (left + right)
            previous = entry
            per_frame.append(entry)
            del loaded
        for channel in transport_totals:
            for face in FACE_DEFINITIONS:
                transport_totals[channel][face] += cumulative[channel][face]
        colliders.append({"collider_index": int(collider_index), "pose": pose, "frames": per_frame, "time_integrated_outward_transport": cumulative})
    return {
        "frames": frames,
        "colliders": colliders,
        "global_deep_maximum": global_deep_max,
        "global_boundary_maximum": global_boundary_max,
        "global_deep_voxel_volume_sum": global_deep_volume_sum,
        "time_integrated_outward_transport": transport_totals,
    }


def analyze_case(case_dir: Path, condition: str, contract: dict, preflight=False) -> dict:
    raw_path = case_dir / "raw.json"
    evidence_path = case_dir / "runner_evidence.json"
    failures = []
    if not raw_path.is_file() or not evidence_path.is_file():
        return {"condition": condition, "case_dir": str(case_dir), "classification": "absolute_safety_failure", "failures": ["raw_or_runner_evidence_missing"]}
    raw = _read(raw_path)
    evidence = _read(evidence_path)
    expected = contract["conditions"][condition]
    startup = raw.get("startup_liveness_gate") or {}
    readbacks = [sample.get("readback_boundary") for sample in raw.get("samples", []) if sample.get("readback_boundary")]
    if startup.get("classification") != "representative_ingestion" or not startup.get("readback_permitted"):
        classification = "startup_prerequisite_failure" if not readbacks else "operation_failure"
        return {"condition": condition, "case_dir": str(case_dir), "classification": classification, "failures": ["representative_startup_missing"], "startup": startup}
    if int(raw.get("point_payload", {}).get("active_point_count", -1)) != int(expected["expected_active_points"]):
        failures.append("active_point_count")
    source = raw.get("source_sums") or {}
    tolerance = float(contract["hard_gates"]["source_sum_relative_tolerance"])
    for channel, expected_sum in expected["expected_source_sums"].items():
        if not math.isclose(float(source.get(channel, float("nan"))), float(expected_sum), rel_tol=tolerance, abs_tol=1e-5):
            failures.append(f"{channel}_source_sum")
    required_readbacks = 1 if preflight else len(contract["readback_frames"])
    if len(readbacks) != required_readbacks:
        failures.append("public_readback_count")
    channel_gate = []
    for boundary in readbacks:
        if boundary.get("mode") != "p3_spatial_release" or boundary.get("operation_counts", {}).get("public_readback_calls") != 1:
            failures.append("readback_mode_or_count")
        if boundary.get("operation_counts", {}).get("numpy_asarray_calls") != 0:
            failures.append("unexpected_numpy_asarray")
        if boundary.get("weak_reference_alive_after_scope_count") != 0:
            failures.append("weak_reference_residual")
        for channel in CHANNELS:
            item = boundary.get("channels", {}).get(channel)
            valid = bool(item and item.get("source", {}).get("is_numpy_ndarray") and item.get("source", {}).get("data_pointer") and item.get("source", {}).get("dtype") == contract["channel_preflight"]["required_dtype"] and not item.get("temporary_nanovdb_present_after_collection"))
            channel_gate.append({"channel": channel, "valid": valid, "metadata": None if not item else item.get("source"), "private_bytes_delta": None if not item else item.get("private_bytes_delta")})
            if not valid:
                failures.append(f"{channel}_channel_gate")
    outcome = evidence.get("outcome") or {}
    lifecycle_ok = bool(outcome.get("functional_status") == "pass" and outcome.get("lifecycle_status") == "normal_exit" and evidence.get("process_exit_code") == 0 and not evidence.get("production_changed") and not evidence.get("fatal_lines") and not evidence.get("dump_inventory") and not evidence.get("automatic_upload_attempt_lines"))
    if not lifecycle_ok:
        failures.append("native_lifecycle_or_safety")
    spatial = None
    if not failures:
        try:
            spatial = _spatial_metrics(raw)
        except Exception as error:
            failures.append(f"spatial_analysis:{type(error).__name__}:{error}")
    if spatial and spatial["global_deep_maximum"]["velocity"] > float(contract["hard_gates"]["maximum_deep_velocity_m_s"]):
        failures.append("deep_velocity")
    profiles = {}
    for sample in raw.get("samples", []):
        boundary = sample.get("readback_boundary")
        if not boundary:
            continue
        profiles[str(sample["frame"])] = {
            channel: boundary["channels"][channel]["field"].get("field_profile")
            for channel in CHANNELS
        }
    guard = _guard_summary(case_dir)
    return {
        "condition": condition,
        "case_dir": str(case_dir),
        "classification": "representative_pass" if not failures else "operation_failure",
        "failures": failures,
        "startup": startup,
        "stage_sha256": raw.get("stage_sha256"),
        "payload_sha256": raw.get("point_payload", {}).get("payload_sha256"),
        "point_payload": raw.get("point_payload"),
        "source_sums": source,
        "active_blocks": [int(sample.get("active_blocks", 0)) for sample in raw.get("samples", [])],
        "readback_count": len(readbacks),
        "channel_gate": channel_gate,
        "spatial": spatial,
        "field_profiles": profiles,
        "stage_close_seconds": _stage_close_seconds(case_dir / "resource_markers.jsonl"),
        "runner_evidence": {"process_exit_code": evidence.get("process_exit_code"), "outcome": outcome, "fatal_count": len(evidence.get("fatal_lines", [])), "dump_count": len(evidence.get("dump_inventory", [])), "upload_count": len(evidence.get("automatic_upload_attempt_lines", []))},
        "guard": guard,
    }


def _ratio(numerator, denominator, floor):
    return float(numerator / max(float(denominator), float(floor)))


def evaluate_pair(s93: dict, s100: dict, contract: dict) -> dict:
    gates = contract["hard_gates"]
    floor = float(contract["materiality"]["zero_denominator_floor"])
    ratios = {"deep": {}, "opposite": {}}
    failures = []
    supply_ratio = float(s100["source_sums"]["fuel"]) / float(s93["source_sums"]["fuel"])
    if supply_ratio < float(gates["minimum_s100_to_s93_weighted_supply_ratio"]):
        failures.append("supply_improvement")
    for channel in ("temperature", "smoke", "fuel"):
        left = s93["spatial"]["global_deep_voxel_volume_sum"][channel]
        right = s100["spatial"]["global_deep_voxel_volume_sum"][channel]
        ratios["deep"][channel] = _ratio(right, left, floor)
        if ratios["deep"][channel] > float(gates["maximum_s100_to_s93_deep_scalar_excess_ratio"]):
            failures.append(f"deep_{channel}_material_worsening")
        left = s93["spatial"]["time_integrated_outward_transport"][channel]["opposite_top"]
        right = s100["spatial"]["time_integrated_outward_transport"][channel]["opposite_top"]
        ratios["opposite"][channel] = _ratio(right, left, floor)
        if ratios["opposite"][channel] > float(gates["maximum_s100_to_s93_opposite_transport_ratio"]):
            failures.append(f"opposite_{channel}_material_worsening")
    left_v = s93["spatial"]["global_deep_maximum"]["velocity"]
    right_v = s100["spatial"]["global_deep_maximum"]["velocity"]
    velocity_ratio = _ratio(right_v, left_v, float(gates["velocity_ratio_floor_m_s"]))
    if velocity_ratio > float(gates["maximum_s100_to_s93_deep_velocity_ratio_with_floor"]):
        failures.append("deep_velocity_material_worsening")
    return {"s93": s93["case_dir"], "s100": s100["case_dir"], "supply_ratio": supply_ratio, "ratios": ratios, "deep_velocity_ratio": velocity_ratio, "failures": failures, "pass": not failures}


def analyze_root(root: Path, contract_path: Path, offline_path: Path) -> dict:
    contract = _read(contract_path)
    offline = _read(offline_path)
    attempts = []
    for metadata_path in sorted(root.glob("formal/attempt*/attempt_metadata.json")):
        metadata = _read(metadata_path)
        case_dir = metadata_path.parent / metadata["label"]
        attempts.append({**metadata, **analyze_case(case_dir, metadata["condition"], contract)})
    preflights = []
    for metadata_path in sorted(root.glob("channel-preflight/channel_attempt*/attempt_metadata.json")):
        metadata = _read(metadata_path)
        preflights.append({**metadata, **analyze_case(metadata_path.parent / metadata["label"], metadata["condition"], contract, preflight=True)})
    pairs = []
    for sequence in range(1, 4):
        members = [item for item in attempts if item.get("sequence") == sequence and item.get("classification") == "representative_pass"]
        by_condition = {item["condition"]: item for item in members}
        if set(by_condition) == {"S93", "S100"}:
            pairs.append({"sequence": sequence, **evaluate_pair(by_condition["S93"], by_condition["S100"], contract)})
    representative = [item for item in attempts if item.get("classification") == "representative_pass"]
    hard_failures = [item for item in attempts if item.get("classification") not in ("representative_pass", "startup_prerequisite_failure")]
    startup_failures = [item for item in attempts if item.get("classification") == "startup_prerequisite_failure"]
    cross_run = {"pass": False, "relative_ranges": {}, "failures": []}
    if len(representative) == 6 and len(pairs) == 3 and all(pair["pass"] for pair in pairs):
        values = {
            "S93_deep_velocity": [item["spatial"]["global_deep_maximum"]["velocity"] for item in representative if item["condition"] == "S93"],
            "S100_deep_velocity": [item["spatial"]["global_deep_maximum"]["velocity"] for item in representative if item["condition"] == "S100"],
            "deep_temperature_ratio": [pair["ratios"]["deep"]["temperature"] for pair in pairs],
            "deep_smoke_ratio": [pair["ratios"]["deep"]["smoke"] for pair in pairs],
            "opposite_temperature_ratio": [pair["ratios"]["opposite"]["temperature"] for pair in pairs],
            "opposite_smoke_ratio": [pair["ratios"]["opposite"]["smoke"] for pair in pairs],
        }
        limit = float(contract["hard_gates"]["maximum_run_relative_range"])
        for name, series in values.items():
            denominator = max(abs(float(np.mean(series))), float(contract["materiality"]["zero_denominator_floor"]))
            relative = float((max(series) - min(series)) / denominator)
            cross_run["relative_ranges"][name] = relative
            if relative > limit:
                cross_run["failures"].append(name)
        cross_run["pass"] = not cross_run["failures"]
    preflight_pass = len(preflights) >= 1 and preflights[-1]["classification"] == "representative_pass"
    qualified = bool(preflight_pass and len(representative) == 6 and len(pairs) == 3 and all(pair["pass"] for pair in pairs) and cross_run["pass"] and not hard_failures)
    return {
        "schema": "campfire.phase6fo.supply-comparison-report.v1",
        "phase": "phase6fo",
        "status": "qualified_numeric" if qualified else "in_progress_or_safe_stop",
        "contract_sha256": _sha(contract_path),
        "offline_sha256": _sha(offline_path),
        "history_reclassified": False,
        "prior_population_reused": False,
        "channel_preflight": preflights,
        "channel_preflight_pass": preflight_pass,
        "attempts": attempts,
        "representative_processes": len(representative),
        "startup_prerequisite_failures": len(startup_failures),
        "nonreplaceable_failures": len(hard_failures),
        "pairs": pairs,
        "cross_run": cross_run,
        "numeric_qualified": qualified,
        "visual_required": qualified,
        "offline": offline,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--offline", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = analyze_root(args.root.resolve(), args.contract.resolve(), args.offline.resolve())
    _write(args.output.resolve(), report)
    print(f"Phase 6FO report: representative={report['representative_processes']} qualified={report['numeric_qualified']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
