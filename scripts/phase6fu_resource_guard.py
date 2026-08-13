"""Phase 6FU fail-closed adapter for the frozen Phase 6EG resource guard.

The underlying guard remains byte-for-byte frozen for historical contracts.
This adapter replaces only its termination and observed-process cleanup hooks,
and adds bounded diagnostic-ownership coordination.
"""

from __future__ import annotations

import time
from pathlib import Path

import psutil

import phase6eg_resource_guard as legacy
from phase6fu_process_identity import exact_cleanup, make_identity, wait_for_cleanup_suppression


ATTEMPT_ID = "unspecified"
LOCK_PATH: Path | None = None
LOCK_DEADLINE = 90.0
MARKER_PATH: Path | None = None
LAST_SUPPRESSION: dict | None = None


def _suppression() -> dict:
    global LAST_SUPPRESSION
    if LAST_SUPPRESSION is None:
        LAST_SUPPRESSION = wait_for_cleanup_suppression(
            LOCK_PATH, deadline_seconds=LOCK_DEADLINE, marker_path=MARKER_PATH
        )
    return LAST_SUPPRESSION


def _identity(process: psutil.Process, role: str) -> dict:
    return make_identity(
        pid=process.pid,
        create_time_utc_epoch=process.create_time(),
        path=process.exe(),
        parent_pid=process.ppid(),
        role=role,
        attempt_id=ATTEMPT_ID,
    )


def terminate_exact_tree(root: psutil.Process) -> None:
    _suppression()
    processes = [root]
    try:
        processes.extend(root.children(recursive=True))
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        pass
    identities: list[dict] = []
    for process in processes:
        try:
            identities.append(_identity(process, "runner" if process.pid == root.pid else "child"))
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, OSError):
            # A query failure creates no termination authority.  The frozen
            # observed set is rechecked by cleanup_observed_exact below.
            continue
    exact_cleanup(identities, marker_path=MARKER_PATH, retry_count=4, retry_seconds=0.25)


def cleanup_observed_exact(observed: dict[tuple[int, float], dict], root_pid: int) -> dict:
    suppression = _suppression()
    identities = []
    now = time.time()
    for record in observed.values():
        parent_pid = None
        try:
            parent_pid = psutil.Process(int(record["pid"])).ppid()
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, OSError):
            pass
        identities.append(
            make_identity(
                pid=int(record["pid"]),
                create_time_utc_epoch=float(record["create_time_utc_epoch"]),
                path=str(record["path"]),
                parent_pid=parent_pid,
                role=str(record.get("role", "child")),
                attempt_id=ATTEMPT_ID,
                observed_at_utc_epoch=now,
            )
        )
    summary = exact_cleanup(identities, marker_path=MARKER_PATH, retry_count=4, retry_seconds=0.25)
    summary["root_pid"] = root_pid
    summary["cleanup_suppression"] = suppression
    return summary


def main() -> int:
    global ATTEMPT_ID, LOCK_PATH, LOCK_DEADLINE, MARKER_PATH
    parser = legacy._parser()
    parser.add_argument("--attempt-id", default="unspecified")
    parser.add_argument("--cleanup-suppression-lock", type=Path)
    parser.add_argument("--cleanup-suppression-deadline-seconds", type=float, default=90.0)
    parser.add_argument("--cleanup-marker-path", type=Path)
    arguments = parser.parse_args()
    ATTEMPT_ID = arguments.attempt_id
    LOCK_PATH = arguments.cleanup_suppression_lock
    LOCK_DEADLINE = arguments.cleanup_suppression_deadline_seconds
    MARKER_PATH = arguments.cleanup_marker_path
    legacy._terminate_tree = terminate_exact_tree
    legacy._cleanup_observed_processes = cleanup_observed_exact
    return legacy.run(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
