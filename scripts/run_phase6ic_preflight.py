"""No-Kit preflight for Phase 6IC deterministic stage authoring dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from phase6hu_atomic_fixture import run_fixture as run_atomic_fixture
from phase6hx_point_policy_fixture import run_fixture as run_point_fixture
from phase6hy_exact_import_fixture import run_fixture as run_exact_fixture
from phase6ic_no_kit_fixture import run_fixture as run_phase_fixture

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CONTRACT = SCRIPTS / "phase6ic_stage_open_contract.json"
SIDECAR = SCRIPTS / "phase6ic_stage_open_contract.sha256"
MANIFEST = SCRIPTS / "phase6ic_authoring_dependencies.json"
MANIFEST_SHA = SCRIPTS / "phase6ic_authoring_dependencies.sha256"
FROZEN = SCRIPTS / "phase6hx_single_log_occlusion_contract.json"
POINT = SCRIPTS / "phase6hx_point_policy_source_set.json"
POINT_SHA = SCRIPTS / "phase6hx_point_policy_source_set.sha256"
SCHEMA = SCRIPTS / "phase6hs_operation_report_schema.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_root.absolute()
    if root.exists():
        raise RuntimeError("Phase 6IC preflight refuses root reuse")
    root.mkdir(parents=True)
    policy = json.loads(CONTRACT.read_text(encoding="utf-8"))
    digest = sha(CONTRACT)
    phase = run_phase_fixture(root / "phase6ic", MANIFEST, MANIFEST_SHA, ROOT, FROZEN)
    exact = run_exact_fixture(root / "exact_import")
    point = run_point_fixture(root / "point_policy", POINT, POINT_SHA, ROOT)
    atomic = run_atomic_fixture(root / "atomic", FROZEN, SCHEMA)
    source_checks = {}
    for name, entry in policy["bootstrap_sources"].items():
        source_checks["bootstrap_sha256:" + name] = sha(ROOT / entry["path"]) == entry["sha256"]
    checks = {
        "contract_digest": digest == SIDECAR.read_text(encoding="ascii").split()[0].upper(),
        "manifest_digest": sha(MANIFEST) == MANIFEST_SHA.read_text(encoding="ascii").split()[0].upper() == policy["dependency_manifest"]["sha256"],
        "frozen_probe_digest": sha(FROZEN) == policy["frozen_probe_contract"]["sha256"],
        "phase6ib_frozen": policy["frozen_history"]["phase6ib"]["status"] == "safe_stop_kit_stage_authoring_import_harness_failure" and policy["frozen_history"]["reclassified"] is False,
        "phase6ic_fixture": phase["status"] == "qualified",
        "phase6hz_exact_loader_fixture": exact["status"] == "qualified",
        "point_policy_fixture": point["status"] == "qualified" and point["canonical_entry_count"] == 13,
        "atomic_report_fixture": atomic["status"] == "qualified",
        "kit_not_launched": all(item["kit_launch_count"] == 0 for item in (phase, exact, point, atomic)),
        "single_runtime_launch": policy["smoke"]["launches"] == 1 and policy["smoke"]["retry"] == policy["smoke"]["replacement"] == 0,
        "forbidden_runtime_operations_zero": all(policy["smoke"][name] == 0 for name in ("timeline_play_calls", "flow_update_calls", "flow_interface_calls", "readback_calls", "capture_calls")),
        **source_checks,
    }
    report = {
        "schema": "campfire.phase6ic.preflight.v1", "phase": "phase6ic",
        "status": "qualified" if all(checks.values()) else "failed",
        "contract_sha256": digest, "manifest_sha256": sha(MANIFEST), "kit_launch_count": 0,
        "checks": checks,
        "fixture_counts": {"phase6ic": phase["case_count"], "exact_import": exact["case_count"], "point_policy": point["case_count"], "atomic": [sum(item["passed"] for item in atomic["cases"]), len(atomic["cases"])]},
        "phase6ib_reclassified": False, "phase6ib_artifact_or_runtime_reused": False,
    }
    (root / "preflight_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
