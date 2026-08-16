from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from phase6hu_atomic_report import atomic_write_json
from phase6il_post_shutdown_boundary import read_bounded_json

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / "scripts"
CONTRACT = S / "phase6il_post_shutdown_contract.json"
SIDECAR = S / "phase6il_post_shutdown_contract.sha256"
PYTHON = Path(r"C:\Python38\python.exe")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dump-audit", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_root.resolve()
    if root.exists():
        raise RuntimeError("Phase 6IL preflight refuses root reuse")
    root.mkdir(parents=True)
    policy = read_bounded_json(CONTRACT)
    contract_sha = sha(CONTRACT)
    checks: dict[str, bool] = {
        "contract_sidecar_matches": SIDECAR.is_file() and SIDECAR.read_text(encoding="ascii").split()[0].upper() == contract_sha,
        "phase6ik_frozen": policy["frozen_history"]["phase6ik_status"] == "safe_stop_parent_lifecycle_boundary_localized" and not policy["frozen_history"]["phase6ik_rerun"],
        "runtime_operation_minimal": all(policy["operation_contract"][key] == 0 for key in ("stage_calls", "timeline_play_calls", "flow_calls", "readback_calls", "renderer_update_calls", "capture_calls")),
        "single_launch_no_retry": policy["operation_contract"]["kit_launches"] == 1 and policy["operation_contract"]["retry"] == 0 and policy["operation_contract"]["replacement"] == 0,
        "post_shutdown_boundary_180": policy["post_shutdown_boundary_seconds"] == 180,
        "schedule_exact": policy["post_shutdown_schedule_seconds"] == [0, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 175],
        "cdb_once_at_60": policy["cdb_contract"]["trigger_same_exact_kit_alive_seconds"] == 60 and policy["cdb_contract"]["maximum_invocations"] == 1,
    }
    for name, specification in policy["modules"].items():
        path = S / specification["path"]
        checks["module_hash:" + name] = path.is_file() and sha(path) == specification["sha256"]
    audit = read_bounded_json(args.dump_audit.resolve())
    checks["prior_dump_audit_bounded_and_immutable"] = audit.get("copies_match_original") is True and audit.get("source_phase_reclassified") is False and audit.get("exception_code") == "C0000005"
    fixture_root = root / "producer-consumer-fixture"
    command = [str(PYTHON), str(S / "phase6il_post_shutdown_fixture.py"), "--output-root", str(fixture_root)]
    with (root / "fixture.stdout.log").open("wb") as stdout, (root / "fixture.stderr.log").open("wb") as stderr:
        completed = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=120)
    fixture = read_bounded_json(fixture_root / "preflight_report.json") if (fixture_root / "preflight_report.json").is_file() else {}
    checks["producer_to_consumer_fixture_qualified"] = completed.returncode == 0 and fixture.get("status") == "qualified" and fixture.get("passed_count") == fixture.get("case_count")
    checks["fixture_kit_launch_zero"] = fixture.get("kit_launch_count") == 0
    report = {
        "schema": "campfire.phase6il.preflight.v1",
        "phase": "phase6il",
        "status": "qualified" if all(checks.values()) else "failed",
        "contract_sha256": contract_sha,
        "checks": checks,
        "fixture_command": command,
        "fixture_exit_code": completed.returncode,
        "fixture_case_count": fixture.get("case_count"),
        "fixture_passed_count": fixture.get("passed_count"),
        "actual_poll_fixture_count": fixture.get("actual_poll_case_count"),
        "kit_launch_count": 0,
    }
    atomic_write_json(root / "preflight_summary.json", report)
    return 0 if report["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
