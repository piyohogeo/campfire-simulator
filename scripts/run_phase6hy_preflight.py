"""Persist the Phase 6HY exact-import and frozen-scene no-Kit preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from phase6hu_atomic_fixture import run_fixture as run_atomic_fixture
from phase6hx_point_policy_fixture import run_fixture as run_point_fixture
from phase6hx_stage_fixture import run_fixture as run_stage_fixture
from phase6hy_exact_import_fixture import run_fixture as run_import_fixture

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_root.absolute()
    if root.exists():
        raise RuntimeError("Phase 6HY preflight refuses root reuse")
    root.mkdir(parents=True)
    import_contract = SCRIPTS / "phase6hy_exact_kit_import_contract.json"
    import_sha = hashlib.sha256(import_contract.read_bytes()).hexdigest().upper()
    child_contract = SCRIPTS / "phase6hx_single_log_occlusion_contract.json"
    child_sha = hashlib.sha256(child_contract.read_bytes()).hexdigest().upper()
    import_fixture = run_import_fixture(root / "exact_import")
    point = run_point_fixture(root / "point_policy", SCRIPTS / "phase6hx_point_policy_source_set.json", SCRIPTS / "phase6hx_point_policy_source_set.sha256", ROOT)
    atomic = run_atomic_fixture(root / "atomic", child_contract, SCRIPTS / "phase6hs_operation_report_schema.json")
    stage = run_stage_fixture(root / "stage", child_contract)
    policy = json.loads(import_contract.read_text(encoding="utf-8"))
    checks = {
        "import_contract_digest": import_sha == (SCRIPTS / "phase6hy_exact_kit_import_contract.sha256").read_text(encoding="ascii").split()[0],
        "frozen_child_contract_digest": child_sha == policy["frozen_probe_contract"]["sha256"],
        "exact_import_fixture": import_fixture["status"] == "qualified",
        "point_policy_fixture": point["status"] == "qualified",
        "atomic_fixture": atomic["status"] == "qualified",
        "stage_fixture": stage["status"] == "qualified",
    }
    report = {
        "schema": "campfire.phase6hy.no-kit-preflight.v1", "phase": "phase6hy", "status": "qualified" if all(checks.values()) else "failed",
        "kit_launch_count": 0, "contract_sha256": import_sha, "frozen_probe_contract_sha256": child_sha, "checks": checks,
        "fixture_counts": {"exact_import": import_fixture["case_count"], "point_policy": point["case_count"], "atomic": len(atomic["cases"]), "stage": len(stage["cases"])},
        "phase6hx_reclassified": False, "phase6hx_artifact_or_runtime_reused": False,
    }
    (root / "preflight_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
