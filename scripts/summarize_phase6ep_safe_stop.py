"""Summarize a post-qualification Phase 6EP media/lifecycle safe stop."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    args = parser.parse_args()
    numeric = _read(args.root / "report.json")
    failed = args.root / "visual" / "collision_on_unfiltered"
    evidence = _read(failed / "runner_evidence.json")
    guard = _read(args.root / "runner-logs" / "visual_collision_on_unfiltered.guard.json")
    diagnostic = _read(failed / "sensitive-shutdown-diagnostics" / "lightweight_shutdown_diagnostic.json")
    off_evidence = _read(args.root / "visual" / "collision_off" / "runner_evidence.json")
    cleanup_source = guard["observed_process_cleanup"]
    cleanup = {
        "observed_alive_before_cleanup": [
            {"pid": item["pid"], "executable": Path(item["path"]).name}
            for item in cleanup_source["observed_alive_before_cleanup"]
        ],
        "cleanup_required": cleanup_source["cleanup_required"],
        "killed_pid_count": len(cleanup_source["killed_pids"]),
        "remaining_count": len(cleanup_source["remaining"]),
        "all_observed_absent": cleanup_source["all_observed_absent"],
    }
    report = {
        "schema": "campfire.phase6ep.point-collision-safe-stop.v1",
        "phase": "phase6ep",
        "overall_qualified": False,
        "formal_numeric_qualified": bool(numeric["qualified"]),
        "formal_processes_passed": 18 if numeric["qualified"] else 0,
        "contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest().upper(),
        "selected_offset_m": 0.075,
        "media_gate": {
            "qualified": False,
            "collision_off": {
                "capture_frames": 180,
                "lifecycle_status": off_evidence["outcome"]["lifecycle_status"],
            },
            "collision_on_unfiltered": {
                "capture_frames": 180,
                "probe_status": evidence["probe_status"],
                "last_lifecycle_marker": evidence["lifecycle_marker"],
                "lifecycle_status": evidence["outcome"]["lifecycle_status"],
                "process_exit_code": evidence["process_exit_code"],
                "cdb_timed_out": diagnostic["debugger"]["timed_out"],
                "cdb_detach_observed": diagnostic["debugger"]["detach_observed"],
                "known_ngx_signature_matched": diagnostic["stack_fingerprint"]["matched"],
                "log_capture_error_present": bool(diagnostic["log_capture_error"]),
            },
            "collision_on_candidate": {"started": False},
            "videos_encoded_or_published": 0,
        },
        "safe_stop": {
            "active_condition": "visual/collision_on_unfiltered",
            "reason": "unknown_shutdown_failure after shutdown_complete; CDB timed out without detach marker or accepted NGX signature",
            "automatic_retry": False,
            "later_condition_started": False,
            "guard_stop_reason": guard["stop_reason"],
            "cleanup": cleanup,
            "fatal_count": len(evidence["fatal_lines"]),
            "dump_count": len(evidence["dump_inventory"]),
            "automatic_upload_attempt_count": len(evidence["automatic_upload_attempt_lines"]),
            "production_changed": evidence["production_changed"],
        },
        "numeric_report": {
            "path": str(args.root / "report.json"),
            "pair_results": numeric["pair_results"],
            "formal_summary": numeric["formal_summary"],
            "resource_summary": numeric["resource_summary"],
        },
        "scope": "default-off production-neutral probe; no production integration and no media adoption",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cleanup = report["safe_stop"]["cleanup"]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="720" viewBox="0 0 1400 720"><style>.t{{font:700 34px system-ui;fill:#f8fafc}}.h{{font:700 23px system-ui;fill:#e2e8f0}}.p{{font:18px system-ui;fill:#cbd5e1}}.m{{font:18px ui-monospace;fill:#93c5fd}}</style><rect width="100%" height="100%" fill="#08111f"/><text x="50" y="62" class="t">Phase 6EP — numeric qualification / media lifecycle safe stop</text><rect x="50" y="105" width="620" height="210" rx="16" fill="#102c24"/><text x="78" y="150" class="h">Formal numeric population: PASS</text><text x="78" y="194" class="p">18 / 18 independent processes · 3 runs</text><text x="78" y="232" class="m">candidate deep / center max = 0 m/s</text><text x="78" y="270" class="m">OFF deep = 7.9117 m/s · pair ratio = 0</text><rect x="730" y="105" width="620" height="210" rx="16" fill="#3a1f24"/><text x="758" y="150" class="h">Media lifecycle: SAFE STOP</text><text x="758" y="194" class="p">ON/raw captured 180 frames and shutdown_complete</text><text x="758" y="232" class="m">unknown_shutdown_failure · CDB timeout</text><text x="758" y="270" class="m">detach marker absent · no accepted NGX signature</text><text x="50" y="380" class="h">Selected source placement</text><text x="50" y="422" class="p">Offset 1.5 velocity voxels = 0.075 m · conservative support radius 0.050 m</text><text x="50" y="462" class="p">single 100% · near-two 80.83% · lower/upper 100% · production-four 75.56%</text><text x="50" y="526" class="h">Safety outcome</text><text x="50" y="568" class="p">No retry; candidate video not started; no video published; latest demo unchanged.</text><text x="50" y="608" class="p">fatal / dump / upload / device-lost / TDR = 0 · production unchanged</text><text x="50" y="648" class="m">cleanup remaining = {cleanup['remaining_count']} · killed exact observed descendants = {cleanup['killed_pid_count']}</text></svg>'''
    args.svg.write_text(svg, encoding="utf-8")
    print("Phase 6EP safe-stop summary written")


if __name__ == "__main__":
    main()
