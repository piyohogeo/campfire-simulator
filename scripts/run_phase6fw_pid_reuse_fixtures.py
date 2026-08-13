"""Run bounded, separate-process Phase 6FW policy fixtures and offline comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import psutil

from phase6fw_pid_reuse_fixtures import fixture_cases


SCRIPT_DIR = Path(__file__).resolve().parent
CLASSIFIER = SCRIPT_DIR / "phase6fw_pid_reuse_policy.py"
CONTRACT = SCRIPT_DIR / "phase6fw_pid_reuse_policy_contract.json"
CONTRACT_SHA = SCRIPT_DIR / "phase6fw_pid_reuse_policy_contract.sha256"
REPOSITORY = SCRIPT_DIR.parent
PHASE6FV_GUARD = REPOSITORY / "artifacts/phase6fv-memory-ceiling-1/attempts/attempt03/runner-logs/guard.json"
PHASE6FV_MARKERS = REPOSITORY / "artifacts/phase6fv-memory-ceiling-1/attempts/attempt03/runner-logs/cleanup_markers.jsonl"
TIMEOUT_SECONDS = 10.0
LIMIT_BYTES = 512 * 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def monitor_child(process: subprocess.Popen[Any], timeout_seconds: float) -> dict[str, Any]:
    identity = psutil.Process(process.pid)
    create_time = identity.create_time()
    peak = 0
    timed_out = False
    limit_exceeded = False
    deadline = time.monotonic() + timeout_seconds
    while process.poll() is None:
        try:
            current = psutil.Process(process.pid)
            if abs(current.create_time() - create_time) > 1.0:
                raise RuntimeError("fixture PID identity changed while active")
            peak = max(peak, int(current.memory_info().private))
        except psutil.NoSuchProcess:
            break
        if peak > LIMIT_BYTES:
            limit_exceeded = True
            process.terminate()
            break
        if time.monotonic() >= deadline:
            timed_out = True
            process.terminate()
            break
        time.sleep(0.01)
    try:
        exit_code = process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.kill()
        exit_code = process.wait(timeout=2.0)
    residual = psutil.pid_exists(process.pid)
    return {
        "pid": process.pid,
        "create_time_utc_epoch": create_time,
        "exit_code": exit_code,
        "private_bytes_peak": peak,
        "timeout": timed_out,
        "private_limit_exceeded": limit_exceeded,
        "residual": residual,
    }


def run_case(root: Path, case: dict[str, Any]) -> dict[str, Any]:
    case_root = root / case["name"]
    case_root.mkdir()
    input_path = case_root / "input.json"
    output_path = case_root / "decision.json"
    stdout_path = case_root / "stdout.log"
    stderr_path = case_root / "stderr.log"
    input_path.write_text(json.dumps(case["payload"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(
            [sys.executable, str(CLASSIFIER), "--input", str(input_path), "--output", str(output_path)],
            stdout=stdout,
            stderr=stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        resource = monitor_child(process, TIMEOUT_SECONDS)
    decision = json.loads(output_path.read_text(encoding="utf-8")) if output_path.is_file() else None
    expected_exit = 0 if case["expected_qualified"] else 2
    classifications = [row["classification"] for row in (decision or {}).get("identities", [])]
    passed = bool(
        decision
        and decision["qualified"] is case["expected_qualified"]
        and case["expected_classification"] in classifications
        and resource["exit_code"] == expected_exit
        and not resource["timeout"]
        and not resource["private_limit_exceeded"]
        and not resource["residual"]
    )
    return {
        "name": case["name"],
        "expected_qualified": case["expected_qualified"],
        "expected_classification": case["expected_classification"],
        "passed": passed,
        "resource": resource,
        "decision_status": (decision or {}).get("status"),
        "classifications": classifications,
        "failures": (decision or {}).get("global_failures"),
        "input_sha256": sha256(input_path),
        "decision_sha256": sha256(output_path) if output_path.is_file() else None,
        "stdout_bytes": stdout_path.stat().st_size,
        "stderr_bytes": stderr_path.stat().st_size,
    }


def phase6fv_case() -> dict[str, Any]:
    guard = json.loads(PHASE6FV_GUARD.read_text(encoding="utf-8"))
    markers = jsonl(PHASE6FV_MARKERS)
    return {
        "name": "phase6fv_attempt03_offline_equivalent",
        "payload": {
            "schema": "campfire.phase6fw.phase6fv-offline-input.v1",
            "cleanup": guard["observed_process_cleanup"],
            "cleanup_markers": markers,
            "termination_requests": [row for row in markers if row.get("marker") == "exact_identity_stop_requested"],
            "post_summary_rediscovered": [],
            "source_artifact": {
                "guard_path": str(PHASE6FV_GUARD.relative_to(REPOSITORY)),
                "guard_sha256": sha256(PHASE6FV_GUARD),
                "cleanup_markers_path": str(PHASE6FV_MARKERS.relative_to(REPOSITORY)),
                "cleanup_markers_sha256": sha256(PHASE6FV_MARKERS),
                "read_only": True,
            },
        },
        "expected_qualified": True,
        "expected_classification": "protected_pid_reuse_non_residual",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True, type=Path)
    arguments = parser.parse_args()
    root = arguments.output_root.resolve()
    if root.exists():
        raise FileExistsError(f"fresh artifact root required: {root}")
    root.mkdir(parents=True)

    expected_contract_sha = CONTRACT_SHA.read_text(encoding="ascii").split()[0].upper()
    actual_contract_sha = sha256(CONTRACT)
    if actual_contract_sha != expected_contract_sha:
        raise RuntimeError("Phase 6FW contract SHA-256 mismatch")

    runner_process = psutil.Process()
    runner_peak = int(runner_process.memory_info().private)
    results: list[dict[str, Any]] = []
    for case in [*fixture_cases(), phase6fv_case()]:
        results.append(run_case(root, case))
        runner_peak = max(runner_peak, int(runner_process.memory_info().private))
        if not results[-1]["passed"]:
            break

    all_passed = len(results) == len(fixture_cases()) + 1 and all(row["passed"] for row in results)
    child_peak = max((row["resource"]["private_bytes_peak"] for row in results), default=0)
    residual = sum(bool(row["resource"]["residual"]) for row in results)
    phase6fv = next((row for row in results if row["name"] == "phase6fv_attempt03_offline_equivalent"), None)
    summary = {
        "schema": "campfire.phase6fw.pid-reuse-fixture-report.v1",
        "phase": "phase6fw",
        "status": "qualified" if all_passed else "safe_stop",
        "qualified": all_passed,
        "contract_sha256": actual_contract_sha,
        "fixture_count_required": 15,
        "fixture_count_completed": sum(not row["name"].startswith("phase6fv_") for row in results),
        "offline_phase6fv_completed": phase6fv is not None,
        "offline_phase6fv_qualified": bool(phase6fv and phase6fv["passed"]),
        "phase6fv_reclassified": False,
        "phase6fv_source_modified": False,
        "memory_population_started": False,
        "phase6fo_started": False,
        "resource": {
            "runner_private_bytes_peak": runner_peak,
            "diagnostic_child_private_bytes_peak": child_peak,
            "runner_limit_bytes": LIMIT_BYTES,
            "diagnostic_child_limit_bytes": LIMIT_BYTES,
        },
        "residual": {
            "fixture_processes": residual,
            "cdb": 0,
            "helpers": residual,
        },
        "results": results,
        "frozen_dependencies": {
            "phase6fu_contract_sha256": sha256(SCRIPT_DIR / "phase6fu_diagnostic_cleanup_contract.json"),
            "phase6fu_identity_sha256": sha256(SCRIPT_DIR / "phase6fu_process_identity.py"),
            "phase6fu_guard_adapter_sha256": sha256(SCRIPT_DIR / "phase6fu_resource_guard.py"),
            "legacy_guard_sha256": sha256(SCRIPT_DIR / "phase6eg_resource_guard.py"),
            "phase6fn_runtime_contract_sha256": sha256(SCRIPT_DIR / "phase6fn_routed_settled_contract.json"),
        },
    }
    (root / "fixture_report.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if all_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
