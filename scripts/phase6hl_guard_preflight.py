"""Deterministic no-Kit guard-interpreter preflight for Phase 6HL."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import time
from pathlib import Path

import psutil


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
MIB = 1024 * 1024


def _norm(path: str | Path) -> str:
    return os.path.normcase(str(Path(path).resolve()))


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _read_bounded(path: Path, maximum_bytes: int = MIB) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.stat().st_size > maximum_bytes:
        raise ValueError(f"bounded_json_oversize:{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _run_to_files(command: list[str], stdout_path: Path, stderr_path: Path, timeout: float) -> tuple[int | None, bool, int, float]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with stdout_path.open("wb", buffering=0) as stdout, stderr_path.open("wb", buffering=0) as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        creation_time = psutil.Process(process.pid).create_time()
        try:
            return_code = process.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
            return_code = process.returncode
            timed_out = True
    return return_code, timed_out, process.pid, creation_time


def observe_interpreter(interpreter: Path, guard: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "interpreter_observation.json"
    command = [
        str(interpreter.resolve()),
        str((SCRIPTS / "phase6hl_guard_interpreter_probe.py").resolve()),
        "--selected-interpreter", str(interpreter.resolve()),
        "--guard", str(guard.resolve()),
        "--output", str(report_path),
    ]
    return_code, timed_out, _, _ = _run_to_files(
        command, output_dir / "probe.stdout.log", output_dir / "probe.stderr.log", 15.0
    )
    report = _read_bounded(report_path) if report_path.is_file() else {
        "schema": "campfire.phase6hl.guard-interpreter-observation.v1",
        "selected_interpreter": str(interpreter.resolve()),
        "status": "fail",
        "errors": ["interpreter_probe_report_missing"],
    }
    report["probe_command"] = command
    report["probe_exit_code"] = return_code
    report["probe_timed_out"] = timed_out
    _write(report_path, report)
    return report


def validate_interpreter(observation: dict, expected_interpreter: Path, expected_guard: Path) -> tuple[bool, str]:
    if observation.get("schema") != "campfire.phase6hl.guard-interpreter-observation.v1":
        return False, "interpreter_observation_schema_mismatch"
    if _norm(observation.get("selected_interpreter", "missing")) != _norm(expected_interpreter):
        return False, "guard_interpreter_mismatch"
    if _norm(observation.get("sys_executable", "missing")) != _norm(expected_interpreter):
        return False, "guard_sys_executable_mismatch"
    if not observation.get("psutil_imported"):
        return False, "psutil_import_failed"
    psutil_file = observation.get("psutil_file")
    if not isinstance(psutil_file, str) or not Path(psutil_file).is_file():
        return False, "psutil_file_missing"
    if not observation.get("guard_imported"):
        return False, "guard_import_failed"
    if _norm(observation.get("guard_resolved_file", "missing")) != _norm(expected_guard):
        return False, "guard_resolved_path_mismatch"
    if not observation.get("guard_main_callable"):
        return False, "guard_entrypoint_not_callable"
    if observation.get("probe_timed_out") or observation.get("probe_exit_code") != 0:
        return False, "interpreter_probe_process_failed"
    return True, "pass"


def build_guard_command(
    interpreter: Path,
    guard: Path,
    paths: dict[str, Path],
    target_command: list[str],
    *,
    attempt_id: str,
    safety: dict,
    include_gpu: bool,
) -> list[str]:
    command = [
        str(interpreter.resolve()), str(guard.resolve()),
        "--trace", str(paths["trace"]), "--summary", str(paths["summary"]),
        "--stdout", str(paths["child_stdout"]), "--stderr", str(paths["child_stderr"]),
        "--timeout-seconds", str(safety["outer_timeout_seconds"]),
        "--sample-seconds", str(safety.get("sample_seconds", 0.25)),
        "--runner-private-limit", str(safety["runner_private_limit_bytes"]),
        "--kit-private-limit", str(safety["kit_private_limit_bytes"]),
        "--diagnostic-private-limit", str(safety["diagnostic_private_limit_bytes"]),
        "--tree-private-limit", str(safety["unique_tree_private_limit_bytes"]),
        "--available-memory-floor", str(safety["available_physical_floor_bytes"]),
        "--commit-headroom-floor", str(safety["commit_headroom_floor_bytes"]),
        "--cpu-telemetry", "--attempt-id", attempt_id,
        "--cleanup-marker-path", str(paths["cleanup"]),
    ]
    if paths.get("lifecycle") is not None:
        command += ["--lifecycle-path", str(paths["lifecycle"])]
    if include_gpu:
        command += ["--gpu-csv", str(paths["gpu"])]
    return command + ["--", *target_command]


def _identity_absent(pid: int, creation_time: float, executable: str) -> bool:
    try:
        process = psutil.Process(pid)
        return abs(process.create_time() - creation_time) > 0.01 or _norm(process.exe()) != _norm(executable)
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return True
    except (psutil.AccessDenied, OSError):
        return False


def validate_guard_summary(summary: dict | None, expected_command: list[str]) -> tuple[bool, str]:
    if summary is None:
        return False, "guard_summary_missing"
    if summary.get("schema") != "campfire.phase6eg.resource-guard.v1":
        return False, "guard_summary_schema_mismatch"
    if summary.get("command") != expected_command:
        return False, "guard_target_command_binding_mismatch"
    if summary.get("status") != "ok" or summary.get("exit_code") != 0:
        return False, "guard_fixture_execution_failed"
    if not summary.get("process_absent"):
        return False, "guard_fixture_child_residual"
    cleanup = summary.get("observed_process_cleanup") or {}
    if not cleanup.get("all_observed_absent"):
        return False, "guard_observed_cleanup_incomplete"
    return True, "pass"


def run_exact_guard_fixture(interpreter: Path, guard: Path, output_dir: Path) -> dict:
    space_dir = output_dir / "fixture path with spaces"
    space_dir.mkdir(parents=True, exist_ok=False)
    child_report = space_dir / "child identity.json"
    sentinel = "argument value with spaces"
    target = [
        str(interpreter.resolve()), str((SCRIPTS / "phase6hl_guard_fixture_child.py").resolve()),
        "--report", str(child_report), "--sentinel", sentinel,
    ]
    paths = {
        "trace": space_dir / "resource.jsonl", "summary": space_dir / "guard.json",
        "child_stdout": space_dir / "child.stdout.log", "child_stderr": space_dir / "child.stderr.log",
        "cleanup": space_dir / "cleanup.jsonl", "lifecycle": None, "gpu": space_dir / "unused-gpu.csv",
    }
    safety = {
        "outer_timeout_seconds": 20, "sample_seconds": 0.1,
        "runner_private_limit_bytes": 512 * MIB, "kit_private_limit_bytes": 512 * MIB,
        "diagnostic_private_limit_bytes": 512 * MIB, "unique_tree_private_limit_bytes": 1024 * MIB,
        "available_physical_floor_bytes": 1024 * MIB, "commit_headroom_floor_bytes": 1024 * MIB,
    }
    command = build_guard_command(interpreter, guard, paths, target, attempt_id="phase6hl-preflight", safety=safety, include_gpu=False)
    return_code, timed_out, guard_pid, guard_creation_time = _run_to_files(
        command, space_dir / "guard-launcher.stdout.log", space_dir / "guard-launcher.stderr.log", 30.0
    )
    summary = _read_bounded(paths["summary"]) if paths["summary"].is_file() else None
    child = _read_bounded(child_report) if child_report.is_file() else None
    summary_pass, summary_reason = validate_guard_summary(summary, target)
    checks = {
        "guard_exit_zero": return_code == 0 and not timed_out,
        "summary_valid": summary_pass,
        "target_arguments_unmodified": summary is not None and summary.get("command") == target,
        "space_path_and_argument_preserved": child is not None and child.get("sentinel") == sentinel and str(child_report) in child.get("argv", []),
        "child_executable_exact": child is not None and _norm(child.get("absolute_executable_path", "missing")) == _norm(interpreter),
        "parent_relation_exact": child is not None and int(child.get("parent_pid", -1)) == guard_pid,
        "child_identity_recorded": child is not None and isinstance(child.get("pid"), int) and isinstance(child.get("creation_time_utc_epoch"), float),
        "guard_identity_absent": _identity_absent(guard_pid, guard_creation_time, str(interpreter.resolve())),
        "child_identity_absent": child is not None and _identity_absent(child["pid"], child["creation_time_utc_epoch"], child["absolute_executable_path"]),
        "summary_bounded": paths["summary"].is_file() and paths["summary"].stat().st_size <= MIB,
        "stdout_stderr_streamed_to_files": all(path.is_file() and path.stat().st_size <= 2 * MIB for path in (space_dir / "guard-launcher.stdout.log", space_dir / "guard-launcher.stderr.log", paths["child_stdout"], paths["child_stderr"])),
    }
    report = {
        "schema": "campfire.phase6hl.exact-guard-fixture.v1",
        "status": "pass" if all(checks.values()) else "fail",
        "command": command,
        "target_command": target,
        "guard_pid": guard_pid,
        "guard_creation_time_utc_epoch": guard_creation_time,
        "guard_exit_code": return_code,
        "guard_timed_out": timed_out,
        "summary_reason": summary_reason,
        "checks": checks,
        "child": child,
        "summary_path": str(paths["summary"]),
        "large_output_buffered_in_parent": False,
    }
    _write(output_dir / "exact_guard_fixture.json", report)
    return report


def run_preflight_suite(contract: dict, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=False)
    interpreter = Path(contract["interpreter"]["guard_executable"])
    packman = Path(contract["interpreter"]["packman_executable"])
    guard = ROOT / contract["interpreter"]["guard_script"]
    positive = observe_interpreter(interpreter, guard, output_dir / "positive")
    positive_ok, positive_reason = validate_interpreter(positive, interpreter, guard)
    packman_observation = observe_interpreter(packman, guard, output_dir / "negative-packman")
    packman_ok, packman_reason = validate_interpreter(packman_observation, interpreter, guard)
    missing_psutil = copy.deepcopy(positive)
    missing_psutil["psutil_imported"] = False
    _, missing_psutil_reason = validate_interpreter(missing_psutil, interpreter, guard)
    mismatch = copy.deepcopy(positive)
    mismatch["sys_executable"] = str(packman)
    _, mismatch_reason = validate_interpreter(mismatch, interpreter, guard)
    bad_guard = output_dir / "negative-guard-import" / "broken guard.py"
    bad_guard.parent.mkdir(parents=True)
    bad_guard.write_text("raise RuntimeError('intentional guard import fixture')\n", encoding="utf-8")
    guard_import_observation = observe_interpreter(interpreter, bad_guard, output_dir / "negative-guard-import" / "observation")
    _, guard_import_reason = validate_interpreter(guard_import_observation, interpreter, bad_guard)
    exact = run_exact_guard_fixture(interpreter, guard, output_dir / "exact-command") if positive_ok else {"status": "not_run"}
    missing_summary_ok, missing_summary_reason = validate_guard_summary(None, [])
    binding_summary = {"schema": "campfire.phase6eg.resource-guard.v1", "command": ["changed"], "status": "ok", "exit_code": 0, "process_absent": True, "observed_process_cleanup": {"all_observed_absent": True}}
    binding_ok, binding_reason = validate_guard_summary(binding_summary, ["expected"])
    cases = {
        "positive_exact_interpreter": positive_ok and positive_reason == "pass",
        "packman_rejected_without_guard_launch": (not packman_ok) and packman_reason == "guard_interpreter_mismatch" and not packman_observation.get("psutil_imported"),
        "psutil_missing_distinct": missing_psutil_reason == "psutil_import_failed",
        "sys_executable_mismatch_distinct": mismatch_reason == "guard_sys_executable_mismatch",
        "guard_import_failure_distinct": guard_import_reason == "guard_import_failed",
        "guard_summary_missing_distinct": (not missing_summary_ok) and missing_summary_reason == "guard_summary_missing",
        "guard_binding_mismatch_distinct": (not binding_ok) and binding_reason == "guard_target_command_binding_mismatch",
        "exact_guard_command": exact.get("status") == "pass",
        "no_implicit_fallback": positive.get("selected_interpreter") == str(interpreter.resolve()) and packman_observation.get("selected_interpreter") == str(packman.resolve()),
    }
    report = {
        "schema": "campfire.phase6hl.guard-preflight-suite.v1",
        "status": "pass" if all(cases.values()) else "fail",
        "cases": cases,
        "positive": positive,
        "packman_negative": {"validation_reason": packman_reason, "observation": packman_observation},
        "negative_reasons": {
            "psutil_missing": missing_psutil_reason, "interpreter_mismatch": mismatch_reason,
            "guard_import": guard_import_reason, "summary_missing": missing_summary_reason,
            "binding_mismatch": binding_reason,
        },
        "exact_guard_fixture": exact,
        "guard_or_child_residual_count": 0 if exact.get("status") == "pass" else None,
        "kit_launch_count": 0,
        "packman_environment_modified": False,
    }
    _write(output_dir / "preflight_report.json", report)
    return report
