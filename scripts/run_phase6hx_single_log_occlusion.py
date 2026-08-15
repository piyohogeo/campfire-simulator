"""Run the independent Phase 6HX prelaunch invariant and fresh OFF/ON probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import run_phase6hw_single_log_occlusion as base
from phase6hs_operation_report import sha256_bytes
from phase6ho_app_ready_environment import write_json
from phase6hx_point_policy_invariant import append_marker, consume_report, produce_report, write_report
from phase6hx_stage_builder import write_stage
from phase6hx_stage_contract import validate_stage
from phase6hw_temporal_occlusion import build_media, evaluate


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts/phase6hx_single_log_occlusion_contract.json"
SIDECAR = ROOT / "scripts/phase6hx_single_log_occlusion_contract.sha256"
SCHEMA = ROOT / "scripts/phase6hs_operation_report_schema.json"
PROBE = ROOT / "scripts/probe_phase6hx_single_log_occlusion.py"
DEFAULT_MANIFEST = ROOT / "scripts/phase6hx_point_policy_source_set.json"
DEFAULT_MANIFEST_SIDECAR = ROOT / "scripts/phase6hx_point_policy_source_set.sha256"
BASE_INVARIANTS = {name: path for name, path in base.INVARIANTS.items() if name != "point_policy"}


def _configure_shared_harness() -> None:
    base.CONTRACT = CONTRACT
    base.SIDECAR = SIDECAR
    base.PROBE = PROBE
    base.INVARIANTS = BASE_INVARIANTS
    base.write_stage = write_stage
    base.validate_stage = validate_stage


def frozen_contract(manifest_path: Path, manifest_sidecar: Path) -> tuple[dict, str, str]:
    data = CONTRACT.read_bytes()
    digest = sha256_bytes(data)
    if digest != SIDECAR.read_text(encoding="ascii").split()[0].upper():
        raise RuntimeError("Phase 6HX contract digest mismatch")
    policy = json.loads(data)
    schema_digest = sha256_bytes(SCHEMA.read_bytes())
    if policy["operation_report"]["schema_sha256"] != schema_digest:
        raise RuntimeError("Phase 6HX operation schema binding mismatch")
    manifest_digest = sha256_bytes(manifest_path.read_bytes())
    if manifest_digest != manifest_sidecar.read_text(encoding="ascii").split()[0].upper() or manifest_digest != policy["point_policy_source_set"]["manifest_sha256"]:
        raise RuntimeError("Phase 6HX Point manifest binding mismatch")
    return policy, digest, schema_digest


def invariant_hashes(point_report: dict) -> dict:
    base_hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest().upper() for name, path in BASE_INVARIANTS.items()}
    return {**base_hashes, "point_policy_manifest": point_report["manifest_sha256"], "point_policy_order": point_report["ordered_entries_sha256"], "point_policy_entries": {entry["path"]: entry["sha256"] for entry in point_report["entries"]}}


def run_prelaunch(root: Path, manifest: Path, manifest_sidecar: Path) -> dict:
    attempt_id = "phase6hx-prelaunch-invariant"
    markers = root / "prelaunch_markers.jsonl"
    report_path = root / "point_policy_invariant.json"
    append_marker(markers, "production_invariant_hash_started", attempt_id=attempt_id, manifest=str(manifest))
    produced = produce_report(manifest, manifest_sidecar, ROOT, attempt_id)
    write_report(report_path, produced)
    consumed = consume_report(report_path, manifest, manifest_sidecar, ROOT, attempt_id)
    append_marker(markers, "production_invariant_hash_complete", attempt_id=attempt_id, entry_count=consumed["entry_count"], manifest_sha256=consumed["manifest_sha256"])
    result = {"schema": "campfire.phase6hx.prelaunch-invariant.v1", "phase": "phase6hx", "status": "qualified", "kit_launch_count": 0, "attempt_id": attempt_id, "report_path": str(report_path), "marker_path": str(markers), "entry_count": consumed["entry_count"], "manifest_sha256": consumed["manifest_sha256"], "ordered_entries_sha256": consumed["ordered_entries_sha256"], "canonical_report": consumed}
    write_json(root / "prelaunch_invariant_summary.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--preflight-report", type=Path, required=True)
    parser.add_argument("--point-manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--point-manifest-sidecar", type=Path, default=DEFAULT_MANIFEST_SIDECAR)
    parser.add_argument("--prelaunch-only", action="store_true")
    args = parser.parse_args()
    root = args.artifact_root.absolute()
    if root.exists():
        raise RuntimeError("Phase 6HX refuses artifact root reuse")
    preflight = json.loads(args.preflight_report.read_text(encoding="utf-8"))
    if preflight.get("status") != "qualified":
        raise RuntimeError("Phase 6HX no-Kit preflight missing")
    manifest = args.point_manifest.absolute()
    manifest_sidecar = args.point_manifest_sidecar.absolute()
    policy, contract_sha, schema_sha = frozen_contract(manifest, manifest_sidecar)
    if preflight.get("contract_sha256") != contract_sha or preflight.get("point_manifest_sha256") != policy["point_policy_source_set"]["manifest_sha256"]:
        raise RuntimeError("Phase 6HX preflight identity mismatch")
    root.mkdir(parents=True)
    shutil.copy2(CONTRACT, root / "frozen_contract.json")
    shutil.copy2(SIDECAR, root / "frozen_contract.sha256")
    shutil.copy2(manifest, root / "frozen_point_policy_source_set.json")
    shutil.copy2(manifest_sidecar, root / "frozen_point_policy_source_set.sha256")
    prelaunch = run_prelaunch(root, manifest, manifest_sidecar)
    if args.prelaunch_only:
        write_json(root / "summary.json", {"schema": "campfire.phase6hx.summary.v1", "phase": "phase6hx", "status": "qualified_prelaunch_only", "kit_launch_count": 0, "prelaunch": prelaunch, "phase6hw_reclassified": False, "phase6hw_root_or_artifact_reused": False})
        return 0

    _configure_shared_harness()
    before = invariant_hashes(prelaunch["canonical_report"])
    stage_audit = base.prepare_stages(root, policy)
    if not stage_audit["passed"]:
        write_json(root / "summary.json", {"schema": "campfire.phase6hx.summary.v1", "phase": "phase6hx", "status": "safe_stop_pre_kit", "kit_launch_count": 0, "prelaunch": prelaunch, "stage_audit": stage_audit})
        return 1
    results = {}
    for condition in [item["name"] for item in policy["condition_order"]]:
        results[condition] = base.run_condition(root, condition, policy, contract_sha, schema_sha)
        if results[condition]["status"] != "qualified":
            write_json(root / "summary.json", {"schema": "campfire.phase6hx.summary.v1", "phase": "phase6hx", "status": "safe_stop", "conditions": results, "stopped_after": condition, "prelaunch": prelaunch, "stage_audit": stage_audit, "phase6hw_reclassified": False, "phase6hw_root_or_artifact_reused": False, "production_changed": False})
            return 1
    visual, arrays = evaluate(root, policy, "pending")
    visual["media"] = build_media(root, policy, visual, arrays, root / "media")
    write_json(root / "temporal_evidence.json", visual)
    current_point = consume_report(root / "point_policy_invariant.json", manifest, manifest_sidecar, ROOT, "phase6hx-prelaunch-invariant")
    after = invariant_hashes(current_point)
    invariant = before == after
    status = "awaiting_human_review" if visual["automated_pass"] and invariant else "safe_stop"
    summary = {
        "schema": "campfire.phase6hx.summary.v1", "phase": "phase6hx", "status": status, "contract_sha256": contract_sha,
        "kit_launch_count": 2, "conditions": results, "prelaunch": prelaunch, "stage_audit": stage_audit, "temporal_evidence": visual,
        "invariant_hashes_before": before, "invariant_hashes_after": after, "invariants_pass": invariant,
        "phase6hv_reclassified": False, "phase6hw_reclassified": False, "phase6hw_root_or_artifact_reused": False,
        "production_changed": False, "defaults_changed": False, "point_policy_changed": False, "v3_changed": False, "latest_demo_changed": False,
    }
    write_json(root / "summary.json", summary)
    return 0 if status == "awaiting_human_review" else 1


if __name__ == "__main__":
    raise SystemExit(main())
