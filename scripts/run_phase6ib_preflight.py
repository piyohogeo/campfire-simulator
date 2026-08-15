"""No-Kit preflight for the Phase 6IB registered-schema stage-open boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from phase6hu_atomic_fixture import run_fixture as run_atomic_fixture
from phase6hx_point_policy_fixture import run_fixture as run_point_fixture
from phase6hy_exact_import_fixture import run_fixture as run_exact_fixture
from phase6ib_no_kit_fixture import run_fixture as run_phase_fixture


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CONTRACT = SCRIPTS / "phase6ib_stage_open_contract.json"
SIDECAR = SCRIPTS / "phase6ib_stage_open_contract.sha256"
FROZEN = SCRIPTS / "phase6hx_single_log_occlusion_contract.json"
POINT = SCRIPTS / "phase6hx_point_policy_source_set.json"
POINT_SHA = SCRIPTS / "phase6hx_point_policy_source_set.sha256"
SCHEMA = SCRIPTS / "phase6hs_operation_report_schema.json"


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output-root", type=Path, required=True); args = parser.parse_args()
    root = args.output_root.absolute()
    if root.exists(): raise RuntimeError("Phase 6IB preflight refuses root reuse")
    root.mkdir(parents=True)
    policy = json.loads(CONTRACT.read_text(encoding="utf-8"))
    digest = sha(CONTRACT)
    phase = run_phase_fixture(root / "phase6ib", CONTRACT, SIDECAR, ROOT)
    exact = run_exact_fixture(root / "exact_import")
    point = run_point_fixture(root / "point_policy", POINT, POINT_SHA, ROOT)
    atomic = run_atomic_fixture(root / "atomic", FROZEN, SCHEMA)
    source_checks = {}
    for name, entry in policy["sources"].items():
        source_checks["source_sha256:" + name] = sha(ROOT / entry["path"]) == entry["sha256"]
    for name, entry in policy["known_good_basis"].items():
        if isinstance(entry, dict) and "path" in entry:
            source_checks["known_good_sha256:" + name] = sha(ROOT / entry["path"]) == entry["sha256"]
    checks = {
        "contract_digest": digest == SIDECAR.read_text(encoding="ascii").split()[0].upper(),
        "frozen_probe_digest": sha(FROZEN) == policy["frozen_probe_contract"]["sha256"],
        "phase6ia_frozen": policy["frozen_history"]["phase6ia"]["status"] == "safe_stop_runtime_stage_parse_harness_failure" and policy["frozen_history"]["reclassified"] is False,
        "phase6ib_fixture": phase["status"] == "qualified",
        "phase6hz_exact_loader_fixture": exact["status"] == "qualified",
        "point_policy_fixture": point["status"] == "qualified" and point["canonical_entry_count"] == 13,
        "atomic_report_fixture": atomic["status"] == "qualified",
        "kit_not_launched": all(item["kit_launch_count"] == 0 for item in (phase, exact, point, atomic)),
        "single_runtime_launch": policy["smoke"]["launches"] == 1 and policy["smoke"]["retry"] == 0 and policy["smoke"]["replacement"] == 0,
        "no_simulation_or_readback": policy["smoke"]["timeline_play_calls"] == policy["smoke"]["flow_interface_calls"] == policy["smoke"]["readback_calls"] == policy["smoke"]["capture_calls"] == 0,
        **source_checks,
    }
    report = {
        "schema":"campfire.phase6ib.preflight.v1","phase":"phase6ib","status":"qualified" if all(checks.values()) else "failed",
        "contract_sha256":digest,"kit_launch_count":0,"checks":checks,
        "fixture_counts":{"phase6ib":phase["case_count"],"exact_import":exact["case_count"],"point_policy":point["case_count"],"atomic":[sum(item["passed"] for item in atomic["cases"]),len(atomic["cases"])]},
        "phase6ia_reclassified":False,"phase6ia_artifact_or_attempt_reused":False,
    }
    (root / "preflight_report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    return 0 if report["status"] == "qualified" else 1


if __name__ == "__main__": raise SystemExit(main())
