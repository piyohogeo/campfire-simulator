from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from phase6hu_atomic_report import atomic_write_json

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CONTRACT = SCRIPTS / "phase6in_post_shutdown_contract.json"
SIDECAR = SCRIPTS / "phase6in_post_shutdown_contract.sha256"
PYTHON = Path(r"C:\Python38\python.exe")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def run(output_root: Path) -> dict:
    if output_root.exists():
        raise RuntimeError("Phase 6IN preflight refuses root reuse")
    output_root.mkdir(parents=True)
    policy = json.loads(CONTRACT.read_text(encoding="utf-8"))
    digest = sha(CONTRACT)
    checks = {
        "contract_sidecar_matches": SIDECAR.is_file() and SIDECAR.read_text(encoding="ascii").split()[0].upper() == digest,
        "phase6il_frozen": policy["frozen_history"]["phase6il_status"] == "safe_stop_post_shutdown_harness_failure" and not policy["frozen_history"]["phase6il_rerun"],
        "phase6im_helper_exact": sha(SCRIPTS / policy["dependencies"]["phase6im_helper"]["path"]) == policy["dependencies"]["phase6im_helper"]["sha256"],
        "single_fresh_kit": policy["operation"]["kit_launches"] == 1 and policy["operation"]["retry"] == 0 and policy["operation"]["replacement"] == 0,
        "no_cdb": policy["monitor"]["cdb_enabled"] is False and policy["operation"]["cdb_attach_calls"] == 0,
        "fixed_monitor_window": policy["monitor"]["schedule_seconds"] == [0.0, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0] and policy["monitor"]["absolute_timeout_seconds"] == 30.0,
        "stage_flow_capture_zero": all(policy["operation"][key] == 0 for key in ("stage_calls", "layer_calls", "timeline_play_calls", "flow_calls", "renderer_update_calls", "readback_calls", "camera_calls", "capture_calls")),
    }
    for name, spec in policy["modules"].items():
        path = SCRIPTS / spec["path"]
        checks["module_hash:" + name] = path.is_file() and sha(path) == spec["sha256"]
    fixture_root = output_root / "producer-consumer-fixture"
    command = [str(PYTHON), str(SCRIPTS / "phase6in_post_shutdown_fixture.py"), "--output-root", str(fixture_root)]
    with (output_root / "fixture.stdout.log").open("wb", buffering=0) as stdout, (output_root / "fixture.stderr.log").open("wb", buffering=0) as stderr:
        process = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=90)
    fixture = json.loads((fixture_root / "fixture_summary.json").read_text(encoding="utf-8")) if (fixture_root / "fixture_summary.json").is_file() else {}
    checks["producer_consumer_fixture_qualified"] = process.returncode == 0 and fixture.get("status") == "qualified" and fixture.get("case_count") == fixture.get("passed_count")
    checks["fixture_kit_launch_zero"] = fixture.get("kit_launch_count") == 0
    result = {"schema": "campfire.phase6in.preflight.v1", "phase": "phase6in", "status": "qualified" if all(checks.values()) else "failed", "contract_sha256": digest, "checks": checks, "fixture_case_count": fixture.get("case_count"), "fixture_passed_count": fixture.get("passed_count"), "fixture_command": command, "fixture_exit_code": process.returncode, "kit_launch_count": 0}
    atomic_write_json(output_root / "preflight_summary.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser();parser.add_argument("--output-root", type=Path, required=True)
    result = run(parser.parse_args().output_root.resolve())
    return 0 if result["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
