from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from phase6hu_atomic_report import atomic_write_json
from phase6ik_parent_lifecycle_boundary import read_bounded_json

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / "scripts"
CONTRACT = S / "phase6ik_parent_lifecycle_contract.json"
SIDECAR = S / "phase6ik_parent_lifecycle_contract.sha256"
PYTHON = Path(r"C:\Python38\python.exe")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_root.absolute()
    if root.exists():
        raise RuntimeError("Phase 6IK preflight refuses root reuse")
    root.mkdir(parents=True)
    policy = read_bounded_json(CONTRACT)
    contract_sha = sha(CONTRACT)
    checks = {
        "contract_sidecar_matches": SIDECAR.is_file() and SIDECAR.read_text().split()[0].upper() == contract_sha,
        "boundary_module_hash_matches": sha(S / policy["boundary_module"]["path"]) == policy["boundary_module"]["sha256"],
        "atomic_module_hash_matches": sha(S / policy["atomic_module"]["path"]) == policy["atomic_module"]["sha256"],
        "probe_hash_matches": sha(S / policy["probe"]["path"]) == policy["probe"]["sha256"],
        "outer_timeout_frozen_180": policy["safety"]["outer_timeout_seconds"] == 180,
        "no_stage_or_flow_operation": all(policy["operation_contract"][key] == 0 for key in ("stage_calls","timeline_play_calls","flow_calls","readback_calls","renderer_update_calls","capture_calls")),
        "fresh_single_launch_no_retry": policy["operation_contract"]["kit_launches"] == 1 and policy["operation_contract"]["retry"] == 0 and policy["operation_contract"]["replacement"] == 0,
    }
    fixture_root = root / "producer-consumer-fixture"
    command = [str(PYTHON), str(S / "phase6ik_parent_lifecycle_fixture.py"), "--contract", str(CONTRACT), "--output-root", str(fixture_root)]
    with (root / "fixture.stdout.log").open("wb") as stdout, (root / "fixture.stderr.log").open("wb") as stderr:
        completed = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=60)
    fixture = read_bounded_json(fixture_root / "preflight_report.json") if (fixture_root / "preflight_report.json").is_file() else {}
    checks["producer_to_consumer_fixture_qualified"] = completed.returncode == 0 and fixture.get("status") == "qualified" and fixture.get("passed_count") == fixture.get("case_count")
    checks["kit_launch_count_zero"] = fixture.get("kit_launch_count") == 0
    report = {
        "schema":"campfire.phase6ik.preflight.v1", "phase":"phase6ik", "status":"qualified" if all(checks.values()) else "failed",
        "contract_sha256":contract_sha, "fixture_command":command, "fixture_exit_code":completed.returncode,
        "fixture_case_count":fixture.get("case_count"), "fixture_passed_count":fixture.get("passed_count"), "checks":checks,
    }
    atomic_write_json(root / "preflight_summary.json", report)
    return 0 if report["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())

