"""Run the fresh Phase 6IA OFF->ON comparison using only frozen contracts."""

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
PARENT = SCRIPTS / "phase6ia_single_log_occlusion_contract.json"
PARENT_SIDECAR = SCRIPTS / "phase6ia_single_log_occlusion_contract.sha256"
PROBE = SCRIPTS / "probe_phase6ia_single_log_occlusion.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--preflight-report", type=Path, required=True)
    args = parser.parse_args()
    root = args.artifact_root.absolute()
    if root.exists():
        raise RuntimeError("Phase 6IA formal root reuse refused")
    parent_sha = sha(PARENT)
    if parent_sha != PARENT_SIDECAR.read_text(encoding="ascii").split()[0].upper():
        raise RuntimeError("Phase 6IA parent contract digest mismatch")
    parent = json.loads(PARENT.read_text(encoding="utf-8"))
    preflight = json.loads(args.preflight_report.read_text(encoding="utf-8"))
    if preflight.get("status") != "qualified" or preflight.get("contract_sha256") != parent_sha:
        raise RuntimeError("Phase 6IA no-Kit preflight did not qualify this contract")
    policy, child_sha, schema_sha = phase6hx.frozen_contract(phase6hx.DEFAULT_MANIFEST, phase6hx.DEFAULT_MANIFEST_SIDECAR)
    if child_sha != parent["frozen_probe_contract"]["sha256"]:
        raise RuntimeError("Phase 6IA frozen child contract mismatch")
    root.mkdir(parents=True)
    shutil.copy2(PARENT, root / "frozen_orchestration_contract.json")
    shutil.copy2(PARENT_SIDECAR, root / "frozen_orchestration_contract.sha256")
    shutil.copy2(phase6hx.CONTRACT, root / "frozen_probe_contract.json")
    shutil.copy2(phase6hx.SIDECAR, root / "frozen_probe_contract.sha256")
    shutil.copy2(phase6hx.DEFAULT_MANIFEST, root / "frozen_point_policy_source_set.json")
    shutil.copy2(phase6hx.DEFAULT_MANIFEST_SIDECAR, root / "frozen_point_policy_source_set.sha256")
    prelaunch = phase6hx.run_prelaunch(root, phase6hx.DEFAULT_MANIFEST, phase6hx.DEFAULT_MANIFEST_SIDECAR)
    phase6hx._configure_shared_harness()
    phase6hx.base.PROBE = PROBE
    before = phase6hx.invariant_hashes(prelaunch["canonical_report"])
    stage_audit = phase6hx.base.prepare_stages(root, policy)
    if not stage_audit["passed"]:
        write_json(root / "summary.json", {"schema":"campfire.phase6ia.summary.v1","phase":"phase6ia","status":"safe_stop_pre_kit","contract_sha256":parent_sha,"kit_launch_count":0,"stage_audit":stage_audit})
        return 1
    results = {}
    for condition in parent["execution"]["condition_order"]:
        results[condition] = phase6hx.base.run_condition(root, condition, policy, child_sha, schema_sha)
        if results[condition]["status"] != "qualified":
            write_json(root / "summary.json", {
                "schema":"campfire.phase6ia.summary.v1","phase":"phase6ia","status":"safe_stop","contract_sha256":parent_sha,
                "kit_launch_count":len(results),"conditions":results,"stopped_after":condition,"prelaunch":prelaunch,"stage_audit":stage_audit,
                "retry_count":0,"replacement_count":0,"phase6hv_hw_hx_hy_hz_reclassified":False,"past_runtime_reused":False,"production_changed":False,
            })
            return 1
    visual, arrays = evaluate(root, policy, "pending")
    visual["media"] = build_media(root, policy, visual, arrays, root / "media")
    write_json(root / "temporal_evidence.json", visual)
    current_point = phase6hx.consume_report(root / "point_policy_invariant.json", phase6hx.DEFAULT_MANIFEST, phase6hx.DEFAULT_MANIFEST_SIDECAR, ROOT, "phase6hx-prelaunch-invariant")
    after = phase6hx.invariant_hashes(current_point)
    invariant = before == after
    status = "awaiting_human_review" if visual["automated_pass"] and invariant else "safe_stop_visual_or_metric_ambiguity"
    summary = {
        "schema":"campfire.phase6ia.summary.v1","phase":"phase6ia","status":status,"contract_sha256":parent_sha,
        "frozen_probe_contract_sha256":child_sha,"kit_launch_count":2,"retry_count":0,"replacement_count":0,
        "conditions":results,"prelaunch":prelaunch,"stage_audit":stage_audit,"temporal_evidence":visual,
        "invariant_hashes_before":before,"invariant_hashes_after":after,"invariants_pass":invariant,
        "phase6hv_hw_hx_hy_hz_reclassified":False,"past_runtime_reused":False,"production_changed":False,"defaults_changed":False,
        "point_policy_changed":False,"v3_changed":False,"latest_demo_changed":False,
    }
    write_json(root / "summary.json", summary)
    return 0 if status == "awaiting_human_review" else 1


if __name__ == "__main__":
    raise SystemExit(main())

