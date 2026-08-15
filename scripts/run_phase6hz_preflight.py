"""Run the Phase 6HZ marker fixture and frozen Phase 6HY import regression without Kit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from phase6hy_exact_import_fixture import run_fixture as run_phase6hy_import_fixture
from phase6hz_marker_fixture import run_fixture as run_marker_fixture


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_root.absolute()
    if root.exists():
        raise RuntimeError("Phase 6HZ preflight refuses root reuse")
    root.mkdir(parents=True)
    contract = SCRIPTS / "phase6hz_import_smoke_contract.json"
    digest = hashlib.sha256(contract.read_bytes()).hexdigest().upper()
    sidecar = (SCRIPTS / "phase6hz_import_smoke_contract.sha256").read_text(encoding="ascii").split()[0].upper()
    marker = run_marker_fixture(root / "marker")
    legacy = run_phase6hy_import_fixture(root / "phase6hy_exact_import_regression")
    checks = {
        "contract_digest": digest == sidecar,
        "marker_fixture": marker["status"] == "qualified",
        "phase6hy_exact_import_regression": legacy["status"] == "qualified",
        "kit_not_launched": marker["kit_launch_count"] == 0 and legacy["kit_launch_count"] == 0,
    }
    report = {
        "schema": "campfire.phase6hz.no-kit-preflight.v1",
        "phase": "phase6hz",
        "status": "qualified" if all(checks.values()) else "failed",
        "kit_launch_count": 0,
        "contract_sha256": digest,
        "checks": checks,
        "fixture_counts": {"phase6hz_marker": marker["case_count"], "phase6hy_exact_import_regression": legacy["case_count"]},
        "phase6hy_reclassified": False,
        "phase6hy_artifact_or_runtime_reused": False,
    }
    (root / "preflight_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())

