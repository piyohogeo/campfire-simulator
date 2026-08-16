from __future__ import annotations

import argparse
import os
from pathlib import Path
import time

from phase6im_process_identity import produce_helper_report
from phase6in_post_shutdown_boundary import OPERATION_SCHEMA, append_marker, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("exit0", "delay0", "hang", "exit5"), required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--markers", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    helper = produce_helper_report(attempt_id=args.attempt_id, pid=os.getpid(), expected_path=Path(__import__("sys").executable))
    identity = helper["identities"][0]

    def mark(step: str) -> None:
        append_marker(args.markers, attempt_id=args.attempt_id, step_id=step, actor="fixture_child",
                      pid=identity["pid"], creation_ticks=identity["creation_time_filetime_ticks"],
                      executable_path=identity["executable_path"], elapsed=time.monotonic() - started)

    mark("kit_app_ready")
    report = {
        "schema": OPERATION_SCHEMA, "phase": "phase6in", "attempt_id": args.attempt_id,
        "phase6im_helper_contract_sha256": "FIXTURE",
        "phase6im_helper_evidence": helper,
        "process_identity": {key: identity[key] for key in ("pid", "creation_time_filetime_ticks", "creation_time_utc_epoch", "executable_path")},
        "operation_complete": True, "shutdown_requested": True, "shutdown_complete": True,
        "forbidden_calls": {"stage": 0, "layer": 0, "timeline_play": 0, "flow": 0, "renderer_update": 0, "readback": 0, "camera": 0, "capture": 0, "cdb_attach": 0, "dump_analysis": 0},
    }
    write_json(args.report, report)
    for step in ("operation_complete", "shutdown_requested", "shutdown_complete"):
        mark(step)
    if args.mode == "delay0":
        time.sleep(0.15)
    elif args.mode == "hang":
        time.sleep(30)
    return 5 if args.mode == "exit5" else 0


if __name__ == "__main__":
    raise SystemExit(main())
