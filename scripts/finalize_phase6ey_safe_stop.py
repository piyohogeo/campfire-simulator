"""Persist a fail-closed Phase 6EY runner/analyzer safe stop."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--production-app", type=Path, required=True)
    args = parser.parse_args()
    report_path = args.root / "dynamic_stationarity_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    run = report["cases"].get("R0_run01")
    if run is None or not run["normal_exit"] or not run["dynamic_stationarity_pass"]:
        raise SystemExit("R0 run 1 is not valid bounded partial evidence")
    if report["r0_completed_runs"] != 1 or report["r1_started"]:
        raise SystemExit("unexpected Phase 6EY process population")
    contract_hash = hashlib.sha256(args.contract.read_bytes()).hexdigest().upper()
    production_hash = hashlib.sha256(args.production_app.read_bytes()).hexdigest().upper()
    now = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema": "campfire.phase6ey.dynamic-stationarity-safe-stop.v1",
        "phase": "phase6ey",
        "status": "safe_stop",
        "reason": "post_run_analyzer_contract_adapter_failure",
        "active_condition": "R0_run01_postprocess",
        "completed_kit_processes": 1,
        "formal_r0_qualification_runs": 0,
        "bounded_partial_evidence_runs": 1,
        "r0_run01_normal_exit": True,
        "r0_run01_dynamic_stationarity_pass_after_offline_analyzer_correction": True,
        "r0_run02_started": False,
        "r0_run03_started": False,
        "r1_started": False,
        "automatic_retry": False,
        "contract_sha256": contract_hash,
        "production_app_sha256": production_hash,
        "production_changed": False,
        "updated_utc": now,
    }
    (args.root / "safe_stop_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    state = {
        "schema": "campfire.phase6ey.incremental-state.v1",
        "phase": "phase6ey",
        "status": "safe_stop",
        "completed_kit_processes": 1,
        "maximum_kit_processes": 4,
        "active_condition": "R0_run01_postprocess",
        "reason": "post_run_analyzer_contract_adapter_failure",
        "contract_sha256": contract_hash,
        "production_app_sha256_before": production_hash,
        "production_app_sha256_current": production_hash,
        "production_changed": False,
        "updated_utc": now,
    }
    (args.root / "incremental_state.json").write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
