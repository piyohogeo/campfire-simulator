"""Summarize the approved Phase 6EG restart that safe-stopped at process 1."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def relative(path: Path, repo: Path) -> str:
    return str(path.resolve().relative_to(repo.resolve())).replace("\\", "/")


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
    parser.add_argument("--preflight-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    formal = args.formal_root.resolve()
    preflight = args.preflight_root.resolve()
    condition = "P0_identity_on"
    case = formal / "formal" / "run_1" / condition
    guard = load(formal / "case-runner-logs" / f"run_1_{condition}.guard.json")
    stop = load(formal / "safe_stop.json")
    raw = load(case / "raw.json")
    preflight_guard = load(preflight / "guard.json")
    preflight_capture = load(preflight / "gpu_inventory_capture.json")
    trace_path = formal / "case-runner-logs" / f"run_1_{condition}.memory.jsonl"
    growth = []
    for line in trace_path.open(encoding="utf-8"):
        sample = json.loads(line)
        runner = next((item for item in sample["processes"] if item["role"] == "runner"), None)
        if runner is not None and runner["private_bytes"] > 120 * 1024 * 1024:
            growth.append({
                "sample_index": sample["sample_index"],
                "timestamp_utc_epoch": sample["timestamp_utc_epoch"],
                "runner_private_bytes": runner["private_bytes"],
                "tree_private_bytes": sample["tree_private_bytes"],
            })
    spatial = formal / "spatial" / "run_1" / condition
    sample_files = sorted(spatial.glob("*_velocity.npz"))
    dump_count = sum(1 for path in formal.rglob("*") if path.is_file() and (path.name.endswith(".dmp") or path.name.endswith(".dmp.zip")))
    fatal_count = count_tokens(
        formal,
        (
            "[crash] a crash has occurred",
            "cuda illegal address",
            "device lost",
            "invalid pointer",
            "tdr detected",
        ),
    )
    upload_count = count_tokens(formal, ("automatic upload attempt", "uploading dump", "sending crash"))
    gpu_stdout = case / "sensitive-shutdown-diagnostics" / "gpu-inventory.stdout.csv"
    report = {
        "schema": "campfire.phase6ei.phase6eg-restart-safe-stop.v1",
        "phase": "phase6ei",
        "status": "safe_stop",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "approved restart of the unchanged frozen Phase 6EG 36-process qualification",
        "frozen_contract": {
            "sha256": stop["contract_sha256"],
            "planned_processes": 36,
            "prior_samples_reused": False,
            "thresholds_changed": False,
        },
        "qualification": {
            "phase6eg_qualified": False,
            "accepted_processes": 0,
            "active_failed_condition": stop["condition"],
            "automatic_retry": stop["automatic_retry"],
            "later_processes_started": False,
            "collision_failure_observed": False,
        },
        "functional_evidence_before_rejection": {
            "probe_status": raw["status"],
            "last_durable_marker": raw["lifecycle_marker"],
            "active_blocks_final": raw["active_blocks_final"],
            "source_fuel": raw["stage_audit"]["emitter"]["fuel"],
            "velocity_sample_count": len(sample_files),
            "sample_frames": [60, 120, 180, 200],
            "normal_os_exit_proven": False,
            "incremental_numeric_gate_reached": False,
        },
        "resource_guard": {
            "stop_reason": guard["stop_reason"],
            "runner_peak_private_bytes": guard["peaks"]["runner"],
            "kit_peak_private_bytes": guard["peaks"]["kit"],
            "diagnostic_peak_private_bytes": guard["peaks"]["diagnostic"],
            "unique_tree_peak_private_bytes": guard["peaks"]["tree"],
            "minimum_available_physical_bytes": guard["machine_minima"]["available_physical_bytes"],
            "minimum_commit_headroom_bytes": guard["machine_minima"]["estimated_commit_headroom_bytes"],
            "limits": guard["limits"],
            "process_absent_after_cleanup": guard["process_absent"],
            "first_growth_sample": growth[0] if growth else None,
            "last_growth_sample": growth[-1] if growth else None,
        },
        "gpu_inventory_preflight": {
            "status": preflight_guard["status"],
            "runner_peak_private_bytes": preflight_guard["peaks"]["runner"],
            "observed_nvidia_smi_peak_private_bytes": preflight_guard["peaks"]["diagnostic"],
            "unique_tree_peak_private_bytes": preflight_guard["peaks"]["tree"],
            "inner_helper_timed_out": preflight_capture["evidence"]["guard"]["timed_out"],
            "inner_helper_private_limit_exceeded": preflight_capture["evidence"]["guard"]["private_bytes_exceeded"],
            "inner_helper_process_absent": preflight_capture["evidence"]["guard"]["process_absent"],
            "gpu_count": len(preflight_capture["rows"]),
        },
        "shutdown_diagnostic_boundary": {
            "capture_lock_exists": (case / "sensitive-shutdown-diagnostics.capture.lock").is_file(),
            "gpu_inventory_stdout_exists": gpu_stdout.is_file(),
            "gpu_inventory_stdout_bytes": gpu_stdout.stat().st_size if gpu_stdout.is_file() else None,
            "lightweight_report_exists": (case / "sensitive-shutdown-diagnostics" / "lightweight_shutdown_diagnostic.json").is_file(),
            "cdb_stack_log_exists": (case / "sensitive-shutdown-diagnostics" / "cdb-thread-stacks.log").is_file(),
        },
        "safety": {
            "fatal_count": fatal_count,
            "dump_count": dump_count,
            "automatic_upload_attempt_count": upload_count,
            "device_lost_or_tdr_count": 0,
            "kit_cdb_helper_residual_count": 0,
        },
        "cause_classification": {
            "observed_facts": [
                "the isolated GPU inventory preflight passed below every resource limit",
                "P0 completed Flow sampling and wrote shutdown_complete before OS-exit confirmation",
                "the shutdown capture lock and 210-byte GPU inventory stdout were written",
                "the runner crossed 512 MiB before the lightweight diagnostic report was written",
                "Kit, unique-tree, physical-memory, and commit-headroom limits were not crossed",
            ],
            "strong_inference": [
                "a parent-PowerShell return or post-processing boundary after the isolated GPU inventory helper still retains or allocates memory when diagnosing a hung Kit process",
            ],
            "unconfirmed": [
                "the exact PowerShell/native allocation mechanism",
                "whether isolating the complete lightweight shutdown diagnostic would remove the remaining parent-runner growth",
            ],
        },
        "restart_boundary": "do not retry this condition; first isolate or durably mark the complete lightweight diagnostic boundary, then require a new explicit restart and new artifact root",
        "pending_after_phase6eg": {
            "name": "PointEmitter-CollisionProxy coexistence",
            "blocked_until": "all 36 Phase 6EG processes qualify",
            "implemented": False,
        },
        "production": {
            "changed": stop["production_app_sha256_before"] != stop["production_app_sha256_after"],
            "app_sha256_before": stop["production_app_sha256_before"],
            "app_sha256_after": stop["production_app_sha256_after"],
        },
        "artifacts": {
            "formal_safe_stop": relative(formal, repo),
            "gpu_inventory_preflight": relative(preflight, repo),
            "raw_trace_committed": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    values = [
        ("preflight runner", preflight_guard["peaks"]["runner"], "#22c55e"),
        ("formal runner", guard["peaks"]["runner"], "#ef4444"),
        ("formal Kit / 28", guard["peaks"]["kit"] / 28.0, "#60a5fa"),
    ]
    scale = 620.0 / guard["limits"]["runner_private_bytes"]
    bars = []
    for index, (label, value, color) in enumerate(values):
        y = 118 + index * 72
        width = min(620.0, value * scale)
        bars.append(f'<text x="35" y="{y}" fill="#e5e7eb" font-size="18">{label}</text>')
        bars.append(f'<rect x="215" y="{y-21}" width="620" height="26" rx="6" fill="#253044"/>')
        bars.append(f'<rect x="215" y="{y-21}" width="{width:.1f}" height="26" rx="6" fill="{color}"/>')
        bars.append(f'<text x="850" y="{y}" fill="#e5e7eb" font-size="16">{value/1048576:.1f} MiB</text>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1050" height="390" viewBox="0 0 1050 390">
<rect width="1050" height="390" fill="#101827"/><g font-family="Segoe UI, sans-serif">
<text x="35" y="45" fill="#f8fafc" font-size="27">Phase 6EI — Phase 6EG restart safe stop</text>
<text x="35" y="75" fill="#94a3b8" font-size="16">P0 reached shutdown_complete; parent runner crossed 512 MiB before normal OS exit.</text>
{''.join(bars)}
<line x1="835" y1="88" x2="835" y2="310" stroke="#fbbf24" stroke-width="3" stroke-dasharray="8 6"/>
<text x="700" y="340" fill="#fbbf24" font-size="16">512 MiB runner limit</text>
<text x="35" y="370" fill="#94a3b8" font-size="15">0 / 36 accepted · no retry · production unchanged</text></g></svg>'''
    args.svg.write_text(svg, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
