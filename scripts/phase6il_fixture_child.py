from __future__ import annotations

import argparse
import ctypes
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("exit0", "delay0", "hang", "exit1", "native-av-code", "reporter-exits", "reporter-residual", "growing-dump"))
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--delay", type=float, default=0.15)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    if args.mode == "exit0":
        return 0
    if args.mode == "delay0":
        time.sleep(args.delay)
        return 0
    if args.mode == "hang":
        time.sleep(30)
        return 0
    if args.mode == "exit1":
        return 1
    if args.mode == "native-av-code":
        ctypes.windll.kernel32.ExitProcess(0xC0000005)
        raise AssertionError("unreachable")
    if args.mode in {"reporter-exits", "reporter-residual"}:
        duration = 0.1 if args.mode == "reporter-exits" else 30.0
        child = subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({duration})"])
        (args.artifact_root / "reporter.pid").write_text(str(child.pid), encoding="ascii")
        return 1
    if args.mode == "growing-dump":
        target = args.artifact_root / "fixture.dmp.partial"
        with target.open("wb", buffering=0) as stream:
            stream.write(b"MDMP" + b"0" * 1024)
            stream.flush()
            __import__("os").fsync(stream.fileno())
            time.sleep(args.delay)
            stream.write(b"1" * 1024)
            stream.flush()
            __import__("os").fsync(stream.fileno())
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
