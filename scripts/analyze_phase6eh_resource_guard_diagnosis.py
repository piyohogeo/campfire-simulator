"""Summarize Phase 6EG resource calibration and the second formal safe stop."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _relative(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--calibration-root", type=Path, required=True)
    parser.add_argument("--formal-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    calibration = _load(args.calibration_root / "report.json")
    formal_stop = _load(args.formal_root / "safe_stop.json")
    outcomes = _load(args.formal_root / "resource_outcomes.json")
    failed_guard = _load(
        args.formal_root / "case-runner-logs" / "run_2_P2_roll_x17_off.guard.json"
    )
    trace_path = args.formal_root / "case-runner-logs" / "run_2_P2_roll_x17_off.memory.jsonl"
    trace = [_load_line for line in trace_path.open(encoding="utf-8") if (_load_line := json.loads(line))]
    growth = []
    nvidia_smi = []
    machine_min_available = None
    machine_min_commit_headroom = None
    for sample in trace:
        machine = sample["machine"]
        available = machine["available_physical_bytes"]
        headroom = machine["estimated_commit_headroom_bytes"]
        machine_min_available = available if machine_min_available is None else min(machine_min_available, available)
        machine_min_commit_headroom = headroom if machine_min_commit_headroom is None else min(machine_min_commit_headroom, headroom)
        for process in sample["processes"]:
            if process["role"] == "runner" and process["private_bytes"] > 120 * 1024 * 1024:
                growth.append(process)
            if process["name"].lower() == "nvidia-smi.exe":
                nvidia_smi.append(process)
    calibration_rows = {
        Path(item["command"][item["command"].index("-SourceStage") + 1]).stem: {
            "duration_seconds": item["duration_seconds"],
            "runner_peak_private_bytes": item["peaks"]["runner"],
            "kit_peak_private_bytes": item["peaks"]["kit"],
            "tree_peak_private_bytes": item["peaks"]["tree"],
            "stop_reason": item["stop_reason"],
        }
        for item in calibration["stage_open_results"]
    }
    completed = outcomes["outcomes"]
    report = {
        "schema": "campfire.phase6eh.resource-guard-diagnosis.v1",
        "phase": "phase6eh",
        "status": "safe_stop",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "production-neutral Phase 6EG resource and lifecycle diagnosis",
        "observed_facts": {
            "old_guard_target": "direct runner PowerShell process only",
            "old_guard_was_tree_aggregate": False,
            "old_runner_pid": 16948,
            "old_kit_pid": 4688,
            "old_runner_private_limit_bytes": 536870912,
            "old_runner_observed_peak_bytes": 552259584,
            "old_growth_phase": "after 330 second Kit hang, during lightweight shutdown diagnostic",
            "old_collector_started": False,
            "old_p0_p2_runner_peaks_available": False,
            "old_p0_p2_kit_peak_rss_range_bytes": [6617702400, 6744616960],
            "old_p0_p2_collector_rss_delta_range_bytes": [578588672, 678457344],
            "calibration": calibration_rows,
            "calibration_formal_restart_safe": calibration["formal_restart_safe"],
            "formal_completed_normal_exit_processes": len(completed),
            "formal_planned_processes": 36,
            "formal_failed_condition": formal_stop["condition"],
            "formal_failed_last_marker": "timeline_stopped",
            "formal_failed_runner_peak_private_bytes": failed_guard["peaks"]["runner"],
            "formal_failed_kit_peak_private_bytes": failed_guard["peaks"]["kit"],
            "formal_failed_tree_peak_private_bytes": failed_guard["peaks"]["tree"],
            "formal_failed_guard_reason": failed_guard["stop_reason"],
            "runner_growth_first_timestamp_utc_epoch": growth[0]["timestamp_utc_epoch"] if growth else None,
            "runner_growth_first_private_bytes": growth[0]["private_bytes"] if growth else None,
            "nvidia_smi_first_timestamp_utc_epoch": nvidia_smi[0]["timestamp_utc_epoch"] if nvidia_smi else None,
            "nvidia_smi_peak_private_bytes": max((row["private_bytes"] for row in nvidia_smi), default=0),
            "cdb_process_observed": any(
                process["name"].lower() == "cdb.exe"
                for sample in trace
                for process in sample["processes"]
            ),
            "process_identity_key": ["pid", "create_time_utc_epoch"],
            "machine_min_available_physical_bytes": machine_min_available,
            "machine_min_estimated_commit_headroom_bytes": machine_min_commit_headroom,
            "fatal_count": 0,
            "dump_count": 0,
            "automatic_upload_attempt_count": 0,
        },
        "cause_classification": {
            "confirmed": [
                "512 MiB guarded the runner PowerShell, not Kit or a process-tree aggregate",
                "the second growth began after the lightweight diagnostic invoked GPU inventory",
                "Kit memory was bounded while runner PowerShell crossed its unchanged 512 MiB limit",
                "P3 stage-open and full run-1 P0-P5 ON/OFF completed under separated budgets",
            ],
            "strong_inference": [
                "in-process native nvidia-smi invocation under the hung-Kit diagnostic boundary triggered the PowerShell allocation growth",
                "the original P3 stop was a transient stage-open/lifecycle hang followed by the same diagnostic boundary, not a pose-specific collision failure",
            ],
            "unconfirmed": [
                "the internal Windows PowerShell/native-command allocation mechanism",
                "whether a future independent process would reproduce the same stage-close hang",
            ],
        },
        "correction": {
            "gpu_inventory_transport": "short-lived guarded nvidia-smi helper",
            "stdout_stderr": "direct to files; stdout parsed with File.ReadLines",
            "helper_timeout_seconds": 15,
            "helper_private_limit_bytes": 134217728,
            "runner_limit_unchanged_bytes": 536870912,
            "formal_kit_limit_bytes": 15032385536,
            "formal_tree_limit_bytes": 17179869184,
            "formal_machine_available_floor_bytes": 8589934592,
            "formal_commit_headroom_floor_bytes": 8589934592,
        },
        "qualification": {
            "phase6eg_qualified": False,
            "completed_fraction": f"{len(completed)}/36",
            "prior_p0_p2_samples_reused": False,
            "second_root_samples_reused_after_failure": False,
            "collision_failure_observed": False,
            "restart_condition": "new artifact root after isolated GPU-inventory policy regression and explicit approval; start from process 1",
        },
        "pending_after_phase6eg": {
            "name": "PointEmitter-CollisionProxy coexistence",
            "blocked_until": "all Phase 6EG qualification processes pass",
            "summary": "Evaluate emitter center and influence-radius distance to the actual Mesh, exclude emitters inside self/other colliders, sweep 0/0.25/0.5/1.0/1.5 Flow-cell offsets, and compare supply efficiency, active blocks, deep intrusion, overhead penetration, and visible flame lift.",
            "implemented_in_phase6eh": False,
        },
        "production": {
            "changed": False,
            "app_sha256_before": formal_stop["production_app_sha256_before"],
            "app_sha256_after": formal_stop["production_app_sha256_after"],
        },
        "artifacts": {
            "calibration": _relative(args.calibration_root, repo),
            "formal_safe_stop": _relative(args.formal_root, repo),
            "raw_memory_trace_committed": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    values = [
        ("P0 runner", calibration_rows["P0_identity"]["runner_peak_private_bytes"]),
        ("P3 runner", calibration_rows["P3_z33"]["runner_peak_private_bytes"]),
        ("failed runner", failed_guard["peaks"]["runner"]),
    ]
    limit = 536870912
    scale = 620 / limit
    bars = []
    for index, (label, value) in enumerate(values):
        y = 112 + index * 72
        width = min(620, value * scale)
        color = "#ef4444" if value > limit else "#22c55e"
        bars.append(f'<text x="32" y="{y}" fill="#e5e7eb" font-size="18">{label}</text>')
        bars.append(f'<rect x="190" y="{y-20}" width="620" height="25" rx="6" fill="#253044"/>')
        bars.append(f'<rect x="190" y="{y-20}" width="{width:.1f}" height="25" rx="6" fill="{color}"/>')
        bars.append(f'<text x="820" y="{y}" fill="#e5e7eb" font-size="17">{value/1048576:.1f} MiB</text>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="380" viewBox="0 0 1000 380">
<rect width="1000" height="380" fill="#101827"/><text x="32" y="46" fill="#f8fafc" font-size="27" font-family="Segoe UI, sans-serif">Phase 6EH — runner memory boundary</text>
<text x="32" y="75" fill="#94a3b8" font-size="16" font-family="Segoe UI, sans-serif">512 MiB remains a strict PowerShell limit; Kit has a separate measured budget.</text>
<g font-family="Segoe UI, sans-serif">{''.join(bars)}</g>
<line x1="810" y1="86" x2="810" y2="300" stroke="#fbbf24" stroke-width="3" stroke-dasharray="8 6"/><text x="690" y="330" fill="#fbbf24" font-size="16" font-family="Segoe UI, sans-serif">512 MiB runner limit</text>
<text x="32" y="355" fill="#94a3b8" font-size="15" font-family="Segoe UI, sans-serif">Formal matrix safe-stopped at 12/36; no collision qualification is claimed.</text></svg>'''
    args.svg.write_text(svg, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
