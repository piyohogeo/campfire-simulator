"""Analyze the Phase 6GA S93/S100/OFF population without changing Phase 6FO."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

import numpy as np

import analyze_phase6fo_supply_comparison as legacy
from phase6fw_pid_reuse_policy import classify as classify_identity


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _jsonl(path: Path):
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []


def _sha(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _artifact_gate(attempt_root: Path, case_dir: Path):
    root = case_dir / "memory-measurement"
    commit = _read(root / "memory_measurement_commit.json") or {}
    summary = _read(root / "committer_summary.json") or {}
    marker_rows = _jsonl(root / "measurement_commit_markers.jsonl")
    marker = next((row for row in marker_rows if row.get("marker") == "memory_measurement_artifact_committed"), None)
    checked = []
    hashes_ok = bool(commit and marker)
    for name, detail in (commit.get("files") or {}).items():
        path = Path(str((detail or {}).get("path") or ""))
        expected = str((detail or {}).get("sha256") or "").upper()
        observed = _sha(path) if path.is_file() else None
        match = bool(expected and observed == expected)
        hashes_ok &= match
        checked.append({"name": name, "path": str(path), "match": match})
    metadata = _read(attempt_root / "attempt_metadata.json") or {}
    snapshot = _read(root / "attempt_metadata_snapshot.json") or {}
    metadata_ok = all(snapshot.get(key) == metadata.get(key) for key in ("attempt_id", "condition", "slot_id"))
    telemetry = commit.get("telemetry") or {}
    telemetry_ok = bool(
        int(telemetry.get("resource_sample_count") or 0) > 0
        and telemetry.get("kit_observed") is True
        and telemetry.get("runner_observed") is True
        and telemetry.get("diagnostic_observed") is True
        and telemetry.get("tree_private_present") is True
    )
    passed = bool(
        summary.get("status") == "ok"
        and commit.get("status") == "committed_before_stage_close"
        and not commit.get("stage_close_observed_during_commit")
        and hashes_ok and metadata_ok and telemetry_ok
    )
    return {"pass": passed, "hashes_match": hashes_ok, "metadata_match": metadata_ok,
            "telemetry_complete": telemetry_ok, "checked_files": checked, "commit": commit}


def _identity_gate(attempt_root: Path, guard: dict):
    cleanup = guard.get("observed_process_cleanup") or {}
    markers = _jsonl(attempt_root / "runner-logs" / "cleanup_markers.jsonl")
    termination = [
        {"identity": row.get("identity"), "marker": row.get("marker")}
        for row in markers
        if row.get("marker") == "exact_identity_stop_requested" and isinstance(row.get("identity"), dict)
    ]
    payload = {"cleanup": cleanup, "cleanup_markers": markers, "termination_requests": termination,
               "post_summary_rediscovered": []}
    decision = classify_identity(payload)
    (attempt_root / "runner-logs" / "phase6fw_identity_policy_decision.json").write_text(
        json.dumps(decision, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return decision


def _resource_gate(guard: dict, contract: dict):
    peaks = guard.get("peaks") or {}
    minima = guard.get("machine_minima") or {}
    limits = contract["safety"]
    checks = {
        "kit": int(peaks.get("kit") or 0) < int(limits["kit_private_limit_bytes"]),
        "tree": int(peaks.get("tree") or 0) < int(limits["unique_tree_private_limit_bytes"]),
        "runner": int(peaks.get("runner") or 0) <= int(limits["runner_private_limit_bytes"]),
        "diagnostic": int(peaks.get("diagnostic") or 0) <= int(limits["diagnostic_private_limit_bytes"]),
        "physical": int(minima.get("available_physical_bytes") or 0) >= int(limits["physical_memory_floor_bytes"]),
        "commit": int(minima.get("estimated_commit_headroom_bytes") or 0) >= int(limits["commit_headroom_floor_bytes"]),
    }
    return {"pass": all(checks.values()), "checks": checks, "peaks": peaks, "machine_minima": minima}


def analyze_attempt(attempt_root: Path, contract: dict, preflight=False):
    metadata = _read(attempt_root / "attempt_metadata.json") or {}
    condition = metadata.get("condition")
    case_dir = attempt_root / str(metadata.get("label") or "")
    compatibility = copy.deepcopy(contract)
    compatibility["hard_gates"]["maximum_deep_velocity_m_s"] = contract["hard_gates"]["maximum_collision_on_deep_velocity_m_s"]
    row = legacy.analyze_case(case_dir, condition, compatibility, preflight=preflight)
    if condition == "OFF" and "deep_velocity" in row.get("failures", []):
        row["failures"] = [value for value in row["failures"] if value != "deep_velocity"]
        row["classification"] = "representative_pass" if not row["failures"] else "operation_failure"
    evidence = _read(case_dir / "runner_evidence.json") or {}
    audit = evidence.get("kit_import_audit") or {}
    import_ok = bool(
        audit.get("status") == "pass"
        and Path(str((audit.get("import") or {}).get("resolved_file") or "")).resolve()
        == (Path(__file__).resolve().parent / "probe_phase6fo_supply_comparison.py").resolve()
    )
    artifact = _artifact_gate(attempt_root, case_dir)
    guard = legacy._guard_summary(case_dir) or {}
    resource = _resource_gate(guard, contract)
    identity = _identity_gate(attempt_root, guard)
    axis = {
        "operation": row.get("classification") == "representative_pass" and import_ok and artifact["pass"],
        "resource": resource["pass"],
        "lifecycle": bool(
            (evidence.get("outcome") or {}).get("lifecycle_status") == "normal_exit"
            and evidence.get("process_exit_code") == 0
        ),
        "diagnostic_cleanup": identity.get("qualified") is True,
    }
    failures = list(row.get("failures") or [])
    if not import_ok: failures.append("kit_import_contract")
    if not artifact["pass"]: failures.append("preclose_artifact")
    if not resource["pass"]: failures.append("resource_gate")
    if not axis["lifecycle"]: failures.append("lifecycle_gate")
    if not axis["diagnostic_cleanup"]: failures.append("identity_cleanup_gate")
    row.update(metadata)
    row.update({"classification": "representative_pass" if all(axis.values()) else "operation_or_safety_failure",
                "failures": list(dict.fromkeys(failures)), "axes": axis, "import_audit": audit,
                "artifact_commit": artifact, "resource": resource, "identity_cleanup": identity})
    return row


def _paired(sequence: int, members: dict, contract: dict):
    pair = legacy.evaluate_pair(members["S93"], members["S100"], contract)
    gates = contract["hard_gates"]
    off_v = float(members["OFF"]["spatial"]["global_deep_maximum"]["velocity"])
    on_v = float(members["S100"]["spatial"]["global_deep_maximum"]["velocity"])
    off_ratio = on_v / max(off_v, float(gates["velocity_ratio_floor_m_s"]))
    failures = list(pair["failures"])
    if off_v < float(gates["minimum_collision_off_deep_velocity_m_s"]): failures.append("collision_off_positive_velocity")
    if off_ratio > float(gates["maximum_s100_to_off_deep_velocity_ratio"]): failures.append("s100_to_off_velocity_ratio")
    return {"sequence": sequence, **pair, "collision_off_deep_velocity_m_s": off_v,
            "s100_to_off_deep_velocity_ratio": off_ratio, "failures": failures, "pass": not failures}


def build(root: Path, contract_path: Path, offline_path: Path):
    contract = _read(contract_path)
    if not contract or contract.get("phase") != "phase6ga": raise ValueError("invalid Phase 6GA contract")
    preflight = [analyze_attempt(path.parent, contract, True) for path in sorted(root.glob("channel-preflight/*/attempt_metadata.json"))]
    attempts = [analyze_attempt(path.parent, contract, False) for path in sorted(root.glob("formal/*/attempt_metadata.json"))]
    pairs = []
    for sequence in range(1, 4):
        selected = {row["condition"]: row for row in attempts if row.get("sequence") == sequence and row.get("classification") == "representative_pass"}
        if set(selected) == {"S93", "S100", "OFF"}: pairs.append(_paired(sequence, selected, contract))
    representative = [row for row in attempts if row.get("classification") == "representative_pass"]
    cross = {"pass": False, "relative_ranges": {}, "failures": []}
    if len(representative) == 9 and len(pairs) == 3 and all(row["pass"] for row in pairs):
        limit = float(contract["hard_gates"]["maximum_run_relative_range"])
        series = {}
        for condition in ("S93", "S100", "OFF"):
            series[f"{condition}_deep_velocity"] = [float(row["spatial"]["global_deep_maximum"]["velocity"]) for row in representative if row["condition"] == condition]
        for name, values in series.items():
            relative = (max(values) - min(values)) / max(abs(float(np.mean(values))), float(contract["materiality"]["zero_denominator_floor"]))
            cross["relative_ranges"][name] = relative
            if relative > limit: cross["failures"].append(name)
        cross["pass"] = not cross["failures"]
    qualified = bool(preflight and preflight[-1]["classification"] == "representative_pass" and len(representative) == 9 and len(pairs) == 3 and all(row["pass"] for row in pairs) and cross["pass"])
    peaks = {role: [int((row.get("resource") or {}).get("peaks", {}).get(role) or 0) for row in representative] for role in ("kit", "tree", "runner", "diagnostic")}
    return {"schema": "campfire.phase6ga.supply-comparison-report.v1", "phase": "phase6ga",
            "status": "qualified_numeric" if qualified else "in_progress_or_safe_stop",
            "contract_sha256": _sha(contract_path), "offline_sha256": _sha(offline_path),
            "phase6fo_reclassified": False, "phase6fz_reclassified": False, "prior_population_reused": False,
            "channel_preflight": preflight, "attempts": attempts, "pairs": pairs, "cross_run": cross,
            "representative_processes": len(representative), "numeric_qualified": qualified,
            "visual_required": qualified, "resource_peak_distributions": peaks, "offline": _read(offline_path)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--offline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build(args.root.resolve(), args.contract.resolve(), args.offline.resolve())
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
