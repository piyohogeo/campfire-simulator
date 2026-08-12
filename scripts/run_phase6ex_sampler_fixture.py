"""Run the Phase 6EX resource sampler without Kit and validate its records."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

try:
    from .analyze_phase6ew_r0_lifecycle import _time
except ImportError:
    from analyze_phase6ew_r0_lifecycle import _time


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration-seconds", type=float, default=8.0)
    parser.add_argument("--sample-seconds", type=float, default=0.20)
    parser.add_argument("--target-samples", type=int, default=30)
    parser.add_argument("--minimum-samples", type=int, default=20)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"Phase 6EX sampler fixture refuses output reuse: {output}")
    output.mkdir(parents=True)
    scripts = Path(__file__).resolve().parent
    trace = output / "resource.jsonl"
    summary = output / "guard.json"
    command = [
        sys.executable, str(scripts / "phase6eg_resource_guard.py"),
        "--trace", str(trace), "--summary", str(summary),
        "--stdout", str(output / "target.stdout.log"),
        "--stderr", str(output / "target.stderr.log"),
        "--timeout-seconds", str(args.duration_seconds + 10.0),
        "--sample-seconds", str(args.sample_seconds),
        "--runner-private-limit", str(256 * 1024**2),
        "--diagnostic-private-limit", str(128 * 1024**2),
        "--kit-private-limit", str(14 * 1024**3),
        "--tree-private-limit", str(512 * 1024**2),
        "--available-memory-floor", str(512 * 1024**2),
        "--commit-headroom-floor", str(512 * 1024**2),
        "--", sys.executable, str(scripts / "phase6ex_sampler_target.py"),
        "--duration-seconds", str(args.duration_seconds),
    ]
    with (output / "guard.stdout.log").open("wb") as stdout, (output / "guard.stderr.log").open("wb") as stderr:
        completed = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=args.duration_seconds + 20.0, check=False)

    rows = []
    with trace.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    guard = json.loads(summary.read_text(encoding="utf-8"))
    timestamps = [float(row["timestamp_utc_epoch"]) for row in rows]
    runner_rows = [
        process for row in rows for process in row.get("processes", []) if process.get("role") == "runner"
    ]
    identities = {
        (row["pid"], row["create_time_utc_epoch"], str(Path(row["path"]).resolve()).casefold())
        for row in runner_rows
    }
    finite_memory = bool(runner_rows) and all(
        isinstance(row.get(name), int) and row[name] >= 0
        for row in runner_rows for name in ("private_bytes", "working_set_bytes")
    )
    seven_digit_parser = _time("2026-08-12T09:26:26.7250933Z") == _time("2026-08-12T09:26:26.725093Z")
    checks = {
        "guard_exit_zero": completed.returncode == 0,
        "guard_status_ok": guard.get("status") == "ok",
        "process_absent": guard.get("process_absent") is True,
        "minimum_sample_count_met": len(rows) >= args.minimum_samples,
        "target_sample_count_met": len(rows) >= args.target_samples,
        "timestamps_strictly_increasing": all(a < b for a, b in zip(timestamps, timestamps[1:])),
        "runner_identity_stable": len(identities) == 1,
        "finite_memory_values": finite_memory,
        "powershell_seven_digit_parser_supported": seven_digit_parser,
    }
    report = {
        "schema": "campfire.phase6ex.sampler-fixture.v1",
        "status": "pass" if all(checks.values()) else "fail",
        "duration_seconds": args.duration_seconds,
        "sampling_interval_seconds": args.sample_seconds,
        "sample_count": len(rows),
        "target_sample_count": args.target_samples,
        "minimum_sample_count": args.minimum_samples,
        "runner_identity_count": len(identities),
        "maximum_runner_private_bytes": max((row["private_bytes"] for row in runner_rows), default=None),
        "maximum_runner_working_set_bytes": max((row["working_set_bytes"] for row in runner_rows), default=None),
        "checks": checks,
    }
    _write(output / "sampler_fixture_report.json", report)
    if report["status"] != "pass":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
