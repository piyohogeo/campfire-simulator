"""Run fresh Phase 6HY OFF/ON only after exact-import smoke qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import run_phase6hx_single_log_occlusion as phase6hx
from phase6ho_app_ready_environment import write_json
from phase6hw_temporal_occlusion import build_media, evaluate

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
IMPORT_CONTRACT = SCRIPTS / "phase6hy_exact_kit_import_contract.json"
IMPORT_SIDECAR = SCRIPTS / "phase6hy_exact_kit_import_contract.sha256"
PROBE = SCRIPTS / "probe_phase6hy_single_log_occlusion.py"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--preflight-report", type=Path, required=True)
    parser.add_argument("--smoke-summary", type=Path, required=True)
    args = parser.parse_args()
    root = args.artifact_root.absolute()
    if root.exists():
        raise RuntimeError("Phase 6HY formal root reuse refused")
    preflight = json.loads(args.preflight_report.read_text(encoding="utf-8"))
    smoke = json.loads(args.smoke_summary.read_text(encoding="utf-8"))
    if preflight.get("status") != "qualified" or smoke.get("status") != "qualified" or smoke.get("accepted_lifecycle") is not True:
        raise RuntimeError("Phase 6HY preflight or real Kit import smoke not qualified")
    import_sha = hashlib.sha256(IMPORT_CONTRACT.read_bytes()).hexdigest().upper()
    if import_sha != IMPORT_SIDECAR.read_text(encoding="ascii").split()[0] or preflight.get("contract_sha256") != import_sha:
        raise RuntimeError("Phase 6HY import contract identity mismatch")
    policy, child_sha, schema_sha = phase6hx.frozen_contract(phase6hx.DEFAULT_MANIFEST, phase6hx.DEFAULT_MANIFEST_SIDECAR)
    root.mkdir(parents=True)
    shutil.copy2(IMPORT_CONTRACT, root / "frozen_import_contract.json")
    shutil.copy2(IMPORT_SIDECAR, root / "frozen_import_contract.sha256")
    shutil.copy2(phase6hx.CONTRACT, root / "frozen_probe_contract.json")
    prelaunch = phase6hx.run_prelaunch(root, phase6hx.DEFAULT_MANIFEST, phase6hx.DEFAULT_MANIFEST_SIDECAR)
    phase6hx._configure_shared_harness()
    phase6hx.base.PROBE = PROBE
    before = phase6hx.invariant_hashes(prelaunch["canonical_report"])
    stage_audit = phase6hx.base.prepare_stages(root, policy)
    if not stage_audit["passed"]:
        write_json(root / "summary.json", {"schema": "campfire.phase6hy.summary.v1", "phase": "phase6hy", "status": "safe_stop_pre_kit", "kit_launch_count": 0, "stage_audit": stage_audit})
        return 1
    results = {}
    for condition in ("collision_off", "collision_on"):
        results[condition] = phase6hx.base.run_condition(root, condition, policy, child_sha, schema_sha)
        if results[condition]["status"] != "qualified":
            write_json(root / "summary.json", {"schema": "campfire.phase6hy.summary.v1", "phase": "phase6hy", "status": "safe_stop", "kit_launch_count": len(results), "conditions": results, "stopped_after": condition, "stage_audit": stage_audit, "phase6hx_reclassified": False, "phase6hx_runtime_reused": False, "production_changed": False})
            return 1
    visual, arrays = evaluate(root, policy, "pending")
    visual["media"] = build_media(root, policy, visual, arrays, root / "media")
    write_json(root / "temporal_evidence.json", visual)
    after_report = phase6hx.consume_report(root / "point_policy_invariant.json", phase6hx.DEFAULT_MANIFEST, phase6hx.DEFAULT_MANIFEST_SIDECAR, ROOT, "phase6hx-prelaunch-invariant")
    invariant = before == phase6hx.invariant_hashes(after_report)
    status = "awaiting_human_review" if visual["automated_pass"] and invariant else "safe_stop"
    summary = {
        "schema": "campfire.phase6hy.summary.v1", "phase": "phase6hy", "status": status, "contract_sha256": import_sha,
        "frozen_probe_contract_sha256": child_sha, "kit_launch_count": 2, "conditions": results, "stage_audit": stage_audit,
        "temporal_evidence": visual, "invariants_pass": invariant, "phase6hx_reclassified": False, "phase6hx_runtime_reused": False,
        "production_changed": False, "defaults_changed": False, "point_policy_changed": False, "v3_changed": False, "latest_demo_changed": False,
    }
    write_json(root / "summary.json", summary)
    return 0 if status == "awaiting_human_review" else 1


if __name__ == "__main__":
    raise SystemExit(main())
