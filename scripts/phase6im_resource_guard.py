"""Phase 6IM exact cleanup adapter for the existing guarded runner."""
from __future__ import annotations

import json
import os
from pathlib import Path

import phase6eg_resource_guard as legacy
import phase6fu_resource_guard as phase6fu
from phase6hq_resource_guard import cleanup_observed_exact


def _write(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = legacy._parser()
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--cleanup-suppression-lock", type=Path)
    parser.add_argument("--cleanup-suppression-deadline-seconds", type=float, default=90.0)
    parser.add_argument("--cleanup-marker-path", type=Path)
    arguments = parser.parse_args()
    phase6fu.ATTEMPT_ID = arguments.attempt_id
    phase6fu.LOCK_PATH = arguments.cleanup_suppression_lock
    phase6fu.LOCK_DEADLINE = arguments.cleanup_suppression_deadline_seconds
    phase6fu.MARKER_PATH = arguments.cleanup_marker_path
    phase6fu.LAST_SUPPRESSION = None
    legacy._terminate_tree = phase6fu.terminate_exact_tree
    legacy._cleanup_observed_processes = cleanup_observed_exact
    code = legacy.run(arguments)
    if arguments.summary.is_file():
        value = json.loads(arguments.summary.read_text(encoding="utf-8"))
        value["phase6im_guard_exit"] = code
        value["phase6im_outer_timeout_seconds"] = 180
        _write(arguments.summary, value)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

