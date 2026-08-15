"""Run the complete no-Kit Phase 6HW preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from phase6hu_atomic_fixture import run_fixture as run_atomic_fixture
from phase6hw_stage_fixture import run_fixture as run_stage_fixture


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.output_root.exists():
        raise RuntimeError("Phase 6HW preflight refuses root reuse")
    args.output_root.mkdir(parents=True)
    contract_path = SCRIPTS / "phase6hw_single_log_occlusion_contract.json"
    sidecar = (SCRIPTS / "phase6hw_single_log_occlusion_contract.sha256").read_text(encoding="ascii").split()[0]
    contract_hash = hashlib.sha256(contract_path.read_bytes()).hexdigest().upper()
    atomic = run_atomic_fixture(args.output_root / "atomic", contract_path, SCRIPTS / "phase6hs_operation_report_schema.json")
    stage = run_stage_fixture(args.output_root / "stage", contract_path)
    probe = (SCRIPTS / "probe_phase6hw_single_log_occlusion.py").read_text(encoding="utf-8")
    case = (SCRIPTS / "run_phase6hw_kit_case.ps1").read_text(encoding="utf-8")
    runner = (SCRIPTS / "run_phase6hw_single_log_occlusion.py").read_text(encoding="utf-8")
    compile(probe, str(SCRIPTS / "probe_phase6hw_single_log_occlusion.py"), "exec")
    forbidden = ("get_latest_nanovdb_readback", "buffer_to_volume", "save_volume", "_sample_grid")
    checks = {
        "contract_digest": contract_hash == sidecar,
        "atomic_fixture_qualified": atomic["status"] == "qualified",
        "stage_fixture_qualified": stage["status"] == "qualified",
        "probe_stage_gate_before_open": probe.index('mark("stage_contract_complete"') < probe.index("await context.open_stage_async"),
        "probe_fixed_temporal_window": "stable_capture_frames" in probe and "active_block_frames" in probe,
        "probe_no_readback_or_cpu_volume": all(token not in probe for token in forbidden),
        "probe_atomic_cleanup": "DurableOperationReporter" in probe and "reporter.enter_cleanup()" in probe,
        "case_exact_condition_binding": 'ValidateSet("collision_on","collision_off")' in case and '"--/phase6hw/condition=$Condition"' in case,
        "runner_fixed_order": 'for condition in [item["name"] for item in policy["condition_order"]]' in runner,
        "runner_no_retry_replacement": '"retry_count": 0, "replacement_count": 0' in runner,
        "runner_fresh_root": "refuses artifact root reuse" in runner,
        "kit_launch_count_zero": atomic["kit_launch_count"] == 0 and stage["kit_launch_count"] == 0,
    }
    report = {
        "schema": "campfire.phase6hw.no-kit-preflight.v1",
        "phase": "phase6hw",
        "status": "qualified" if all(checks.values()) else "failed",
        "kit_launch_count": 0,
        "contract_sha256": contract_hash,
        "checks": checks,
        "atomic_fixture": {"status": atomic["status"], "case_count": len(atomic["cases"])},
        "stage_fixture": {"status": stage["status"], "case_count": len(stage["cases"])},
        "phase6hv_reclassified": False,
        "phase6hv_artifacts_or_images_reused": False,
    }
    (args.output_root / "preflight_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
