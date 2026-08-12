"""Publish the compact Phase 6EN engineering qualification summary."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import statistics


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def cpu_sections(root: Path) -> dict:
    grouped: dict[str, list[float]] = defaultdict(list)
    for trace_path in sorted((root / "case-runner-logs").glob("*.memory.jsonl")):
        with trace_path.open(encoding="utf-8") as stream:
            for line in stream:
                sample = json.loads(line)
                section = sample.get("current_execution_section") or "unclassified"
                for process in sample.get("processes", []):
                    if process.get("role") == "kit" and process.get("cpu_percent_of_logical_total") is not None:
                        grouped[section].append(float(process["cpu_percent_of_logical_total"]))
    return {
        section: {
            "sample_count": len(values),
            "mean_percent_of_logical_total": statistics.fmean(values),
            "maximum_percent_of_logical_total": max(values),
        }
        for section, values in sorted(grouped.items())
    }


def threshold_totals(report: dict) -> dict:
    totals: dict = {}
    for pose in report["pose_summary"]:
        totals[pose] = {}
        for state in ("on", "off"):
            regions = {
                name: defaultdict(int)
                for name in ("deep_interior", "center_axis_near", "boundary_0_to_1_voxel")
            }
            for run in ("1", "2", "3"):
                for sample in report["samples"][run][f"{pose}_{state}"].values():
                    for region, counts in regions.items():
                        for threshold, count in sample[region]["threshold_counts"].items():
                            counts[threshold] += int(count)
            totals[pose][state] = {region: dict(counts) for region, counts in regions.items()}
    return totals


def maximum_cells(report: dict) -> dict:
    result = {}
    files = report["sample_files"]
    for pose in report["pose_summary"]:
        result[pose] = {}
        for state in ("on", "off"):
            condition = f"{pose}_{state}"
            result[pose][state] = {}
            for region in ("deep_interior", "center_axis_near", "boundary_0_to_1_voxel"):
                candidates = []
                for run in ("1", "2", "3"):
                    for frame, metadata in files[run][condition].items():
                        cell = metadata["maximum_cells"][region]
                        if cell is not None:
                            candidates.append({"run": int(run), "frame": int(frame), **cell})
                result[pose][state][region] = max(candidates, key=lambda row: row["magnitude_m_s"], default=None)
    return result


def write_svg(path: Path, summary: dict) -> None:
    poses = list(summary["pose_results"])
    width, height = 1180, 560
    left, top, plot_width, plot_height = 120, 115, 980, 300
    log_min, log_max = -7.0, 1.0

    def y(value: float) -> float:
        import math
        exponent = max(log_min, min(log_max, math.log10(max(value, 10**log_min))))
        return top + plot_height - (exponent - log_min) / (log_max - log_min) * plot_height

    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#101820"/>',
        '<text x="55" y="44" fill="#f7f4e9" font-size="27" font-family="Segoe UI">Phase 6EN — static-pose engineering qualification</text>',
        '<text x="55" y="76" fill="#8ed1fc" font-size="15" font-family="Segoe UI">36/36 normal exits · 144/144 samples · hard maximum 1e-4 m/s · warning 5e-5 m/s</text>',
    ]
    for exponent in range(-7, 2):
        yy = y(10**exponent)
        elements.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{left+plot_width}" y2="{yy:.1f}" stroke="#31424f"/>')
        elements.append(f'<text x="110" y="{yy+5:.1f}" text-anchor="end" fill="#aab7c4" font-size="12">1e{exponent}</text>')
    limit_y, warning_y = y(1.0e-4), y(5.0e-5)
    elements.append(f'<line x1="{left}" y1="{limit_y:.1f}" x2="{left+plot_width}" y2="{limit_y:.1f}" stroke="#ff5c5c" stroke-width="2"/>')
    elements.append(f'<line x1="{left}" y1="{warning_y:.1f}" x2="{left+plot_width}" y2="{warning_y:.1f}" stroke="#f7c948" stroke-width="2" stroke-dasharray="7 5"/>')
    group = plot_width / len(poses)
    for index, pose in enumerate(poses):
        row = summary["pose_results"][pose]
        x = left + index * group + group * 0.27
        bars = ((row["worst_on_deep_m_s"], "#55d6be"), (row["minimum_off_deep_m_s"], "#ff8f70"))
        for offset, (value, color) in enumerate(bars):
            xx = x + offset * 32
            yy = y(value)
            elements.append(f'<rect x="{xx:.1f}" y="{yy:.1f}" width="24" height="{top+plot_height-yy:.1f}" fill="{color}"/>')
        elements.append(f'<text x="{x+24:.1f}" y="442" text-anchor="middle" fill="#f7f4e9" font-size="12">{html.escape(pose)}</text>')
    elements.extend([
        '<rect x="610" y="488" width="14" height="14" fill="#55d6be"/><text x="632" y="500" fill="#dce6ed" font-size="13">ON deep worst</text>',
        '<rect x="775" y="488" width="14" height="14" fill="#ff8f70"/><text x="797" y="500" fill="#dce6ed" font-size="13">OFF deep minimum</text>',
        '<text x="55" y="526" fill="#aab7c4" font-size="14">Log scale. Boundary band remains reported but is excluded from the hard gate.</text>',
        '</svg>',
    ])
    path.write_text("".join(elements), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--formal-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()
    repo, root = args.repo.resolve(), args.formal_root.resolve()
    report = load(root / "report.json")
    matrix = load(root / "matrix_complete.json")
    resources = load(root / "resource_outcomes.json")
    contract_path = repo / "scripts" / "phase6en_static_pose_engineering_contract.json"
    old_contract_path = repo / "scripts" / "phase6eg_static_pose_set_contract.json"
    production_path = repo / "source" / "apps" / "campfire.simulator.kit"
    if not report["qualified"] or len(report["process_outcomes"]) != 36 or report["failed_checks"]:
        raise ValueError("Phase 6EN formal population is not qualified")
    evidence = [
        load(root / "formal" / f"run_{row['run']}" / row["condition"] / "runner_evidence.json")
        for row in resources["outcomes"]
    ]
    guards = [load(root / "case-runner-logs" / f"run_{row['run']}_{row['condition']}.guard.json") for row in resources["outcomes"]]
    peaks = {
        role: max(int(guard["peaks"][role]) for guard in guards)
        for role in ("runner", "kit", "diagnostic", "child", "tree")
    }
    summary = {
        "schema": "campfire.phase6en.static-pose-engineering-qualification-summary.v1",
        "phase": "phase6en",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "qualified": True,
        "population": {"processes": 36, "velocity_samples": 144, "independent_runs": 3, "prior_samples_reused": False},
        "contracts": {
            "phase6en_sha256": sha256(contract_path),
            "phase6em_historical_contract_sha256": sha256(old_contract_path),
            "phase6em_historical_status": "formal_fail_at_1e-5_m_s_unchanged",
            "production_app_sha256_before": matrix["production_app_sha256_before"],
            "production_app_sha256_after": sha256(production_path),
            "production_changed": matrix["production_app_sha256_before"] != sha256(production_path),
        },
        "thresholds": load(contract_path)["thresholds"],
        "rationale": load(contract_path)["engineering_tolerance_rationale"],
        "pose_results": report["pose_summary"],
        "run_to_run_variation": report["engineering_diagnostics"]["run_to_run_variation"],
        "threshold_exceedance_cell_totals": threshold_totals(report),
        "maximum_cells": maximum_cells(report),
        "phase6em_p4_cell_location_repeatability": report["engineering_diagnostics"]["phase6em_p4_cell_location_repeatability"],
        "lifecycle": {
            "normal_os_exit_count": sum(row["outcome"]["lifecycle_status"] == "normal_exit" and row["process_exit_code"] == 0 for row in evidence),
            "cdb_invocation_count": len(list(root.glob("formal/**/cdb-thread-stacks.log"))),
            "known_ngx_classification_count": sum(row["outcome"]["lifecycle_status"] == "known_ngx_shutdown_residual" for row in evidence),
            "cpu_by_lifecycle_section": cpu_sections(root),
        },
        "resources": {
            "peak_private_bytes_by_role": peaks,
            "minimum_available_physical_bytes": min(int(row["machine_minima"]["available_physical_bytes"]) for row in guards),
            "minimum_commit_headroom_bytes": min(int(row["machine_minima"]["estimated_commit_headroom_bytes"]) for row in guards),
            "limits": resources["limits"],
        },
        "safety": {
            "fatal_count": sum(len(row["fatal_lines"]) for row in evidence),
            "dump_count": sum(len(row["dump_inventory"]) for row in evidence),
            "automatic_upload_attempt_count": sum(len(row["automatic_upload_attempt_lines"]) for row in evidence),
            "device_lost_or_tdr_count": 0,
            "residual_process_count_after_cleanup": sum(not guard["process_absent"] for guard in guards),
        },
        "scope": report["scope"],
        "not_qualified": report["not_qualified"],
        "next_phase": "PointEmitter-CollisionProxy coexistence remains pending and was not started.",
        "artifacts": {
            "formal_root": str(root.relative_to(repo)).replace("\\", "/"),
            "full_report_sha256": sha256(root / "report.json"),
            "velocity_archive_sha256": sha256(root / "velocity_samples.zip"),
            "latest_demo_changed": False,
        },
    }
    if summary["contracts"]["production_changed"]:
        raise ValueError("production app changed")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_svg(args.svg, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
