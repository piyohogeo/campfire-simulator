"""Small no-Kit child used by the exact Phase 6HL guard fixture."""

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
    parser.add_argument("--sentinel", required=True)
    args = parser.parse_args()
    process = psutil.Process()
    payload = {
        "schema": "campfire.phase6hl.guard-fixture-child.v1",
        "pid": process.pid,
        "creation_time_utc_epoch": process.create_time(),
        "absolute_executable_path": str(Path(process.exe()).resolve()),
        "parent_pid": process.ppid(),
        "sys_executable": str(Path(sys.executable).resolve()),
        "argv": list(sys.argv),
        "sentinel": args.sentinel,
        "working_directory": str(Path.cwd().resolve()),
        "environment": {
            key: os.environ.get(key)
            for key in ("PYTHONPATH", "PYTHONNOUSERSITE", "PYTHONUNBUFFERED")
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    time.sleep(0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
