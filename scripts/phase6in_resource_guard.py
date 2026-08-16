"""Phase 6IN guard adapter with durable exact-cleanup boundary markers."""
from __future__ import annotations

import json
import os
from pathlib import Path
import time

import phase6eg_resource_guard as legacy
import phase6fu_resource_guard as phase6fu
from phase6hq_resource_guard import cleanup_observed_exact
from phase6im_process_identity import capture_process_identity
from phase6in_post_shutdown_boundary import append_marker

ATTEMPT_ID = "unspecified"
LIFECYCLE_PATH: Path | None = None
CLEANUP_MARKERS: Path | None = None
STARTED = time.monotonic()


def _identity() -> dict:
    if LIFECYCLE_PATH and LIFECYCLE_PATH.is_file():
        try:
            value = json.loads(LIFECYCLE_PATH.read_text(encoding="utf-8-sig"))
            identity = value.get("process_identity")
            if isinstance(identity, dict):
                return identity
        except (OSError, ValueError, TypeError):
            pass
    return capture_process_identity(os.getpid())


def _marker(step: str, details: dict) -> None:
    if CLEANUP_MARKERS is None:
        return
    identity = _identity()
    append_marker(
        CLEANUP_MARKERS, attempt_id=ATTEMPT_ID, step_id=step, actor="outer_guard",
        pid=int(identity["pid"]), creation_ticks=int(identity["creation_time_filetime_ticks"]),
        executable_path=str(identity["executable_path"]), elapsed=time.monotonic() - STARTED,
        details=details,
    )


def _cleanup(observed: dict, root_pid: int) -> dict:
    _marker("cleanup_started", {"root_pid": root_pid, "observed_identity_count": len(observed)})
    result = cleanup_observed_exact(observed, root_pid)
    residual = 0 if result.get("all_observed_absent") is True else len(result.get("residual_identities") or [])
    _marker("cleanup_complete", {"root_pid": root_pid, "all_observed_absent": result.get("all_observed_absent"), "residual_process_count": residual})
    _marker("final_residual_confirmed", {"root_pid": root_pid, "residual_process_count": residual})
    return result


def _write(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    global ATTEMPT_ID, LIFECYCLE_PATH, CLEANUP_MARKERS
    parser = legacy._parser()
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--cleanup-suppression-lock", type=Path)
    parser.add_argument("--cleanup-suppression-deadline-seconds", type=float, default=90.0)
    parser.add_argument("--cleanup-marker-path", type=Path)
    parser.add_argument("--phase6in-cleanup-markers", type=Path, required=True)
    arguments = parser.parse_args()
    ATTEMPT_ID = arguments.attempt_id
    LIFECYCLE_PATH = arguments.lifecycle_path
    CLEANUP_MARKERS = arguments.phase6in_cleanup_markers
    phase6fu.ATTEMPT_ID = arguments.attempt_id
    phase6fu.LOCK_PATH = arguments.cleanup_suppression_lock
    phase6fu.LOCK_DEADLINE = arguments.cleanup_suppression_deadline_seconds
    phase6fu.MARKER_PATH = arguments.cleanup_marker_path
    phase6fu.LAST_SUPPRESSION = None
    legacy._terminate_tree = phase6fu.terminate_exact_tree
    legacy._cleanup_observed_processes = _cleanup
    code = legacy.run(arguments)
    if arguments.summary.is_file():
        value = json.loads(arguments.summary.read_text(encoding="utf-8"))
        value["phase6in_guard_exit"] = code
        value["phase6in_outer_timeout_seconds"] = 180
        _write(arguments.summary, value)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
