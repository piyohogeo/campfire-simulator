"""Publish the Phase 6EG fourth-root safe stop without accepting partial data."""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path


FRAMES = (60, 120, 180, 200)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def relative(path: Path, repo: Path) -> str:
    return str(path.resolve().relative_to(repo.resolve())).replace("\\", "/")


def cpu_sections(trace_path: Path) -> dict:
    grouped: dict[str, list[float]] = {}
    with trace_path.open(encoding="utf-8") as stream:
        for line in stream:
            sample = json.loads(line)
            section = sample.get("current_execution_section") or "unclassified"
            for process in sample.get("processes", []):
                if process.get("role") != "kit":
                    continue
                value = process.get("cpu_percent_of_logical_total")
                if value is not None:
                    grouped.setdefault(section, []).append(float(value))
    return {
        section: {
            "sample_count": len(values),
            "mean_percent_of_logical_total": statistics.fmean(values),
            "maximum_percent_of_logical_total": max(values),
        }
        for section, values in grouped.items()
    }


def condition_numeric(case: Path) -> dict:
    gate = load(case / "incremental_numeric_gate.json")
    samples = gate["samples"]
    result = {
        "pass": gate["pass"],
        "pair_available": gate["pair_available"],
        "deep_maximum_m_s": max(samples[str(frame)]["deep_interior"]["maximum"] for frame in FRAMES),
        "center_maximum_m_s": max(samples[str(frame)]["center_axis_near"]["maximum"] for frame in FRAMES),
        "boundary_p95_maximum_m_s": max(samples[str(frame)]["boundary_0_to_1_voxel"]["p95"] for frame in FRAMES),
        "boundary_maximum_m_s": max(samples[str(frame)]["boundary_0_to_1_voxel"]["maximum"] for frame in FRAMES),
    }
    ratios = [
        check["pair_values"]["deep_ratio"]
        for check in gate["checks"]
        if check.get("pair_values") and check["pair_values"].get("deep_ratio") is not None
    ]
    identity_checks = [
        check["predicates"].get("identity_only_not_stale_suppressed")
        for check in gate["checks"]
        if "identity_only_not_stale_suppressed" in check["predicates"]
    ]
    result["worst_on_off_deep_ratio"] = max(ratios) if ratios else None
    result["stale_position_checks_pass"] = all(identity_checks) if identity_checks else None
    return result


def count_tokens(root: Path, tokens: tuple[str, ...]) -> int:
    count = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".log", ".txt", ".json", ".jsonl"}:
            continue
        try:
            with path.open(encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    lowered = line.lower()
                    count += sum(token in lowered for token in tokens)
        except OSError:
            continue
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--formal-root", type=Path, required=True)
    parser.add_argument("--locked-log-fixture", type=Path, required=True)
    parser.add_argument("--orphan-fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    formal = args.formal_root.resolve()
    p4_name = "P4_y24_z31_on"
    p4_case = formal / "formal" / "run_1" / p4_name
    stop = load(formal / "safe_stop.json")
    resources = load(formal / "resource_outcomes.json")
    p4_guard = load(formal / "case-runner-logs" / f"run_1_{p4_name}.guard.json")
    p4_raw = load(p4_case / "raw.json")
    p4_evidence = load(p4_case / "runner_evidence.json")
    locked_report = load(args.locked_log_fixture / "report.json")
    locked_json = load(args.locked_log_fixture / "isolated-child" / "diagnostic" / "lightweight_shutdown_diagnostic.json")
    orphan_guard = load(args.orphan_fixture / "guard.json")

    completed = []
    for outcome in resources["outcomes"]:
        condition = outcome["condition"]
        case = formal / "formal" / f"run_{outcome['run']}" / condition
        completed.append({
            "run": outcome["run"],
            "condition": condition,
            "functional_status": outcome["functional_status"],
            "lifecycle_status": outcome["lifecycle_status"],
            "exit_code": outcome["exit_code"],
            "active_blocks_final": outcome["active_blocks_final"],
            "source_fuel": outcome["source_fuel"],
            "runner_peak_private_bytes": outcome["runner_peak_private_bytes"],
            "kit_peak_private_bytes": outcome["kit_peak_private_bytes"],
            "diagnostic_peak_private_bytes": outcome["diagnostic_peak_private_bytes"],
            "tree_peak_private_bytes": outcome["tree_peak_private_bytes"],
            "minimum_available_physical_bytes": outcome["minimum_available_physical_bytes"],
            "minimum_commit_headroom_bytes": outcome["minimum_commit_headroom_bytes"],
            "spatial_peak_rss_bytes": outcome["spatial_peak_rss_bytes"],
            "spatial_peak_rss_delta_bytes": outcome["spatial_peak_rss_delta_bytes"],
            "numeric": condition_numeric(case),
            "shutdown_cpu": cpu_sections(
                formal / "case-runner-logs" / f"run_{outcome['run']}_{condition}.memory.jsonl"
            ),
        })

    p4_cpu = cpu_sections(formal / "case-runner-logs" / f"run_1_{p4_name}.memory.jsonl")
    p4_samples = sorted((formal / "spatial" / "run_1" / p4_name).glob("*_velocity.npz"))
    marker_path = p4_case / "sensitive-shutdown-diagnostics.markers.jsonl"
    markers = [json.loads(line)["marker"] for line in marker_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = {
        "schema": "campfire.phase6ek.phase6eg-restart-safe-stop.v1",
        "phase": "phase6ek",
        "status": "safe_stop",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_contract": {
            "sha256": stop["contract_sha256"],
            "planned_processes": 36,
            "prior_samples_reused": False,
            "pose_order_threshold_mesh_emitter_flow_changed": False,
        },
        "qualification": {
            "phase6eg_qualified": False,
            "completed_normal_exit_incremental_gate_processes": len(completed),
            "accepted_formal_population": 0,
            "active_failed_condition": stop["condition"],
            "automatic_retry": stop["automatic_retry"],
            "later_processes_started": False,
            "collision_failure_observed": False,
            "completed_conditions": completed,
        },
        "active_condition": {
            "probe_status": p4_raw["status"],
            "last_probe_marker": p4_raw["lifecycle_marker"],
            "velocity_samples_written": len(p4_samples),
            "sample_frames": list(FRAMES),
            "active_blocks_final": p4_raw["active_blocks_final"],
            "source_fuel": p4_raw["stage_audit"]["emitter"]["fuel"],
            "normal_os_exit": False,
            "lifecycle_status": p4_evidence["outcome"]["lifecycle_status"],
            "incremental_numeric_gate_written": (p4_case / "incremental_numeric_gate.json").is_file(),
            "diagnostic_markers": markers,
            "diagnostic_report_written": (p4_case / "sensitive-shutdown-diagnostics" / "lightweight_shutdown_diagnostic.json").is_file(),
            "shutdown_cpu_by_section": p4_cpu,
            "resource_peaks_bytes": p4_guard["peaks"],
            "resource_limits": p4_guard["limits"],
            "minimum_machine_headroom_bytes": p4_guard["machine_minima"],
        },
        "cause_classification": {
            "observed_facts": [
                "P4 completed Flow measurement and timeline stop but did not reach normal OS exit",
                "the isolated diagnostic failed while File.ReadLines opened Kit's exclusively-held log",
                "CDB was unavailable, so no accepted NGX stack signature was obtained",
                "the silent timeline-stopped interval had low Kit CPU rather than sustained spin",
                "the original guard confirmed only root absence; one exactly identified Kit descendant remained until safely stopped",
            ],
            "strong_inference": [
                "the observed silent interval is a low-CPU shutdown wait in this run",
                "exclusive Kit-log ownership was the immediate diagnostic-report failure, not a resource-limit breach",
            ],
            "unconfirmed": [
                "the native wait owner and whether it matches the known NGX shutdown stack",
                "whether P4 would satisfy the frozen numeric gate after a normal OS exit",
            ],
        },
        "policy_correction": {
            "locked_kit_log_is_auxiliary": True,
            "locked_log_fixture": {
                "status": locked_report["status"],
                "diagnostic_report_written": True,
                "log_capture_error_recorded": bool(locked_json.get("log_capture_error")),
                "diagnostic_capture_succeeded": locked_json["diagnostic_capture_succeeded"],
            },
            "observed_descendant_cleanup": {
                "fixture_status": orphan_guard["status"],
                "stop_reason": orphan_guard["stop_reason"],
                "cleanup_required": orphan_guard["observed_process_cleanup"]["cleanup_required"],
                "all_observed_absent": orphan_guard["observed_process_cleanup"]["all_observed_absent"],
                "identity": "pid + creation time + exact executable path",
            },
        },
        "safety": {
            "fatal_count": count_tokens(formal, ("[crash] a crash has occurred", "cuda illegal address", "device lost", "tdr detected")),
            "dump_count": sum(1 for path in formal.rglob("*") if path.is_file() and (path.name.endswith(".dmp") or path.name.endswith(".dmp.zip"))),
            "automatic_upload_attempt_count": count_tokens(formal, ("automatic upload attempt", "uploading dump", "sending crash")),
            "active_kit_residual_safely_removed": True,
            "post_cleanup_residual_count": 0,
        },
        "production": {
            "changed": stop["production_app_sha256_before"] != stop["production_app_sha256_after"],
            "app_sha256_before": stop["production_app_sha256_before"],
            "app_sha256_after": stop["production_app_sha256_after"],
        },
        "next_boundary": "do not resume the 36-process matrix automatically; require a fresh root and explicit approval after this safe stop",
        "pending_after_phase6eg": {
            "name": "PointEmitter-CollisionProxy coexistence",
            "blocked_until": "all 36 Phase 6EG processes qualify",
            "implemented": False,
        },
        "artifacts": {
            "formal_safe_stop": relative(formal, repo),
            "locked_log_fixture": relative(args.locked_log_fixture, repo),
            "orphan_cleanup_fixture": relative(args.orphan_fixture, repo),
            "raw_artifacts_committed": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    timeline_cpu = p4_cpu.get("timeline_stopped", {})
    bars = [
        ("runner", p4_guard["peaks"]["runner"], p4_guard["limits"]["runner_private_bytes"], "#22c55e"),
        ("diagnostic", p4_guard["peaks"]["diagnostic"], p4_guard["limits"]["diagnostic_private_bytes"], "#60a5fa"),
        ("Kit", p4_guard["peaks"]["kit"], p4_guard["limits"]["kit_private_bytes"], "#a78bfa"),
        ("unique tree", p4_guard["peaks"]["tree"], p4_guard["limits"]["tree_private_bytes"], "#f59e0b"),
    ]
    rows = []
    for index, (label, value, limit, color) in enumerate(bars):
        y = 145 + index * 58
        width = 540 * min(1.0, value / limit)
        rows.append(f'<text x="45" y="{y}" fill="#e5e7eb" font-size="18">{label}</text>')
        rows.append(f'<rect x="205" y="{y-20}" width="540" height="25" rx="5" fill="#253044"/>')
        rows.append(f'<rect x="205" y="{y-20}" width="{width:.1f}" height="25" rx="5" fill="{color}"/>')
        rows.append(f'<text x="765" y="{y}" fill="#e5e7eb" font-size="16">{value/1048576:.1f} / {limit/1048576:.0f} MiB</text>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="470" viewBox="0 0 1100 470">
<rect width="1100" height="470" fill="#101827"/><g font-family="Segoe UI, sans-serif">
<text x="45" y="48" fill="#f8fafc" font-size="29">Phase 6EK - Phase 6EG formal restart safe stop</text>
<text x="45" y="82" fill="#94a3b8" font-size="17">8 normal-exit gates completed; P4 stopped after measurement at a low-CPU shutdown wait.</text>
{''.join(rows)}
<text x="45" y="395" fill="#f8fafc" font-size="19">timeline_stopped Kit CPU: mean {timeline_cpu.get('mean_percent_of_logical_total', 0):.3f}% / max {timeline_cpu.get('maximum_percent_of_logical_total', 0):.3f}%</text>
<text x="45" y="430" fill="#fbbf24" font-size="18">0 / 36 accepted as a complete population - no retry - production unchanged</text>
</g></svg>'''
    args.svg.write_text(svg, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
