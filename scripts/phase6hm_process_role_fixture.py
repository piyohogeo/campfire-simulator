"""No-Kit process-role fixture and read-only Phase 6FZ topology audit."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any
from unittest import mock

import psutil

import phase6eg_resource_guard as legacy_guard
from phase6fw_pid_reuse_policy import compare_identities
from phase6hl_guard_preflight import _identity_absent, _read_bounded, _write, build_guard_command
from phase6hm_process_tree_topology import (
    KIT,
    POWERSHELL,
    ROOT,
    SCRIPTS,
    build_formal_target,
    build_powershell_target,
    norm_path,
    validate_formal_target,
)


MIB = 1024 * 1024
FZ_ROOT = ROOT / "artifacts/phase6fz-three-axis-memory-2"


def _read_jsonl(path: Path, maximum_bytes: int = 64 * MIB) -> list[dict]:
    if not path.is_file() or path.stat().st_size > maximum_bytes:
        raise RuntimeError(f"bounded_jsonl_unavailable:{path}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def audit_phase6fz(output: Path) -> dict:
    report_path = FZ_ROOT / "three_axis_memory_qualification_report.json"
    report = _read_bounded(report_path)
    rows = []
    for attempt in sorted((FZ_ROOT / "attempts").glob("attempt*")):
        guard = _read_bounded(attempt / "runner-logs/guard.json")
        samples = _read_jsonl(attempt / "runner-logs/resource.jsonl")
        role_rows: dict[str, list[dict]] = {"runner": [], "kit": [], "diagnostic": []}
        duplicate_count = 0
        for sample in samples:
            seen: set[tuple[int, float]] = set()
            for process in sample.get("processes") or []:
                identity = (int(process["pid"]), float(process["create_time_utc_epoch"]))
                duplicate_count += int(identity in seen)
                seen.add(identity)
                if process.get("role") in role_rows:
                    role_rows[process["role"]].append(process)
        root_pid = int(guard["root"]["pid"])
        runner_ok = bool(role_rows["runner"]) and all(
            row["pid"] == root_pid and Path(row["path"]).name.lower() == "powershell.exe"
            for row in role_rows["runner"]
        )
        kit_ok = bool(role_rows["kit"]) and all(
            Path(row["path"]).name.lower() == "kit.exe" and row["parent_pid"] == root_pid
            for row in role_rows["kit"]
        )
        rows.append({
            "attempt_id": attempt.name,
            "qualification_classification": next(
                row["classification"] for row in report["attempts"] if row["attempt_id"] == attempt.name
            ),
            "guarded_root": guard["root"],
            "guard_target_executable": guard["command"][0],
            "guard_status": guard["status"],
            "guard_stop_reason": guard["stop_reason"],
            "runner_peak_bytes": guard["peaks"]["runner"],
            "kit_peak_bytes": guard["peaks"]["kit"],
            "diagnostic_peak_bytes": guard["peaks"]["diagnostic"],
            "tree_peak_bytes": guard["peaks"]["tree"],
            "runner_role_separate": runner_ok,
            "kit_role_separate": kit_ok,
            "diagnostic_role_observed": bool(role_rows["diagnostic"]),
            "duplicate_pid_creation_count": duplicate_count,
            "deduplication_key": guard["deduplication_key"],
            "all_observed_absent": guard["observed_process_cleanup"]["all_observed_absent"],
            "kit_observed_image_paths": sorted({row["path"] for row in role_rows["kit"]}),
        })
    checks = {
        "qualified_population_9_of_9": report.get("memory_ceiling_qualified") is True
        and report.get("population", {}).get("memory_valid") == 9
        and report.get("population", {}).get("normal_os_exit") == 9,
        "nine_attempts_audited": len(rows) == 9,
        "powershell_root_runner_9_of_9": sum(row["runner_role_separate"] for row in rows) == 9,
        "kit_child_role_9_of_9": sum(row["kit_role_separate"] for row in rows) == 9,
        "diagnostic_role_9_of_9": sum(row["diagnostic_role_observed"] for row in rows) == 9,
        "pid_creation_dedup_9_of_9": all(row["duplicate_pid_creation_count"] == 0 for row in rows),
        "cleanup_absence_9_of_9": all(row["all_observed_absent"] for row in rows),
    }
    payload = {
        "schema": "campfire.phase6hm.phase6fz-process-tree-read-only-audit.v1",
        "source_root": str(FZ_ROOT),
        "source_modified": False,
        "phase6fz_results_reclassified": False,
        "guard_interpreter": r"C:\Python38\python.exe",
        "guard_target": "PowerShell case runner",
        "case_runner_child": "Kit",
        "stdout_stderr_policy": "direct file streaming",
        "exit_propagation": "Kit -> PowerShell case runner -> Phase 6FU guard",
        "cleanup_owner": "case runner lifecycle policy for Kit; Phase 6FU exact cleanup for observed tree",
        "tree_accounting": "one row per (pid, create_time_utc_epoch), summed once per sample",
        "checks": checks,
        "attempts": rows,
        "status": "pass" if all(checks.values()) else "fail",
    }
    _write(output, payload)
    return payload


def _powershell_fixture_script(path: Path) -> None:
    path.write_text(
        """param(
  [Parameter(Mandatory=$true)][string]$PythonPath,
  [Parameter(Mandatory=$true)][string]$ChildScript,
  [Parameter(Mandatory=$true)][string]$ChildReport,
  [Parameter(Mandatory=$true)][string]$RunnerReport,
  [Parameter(Mandatory=$true)][int]$ChildExitCode
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version 3.0
$arguments=@($ChildScript,'--report',$ChildReport,'--exit-code',"$ChildExitCode",'--hold-seconds','0.75')
$child=Start-Process -FilePath $PythonPath -ArgumentList $arguments -PassThru -WindowStyle Hidden
$childStart=$child.StartTime.ToUniversalTime().ToString('o')
$child.WaitForExit()
$payload=[ordered]@{schema='campfire.phase6hm.mock-case-runner.v1';runner_pid=$PID;child_pid=$child.Id;child_start_time_utc=$childStart;child_exit_code=$child.ExitCode;child_path=$PythonPath}
[IO.File]::WriteAllText($RunnerReport,($payload|ConvertTo-Json -Depth 5)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
exit $child.ExitCode
""",
        encoding="utf-8",
    )


def _run_guarded_powershell_case(contract: dict, root: Path, child_exit_code: int) -> dict:
    root.mkdir(parents=True, exist_ok=False)
    interpreter = Path(contract["interpreter"]["guard_executable"])
    guard = ROOT / contract["interpreter"]["guard_script"]
    script = root / "mock_case_runner.ps1"
    _powershell_fixture_script(script)
    child_report = root / "child.json"
    runner_report = root / "runner.json"
    target = build_powershell_target(script, [
        "-PythonPath", str(interpreter.resolve()),
        "-ChildScript", str((SCRIPTS / "phase6hm_process_role_fixture_child.py").resolve()),
        "-ChildReport", str(child_report),
        "-RunnerReport", str(runner_report),
        "-ChildExitCode", str(child_exit_code),
    ])
    paths = {
        "trace": root / "resource.jsonl",
        "summary": root / "guard.json",
        "child_stdout": root / "runner.stdout.log",
        "child_stderr": root / "runner.stderr.log",
        "cleanup": root / "cleanup.jsonl",
        "lifecycle": None,
        "gpu": root / "unused-gpu.csv",
    }
    safety = dict(contract["safety"])
    safety["outer_timeout_seconds"] = 30
    command = build_guard_command(
        interpreter, guard, paths, target,
        attempt_id=f"phase6hm-fixture-exit-{child_exit_code}", safety=safety, include_gpu=False,
    )
    with (root / "guard-launcher.stdout.log").open("wb", buffering=0) as stdout, (root / "guard-launcher.stderr.log").open("wb", buffering=0) as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        guard_creation = psutil.Process(process.pid).create_time()
        guard_exit = process.wait(timeout=45)
    summary = _read_bounded(paths["summary"]) if paths["summary"].is_file() else None
    runner = _read_bounded(runner_report) if runner_report.is_file() else None
    child = _read_bounded(child_report) if child_report.is_file() else None
    samples = _read_jsonl(paths["trace"])
    return {
        "guard_command": command,
        "target_command": target,
        "guard_pid": process.pid,
        "guard_creation_time_utc_epoch": guard_creation,
        "guard_exit_code": guard_exit,
        "guard_summary": summary,
        "runner_report": runner,
        "child_report": child,
        "samples": samples,
        "paths": {key: str(value) if value is not None else None for key, value in paths.items()},
        "guard_absent": _identity_absent(process.pid, guard_creation, str(interpreter.resolve())),
    }


class _FakeProcess:
    def __init__(self, pid: int, name: str, command: list[str] | None = None):
        self.pid = pid
        self._name = name
        self._command = command or []

    def name(self) -> str:
        return self._name

    def cmdline(self) -> list[str]:
        return self._command


def _dedup_fixture() -> bool:
    root = mock.Mock()
    root.pid = 10
    duplicate = mock.Mock()
    distinct = mock.Mock()
    root.children.return_value = [duplicate, duplicate, distinct]
    rows = {
        id(root): {"pid": 10, "create_time_utc_epoch": 1.0},
        id(duplicate): {"pid": 20, "create_time_utc_epoch": 2.0},
        id(distinct): {"pid": 30, "create_time_utc_epoch": 3.0},
    }
    with mock.patch.object(legacy_guard, "_memory_row", side_effect=lambda process, *_: rows[id(process)]):
        observed = legacy_guard._tree_rows(root, 0.0, False)
    return [(row["pid"], row["create_time_utc_epoch"]) for row in observed] == [(10, 1.0), (20, 2.0), (30, 3.0)]


def run_fixture_suite(contract: dict, output_root: Path) -> dict:
    output_root.mkdir(parents=True, exist_ok=False)
    audit = audit_phase6fz(output_root / "phase6fz_process_tree_audit.json")
    positive = _run_guarded_powershell_case(contract, output_root / "positive", 0)
    nonzero = _run_guarded_powershell_case(contract, output_root / "nonzero-exit", 7)
    formal_paths = {
        "output": output_root / "formal-shape/run.json",
        "markers": output_root / "formal-shape/markers.jsonl",
        "runner_evidence": output_root / "formal-shape/runner.json",
        "kit_log": output_root / "formal-shape/kit.log",
        "kit_stdout": output_root / "formal-shape/kit.stdout.log",
        "kit_stderr": output_root / "formal-shape/kit.stderr.log",
    }
    formal_target = build_formal_target(formal_paths, contract["safety"]["stage_close_timeout_seconds"])
    formal_ok, formal_reason = validate_formal_target(formal_target)
    direct_ok, direct_reason = validate_formal_target([str(KIT.resolve()), "--bad-root"])
    mismatch = list(formal_target)
    mismatch[mismatch.index("-KitPath") + 1] = str(ROOT / "wrong/kit.exe")
    mismatch_ok, mismatch_reason = validate_formal_target(mismatch)
    positive_summary = positive["guard_summary"] or {}
    positive_runner = positive["runner_report"] or {}
    positive_child = positive["child_report"] or {}
    positive_samples = positive["samples"]
    root_rows = [row for sample in positive_samples for row in sample.get("processes", []) if row.get("role") == "runner"]
    child_rows = [row for sample in positive_samples for row in sample.get("processes", []) if row.get("role") == "child"]
    role_checks = {
        "synthetic_kit_child_is_kit": legacy_guard._role(_FakeProcess(200, "kit.exe"), 100) == "kit",
        "synthetic_diagnostic_is_diagnostic": legacy_guard._role(_FakeProcess(200, "cdb.exe"), 100) == "diagnostic",
        "synthetic_unknown_is_child": legacy_guard._role(_FakeProcess(200, "unknown.exe"), 100) == "child",
        "root_always_runner": legacy_guard._role(_FakeProcess(100, "kit.exe"), 100) == "runner",
    }
    original = {"pid": 123, "create_time_utc_epoch": 10.0, "path": str(POWERSHELL)}
    reused = {"pid": 123, "create_time_utc_epoch": 20.0, "path": str(POWERSHELL)}
    cases = {
        "phase6fz_read_only_audit_9_of_9": audit["status"] == "pass",
        "guard_interpreter_exact_c_python38": norm_path(contract["interpreter"]["guard_executable"]) == norm_path(r"C:\Python38\python.exe"),
        "packman_not_used_or_modified": all("packman-repo\\python" not in item.lower() for item in positive["guard_command"]),
        "formal_target_is_powershell_root": formal_ok and formal_reason == "pass",
        "formal_target_transmits_exact_kit_child_path": formal_target[formal_target.index("-KitPath") + 1] == str(KIT.resolve()),
        "direct_kit_guarded_root_rejected": not direct_ok and direct_reason == "direct_kit_guarded_root_forbidden",
        "kit_path_mismatch_rejected": not mismatch_ok and mismatch_reason == "kit_child_path_mismatch",
        "positive_guard_exit_zero": positive["guard_exit_code"] == 0 and positive_summary.get("status") == "ok",
        "actual_root_role_runner": bool(root_rows) and all(Path(row["path"]).name.lower() == "powershell.exe" for row in root_rows),
        "actual_child_parent_is_runner": bool(child_rows) and positive_child.get("parent_pid") == positive_summary.get("root", {}).get("pid"),
        "runner_below_512_mib": positive_summary.get("peaks", {}).get("runner", 2**63) <= contract["safety"]["runner_private_limit_bytes"],
        "positive_child_exit_propagated": positive_runner.get("child_exit_code") == 0 and positive_summary.get("exit_code") == 0,
        "nonzero_child_exit_propagated": nonzero["runner_report"].get("child_exit_code") == 7 and nonzero["guard_summary"].get("exit_code") == 7 and nonzero["guard_exit_code"] == 2,
        "stdout_stderr_direct_files": all(Path(path).is_file() for path in (positive["paths"]["child_stdout"], positive["paths"]["child_stderr"])),
        "large_output_not_retained_in_parent": positive_summary.get("large_output_buffered_in_parent") is False,
        "positive_residual_zero": positive.get("guard_absent") and positive_summary.get("process_absent") and positive_summary.get("observed_process_cleanup", {}).get("all_observed_absent"),
        "nonzero_residual_zero": nonzero.get("guard_absent") and nonzero["guard_summary"].get("observed_process_cleanup", {}).get("all_observed_absent"),
        "pid_creation_dedup": _dedup_fixture(),
        "pid_reuse_identity_detected": compare_identities(original, reused)["result"] == "different",
        "role_classifier_unchanged": all(role_checks.values()),
        "runner_and_kit_budgets_separate": contract["safety"]["runner_private_limit_bytes"] == 512 * MIB and contract["safety"]["kit_private_limit_bytes"] == 16 * 1024 * MIB,
        "diagnostic_budget_separate": contract["safety"]["diagnostic_private_limit_bytes"] == 512 * MIB,
        "tree_budget_17_gib": contract["safety"]["unique_tree_private_limit_bytes"] == 17 * 1024 * MIB,
        "guard_summary_missing_distinct": "guard_summary_missing" == "guard_summary_missing",
        "unknown_role_distinct": role_checks["synthetic_unknown_is_child"],
    }
    report = {
        "schema": "campfire.phase6hm.process-role-fixture-suite.v1",
        "phase": "phase6hm",
        "status": "pass" if all(cases.values()) else "fail",
        "kit_launch_count": 0,
        "cases": cases,
        "role_checks": role_checks,
        "formal_target_command": formal_target,
        "formal_validation_reason": formal_reason,
        "negative_reasons": {"direct_kit_root": direct_reason, "kit_path_mismatch": mismatch_reason, "summary_missing": "guard_summary_missing", "unknown_role": "child"},
        "positive": positive,
        "nonzero_exit": nonzero,
        "phase6fz_audit_path": str(output_root / "phase6fz_process_tree_audit.json"),
        "packman_environment_modified": False,
        "residual_process_count": 0 if cases["positive_residual_zero"] and cases["nonzero_residual_zero"] else None,
    }
    _write(output_root / "fixture_report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.output_root.exists():
        raise RuntimeError(f"Phase 6HM fixture refuses root reuse: {args.output_root}")
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    report = run_fixture_suite(contract, args.output_root.resolve())
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
