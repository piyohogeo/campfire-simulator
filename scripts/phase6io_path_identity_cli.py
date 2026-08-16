from __future__ import annotations

import argparse
from pathlib import Path

from phase6io_executable_identity import (
    produce_path_identity_report, read_report, validate_path_identity_report,
    write_report,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--lexical-launch-path", required=True)
    parser.add_argument("--expected-lexical-launch-path", required=True)
    parser.add_argument("--operation-report", type=Path, required=True)
    parser.add_argument("--launch-pid", type=int, required=True)
    parser.add_argument("--launch-creation-ticks", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    operation = read_report(args.operation_report.resolve())
    identity = operation.get("process_identity")
    report = produce_path_identity_report(
        attempt_id=args.attempt_id,
        lexical_launch_path=args.lexical_launch_path,
        expected_lexical_launch_path=args.expected_lexical_launch_path,
        process_identity=identity,
        launch_pid=args.launch_pid,
        launch_creation_ticks=args.launch_creation_ticks,
    )
    validation = validate_path_identity_report(report, attempt_id=args.attempt_id)
    # The transport envelope is separate so the strict canonical report remains
    # unchanged between producer and validator.
    envelope = {"report": report, "validation": validation}
    write_report(args.output.resolve(), envelope)
    return 0 if validation["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
