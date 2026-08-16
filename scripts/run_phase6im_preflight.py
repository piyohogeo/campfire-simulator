from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from phase6hu_atomic_report import atomic_write_json

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CONTRACT = SCRIPTS / "phase6im_process_identity_contract.json"
SIDECAR = SCRIPTS / "phase6im_process_identity_contract.sha256"
PYTHON = Path(r"C:\Python38\python.exe")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def run(output_root: Path) -> dict:
    if output_root.exists():
        raise RuntimeError("Phase 6IM preflight refuses root reuse")
    output_root.mkdir(parents=True)
    policy = json.loads(CONTRACT.read_text(encoding="utf-8"))
    digest = _sha(CONTRACT)
    checks = {
        "contract_sidecar_matches": SIDECAR.is_file() and SIDECAR.read_text(encoding="ascii").split()[0].upper() == digest,
        "phase6il_frozen": policy["frozen_history"]["phase6il_status"] == "safe_stop_post_shutdown_harness_failure" and not policy["frozen_history"]["phase6il_rerun"],
        "single_kit_launch": policy["operation"]["kit_launches"] == 1 and policy["operation"]["retry"] == 0 and policy["operation"]["replacement"] == 0,
        "no_post_shutdown_monitor": policy["operation"]["post_shutdown_schedule_samples"] == 0 and policy["operation"]["cdb_attach_calls"] == 0,
        "pointer_sized_contract": policy["windows_api"]["handle_pointer_sized"] is True and policy["windows_api"]["architecture"] == "x64",
    }
    for name, spec in policy["modules"].items():
        path = SCRIPTS / spec["path"]
        checks["module_hash:" + name] = path.is_file() and _sha(path) == spec["sha256"]
    fixture_root = output_root / "producer-consumer-fixture"
    command = [str(PYTHON), str(SCRIPTS / "phase6im_process_identity_fixture.py"), "--output-root", str(fixture_root)]
    with (output_root / "fixture.stdout.log").open("wb", buffering=0) as stdout, (output_root / "fixture.stderr.log").open("wb", buffering=0) as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        fixture_exit = process.wait(timeout=120)
    fixture = json.loads((fixture_root / "fixture_summary.json").read_text(encoding="utf-8")) if (fixture_root / "fixture_summary.json").is_file() else {}
    checks["producer_to_consumer_fixture_qualified"] = fixture_exit == 0 and fixture.get("status") == "qualified" and fixture.get("passed_count") == fixture.get("case_count")
    checks["fixture_uses_real_windows_handle"] = fixture.get("real_windows_handle_used") is True
    checks["fixture_kit_launch_zero"] = fixture.get("kit_launch_count") == 0
    signature = fixture.get("signature_evidence") or {}
    checks["runtime_pointer_and_handle_are_64_bit"] = signature.get("pointer_size_bytes") == 8 and signature.get("handle_size_bytes") == 8
    result = {
        "schema": "campfire.phase6im.preflight.v1",
        "phase": "phase6im",
        "status": "qualified" if all(checks.values()) else "failed",
        "contract_sha256": digest,
        "checks": checks,
        "fixture_case_count": fixture.get("case_count"),
        "fixture_passed_count": fixture.get("passed_count"),
        "signature_evidence": signature,
        "fixture_command": command,
        "fixture_exit_code": fixture_exit,
        "kit_launch_count": 0,
    }
    atomic_write_json(output_root / "preflight_summary.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output_root.resolve())
    return 0 if result["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())

