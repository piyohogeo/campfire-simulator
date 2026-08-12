"""Aggregate bounded Phase 6FB startup probes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from phase6fb_startup_contract import classify_startup


LABELS = ("P0_no_readback", "P1_no_readback_repeat")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def marker_names(path: Path):
    if not path.exists():
        return []
    return [json.loads(line)["marker"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def analyze_case(root: Path, label: str, contract: dict) -> dict:
    directory = root / label
    raw = load(directory / "raw.json") or {}
    evidence = load(directory / "runner_evidence.json") or {}
    guard = load(root / "runner-logs" / f"{label}.guard.json") or {}
    names = marker_names(directory / "resource_markers.jsonl")
    source = raw.get("startup_live_point_emitter_contract") or {}
    history = (raw.get("startup_probe") or {}).get("history") or raw.get("flow_liveness_history") or []
    startup = classify_startup(history, source, contract["classification"])
    missing = [name for name in contract["required_startup_markers"] if name not in names]
    outcome = evidence.get("outcome") or {}
    lifecycle_pass = bool(
        raw.get("status") == "ok" and raw.get("lifecycle_marker") == "shutdown_complete"
        and outcome.get("functional_status") == "pass" and outcome.get("lifecycle_status") == "normal_exit"
        and guard.get("status") == "ok" and guard.get("exit_code") == 0 and guard.get("process_absent") is True
    )
    return {
        "classification": startup,
        "startup_markers_complete": not missing,
        "missing_startup_markers": missing,
        "lifecycle_pass": lifecycle_pass,
        "probe_status": raw.get("status"),
        "lifecycle_marker": raw.get("lifecycle_marker"),
        "stage_sha256": raw.get("stage_sha256"),
        "payload_sha256": (raw.get("point_payload") or {}).get("payload_sha256"),
        "source_contract": source,
        "resource_guard": guard,
        "shutdown_outcome": outcome,
        "condition_formal_pass": bool(
            startup["classification"] == "representative_ingestion" and not missing and lifecycle_pass
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = load(args.contract)
    cases = {label: analyze_case(args.root, label, contract) for label in LABELS if (args.root / label).exists()}
    classes = [item["classification"]["classification"] for item in cases.values()]
    stage_hashes = {item["stage_sha256"] for item in cases.values()}
    payload_hashes = {item["payload_sha256"] for item in cases.values()}
    report = {
        "schema": "campfire.phase6fb.startup-ingestion-report.v1",
        "phase": "phase6fb",
        "contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest().upper(),
        "history_frozen": True,
        "cases": cases,
        "process_count": len(cases),
        "classifications": classes,
        "stage_hash_equal_across_processes": len(stage_hashes) <= 1,
        "payload_hash_equal_across_processes": len(payload_hashes) <= 1,
        "reproducible_representative_startup": bool(
            len(cases) == 2 and all(item["condition_formal_pass"] for item in cases.values())
        ),
        "split_startup_observed": len(set(classes)) > 1,
        "public_field_checked": False,
        "long_population_started": False,
        "production_changed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
