"""Short-lived process trees used only by Phase 6FU safety fixtures."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def identity() -> dict:
    process = psutil.Process()
    return {
        "pid": process.pid,
        "create_time_utc_epoch": process.create_time(),
        "path": process.exe(),
        "parent_pid": process.ppid(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("wait", "parent-exits", "suppression-child", "suppression-parent"), required=True)
    parser.add_argument("--ready", type=Path, required=True)
    parser.add_argument("--child-ready", type=Path)
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--seconds", type=float, default=120.0)
    args = parser.parse_args()
    if args.mode == "wait":
        write(args.ready, identity())
        time.sleep(args.seconds)
        return 0
    if args.mode == "suppression-child":
        write(args.ready, identity())
        time.sleep(0.75)
        if args.lock and args.lock.exists():
            args.lock.unlink()
        time.sleep(args.seconds)
        return 0

    if args.mode == "suppression-parent":
        if args.lock is None or args.child_ready is None:
            raise SystemExit("--lock and --child-ready are required")
        args.lock.parent.mkdir(parents=True, exist_ok=True)
        args.lock.write_text(json.dumps({"owner_pid": os.getpid()}) + "\n", encoding="utf-8")
        child = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--mode", "suppression-child", "--ready", str(args.child_ready), "--lock", str(args.lock), "--seconds", str(args.seconds)],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        payload = identity(); payload["child_pid"] = child.pid
        write(args.ready, payload)
        time.sleep(0.4)
        return 0

    if args.child_ready is None:
        raise SystemExit("--child-ready is required")
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--mode",
        "wait",
        "--ready",
        str(args.child_ready),
        "--seconds",
        str(args.seconds),
    ]
    child = subprocess.Popen(command, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    payload = identity()
    payload["child_pid"] = child.pid
    write(args.ready, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
