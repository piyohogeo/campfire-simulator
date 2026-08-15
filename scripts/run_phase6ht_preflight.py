"""Persist the no-Kit Phase 6HT contract/source/visual fixture result."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError("Phase 6HT preflight refuses output reuse")
    process = subprocess.run(
        [sys.executable, "-m", "unittest", "scripts.test_phase6ht_static_flow_occlusion", "-v"],
        cwd=Path(__file__).absolute().parent.parent,
        capture_output=True,
        text=True,
    )
    report = {
        "schema": "campfire.phase6ht.no-kit-preflight.v1",
        "phase": "phase6ht",
        "status": "qualified" if process.returncode == 0 else "safe_stop",
        "kit_launch_count": 0,
        "test_count": 8,
        "passed": 8 if process.returncode == 0 else None,
        "exit_code": process.returncode,
        "stdout_tail": process.stdout[-4096:],
        "stderr_tail": process.stderr[-4096:],
    }
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
