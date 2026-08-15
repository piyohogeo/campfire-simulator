"""Run Phase 6HX Point-invariant, atomic, stage, and exact prelaunch fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from phase6hu_atomic_fixture import run_fixture as run_atomic_fixture
from phase6hx_point_policy_fixture import run_fixture as run_point_fixture
from phase6hx_probe_source import build_probe_source
from phase6hx_stage_fixture import run_fixture as run_stage_fixture


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.output_root.exists():
        raise RuntimeError("Phase 6HX preflight refuses root reuse")
    args.output_root.mkdir(parents=True)
    contract_path = SCRIPTS / "phase6hx_single_log_occlusion_contract.json"
    contract_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest().upper()
    contract_sidecar = (SCRIPTS / "phase6hx_single_log_occlusion_contract.sha256").read_text(encoding="ascii").split()[0]
    manifest = SCRIPTS / "phase6hx_point_policy_source_set.json"
    manifest_sidecar = SCRIPTS / "phase6hx_point_policy_source_set.sha256"
    manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest().upper()
    point = run_point_fixture(args.output_root / "point_policy", manifest, manifest_sidecar, ROOT)
    atomic = run_atomic_fixture(args.output_root / "atomic", contract_path, SCRIPTS / "phase6hs_operation_report_schema.json")
    stage = run_stage_fixture(args.output_root / "stage", contract_path)
    exact_source = build_probe_source(SCRIPTS / "probe_phase6hw_single_log_occlusion.py")
    compile(exact_source, str(SCRIPTS / "probe_phase6hx_single_log_occlusion.py"), "exec")
    provisional = args.output_root / "provisional_preflight.json"
    provisional.write_text(json.dumps({"status": "qualified", "contract_sha256": contract_sha, "point_manifest_sha256": manifest_sha}) + "\n", encoding="utf-8")
    smoke_root = args.output_root / "exact_prelaunch_smoke"
    command = [sys.executable, str(SCRIPTS / "run_phase6hx_single_log_occlusion.py"), "--artifact-root", str(smoke_root), "--preflight-report", str(provisional), "--point-manifest", str(manifest), "--point-manifest-sidecar", str(manifest_sidecar), "--prelaunch-only"]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
    smoke_summary = json.loads((smoke_root / "summary.json").read_text(encoding="utf-8")) if (smoke_root / "summary.json").is_file() else {}
    marker_text = (smoke_root / "prelaunch_markers.jsonl").read_text(encoding="utf-8") if (smoke_root / "prelaunch_markers.jsonl").is_file() else ""
    runner_source = (SCRIPTS / "run_phase6hx_single_log_occlusion.py").read_text(encoding="utf-8")
    forbidden = ("get_latest_nanovdb_readback", "buffer_to_volume", "save_volume", "_sample_grid")
    checks = {
        "contract_digest": contract_sha == contract_sidecar,
        "point_policy_fixture": point["status"] == "qualified",
        "point_policy_current_repository": point["canonical_entry_count"] == 13,
        "atomic_fixture": atomic["status"] == "qualified",
        "stage_fixture": stage["status"] == "qualified",
        "exact_probe_compiles": True,
        "no_readback_or_cpu_volume": all(token not in exact_source for token in forbidden),
        "formal_runner_fixed_order": 'for condition in [item["name"] for item in policy["condition_order"]]' in runner_source,
        "formal_runner_no_retry": '"retry_count": 0, "replacement_count": 0' in (SCRIPTS / "run_phase6hw_single_log_occlusion.py").read_text(encoding="utf-8"),
        "exact_prelaunch_command_exit_zero": completed.returncode == 0,
        "exact_prelaunch_marker_complete": "production_invariant_hash_complete" in marker_text,
        "exact_prelaunch_kit_launch_zero": smoke_summary.get("kit_launch_count") == 0,
        "exact_prelaunch_same_manifest": ((smoke_summary.get("prelaunch") or {}).get("manifest_sha256") == manifest_sha),
    }
    report = {
        "schema": "campfire.phase6hx.no-kit-preflight.v1", "phase": "phase6hx",
        "status": "qualified" if all(checks.values()) else "failed", "kit_launch_count": 0,
        "contract_sha256": contract_sha, "point_manifest_sha256": manifest_sha,
        "checks": checks, "point_policy_fixture": {"status": point["status"], "case_count": point["case_count"]},
        "atomic_fixture": {"status": atomic["status"], "case_count": len(atomic["cases"])},
        "stage_fixture": {"status": stage["status"], "case_count": len(stage["cases"])},
        "exact_prelaunch_command": command, "exact_prelaunch_stdout": completed.stdout[-2048:], "exact_prelaunch_stderr": completed.stderr[-2048:],
        "phase6hw_reclassified": False, "phase6hw_root_or_artifact_reused": False,
    }
    (args.output_root / "preflight_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
