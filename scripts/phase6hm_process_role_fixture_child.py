"""Short-lived child used by the no-Kit Phase 6HM process-tree fixture."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import psutil


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--hold-seconds", type=float, default=0.75)
    args = parser.parse_args()
    process = psutil.Process()
    payload = {
        "schema": "campfire.phase6hm.process-role-mock-child.v1",
        "pid": process.pid,
        "parent_pid": process.ppid(),
        "creation_time_utc_epoch": process.create_time(),
        "absolute_executable_path": process.exe(),
        "argv": sys.argv,
        "requested_exit_code": args.exit_code,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.report.with_suffix(".partial")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, args.report)
    print("phase6hm mock child stdout streamed", flush=True)
    print("phase6hm mock child stderr streamed", file=sys.stderr, flush=True)
    time.sleep(args.hold_seconds)
    return args.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
