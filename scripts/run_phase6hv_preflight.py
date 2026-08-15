"""Run Phase 6HV no-Kit atomic, stage-authoring, and exact-harness preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from phase6hu_atomic_fixture import run_fixture as run_atomic_fixture
from phase6hv_probe_source import build_probe_source
from phase6hv_stage_fixture import run_fixture as run_stage_fixture


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--phase6hu-stage", type=Path, required=True)
    args = parser.parse_args()
    if args.output_root.exists():
        raise RuntimeError("Phase 6HV preflight refuses root reuse")
    args.output_root.mkdir(parents=True)
    contract_path = SCRIPTS / "phase6hv_static_flow_occlusion_contract.json"
    sidecar = (SCRIPTS / "phase6hv_static_flow_occlusion_contract.sha256").read_text(encoding="ascii").split()[0]
    contract_hash = hashlib.sha256(contract_path.read_bytes()).hexdigest().upper()
    atomic = run_atomic_fixture(args.output_root / "atomic", contract_path, SCRIPTS / "phase6hs_operation_report_schema.json")
    stage = run_stage_fixture(args.output_root / "stage", contract_path, args.phase6hu_stage)
    source = build_probe_source(SCRIPTS / "probe_phase6hk_flow_proxy_boundary.py")
    compile(source, str(SCRIPTS / "probe_phase6hv_static_flow_occlusion.py"), "exec")
    case = (SCRIPTS / "run_phase6hv_kit_case.ps1").read_text(encoding="utf-8")
    runner = (SCRIPTS / "run_phase6hv_static_flow_occlusion.py").read_text(encoding="utf-8")
    checks = {
        "contract_digest": contract_hash == sidecar,
        "atomic_fixture_qualified": atomic["status"] == "qualified",
        "stage_fixture_qualified": stage["status"] == "qualified",
        "probe_one_variable": 'collision_enabled = condition == "collision_on"' in source and source.count("known_good._define_flow(stage, collision_enabled)") == 1,
        "probe_fixed_phase6hu_settings": "EMITTER_RADIUS_M = 0.20" in source and "CAMERA_EYE = (2.65, -4.2, 2.35)" in source and "CAPTURE_RESOLUTION = (1280, 720)" in source,
        "probe_stage_gate_before_open": source.index('mark("stage_contract_complete"') < source.index("await context.open_stage_async"),
        "probe_atomic_cleanup": "DurableOperationReporter" in source and "reporter.enter_cleanup()" in source,
        "probe_no_readback": "get_latest_nanovdb_readback" not in source and "buffer_to_volume" not in source and "save_volume" not in source,
        "case_exact_condition_binding": 'ValidateSet("collision_on","collision_off")' in case and '"--/phase6hv/condition=$Condition"' in case,
        "runner_fixed_order": 'for condition in [item["name"] for item in policy["condition_order"]]' in runner,
        "runner_no_retry_replacement": '"retry_count": 0, "replacement_count": 0' in runner,
        "kit_launch_count_zero": atomic["kit_launch_count"] == 0 and stage["kit_launch_count"] == 0,
    }
    report = {
        "schema": "campfire.phase6hv.no-kit-preflight.v1",
        "phase": "phase6hv",
        "status": "qualified" if all(checks.values()) else "failed",
        "kit_launch_count": 0,
        "contract_sha256": contract_hash,
        "checks": checks,
        "atomic_fixture": {"status": atomic["status"], "case_count": len(atomic["cases"])},
        "stage_fixture": {"status": stage["status"], "case_count": len(stage["cases"]), "report": str(args.output_root / "stage/stage_fixture_report.json")},
        "phase6hs_reclassified": False,
        "phase6ht_reclassified": False,
        "phase6hu_reclassified": False,
        "phase6hu_runtime_reused_as_formal_result": False,
    }
    (args.output_root / "preflight_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
