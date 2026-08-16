from __future__ import annotations

import argparse
import time
from pathlib import Path

from phase6ik_parent_lifecycle_boundary import append_marker, write_runner_evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--markers", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    parser.add_argument("--hang-seconds", type=float, default=0.0)
    parser.add_argument("--exit-code", type=int, default=0)
    args = parser.parse_args()
    started = time.monotonic()
    operation = {"schema": "campfire.phase6ik.fixture-child.v1", "status": "qualified", "operation_complete": True, "shutdown_complete": False}
    write_runner_evidence(args.report, operation)
    append_marker(args.markers, args.attempt_id, "operation_complete", monotonic_elapsed_seconds=time.monotonic() - started)
    operation["shutdown_complete"] = True
    write_runner_evidence(args.report, operation)
    append_marker(args.markers, args.attempt_id, "shutdown_complete", monotonic_elapsed_seconds=time.monotonic() - started)
    if args.delay_seconds:
        time.sleep(args.delay_seconds)
    if args.hang_seconds:
        time.sleep(args.hang_seconds)
    return args.exit_code


if __name__ == "__main__":
    raise SystemExit(main())

