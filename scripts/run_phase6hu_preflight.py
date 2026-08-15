"""Run Phase 6HU no-Kit atomic and inherited canonical-report fixtures."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from phase6hu_atomic_fixture import run_fixture


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.output_root.exists():
        raise RuntimeError("Phase 6HU preflight refuses root reuse")
    args.output_root.mkdir(parents=True)
    fixture = run_fixture(
        args.output_root / "atomic",
        SCRIPTS / "phase6hu_atomic_flow_baseline_contract.json",
        SCRIPTS / "phase6hs_operation_report_schema.json",
    )
    inherited_root = args.output_root / "inherited_phase6hs"
    inherited = subprocess.run(
        [
            sys.executable, str(SCRIPTS / "run_phase6hs_preflight.py"),
            "--contract", str(SCRIPTS / "phase6hs_canonical_proxy_contract.json"),
            "--schema", str(SCRIPTS / "phase6hs_operation_report_schema.json"),
            "--output-root", str(inherited_root),
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=120,
    )
    inherited_report_path = inherited_root / "preflight_report.json"
    inherited_report = json.loads(inherited_report_path.read_text(encoding="utf-8")) if inherited_report_path.is_file() else None
    checks = {
        "atomic_fixture_qualified": fixture["status"] == "qualified",
        "actual_producer_consumer_qualified": any(case["name"] == "actual_producer_to_consumer_unmodified" and case["passed"] for case in fixture["cases"]),
        "reader_contention_reproduced_and_bounded": any(case["name"] == "temporary_sharing_violation_retried" and case["passed"] for case in fixture["cases"]),
        "cleanup_continues_after_snapshot_failure": any(case["name"] == "snapshot_failure_does_not_block_cleanup_markers" and case["passed"] for case in fixture["cases"]),
        "inherited_phase6hs_fixture_qualified": inherited.returncode == 0 and inherited_report is not None and inherited_report.get("status") == "qualified",
        "kit_launch_count_zero": fixture["kit_launch_count"] == 0 and (inherited_report or {}).get("kit_launch_count") == 0,
        "bounded_json": all(path.stat().st_size <= 1024 * 1024 for path in args.output_root.rglob("*.json")),
    }
    report = {
        "schema": "campfire.phase6hu.no-kit-preflight.v1",
        "phase": "phase6hu",
        "status": "qualified" if all(checks.values()) else "failed",
        "kit_launch_count": 0,
        "checks": checks,
        "atomic_fixture": fixture,
        "inherited_phase6hs_fixture": {
            "exit_code": inherited.returncode,
            "status": (inherited_report or {}).get("status"),
            "report": str(inherited_report_path),
        },
        "phase6ht_reclassified": False,
        "phase6ht_artifacts_reused": False,
    }
    (args.output_root / "preflight_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
