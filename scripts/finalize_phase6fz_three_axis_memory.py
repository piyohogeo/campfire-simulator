"""Finalize an already complete Phase 6FZ population without rerunning Kit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import analyze_phase6fz_three_axis_memory_qualification as analyzer


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _atomic_json(path: Path, value: dict) -> None:
    partial = path.with_suffix(path.suffix + ".partial")
    encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with partial.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    partial.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--production-app", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    contract = root / "frozen_contract.json"
    hash_path = root / "frozen_contract.sha256"
    expected_hash = hash_path.read_text(encoding="utf-8").split()[0].upper()
    if _sha256(contract) != expected_hash:
        raise RuntimeError("frozen contract hash mismatch")
    prior_state = json.loads((root / "incremental_state.json").read_text(encoding="utf-8"))
    if prior_state.get("status") != "running" or int(prior_state.get("launches", -1)) != 9:
        raise RuntimeError("finalizer only accepts the nine-launch post-population handoff boundary")
    report = analyzer.build(root, contract)
    attempts = report.get("attempts") or []
    if len(attempts) != 9:
        raise RuntimeError("exactly nine attempts are required")
    if any(row.get("classification") != "memory_valid_lifecycle_normal" for row in attempts):
        raise RuntimeError("all nine attempts must already be memory-valid normal exits")
    if report.get("replacement_map"):
        raise RuntimeError("post-population finalizer does not accept replacements")
    if not report.get("memory_ceiling_qualified") or not report.get("phase6fo_monitored_restart_ready"):
        raise RuntimeError("analyzer did not qualify the completed population")
    production_hash = _sha256(args.production_app.resolve(strict=True))
    if production_hash != str(prior_state.get("production_sha256") or "").upper():
        raise RuntimeError("production app hash changed")
    _atomic_json(root / "three_axis_memory_qualification_report.json", report)
    finalization = {
        "schema": "campfire.phase6fz.post-population-finalization.v1",
        "phase": "phase6fz",
        "status": "qualified",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "reason": "all nine attempts and the analyzer report were committed before the empty replacement-queue PowerShell handoff error",
        "harness_error": "Argument types do not match while enumerating an empty generic replacement queue",
        "kit_processes_rerun": 0,
        "attempt_count": 9,
        "memory_valid": report["counts"]["memory_valid"],
        "normal_os_exit": report["counts"]["normal_os_exit"],
        "stage_close_timeout": report["counts"]["stage_close_timeout"],
        "replacement_count": len(report.get("replacement_map") or []),
        "memory_ceiling_qualified": report["memory_ceiling_qualified"],
        "phase6fo_monitored_restart_ready": report["phase6fo_monitored_restart_ready"],
        "contract_sha256": expected_hash,
        "production_sha256": production_hash,
    }
    _atomic_json(root / "post_population_finalization.json", finalization)
    final_state = dict(prior_state)
    final_state.update(
        status="qualified",
        active_attempt="complete",
        active_classification="memory_qualified_lifecycle_separate",
        stop_reason="",
        timestamp_utc=finalization["timestamp_utc"],
        post_population_finalizer="finalize_phase6fz_three_axis_memory.py",
    )
    _atomic_json(root / "incremental_state.json", final_state)
    print(json.dumps(finalization, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

