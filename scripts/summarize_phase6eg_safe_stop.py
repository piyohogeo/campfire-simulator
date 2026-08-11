"""Create a bounded, non-qualification summary after a Phase 6EG safe stop."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import analyze_phase6ef_static_y40_qualification as phase6ef  # noqa: E402


FRAMES = (60, 120, 180, 200)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    contract = load(args.contract.resolve())
    safe_stop = load(root / "safe_stop.json")
    completed = [entry.split("/", 1) for entry in safe_stop["completed"]]
    completed_keys = {(int(run[4:] if run.startswith("run_") else run), condition) for run, condition in completed}
    incomplete = []
    for raw_path in sorted((root / "formal").glob("run_*/*/raw.json")):
        run_name = raw_path.parents[1].name
        run_index = int(run_name[4:] if run_name.startswith("run_") else run_name)
        condition = raw_path.parent.name
        if (run_index, condition) not in completed_keys:
            raw = load(raw_path)
            incomplete.append(
                {
                    "run": run_index,
                    "condition": condition,
                    "raw_status": raw.get("status"),
                    "last_lifecycle_marker": raw.get("lifecycle_marker"),
                    "active_blocks_final": raw.get("active_blocks_final"),
                    "source_fuel": raw.get("stage_audit", {}).get("emitter", {}).get("fuel"),
                    "runner_evidence_present": (raw_path.parent / "runner_evidence.json").is_file(),
                }
            )
    thresholds = tuple(float(value) for value in contract["thresholds"]["reported_velocity_thresholds_m_s"])
    limit = float(contract["thresholds"]["existing_velocity_limit_m_s"])
    positive = float(contract["thresholds"]["collision_off_positive_minimum_m_s"])
    suppression = float(contract["thresholds"]["on_to_off_deep_maximum_ratio"])
    complete_pairs = []
    for pose in contract["poses"]:
        if (1, f"{pose}_on") not in completed_keys or (1, f"{pose}_off") not in completed_keys:
            continue
        frames = []
        for frame in FRAMES:
            on_path = root / "spatial" / "run_1" / f"{pose}_on" / f"{pose}_on_f{frame:04d}_velocity.npz"
            off_path = root / "spatial" / "run_1" / f"{pose}_off" / f"{pose}_off_f{frame:04d}_velocity.npz"
            on, on_file = phase6ef.sample_stats(on_path, thresholds)
            off, off_file = phase6ef.sample_stats(off_path, thresholds)
            ratio = on["deep_interior"]["maximum"] / off["deep_interior"]["maximum"] if off["deep_interior"]["maximum"] > 0.0 else None
            gates = {
                "on_deep_at_or_below_limit": on["deep_interior"]["maximum"] <= limit,
                "on_center_at_or_below_limit": on["center_axis_near"]["maximum"] <= limit,
                "off_deep_at_or_above_positive_minimum": off["deep_interior"]["maximum"] >= positive,
                "off_center_at_or_above_positive_minimum": off["center_axis_near"]["maximum"] >= positive,
                "on_over_off_ratio_at_or_below_limit": ratio is not None and ratio <= suppression,
            }
            frames.append(
                {
                    "frame": frame,
                    "on": on,
                    "off": off,
                    "on_over_off_deep_maximum_ratio": ratio,
                    "gates": gates,
                    "diagnostic_pass": all(gates.values()),
                    "files": {"on": on_file, "off": off_file},
                }
            )
        complete_pairs.append(
            {
                "pose": pose,
                "run_count": 1,
                "frames": frames,
                "diagnostic_pass": all(frame["diagnostic_pass"] for frame in frames),
                "qualification": False,
                "reason": "only one of three predeclared independent runs completed",
            }
        )
    match = re.search(r"peak_private_bytes=(\d+)", safe_stop.get("error", ""))
    payload = {
        "schema": "campfire.phase6eg.safe-stop-summary.v1",
        "phase": "phase6eg",
        "status": "safe_stop",
        "qualified": False,
        "formal_population_accepted": False,
        "reason": "the P3 Z33 collision-ON helper crossed the predeclared 512 MiB Private Bytes guard before stage-open/functional evidence completed",
        "safe_stop": safe_stop,
        "safe_stop_condition_recording": {
            "recorded_value": safe_stop.get("condition"),
            "recorded_value_is_last_completed_not_failed": True,
            "failed_condition_from_incomplete_raw": incomplete[0]["condition"] if len(incomplete) == 1 else None,
            "runner_corrected_for_future_roots": True,
        },
        "incomplete_conditions": incomplete,
        "resource_guard": {
            "limit_bytes": 512 * 1024 * 1024,
            "observed_peak_private_bytes": int(match.group(1)) if match else None,
            "target_process_tree_absent_after_abort": True,
            "automatic_retry": False,
        },
        "preflight": load(root / "preflight.json"),
        "completed_normal_exit_process_count": len(completed_keys),
        "planned_process_count": 36,
        "completed_pose_pairs_diagnostic_only": complete_pairs,
        "partial_numeric_checks_pass": bool(complete_pairs) and all(pair["diagnostic_pass"] for pair in complete_pairs),
        "formal_svg_generated": False,
        "formal_npz_archive_generated": False,
        "production_app_sha256_before": safe_stop["production_app_sha256_before"],
        "production_app_sha256_after": safe_stop["production_app_sha256_after"],
        "production_changed": safe_stop["production_app_sha256_before"] != safe_stop["production_app_sha256_after"],
        "interpretation": {
            "P0_P1_P2_qualified": False,
            "P3_collision_behavior_assessed": False,
            "P3_failure_is_collision_failure": False,
            "all_SO3_qualified": False,
            "next_minimum_confirmation": "classify why the existing guarded helper exceeded 512 MiB during P3 stage-open without rerunning the condition automatically",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
