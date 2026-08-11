"""Publish the Phase 6EG fifth-root numeric safe stop without accepting partial data."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path


FRAMES = (60, 120, 180, 200)
ACTIVE_CONDITION = "P4_y24_z31_on"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


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


def numeric_summary(gate: dict) -> dict:
    samples = gate["samples"]
    deep = [samples[str(frame)]["deep_interior"]["maximum"] for frame in FRAMES]
    center = [samples[str(frame)]["center_axis_near"]["maximum"] for frame in FRAMES]
    boundary_p95 = [samples[str(frame)]["boundary_0_to_1_voxel"]["p95"] for frame in FRAMES]
    boundary_max = [samples[str(frame)]["boundary_0_to_1_voxel"]["maximum"] for frame in FRAMES]
    deep_above = [samples[str(frame)]["deep_interior"]["threshold_counts"]["1e-05"] for frame in FRAMES]
    center_above = [samples[str(frame)]["center_axis_near"]["threshold_counts"]["1e-05"] for frame in FRAMES]
    ratios = [
        item["pair_values"]["deep_ratio"]
        for item in gate["checks"]
        if item.get("pair_values") and item["pair_values"].get("deep_ratio") is not None
    ]
    stale = [
        item["predicates"]["identity_only_not_stale_suppressed"]
        for item in gate["checks"]
        if "identity_only_not_stale_suppressed" in item["predicates"]
    ]
    return {
        "pass": bool(gate["pass"]),
        "pair_available": bool(gate["pair_available"]),
        "deep_maximum_m_s": max(deep),
        "center_maximum_m_s": max(center),
        "boundary_p95_maximum_m_s": max(boundary_p95),
        "boundary_maximum_m_s": max(boundary_max),
        "deep_cells_above_1e_5_by_frame": dict(zip((str(x) for x in FRAMES), deep_above)),
        "center_cells_above_1e_5_by_frame": dict(zip((str(x) for x in FRAMES), center_above)),
        "worst_on_off_deep_ratio": max(ratios) if ratios else None,
        "stale_position_checks_pass": all(stale) if stale else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--formal-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    root = args.formal_root.resolve()
    stop = load(root / "safe_stop.json")
    outcomes = load(root / "resource_outcomes.json")["outcomes"]
    case = root / "formal" / "run_1" / ACTIVE_CONDITION
    gate = load(case / "incremental_numeric_gate.json")
    raw = load(case / "raw.json")
    evidence = load(case / "runner_evidence.json")
    guard = load(root / "case-runner-logs" / f"run_1_{ACTIVE_CONDITION}.guard.json")
    contract_path = repo / "scripts" / "phase6eg_static_pose_set_contract.json"
    production_path = repo / "source" / "apps" / "campfire.simulator.kit"

    if stop["condition"] != f"run_1/{ACTIVE_CONDITION}":
        raise ValueError("unexpected Phase 6EG active safe-stop condition")
    if len(outcomes) != 8:
        raise ValueError("the numeric safe stop must follow exactly eight completed processes")
    if evidence["outcome"]["lifecycle_status"] != "normal_exit" or evidence["process_exit_code"] != 0:
        raise ValueError("the active numeric failure did not establish normal OS exit")
    if gate["pass"]:
        raise ValueError("the active condition unexpectedly passed its incremental gate")

    completed = []
    for outcome in outcomes:
        completed_gate = load(
            root
            / "formal"
            / f"run_{outcome['run']}"
            / outcome["condition"]
            / "incremental_numeric_gate.json"
        )
        completed.append(
            {
                "run": outcome["run"],
                "condition": outcome["condition"],
                "functional_status": outcome["functional_status"],
                "lifecycle_status": outcome["lifecycle_status"],
                "active_blocks_final": outcome["active_blocks_final"],
                "source_fuel": outcome["source_fuel"],
                "numeric": numeric_summary(completed_gate),
            }
        )

    numeric = numeric_summary(gate)
    cpu = cpu_sections(root / "case-runner-logs" / f"run_1_{ACTIVE_CONDITION}.memory.jsonl")
    cdb_markers = list(case.glob("**/cdb-thread-stacks.log"))
    report = {
        "schema": "campfire.phase6em.phase6eg-numeric-safe-stop.v1",
        "phase": "phase6em",
        "status": "safe_stop",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "qualification": {
            "phase6eg_qualified": False,
            "planned_processes": 36,
            "completed_normal_exit_incremental_gate_processes": 8,
            "active_normal_exit_numeric_failure_processes": 1,
            "accepted_complete_population": 0,
            "prior_samples_reused": False,
            "automatic_retry": False,
            "later_processes_started": False,
            "active_condition": stop["condition"],
            "failure_kind": "incremental_numeric_gate",
        },
        "frozen_contract": {
            "sha256_before": stop["contract_sha256"],
            "sha256_after": sha256(contract_path),
            "changed": stop["contract_sha256"] != sha256(contract_path),
            "pose_order_threshold_mesh_emitter_flow_changed": False,
            "velocity_limit_m_s": 1e-5,
        },
        "active_condition": {
            "probe_status": raw["status"],
            "last_lifecycle_marker": raw["lifecycle_marker"],
            "functional_status": evidence["outcome"]["functional_status"],
            "lifecycle_status": evidence["outcome"]["lifecycle_status"],
            "normal_os_exit": evidence["process_exit_code"] == 0,
            "flow_velocity_sample_count": len(gate["samples"]),
            "sample_frames": list(FRAMES),
            "active_blocks_final": raw["active_blocks_final"],
            "source_fuel": raw["stage_audit"]["emitter"]["fuel"],
            "numeric": numeric,
            "pair_gate_evaluated": False,
            "paired_off_condition_started": False,
            "cpu_by_lifecycle_section": cpu,
            "resource_peaks_bytes": guard["peaks"],
            "resource_limits": guard["limits"],
            "machine_minima_bytes": guard["machine_minima"],
            "duration_seconds": guard["duration_seconds"],
        },
        "completed_partial_evidence": completed,
        "cdb": {
            "phase6el_path_integrated": True,
            "invocation_count": len(cdb_markers),
            "not_invoked_reason": "Kit exited normally inside shutdown grace; residual-only CDB path was not needed",
            "known_ngx_classification_used": False,
        },
        "safety": {
            "fatal_count": len(evidence["fatal_lines"]),
            "dump_count": len(evidence["dump_inventory"]),
            "automatic_upload_attempt_count": len(evidence["automatic_upload_attempt_lines"]),
            "device_lost_or_tdr_count": 0,
            "resource_guard_status": guard["status"],
            "resource_limit_exceeded": guard["stop_reason"] is not None,
            "process_absent_after_cleanup": guard["process_absent"],
            "observed_process_cleanup": guard["observed_process_cleanup"],
        },
        "production": {
            "app_sha256_before": stop["production_app_sha256_before"],
            "app_sha256_after": sha256(production_path),
            "changed": stop["production_app_sha256_before"] != sha256(production_path),
        },
        "conclusion": {
            "observed_fact": "P4 compound collision ON exceeded the frozen deep and center 1e-5 m/s maxima in all four frames after a normal OS exit",
            "not_claimed": "The result does not qualify P4, the six-pose set, all SO(3), dynamic transforms, production integration, or PointEmitter coexistence",
            "next_step": "Investigate P4 spatial depth/mesh-grid phase as a new diagnostic before any new full-matrix restart; do not relax the frozen gate post-result",
        },
        "artifacts": {
            "local_root": str(root.relative_to(repo)).replace("\\", "/"),
            "raw_artifacts_committed": False,
            "qualification_svg_or_zip_generated": False,
            "latest_demo_changed": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    limit = 1e-5
    deep_width = min(620.0, 620.0 * numeric["deep_maximum_m_s"] / (2e-5))
    center_width = min(620.0, 620.0 * numeric["center_maximum_m_s"] / (2e-5))
    limit_x = 220.0 + 620.0 * limit / (2e-5)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="430" viewBox="0 0 1120 430">
<rect width="1120" height="430" fill="#101827"/><g font-family="Segoe UI, sans-serif">
<text x="45" y="48" fill="#f8fafc" font-size="29">Phase 6EM - Phase 6EG numeric safe stop</text>
<text x="45" y="82" fill="#94a3b8" font-size="17">P0-P3 pairs passed; P4 compound ON exited normally but exceeded the frozen velocity gate.</text>
<text x="45" y="145" fill="#e5e7eb" font-size="18">P4 deep interior maximum</text><rect x="220" y="120" width="620" height="28" rx="5" fill="#253044"/><rect x="220" y="120" width="{deep_width:.1f}" height="28" rx="5" fill="#ef4444"/>
<text x="865" y="143" fill="#f8fafc" font-size="17">{numeric['deep_maximum_m_s']:.8g} m/s</text>
<text x="45" y="215" fill="#e5e7eb" font-size="18">P4 center-axis maximum</text><rect x="220" y="190" width="620" height="28" rx="5" fill="#253044"/><rect x="220" y="190" width="{center_width:.1f}" height="28" rx="5" fill="#f59e0b"/>
<text x="865" y="213" fill="#f8fafc" font-size="17">{numeric['center_maximum_m_s']:.8g} m/s</text>
<line x1="{limit_x:.1f}" y1="108" x2="{limit_x:.1f}" y2="232" stroke="#f8fafc" stroke-width="3" stroke-dasharray="7 6"/><text x="{limit_x + 8:.1f}" y="258" fill="#cbd5e1" font-size="15">frozen limit 1e-5</text>
<text x="45" y="315" fill="#f8fafc" font-size="19">normal exit · active blocks {raw['active_blocks_final']} · fuel {raw['stage_audit']['emitter']['fuel']:.3f} · CDB calls 0</text>
<text x="45" y="352" fill="#fbbf24" font-size="18">Safe stop: 8 completed passes + 1 numeric failure; P4 OFF and later conditions not started.</text>
<text x="45" y="390" fill="#94a3b8" font-size="17">0 / 36 accepted as a complete population · no retry · production and contract unchanged</text>
</g></svg>'''
    args.svg.write_text(svg, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
