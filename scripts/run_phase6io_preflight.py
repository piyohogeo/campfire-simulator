from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from phase6hu_atomic_report import atomic_write_json
from phase6ho_process_tree_topology import KIT
from phase6io_executable_identity import resolve_file_identity

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CONTRACT = SCRIPTS / "phase6io_post_shutdown_contract.json"
SIDECAR = SCRIPTS / "phase6io_post_shutdown_contract.sha256"
PYTHON = Path(r"C:\Python38\python.exe")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def run(output_root: Path) -> dict:
    if output_root.exists():
        raise RuntimeError("Phase 6IO preflight refuses root reuse")
    output_root.mkdir(parents=True)
    policy = json.loads(CONTRACT.read_text(encoding="utf-8")); digest = sha(CONTRACT)
    current = resolve_file_identity(KIT.absolute())
    expected = policy["path_identity"]
    checks = {
        "contract_sidecar_matches": SIDECAR.is_file() and SIDECAR.read_text(encoding="ascii").split()[0].upper() == digest,
        "phase6in_frozen": policy["frozen_history"]["phase6in_status"] == "safe_stop_post_shutdown_monitor_harness_failure" and not policy["frozen_history"]["phase6in_rerun"] and not policy["frozen_history"]["phase6in_artifact_reused"],
        "phase6im_helper_unchanged": sha(SCRIPTS / policy["dependencies"]["phase6im_helper"]["path"]) == policy["dependencies"]["phase6im_helper"]["sha256"],
        "fixed_schedule": policy["monitor"]["schedule_seconds"] == [0.0, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0] and policy["monitor"]["normal_exit_max_seconds"] == 15.0 and policy["monitor"]["absolute_timeout_seconds"] == 30.0,
        "single_fresh_kit": policy["operation"]["kit_launches"] == 1 and policy["operation"]["retry"] == 0 and policy["operation"]["replacement"] == 0,
        "forbidden_operations_zero": all(policy["operation"][key] == 0 for key in ("stage_calls", "layer_calls", "timeline_play_calls", "flow_calls", "renderer_update_calls", "readback_calls", "camera_calls", "capture_calls", "cdb_attach_calls", "dump_analysis_calls")),
        "live_lexical_boundary_exact": str(KIT.absolute()).lower() == expected["lexical_launch_path"].lower(),
        "live_canonical_path_exact": current["canonical_path"] == expected["expected_canonical_path"],
        "live_file_identity_exact": current["volume_serial"] == expected["expected_volume_serial"] and current["file_index"] == expected["expected_file_index"] and current["file_size_bytes"] == expected["expected_file_size_bytes"] and current["sha256"] == expected["expected_sha256"],
    }
    for name, spec in policy["modules"].items():
        checks["module_hash:" + name] = sha(SCRIPTS / spec["path"]) == spec["sha256"]
    fixture_root = output_root / "producer-consumer-fixture"
    command = [str(PYTHON), str(SCRIPTS / "phase6io_path_identity_fixture.py"), "--output-root", str(fixture_root)]
    with (output_root / "fixture.stdout.log").open("wb", buffering=0) as stdout, (output_root / "fixture.stderr.log").open("wb", buffering=0) as stderr:
        process = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=90)
    fixture = json.loads((fixture_root / "fixture_summary.json").read_text(encoding="utf-8")) if (fixture_root / "fixture_summary.json").is_file() else {}
    checks["producer_consumer_fixture_qualified"] = process.returncode == 0 and fixture.get("status") == "qualified" and fixture.get("case_count") == fixture.get("passed_count")
    checks["fixture_kit_launch_zero"] = fixture.get("kit_launch_count") == 0
    result = {"schema": "campfire.phase6io.preflight.v1", "phase": "phase6io", "status": "qualified" if all(checks.values()) else "failed", "contract_sha256": digest, "checks": checks, "fixture_case_count": fixture.get("case_count"), "fixture_passed_count": fixture.get("passed_count"), "fixture_command": command, "fixture_exit_code": process.returncode, "kit_launch_count": 0, "resolved_file_identity": current}
    atomic_write_json(output_root / "preflight_summary.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--output-root", type=Path, required=True)
    raise SystemExit(0 if run(parser.parse_args().output_root.resolve())["status"] == "qualified" else 1)
