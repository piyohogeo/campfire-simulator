"""Analyze the Phase 6FX memory population with the Phase 6FW identity policy."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import analyze_phase6fv_memory_ceiling_qualification as phase6fv
from phase6fw_pid_reuse_policy import classify as classify_identity


def _json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _identity_policy_gate(attempt_root: Path, attempt: dict) -> tuple[list[str], dict]:
    cleanup = attempt.get("cleanup") or {}
    marker_path = attempt_root / "runner-logs" / "cleanup_markers.jsonl"
    markers = phase6fv.legacy._jsonl(marker_path)
    termination_requests = [
        {"identity": row.get("identity"), "marker": row.get("marker")}
        for row in markers
        if row.get("marker") == "exact_identity_stop_requested" and isinstance(row.get("identity"), dict)
    ]
    post_audit = _json(attempt_root / "runner-logs" / "post_cleanup_identity_audit.json") or {}
    payload = {
        "source_artifact": str(attempt_root),
        "cleanup": cleanup,
        "cleanup_markers": markers,
        "termination_requests": termination_requests,
        "post_summary_rediscovered": post_audit.get("rediscovered_matching_identities") or [],
    }
    decision = classify_identity(payload)
    log_root = attempt_root / "runner-logs"
    log_root.mkdir(parents=True, exist_ok=True)
    (log_root / "phase6fw_identity_policy_input.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (log_root / "phase6fw_identity_policy_decision.json").write_text(
        json.dumps(decision, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    failures = [] if decision.get("qualified") is True else [
        *(str(value) for value in decision.get("global_failures") or []),
        "phase6fw_identity_policy_failed",
    ]
    evidence = {
        "policy_schema": decision.get("schema"),
        "policy_status": decision.get("status"),
        "qualified": decision.get("qualified"),
        "counts": decision.get("counts") or {},
        "marker_integrity": decision.get("marker_integrity") or {},
        "global_failures": decision.get("global_failures") or [],
        "all_other_attempt_identities_ended": decision.get("all_other_attempt_identities_ended"),
        "input_path": str(log_root / "phase6fw_identity_policy_input.json"),
        "decision_path": str(log_root / "phase6fw_identity_policy_decision.json"),
        "post_summary_identity_audit_present": bool(post_audit),
        "final_summary_is_dual_source_os_enumeration": set(cleanup.get("absence_confirmation_sources") or []) == {"psutil", "win32"},
    }
    return list(dict.fromkeys(failures)), evidence


def build(root: Path, contract_path: Path) -> dict:
    contract = _json(contract_path)
    if not contract or contract.get("phase") != "phase6fx":
        raise ValueError("invalid Phase 6FX contract")

    compatibility = copy.deepcopy(contract)
    compatibility["phase"] = "phase6fv"
    original_gate = phase6fv._identity_cleanup_gate
    try:
        phase6fv._identity_cleanup_gate = _identity_policy_gate
        with tempfile.TemporaryDirectory(prefix="phase6fx-analyzer-") as directory:
            temporary_contract = Path(directory) / "compatibility.json"
            temporary_contract.write_text(json.dumps(compatibility), encoding="utf-8")
            report = phase6fv.build(root, temporary_contract)
    finally:
        phase6fv._identity_cleanup_gate = original_gate

    total_counts: dict[str, int] = {}
    for attempt in report.get("attempts") or []:
        counts = (attempt.get("identity_cleanup") or {}).get("counts") or {}
        for key, value in counts.items():
            if isinstance(value, int):
                total_counts[key] = total_counts.get(key, 0) + value

    qualified = bool(
        report.get("qualification_complete")
        and report.get("candidate_16_gib_qualified")
        and report.get("candidate_17_gib_tree_qualified")
        and total_counts.get("final_attempt_owned_residual", 0) == 0
        and total_counts.get("unresolved_unknown", 0) == 0
    )
    report.update(
        {
            "schema": "campfire.phase6fx.memory-ceiling-qualification-report.v1",
            "phase": "phase6fx",
            "phase6ft_reclassified": False,
            "phase6fv_reclassified": False,
            "phase6fv_artifact_reused": False,
            "phase6fw_identity_policy_required": True,
            "phase6fo_restarted": False,
            "production_changed": False,
            "identity_policy_totals": total_counts,
            "identity_policy_qualified": total_counts.get("final_attempt_owned_residual", 0) == 0
            and total_counts.get("unresolved_unknown", 0) == 0,
            "qualification_complete": qualified,
            "candidate_16_gib_qualified": qualified,
            "candidate_17_gib_tree_qualified": qualified,
            "phase6fo_restart_ready": qualified,
        }
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    report = build(arguments.root.resolve(), arguments.contract.resolve())
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
