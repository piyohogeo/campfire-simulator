"""Publish the bounded Phase 6EQ numeric safe stop without accepting partial data."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _deep_rows(directory: Path, collider: int, channel: str) -> list[dict]:
    rows: list[dict] = []
    for path in sorted((directory / "spatial" / f"collider_{collider}").glob(f"*_{channel}.npz")):
        with np.load(path) as archive:
            values = archive["magnitude"].astype(np.float64)
            depth = archive["mesh_distance_voxels"].astype(np.float64)
            selected = values[depth < -1.0]
            rows.append(
                {
                    "frame": int(archive["frame"][0]),
                    "voxel_count": int(selected.size),
                    "mean": float(selected.mean()) if selected.size else 0.0,
                    "p95": float(np.quantile(selected, 0.95)) if selected.size else 0.0,
                    "maximum": float(selected.max()) if selected.size else 0.0,
                }
            )
    return rows


def _condition_summary(root: Path, relative: Path) -> dict:
    directory = root / relative
    raw = _read(directory / "raw.json")
    evidence = _read(directory / "runner_evidence.json")
    gate = _read(directory / "incremental_gate.json")
    guard = _read(root / "runner-logs" / ("_".join(relative.parts) + ".guard.json"))
    return {
        "path": relative.as_posix(),
        "policy": gate["policy"],
        "collision": gate["collision"],
        "incremental_gate_passed": gate["passed"],
        "failed_gates": gate["failed_gates"],
        "point_retention": gate["point_retention"],
        "weighted_supply": gate["weighted_supply"],
        "active_other_support_intersections": gate["active_other_support_intersections"],
        "other_deep_maximum": gate["other_deep_maximum"],
        "other_collider_deep_by_frame": {
            channel: _deep_rows(directory, 1, channel)
            for channel in ("velocity", "temperature", "smoke")
        },
        "active_blocks": gate["active_blocks"],
        "external_ignition_frame": gate["external_ignition_frame"],
        "external_vertical_extent_m": gate["external_vertical_extent_m"],
        "probe_status": raw["status"],
        "last_lifecycle_marker": raw["lifecycle_marker"],
        "functional_status": evidence["outcome"]["functional_status"],
        "lifecycle_status": evidence["outcome"]["lifecycle_status"],
        "os_process_normal_exit": evidence["outcome"]["os_process_normal_exit"],
        "fatal_count": len(evidence["fatal_lines"]),
        "dump_count": len(evidence["dump_inventory"]),
        "automatic_upload_attempt_count": len(evidence["automatic_upload_attempt_lines"]),
        "resource_peaks_bytes": guard["peaks"],
        "machine_minima_bytes": guard["machine_minima"],
        "cleanup_remaining_count": len(guard["observed_process_cleanup"]["remaining"]),
    }


def _selected_geometry(offline: dict, contract: dict) -> list[dict]:
    result = []
    for policy in ("strict_all", "allow_self_support", "allow_self_center"):
        offset = float(contract["policies"][policy]["selected_offset_m"])
        row = next(
            item
            for item in offline["rows"]
            if item["scenario"] == "production_four"
            and item["policy"] == policy
            and float(item["offset_m"]) == offset
        )
        result.append(
            {
                "policy": policy,
                "offset_m": offset,
                "point_count": row["point_count"],
                "active_point_count": row["active_point_count"],
                "point_retention": row["point_retention"],
                "weighted_supply": row["weighted_supply"],
                "self_center_inside_count": row["self_center_inside_count"],
                "other_center_inside_count": row["other_center_inside_count"],
                "self_support_intersection_count": row["self_support_intersection_count"],
                "other_support_intersection_count": row["other_support_intersection_count"],
                "active_other_support_intersection_count": row[
                    "active_other_support_intersection_count"
                ],
                "disable_reason_counts": row["disable_reason_counts"],
            }
        )
    return result


def _write_svg(report: dict, path: Path) -> None:
    geometry = report["production_four_selected_geometry"]
    labels = {"strict_all": "all overlap forbidden", "allow_self_support": "self support allowed", "allow_self_center": "self center allowed"}
    colors = ["#60a5fa", "#f59e0b", "#34d399"]
    bars = []
    for index, row in enumerate(geometry):
        y = 390 + index * 72
        width = 500 * float(row["weighted_supply"]["fuel"]["retention"])
        bars.append(
            f'<text x="55" y="{y}" class="label">{labels[row["policy"]]}</text>'
            f'<rect x="430" y="{y-24}" width="{width:.1f}" height="25" rx="5" fill="{colors[index]}"/>'
            f'<text x="950" y="{y}" class="mono">{100*row["point_retention"]:.2f}% · other overlap disabled {row["other_support_intersection_count"]}</text>'
        )
    failed = report["safe_stop"]["failed_condition"]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="700" viewBox="0 0 1400 700"><style>.title{{font:700 31px system-ui;fill:#f8fafc}}.head{{font:700 22px system-ui;fill:#e2e8f0}}.text{{font:17px system-ui;fill:#cbd5e1}}.label{{font:16px system-ui;fill:#dbeafe}}.mono{{font:16px ui-monospace;fill:#bae6fd}}</style><rect width="100%" height="100%" fill="#08111f"/><text x="55" y="58" class="title">Phase 6EQ — self-Collider tolerance safe stop</text><rect x="55" y="96" width="1290" height="210" rx="16" fill="#3a1f24"/><text x="85" y="140" class="head">Formal population stopped at 2 / 24; accepted population = 0</text><text x="85" y="182" class="text">Collision OFF control passed. The first strict Collision ON condition failed the predeclared scalar deep-interior gates.</text><text x="85" y="224" class="mono">other deep velocity {failed['other_deep_maximum']['velocity']:.3e} m/s · temperature {failed['other_deep_maximum']['temperature']:.3e} · smoke {failed['other_deep_maximum']['smoke']:.3e}</text><text x="85" y="266" class="text">normal OS exit · fatal/dump/upload/residual = 0 · no retry · visual population not started</text><text x="55" y="350" class="head">Offline production-four supply retention at each predeclared representative offset</text>{''.join(bars)}<text x="55" y="635" class="text">Allowing self overlap did not exceed the 75.56% conservative baseline because other-log support intersections dominate.</text><text x="55" y="670" class="mono">production/defaults unchanged · contract frozen · Phase 6EP artifacts untouched</text></svg>'''
    path.write_text(svg, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--phase6ep-report", required=True, type=Path)
    parser.add_argument("--production-app", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    args = parser.parse_args()

    contract = _read(args.contract)
    offline = _read(args.root / "offline_geometry.json")
    sweep = _read(args.root / "runtime_offset_sweep.json")
    collision_off = _condition_summary(
        args.root, Path("formal/run_1/lower_upper/collision_off")
    )
    failed = _condition_summary(args.root, Path("formal/run_1/lower_upper/strict_all"))
    if not collision_off["incremental_gate_passed"] or failed["incremental_gate_passed"]:
        raise ValueError("unexpected Phase 6EQ safe-stop boundary")
    if failed["failed_gates"] != ["other_deep_temperature", "other_deep_smoke"]:
        raise ValueError("unexpected Phase 6EQ failed gates")

    guards = sorted((args.root / "runner-logs").glob("*.guard.json"))
    guard_rows = [_read(path) for path in guards]
    if any(row["status"] != "ok" or not row["process_absent"] for row in guard_rows):
        raise ValueError("resource/lifecycle guard did not finish cleanly")

    report = {
        "schema": "campfire.phase6eq.self-collider-safe-stop.v1",
        "phase": "phase6eq",
        "status": "safe_stop",
        "overall_qualified": False,
        "formal_population_accepted": False,
        "formal_processes_completed_as_partial_evidence": 2,
        "formal_processes_required": int(contract["formal_process_count"]),
        "runtime_sweep_processes_completed": len(sweep["rows"]),
        "runtime_sweep_processes_required": int(contract["runtime_offset_sweep_process_count"]),
        "contract_sha256": _sha256(args.contract),
        "phase6ep_report_sha256": _sha256(args.phase6ep_report),
        "production_app_sha256": _sha256(args.production_app),
        "production_changed": False,
        "phase6ep_artifacts_reclassified_or_overwritten": False,
        "safe_stop": {
            "active_condition": "formal/run_1/lower_upper/strict_all",
            "reason": "predeclared other-Collider deep temperature and smoke hard gates failed",
            "failed_condition": failed,
            "preceding_control": collision_off,
            "automatic_retry": False,
            "later_condition_started": False,
            "visual_population_started": False,
            "videos_encoded_or_published": 0,
            "latest_demo_changed": False,
        },
        "runtime_offset_sweep": sweep,
        "production_four_selected_geometry": _selected_geometry(offline, contract),
        "interpretation": {
            "confirmed": [
                "self/other signed distance and support-sphere causes are separated per point",
                "the selected policies keep active other-log support intersections at zero",
                "strict collision suppresses other-log deep velocity to zero in the completed condition",
                "other-log deep temperature and smoke remain nonzero and fail the frozen contract",
                "self-overlap allowance at the chosen lower offsets does not exceed the 75.56 percent conservative production-four retention",
            ],
            "not_confirmed": [
                "a production recommendation for self-overlap allowance",
                "three-run reproducibility",
                "visual flame lift or absence of reverse-side emergence",
                "a scalar occupancy interpretation for Flow Collision",
            ],
            "next_one_variable_question": "separate collision scalar transport from velocity occlusion using control-relative, spatially resolved temperature/smoke criteria in a newly approved contract; do not relax this frozen result post hoc",
        },
        "scope": "default-off production-neutral diagnostic; no production integration",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    _write_svg(report, args.svg)
    print("Phase 6EQ safe-stop summary written")


if __name__ == "__main__":
    main()
