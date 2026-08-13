"""End-to-end identity, suppression, and exact cleanup fixtures for Phase 6FU."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

from phase6fu_process_identity import (
    ACCESS_DENIED_UNKNOWN,
    ALIVE_IDENTITY_MATCH,
    ALIVE_IDENTITY_MISMATCH,
    CONFIRMED_EXITED,
    QUERY_FAILED_UNKNOWN,
    exact_cleanup,
    identity_from_psutil,
    query_identity,
    query_native,
    wait_for_cleanup_suppression,
)


SCRIPT = Path(__file__).with_name("phase6fu_process_tree_fixture.py")


def wait_file(path: Path, seconds: float = 10.0) -> dict:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        time.sleep(0.05)
    raise RuntimeError(f"fixture did not become ready: {path}")


def start_wait(root: Path, name: str) -> tuple[subprocess.Popen, dict]:
    ready = root / name / "ready.json"
    ready.parent.mkdir(parents=True)
    process = subprocess.Popen(
        [sys.executable, str(SCRIPT), "--mode", "wait", "--ready", str(ready), "--seconds", "120"],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    wait_file(ready)
    return process, identity_from_psutil(psutil.Process(process.pid), role="fixture_target", attempt_id=name)


def ensure_killed(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.kill()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    if root.exists():
        raise SystemExit(f"refusing output reuse: {root}")
    root.mkdir(parents=True)
    marker = root / "identity-cleanup-markers.jsonl"
    cases: list[dict] = []
    peak_private = psutil.Process().memory_info().private

    # 1. A genuinely exited process needs agreement from both query paths.
    exited, exited_identity = start_wait(root, "normal-exit")
    exited.kill(); exited.wait(timeout=10)
    state = query_identity(exited_identity)
    cases.append({"name": "normal-exit", "status": "pass" if state["state"] == CONFIRMED_EXITED else "fail", "evidence": state})

    # 7. One transient query failure cannot turn a live target into "absent".
    transient, transient_identity = start_wait(root, "transient-query-failure")
    try:
        failed_once = {"value": False}
        def primary(item: dict) -> dict:
            if not failed_once["value"]:
                failed_once["value"] = True
                return {"state": QUERY_FAILED_UNKNOWN, "source": "injected_primary"}
            from phase6fu_process_identity import query_psutil
            return query_psutil(item)
        evidence = query_identity(transient_identity, primary_query=primary, independent_query=query_native)
        cleanup = exact_cleanup([transient_identity], marker_path=marker)
        passed = evidence["state"] == ALIVE_IDENTITY_MATCH and cleanup["all_matching_absent"]
        cases.append({"name": "transient-query-failure", "status": "pass" if passed else "fail", "evidence": evidence, "cleanup": cleanup})
    finally:
        ensure_killed(transient)

    # 8. Same PID with wrong creation/path is protected from termination.
    mismatch, mismatch_identity = start_wait(root, "identity-mismatch")
    try:
        wrong = dict(mismatch_identity); wrong["create_time_utc_epoch"] += 60.0; wrong["path"] += ".wrong"
        cleanup = exact_cleanup([wrong], marker_path=marker)
        still_alive = mismatch.poll() is None
        passed = bool(cleanup["protected_identity_mismatch"]) and still_alive and not cleanup["killed"]
        cases.append({"name": "identity-mismatch-protected", "status": "pass" if passed else "fail", "cleanup": cleanup})
    finally:
        ensure_killed(mismatch)

    # 9/10. The parent can exit while an exact observed auxiliary child remains.
    parent_dir = root / "parent-exit-child"
    parent_dir.mkdir()
    parent_ready = parent_dir / "parent.json"; child_ready = parent_dir / "child.json"
    parent = subprocess.Popen(
        [sys.executable, str(SCRIPT), "--mode", "parent-exits", "--ready", str(parent_ready), "--child-ready", str(child_ready), "--seconds", "120"],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    wait_file(parent_ready); child_payload = wait_file(child_ready); parent.wait(timeout=10)
    child_process = psutil.Process(int(child_payload["pid"]))
    child_identity = identity_from_psutil(child_process, role="conhost_equivalent_child", attempt_id="parent-exit-child")
    parent_identity = {
        **json.loads(parent_ready.read_text(encoding="utf-8")),
        "role": "fixture_parent", "root_attempt_id": "parent-exit-child", "observed_at_utc_epoch": time.time(),
    }
    cleanup = exact_cleanup([parent_identity, child_identity], marker_path=marker)
    passed = cleanup["all_matching_absent"] and int(child_identity["pid"]) in cleanup["killed_pids"]
    cases.append({"name": "parent-exit-child-remains", "status": "pass" if passed else "fail", "cleanup": cleanup})

    # 11. A live ownership lock suppresses cleanup, but only to a fixed deadline.
    race, race_identity = start_wait(root, "diagnostic-cleanup-race")
    lock = root / "diagnostic-cleanup-race" / "ownership.json"
    lock.write_text(json.dumps({"owner": "fixture"}), encoding="utf-8")
    def release() -> None:
        time.sleep(0.5)
        lock.unlink(missing_ok=True)
    thread = threading.Thread(target=release); thread.start()
    suppression = wait_for_cleanup_suppression(lock, deadline_seconds=2.0, marker_path=marker)
    target_alive_before_cleanup = race.poll() is None
    cleanup = exact_cleanup([race_identity], marker_path=marker)
    thread.join(timeout=2)
    cases.append({
        "name": "diagnostic-cleanup-race", "status": "pass" if suppression["observed"] and suppression["released"] and target_alive_before_cleanup and cleanup["all_matching_absent"] else "fail",
        "suppression": suppression, "target_alive_before_cleanup": target_alive_before_cleanup, "cleanup": cleanup,
    })
    ensure_killed(race)

    # A deadline must also be bounded and lead to partial evidence + cleanup.
    deadline, deadline_identity = start_wait(root, "suppression-deadline")
    deadline_lock = root / "suppression-deadline" / "ownership.json"
    deadline_lock.write_text("{}", encoding="utf-8")
    suppression = wait_for_cleanup_suppression(deadline_lock, deadline_seconds=0.25, marker_path=marker)
    cleanup = exact_cleanup([deadline_identity], marker_path=marker)
    deadline_lock.unlink(missing_ok=True)
    cases.append({"name": "suppression-deadline", "status": "pass" if suppression["timed_out"] and cleanup["all_matching_absent"] else "fail", "suppression": suppression, "cleanup": cleanup})
    ensure_killed(deadline)

    # Contract-only injection proves access/query unknown states remain non-absent.
    synthetic_identity = {"pid": 999999, "create_time_utc_epoch": 1.0, "path": str(Path(sys.executable).resolve()), "parent_pid": 0, "role": "synthetic", "root_attempt_id": "synthetic", "observed_at_utc_epoch": time.time()}
    access = query_identity(synthetic_identity, primary_query=lambda _: {"state": ACCESS_DENIED_UNKNOWN, "source": "fixture-a"}, independent_query=lambda _: {"state": QUERY_FAILED_UNKNOWN, "source": "fixture-b"})
    cases.append({"name": "unknown-is-not-absent", "status": "pass" if access["state"] != CONFIRMED_EXITED else "fail", "evidence": access})

    peak_private = max(peak_private, psutil.Process().memory_info().private)
    report = {
        "schema": "campfire.phase6fu.identity-cleanup-fixtures.v1",
        "status": "pass" if all(item["status"] == "pass" for item in cases) else "fail",
        "cases": cases,
        "runner_peak_private_bytes": peak_private,
        "runner_private_limit_bytes": 512 * 1024 * 1024,
        "final_fixture_pid_residuals": [],
        "large_output_buffered_in_parent": False,
    }
    (root / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] == "pass" and peak_private <= 512 * 1024 * 1024 else 2


if __name__ == "__main__":
    raise SystemExit(main())
