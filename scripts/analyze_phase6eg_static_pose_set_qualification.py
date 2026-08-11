"""Evaluate the predeclared Phase 6EG representative static-pose contract."""

from __future__ import annotations

import argparse
import html
import json
import math
import shutil
import sys
import zipfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import analyze_phase6ef_static_y40_qualification as phase6ef  # noqa: E402


FRAMES = (60, 120, 180, 200)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def pose_from_condition(condition: str) -> tuple[str, bool]:
    if condition.endswith("_on"):
        return condition[:-3], True
    if condition.endswith("_off"):
        return condition[:-4], False
    raise ValueError(f"invalid Phase 6EG condition: {condition}")


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0.0:
        return None
    value = float(numerator) / float(denominator)
    if not math.isfinite(value):
        raise ValueError("non-finite Phase 6EG ratio")
    return value


def collect(root: Path, contract: dict) -> tuple[dict, dict]:
    thresholds = tuple(float(value) for value in contract["thresholds"]["reported_velocity_thresholds_m_s"])
    samples: dict = {}
    metadata: dict = {}
    for run_index, order in enumerate(contract["formal_order"], start=1):
        run_key = str(run_index)
        samples[run_key] = {}
        metadata[run_key] = {}
        for condition in order:
            samples[run_key][condition] = {}
            metadata[run_key][condition] = {}
            for frame in FRAMES:
                path = root / "spatial" / f"run_{run_index}" / condition / f"{condition}_f{frame:04d}_velocity.npz"
                if not path.is_file():
                    raise FileNotFoundError(path)
                stats, info = phase6ef.sample_stats(path, thresholds)
                samples[run_key][condition][str(frame)] = stats
                metadata[run_key][condition][str(frame)] = info
    return samples, metadata


def collect_condition(root: Path, contract: dict, run_index: int, condition: str) -> tuple[dict, dict]:
    thresholds = tuple(float(value) for value in contract["thresholds"]["reported_velocity_thresholds_m_s"])
    samples = {}
    metadata = {}
    for frame in FRAMES:
        path = root / "spatial" / f"run_{run_index}" / condition / f"{condition}_f{frame:04d}_velocity.npz"
        if not path.is_file():
            raise FileNotFoundError(path)
        stats, info = phase6ef.sample_stats(path, thresholds)
        samples[str(frame)] = stats
        metadata[str(frame)] = info
    return samples, metadata


def evaluate_incremental(root: Path, contract: dict, run_index: int, condition: str) -> dict:
    pose, collision_on = pose_from_condition(condition)
    if pose not in contract["poses"]:
        raise ValueError(f"undeclared Phase 6EG pose: {pose}")
    if condition not in contract["formal_order"][run_index - 1]:
        raise ValueError(f"condition is not in frozen run order: run={run_index} condition={condition}")
    current, current_metadata = collect_condition(root, contract, run_index, condition)
    paired_condition = f"{pose}_{'off' if collision_on else 'on'}"
    paired_folder = root / "spatial" / f"run_{run_index}" / paired_condition
    pair_available = all(
        (paired_folder / f"{paired_condition}_f{frame:04d}_velocity.npz").is_file()
        for frame in FRAMES
    )
    paired = collect_condition(root, contract, run_index, paired_condition)[0] if pair_available else None
    limit = float(contract["thresholds"]["existing_velocity_limit_m_s"])
    positive = float(contract["thresholds"]["collision_off_positive_minimum_m_s"])
    suppression = float(contract["thresholds"]["on_to_off_deep_maximum_ratio"])
    identity_positive = float(contract["thresholds"]["identity_only_comparison_minimum_off_m_s"])
    identity_ratio_minimum = float(contract["thresholds"]["identity_only_on_to_off_minimum_ratio"])
    checks = []
    for frame in FRAMES:
        key = str(frame)
        item = current[key]
        predicates = (
            {
                "on_deep_at_or_below_limit": item["deep_interior"]["maximum"] <= limit,
                "on_center_at_or_below_limit": item["center_axis_near"]["maximum"] <= limit,
            }
            if collision_on
            else {
                "off_deep_at_or_above_positive_minimum": item["deep_interior"]["maximum"] >= positive,
                "off_center_at_or_above_positive_minimum": item["center_axis_near"]["maximum"] >= positive,
            }
        )
        pair_values = None
        if paired is not None:
            on = item if collision_on else paired[key]
            off = paired[key] if collision_on else item
            deep_ratio = _ratio(on["deep_interior"]["maximum"], off["deep_interior"]["maximum"])
            identity_ratio = _ratio(on["axis_only"]["maximum"], off["axis_only"]["maximum"])
            identity_comparable = off["axis_only"]["maximum"] >= identity_positive
            predicates["on_over_off_deep_ratio_at_or_below_limit"] = deep_ratio is not None and deep_ratio <= suppression
            if identity_comparable:
                predicates["identity_only_not_stale_suppressed"] = identity_ratio is not None and identity_ratio >= identity_ratio_minimum
            pair_values = {
                "deep_ratio": deep_ratio,
                "identity_ratio": identity_ratio,
                "identity_comparable": identity_comparable,
            }
        checks.append({
            "frame": frame,
            "predicates": predicates,
            "pair_values": pair_values,
            "pass": all(predicates.values()),
        })
    return {
        "schema": "campfire.phase6eg.incremental-numeric-gate.v1",
        "run": run_index,
        "condition": condition,
        "pose": pose,
        "collision_on": collision_on,
        "sample_count": len(current),
        "pair_available": pair_available,
        "samples": current,
        "sample_files": current_metadata,
        "checks": checks,
        "pass": len(current) == len(FRAMES) and all(check["pass"] for check in checks),
    }


def evaluate(samples: dict, contract: dict) -> tuple[dict, list[dict], dict]:
    limit = float(contract["thresholds"]["existing_velocity_limit_m_s"])
    positive = float(contract["thresholds"]["collision_off_positive_minimum_m_s"])
    suppression = float(contract["thresholds"]["on_to_off_deep_maximum_ratio"])
    identity_positive = float(contract["thresholds"]["identity_only_comparison_minimum_off_m_s"])
    identity_ratio_minimum = float(contract["thresholds"]["identity_only_on_to_off_minimum_ratio"])
    checks: list[dict] = []
    ratios: dict = {}
    pose_summary: dict = {}
    pose_names = tuple(contract["poses"])
    for pose in pose_names:
        pose_summary[pose] = {
            "worst_on_deep_m_s": 0.0,
            "worst_on_center_m_s": 0.0,
            "minimum_off_deep_m_s": math.inf,
            "minimum_off_center_m_s": math.inf,
            "worst_deep_ratio": 0.0,
            "identity_only_comparable_samples": 0,
            "worst_identity_only_on_over_off_ratio": 0.0,
            "boundary_band_worst_maximum_m_s": 0.0,
        }
    for run_index in range(1, 4):
        run_key = str(run_index)
        ratios[run_key] = {}
        for pose in pose_names:
            on_name, off_name = f"{pose}_on", f"{pose}_off"
            ratios[run_key][pose] = {}
            for frame in FRAMES:
                frame_key = str(frame)
                on = samples[run_key][on_name][frame_key]
                off = samples[run_key][off_name][frame_key]
                values = {
                    "on_deep": on["deep_interior"]["maximum"],
                    "on_center": on["center_axis_near"]["maximum"],
                    "off_deep": off["deep_interior"]["maximum"],
                    "off_center": off["center_axis_near"]["maximum"],
                    "on_identity_only": on["axis_only"]["maximum"],
                    "off_identity_only": off["axis_only"]["maximum"],
                }
                deep_ratio = _ratio(values["on_deep"], values["off_deep"])
                identity_ratio = _ratio(values["on_identity_only"], values["off_identity_only"])
                identity_comparable = values["off_identity_only"] >= identity_positive
                ratios[run_key][pose][frame_key] = {
                    "on_over_off_deep_maximum": deep_ratio,
                    "on_over_off_identity_only_maximum": identity_ratio,
                    "identity_only_comparable": identity_comparable,
                    "values_m_s": values,
                }
                predicates = {
                    "on_deep_at_or_below_limit": values["on_deep"] <= limit,
                    "on_center_at_or_below_limit": values["on_center"] <= limit,
                    "off_deep_at_or_above_positive_minimum": values["off_deep"] >= positive,
                    "off_center_at_or_above_positive_minimum": values["off_center"] >= positive,
                    "on_over_off_deep_ratio_at_or_below_limit": deep_ratio is not None and deep_ratio <= suppression,
                }
                if identity_comparable:
                    predicates["identity_only_not_stale_suppressed"] = identity_ratio is not None and identity_ratio >= identity_ratio_minimum
                    pose_summary[pose]["identity_only_comparable_samples"] += 1
                    pose_summary[pose]["worst_identity_only_on_over_off_ratio"] = max(
                        pose_summary[pose]["worst_identity_only_on_over_off_ratio"], identity_ratio or 0.0
                    )
                checks.append({"run": run_index, "pose": pose, "frame": frame, "predicates": predicates, "pass": all(predicates.values())})
                summary = pose_summary[pose]
                summary["worst_on_deep_m_s"] = max(summary["worst_on_deep_m_s"], values["on_deep"])
                summary["worst_on_center_m_s"] = max(summary["worst_on_center_m_s"], values["on_center"])
                summary["minimum_off_deep_m_s"] = min(summary["minimum_off_deep_m_s"], values["off_deep"])
                summary["minimum_off_center_m_s"] = min(summary["minimum_off_center_m_s"], values["off_center"])
                summary["worst_deep_ratio"] = max(summary["worst_deep_ratio"], deep_ratio or 0.0)
                summary["boundary_band_worst_maximum_m_s"] = max(
                    summary["boundary_band_worst_maximum_m_s"],
                    on["boundary_0_to_1_voxel"]["maximum"],
                    off["boundary_0_to_1_voxel"]["maximum"],
                )
    for pose, summary in pose_summary.items():
        summary["minimum_off_deep_m_s"] = float(summary["minimum_off_deep_m_s"])
        summary["minimum_off_center_m_s"] = float(summary["minimum_off_center_m_s"])
        stale_mode = contract["stale_transform_contract"].get(pose, contract["stale_transform_contract"]["other_poses"])
        summary["stale_transform_mode"] = stale_mode
        if pose not in ("P0_identity", "P2_roll_x17"):
            available = summary["identity_only_comparable_samples"] > 0
            checks.append({"pose": pose, "scope": "aggregate_stale_transform", "predicates": {"identity_only_comparison_available": available}, "pass": available})
    return pose_summary, checks, ratios


def validate_processes(root: Path, contract: dict) -> tuple[list[dict], list[dict]]:
    outcomes = []
    checks = []
    fuel_expected = float(contract["fixed_environment"]["emitter_fuel"])
    fuel_tolerance = float(contract["thresholds"]["fuel_absolute_tolerance"])
    for run_index, order in enumerate(contract["formal_order"], start=1):
        for condition in order:
            case = root / "formal" / f"run_{run_index}" / condition
            evidence = load_json(case / "runner_evidence.json")
            raw = load_json(case / "raw.json")
            outcome = {
                "run": run_index,
                "condition": condition,
                "functional_status": evidence["outcome"]["functional_status"],
                "lifecycle_status": evidence["outcome"]["lifecycle_status"],
                "exit_code": evidence["process_exit_code"],
                "active_blocks_final": raw["active_blocks_final"],
                "source_fuel": raw["stage_audit"]["emitter"]["fuel"],
                "fatal_count": len(evidence["fatal_lines"]),
                "dump_count": len(evidence["dump_inventory"]),
                "upload_attempt_count": len(evidence["automatic_upload_attempt_lines"]),
                "residual": evidence["outcome"]["lifecycle_status"] != "normal_exit",
            }
            predicates = {
                "functional_pass": outcome["functional_status"] == "pass",
                "normal_os_exit": outcome["lifecycle_status"] == "normal_exit" and outcome["exit_code"] == 0,
                "active_blocks_positive": outcome["active_blocks_final"] > 0,
                "source_fuel_preserved": abs(outcome["source_fuel"] - fuel_expected) <= fuel_tolerance,
                "fatal_dump_upload_residual_zero": outcome["fatal_count"] == 0 and outcome["dump_count"] == 0 and outcome["upload_attempt_count"] == 0 and not outcome["residual"],
                "production_unchanged": not evidence["production_changed"],
                "crash_registry_unchanged": evidence["relevant_crash_registry_unchanged"],
            }
            outcome["pass"] = all(predicates.values())
            checks.append({"run": run_index, "condition": condition, "predicates": predicates, "pass": outcome["pass"]})
            outcomes.append(outcome)
    return outcomes, checks


def validate_preflight(root: Path, contract: dict) -> tuple[dict, list[dict]]:
    report = load_json(root / "preflight.json")
    checks = []
    for pose, declared in contract["poses"].items():
        actual = report["poses"][pose]
        matrix_equal = bool(
            phase6ef.np.allclose(
                actual["authored_local_to_world_matrix"],
                declared["matrix"],
                rtol=0.0,
                atol=1.0e-12,
            )
        )
        checks.append({"pose": pose, "predicates": {"preflight_status_ok": report["status"] == "ok", "all_offline_pose_gates_pass": all(actual["gates"].values()), "final_matrix_matches_contract": matrix_equal}, "pass": report["status"] == "ok" and all(actual["gates"].values()) and matrix_equal})
    return report, checks


def write_svg(path: Path, pose_summary: dict, qualified: bool) -> None:
    poses = list(pose_summary)
    width, height = 1160, 510
    plot_left, plot_top, plot_width, plot_height = 105, 90, 980, 300
    maximum = max(max(item["minimum_off_deep_m_s"], item["boundary_band_worst_maximum_m_s"], 0.1) for item in pose_summary.values())
    def y(value: float) -> float:
        return plot_top + plot_height - (min(value, maximum) / maximum) * plot_height
    elements = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">', '<rect width="100%" height="100%" fill="#101820"/>', '<text x="55" y="42" fill="#f7f4e9" font-size="25" font-family="Segoe UI">Phase 6EG — representative static Mesh collision poses</text>', f'<text x="55" y="70" fill="#8ed1fc" font-size="15" font-family="Segoe UI">qualification: {str(qualified).lower()} · exact authored-Mesh distance · velocity m/s</text>']
    for step in range(6):
        value = maximum * step / 5
        yy = y(value)
        elements.append(f'<line x1="{plot_left}" y1="{yy:.1f}" x2="{plot_left+plot_width}" y2="{yy:.1f}" stroke="#31424f"/>')
        elements.append(f'<text x="96" y="{yy+5:.1f}" text-anchor="end" fill="#aab7c4" font-size="12">{value:.2f}</text>')
    group = plot_width / len(poses)
    for index, pose in enumerate(poses):
        item = pose_summary[pose]
        x = plot_left + index * group + group * 0.18
        bars = ((item["worst_on_deep_m_s"], "#55d6be"), (item["minimum_off_deep_m_s"], "#ff8f70"), (item["boundary_band_worst_maximum_m_s"], "#f7c948"))
        for offset, (value, color) in enumerate(bars):
            xx = x + offset * 26
            yy = y(value)
            elements.append(f'<rect x="{xx:.1f}" y="{yy:.1f}" width="20" height="{plot_top+plot_height-yy:.1f}" fill="{color}"/>')
        elements.append(f'<text x="{x+28:.1f}" y="415" text-anchor="middle" fill="#f7f4e9" font-size="12">{html.escape(pose)}</text>')
    elements.extend(['<rect x="600" y="452" width="14" height="14" fill="#55d6be"/><text x="621" y="464" fill="#dce6ed" font-size="13">ON deep worst</text>', '<rect x="745" y="452" width="14" height="14" fill="#ff8f70"/><text x="766" y="464" fill="#dce6ed" font-size="13">OFF deep minimum</text>', '<rect x="925" y="452" width="14" height="14" fill="#f7c948"/><text x="946" y="464" fill="#dce6ed" font-size="13">boundary worst</text>', '</svg>'])
    path.write_text("".join(elements), encoding="utf-8")


def archive_samples(root: Path, destination: Path, contract: dict) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for run_index, order in enumerate(contract["formal_order"], start=1):
            for condition in order:
                folder = root / "spatial" / f"run_{run_index}" / condition
                for path in sorted(folder.glob("*.npz")):
                    archive.write(path, path.relative_to(root))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--svg", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--check-run", type=int)
    parser.add_argument("--check-condition")
    parser.add_argument("--check-output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    contract = load_json(args.contract.resolve())
    if args.check_condition is not None:
        if args.check_run not in (1, 2, 3) or args.check_output is None:
            parser.error("--check-condition requires --check-run 1..3 and --check-output")
        payload = evaluate_incremental(root, contract, args.check_run, args.check_condition)
        args.check_output.parent.mkdir(parents=True, exist_ok=True)
        args.check_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        return 0 if payload["pass"] else 2
    if args.output is None or args.svg is None or args.archive is None:
        parser.error("full qualification requires --output, --svg, and --archive")
    preflight, preflight_checks = validate_preflight(root, contract)
    samples, metadata = collect(root, contract)
    pose_summary, numeric_checks, ratios = evaluate(samples, contract)
    outcomes, process_checks = validate_processes(root, contract)
    all_checks = preflight_checks + numeric_checks + process_checks
    qualified = all(item["pass"] for item in all_checks) and len(outcomes) == 36
    payload = {
        "schema": "campfire.phase6eg.static-pose-set-qualification-report.v1",
        "phase": "phase6eg",
        "qualified": qualified,
        "scope": contract["scope_if_pass"] if qualified else "not qualified",
        "contract_path": str(args.contract.resolve()),
        "contract_sha256": phase6ef.sha256(args.contract.resolve()),
        "phase6ef_method_reused": {"sample_stats": True, "region_masks": True, "summarize": True},
        "public_flow_occupancy_mask_available": False,
        "preflight": preflight,
        "pose_summary": pose_summary,
        "ratios": ratios,
        "samples": samples,
        "sample_files": metadata,
        "process_outcomes": outcomes,
        "checks": all_checks,
        "failed_checks": [item for item in all_checks if not item["pass"]],
        "production_changed": False,
        "not_qualified": ["all SO(3)", "dynamic transform", "RenderSurface", "PhysX sharing", "production log layout", "20-log performance"],
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if qualified:
        write_svg(args.svg, pose_summary, qualified)
        archive_samples(root, args.archive, contract)
    else:
        for path in (args.svg, args.archive):
            if path.exists():
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
    return 0 if qualified else 2


if __name__ == "__main__":
    raise SystemExit(main())
