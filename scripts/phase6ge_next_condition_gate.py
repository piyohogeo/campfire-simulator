"""Fail-closed Phase 6GE next-condition gate and bounded fixtures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def evaluate(runner: dict, guard: dict) -> dict:
    outcome = runner.get("outcome") or {}
    shutdown = runner.get("shutdown_monitor") or {}
    cleanup = guard.get("observed_process_cleanup") or {}
    checks = {
        "functional_pass": outcome.get("functional_status") == "pass",
        "lifecycle_normal_exit": outcome.get("lifecycle_status") == "normal_exit",
        "normal_exit_sample_accepted": outcome.get("normal_exit_sample_accepted") is True,
        "os_process_normal_exit": outcome.get("os_process_normal_exit") is True,
        "process_exit_code_zero": runner.get("process_exit_code") == 0,
        "guard_status_ok": guard.get("status") == "ok" and guard.get("exit_code") == 0,
        "exact_cleanup": cleanup.get("all_observed_absent") is True,
        "residual_zero": shutdown.get("residual_process") is False,
    }
    return {
        "schema": "campfire.phase6ge.next-condition-gate.v1",
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "next_condition_allowed": all(checks.values()),
    }


def fixtures() -> dict:
    normal_runner = {
        "process_exit_code": 0,
        "outcome": {
            "functional_status": "pass",
            "lifecycle_status": "normal_exit",
            "normal_exit_sample_accepted": True,
            "os_process_normal_exit": True,
        },
        "shutdown_monitor": {"residual_process": False},
    }
    normal_guard = {
        "status": "ok",
        "exit_code": 0,
        "observed_process_cleanup": {"all_observed_absent": True},
    }
    cases = []

    def case(name: str, runner: dict, guard: dict, expected: str) -> None:
        result = evaluate(runner, guard)
        cases.append({"name": name, "expected": expected, "observed": result["status"], "pass": result["status"] == expected})

    case("normal_all_axes", normal_runner, normal_guard, "pass")
    for name, path, value in (
        ("functional_failure", ("outcome", "functional_status"), "fail"),
        ("unknown_lifecycle", ("outcome", "lifecycle_status"), "unknown_shutdown_failure"),
        ("normal_sample_rejected", ("outcome", "normal_exit_sample_accepted"), False),
        ("os_exit_missing", ("outcome", "os_process_normal_exit"), False),
        ("process_exit_missing", ("process_exit_code",), None),
        ("residual_present", ("shutdown_monitor", "residual_process"), True),
    ):
        runner = json.loads(json.dumps(normal_runner))
        target = runner
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        case(name, runner, normal_guard, "fail")
    bad_cleanup = json.loads(json.dumps(normal_guard))
    bad_cleanup["observed_process_cleanup"]["all_observed_absent"] = False
    case("cleanup_incomplete", normal_runner, bad_cleanup, "fail")
    report = {
        "schema": "campfire.phase6ge.next-condition-gate-fixtures.v1",
        "cases": cases,
        "passed": sum(item["pass"] for item in cases),
        "total": len(cases),
    }
    report["status"] = "pass" if report["passed"] == report["total"] else "fail"
    return report


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner-evidence", type=Path)
    parser.add_argument("--guard", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixtures", action="store_true")
    arguments = parser.parse_args()
    if arguments.fixtures:
        result = fixtures()
    else:
        if arguments.runner_evidence is None or arguments.guard is None:
            parser.error("--runner-evidence and --guard are required outside fixture mode")
        result = evaluate(
            json.loads(arguments.runner_evidence.read_text(encoding="utf-8-sig")),
            json.loads(arguments.guard.read_text(encoding="utf-8-sig")),
        )
    write(arguments.output, result)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
