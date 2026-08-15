from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from phase6ho_app_ready_environment import ROOT, write_json
from phase6ii_stage_open_composition_fixture import run_fixture

S = ROOT / "scripts"
CONTRACT = S / "phase6ii_stage_open_composition_contract.json"
SIDECAR = S / "phase6ii_stage_open_composition_contract.sha256"
MANIFEST = S / "phase6ii_authoring_dependencies.json"
MANIFEST_SIDECAR = S / "phase6ii_authoring_dependencies.sha256"


def run(root: Path) -> dict:
    if root.exists():
        raise RuntimeError("Phase 6II preflight refuses root reuse")
    root.mkdir(parents=True)
    digest = hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper()
    policy = json.loads(CONTRACT.read_text())
    manifest_digest = hashlib.sha256(MANIFEST.read_bytes()).hexdigest().upper()
    manifest = json.loads(MANIFEST.read_text())
    dependencies = []
    for row in manifest["modules"]:
        path = ROOT / row["repository_relative_path"]
        observed = hashlib.sha256(path.read_bytes()).hexdigest().upper() if path.is_file() else None
        dependencies.append({"module_id": row["module_id"], "passed": observed == row["sha256"], "expected_sha256": row["sha256"], "observed_sha256": observed})
    fixture = run_fixture(root / "composition-fixture")
    accepted = digest == SIDECAR.read_text().split()[0].upper() and manifest_digest == MANIFEST_SIDECAR.read_text().split()[0].upper() == policy["dependency_manifest"]["sha256"] and all(row["passed"] for row in dependencies) and fixture["status"] == "qualified"
    report = {"schema": "campfire.phase6ii.preflight.v1", "phase": "phase6ii", "status": "qualified" if accepted else "failed", "contract_sha256": digest, "manifest_sha256": manifest_digest, "dependency_audit": dependencies, "fixture": fixture, "condition_order": ["A", "B", "C"], "requested_D_mapping": "C", "kit_launch_count": 0, "phase6ih_reclassified": False, "phase6ih_artifact_dump_reused": False}
    write_json(root / "summary.json", report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    return 0 if run(args.artifact_root.absolute())["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
