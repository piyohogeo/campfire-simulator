"""Low-overhead process-tree resource guard for Phase 6EG diagnostics.

The Phase 6EA helper limit remains a strict per-runner-process limit.  This
guard adds separate, explicitly named budgets for Kit, diagnostic children,
and the de-duplicated process tree while streaming every sample to JSONL.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil


MIB = 1024 * 1024
DIAGNOSTIC_NAMES = {
    "cdb.exe",
    "windbg.exe",
    "windbgx.exe",
    "procdump.exe",
    "nvidia-smi.exe",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--stdout", type=Path, required=True)
    parser.add_argument("--stderr", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    parser.add_argument("--sample-seconds", type=float, default=0.25)
    parser.add_argument("--runner-private-limit", type=int, default=512 * MIB)
    parser.add_argument("--kit-private-limit", type=int, default=12 * 1024 * MIB)
    parser.add_argument("--diagnostic-private-limit", type=int, default=512 * MIB)
    parser.add_argument("--tree-private-limit", type=int, default=14 * 1024 * MIB)
    parser.add_argument("--available-memory-floor", type=int, default=8 * 1024 * MIB)
    parser.add_argument("--commit-headroom-floor", type=int, default=8 * 1024 * MIB)
    parser.add_argument("--cpu-telemetry", action="store_true")
    parser.add_argument("--cpu-high-thread-threshold-percent", type=float, default=10.0)
    parser.add_argument("--lifecycle-path", type=Path)
    parser.add_argument("--diagnostic-marker-path", type=Path)
    parser.add_argument("--gpu-csv", type=Path)
    parser.add_argument("--gpu-sample-ms", type=int, default=1000)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def _role(process: psutil.Process, root_pid: int) -> str:
    if process.pid == root_pid:
        return "runner"
    name = process.name().lower()
    if name == "kit.exe":
        return "kit"
    if name in DIAGNOSTIC_NAMES:
        return "diagnostic"
    try:
        command = " ".join(process.cmdline()).lower()
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, OSError):
        command = ""
    if "run_lightweight_shutdown_diagnostic_helper.ps1" in command:
        return "diagnostic"
    return "child"


def _memory_row(process: psutil.Process, root_pid: int, timestamp: float, cpu_telemetry: bool) -> dict | None:
    try:
        info = process.memory_info()
        private = int(getattr(info, "private", getattr(info, "pagefile", info.vms)))
        row = {
            "timestamp_utc_epoch": timestamp,
            "pid": process.pid,
            "parent_pid": process.ppid(),
            "create_time_utc_epoch": process.create_time(),
            "name": process.name(),
            "path": process.exe(),
            "role": _role(process, root_pid),
            "private_bytes": private,
            "working_set_bytes": int(info.rss),
            "peak_working_set_bytes": int(getattr(info, "peak_wset", info.rss)),
            "commit_bytes": int(getattr(info, "pagefile", private)),
        }
        if cpu_telemetry:
            times = process.cpu_times()
            row["cpu_user_seconds"] = float(times.user)
            row["cpu_kernel_seconds"] = float(times.system)
            row["cpu_total_seconds"] = float(times.user + times.system)
        return row
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, OSError):
        return None


def _tree_rows(root: psutil.Process, timestamp: float, cpu_telemetry: bool) -> list[dict]:
    candidates = [root]
    try:
        candidates.extend(root.children(recursive=True))
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass
    rows: list[dict] = []
    identities: set[tuple[int, float]] = set()
    for process in candidates:
        row = _memory_row(process, root.pid, timestamp, cpu_telemetry)
        if row is None:
            continue
        identity = (row["pid"], row["create_time_utc_epoch"])
        if identity in identities:
            continue
        identities.add(identity)
        rows.append(row)
    return rows


def _bounded_json_marker(path: Path | None, key: str) -> str | None:
    if path is None or not path.is_file():
        return None
    try:
        if path.stat().st_size > MIB:
            return "oversize"
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = payload.get(key)
        return str(value) if value is not None else None
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "unavailable"


def _last_jsonl_marker(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    try:
        if path.stat().st_size > MIB:
            return "oversize"
        last = None
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    last = line
        if last is None:
            return None
        return str(json.loads(last).get("marker"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "unavailable"


def _append_cpu_deltas(
    rows: list[dict],
    previous: dict[tuple[int, float], tuple[float, float]],
    timestamp: float,
    logical_cpu_count: int,
    high_thread_threshold: float,
) -> None:
    for row in rows:
        identity = (row["pid"], row["create_time_utc_epoch"])
        total = row.get("cpu_total_seconds")
        prior = previous.get(identity)
        utilization = None
        if total is not None and prior is not None:
            elapsed = timestamp - prior[0]
            if elapsed > 0:
                utilization = max(0.0, total - prior[1]) / elapsed * 100.0 / logical_cpu_count
        row["cpu_percent_of_logical_total"] = utilization
        row["cpu_sample_interval_seconds"] = None if prior is None else max(0.0, timestamp - prior[0])
        if total is not None:
            previous[identity] = (timestamp, total)
        row["top_cpu_thread"] = None
        if row["role"] == "kit" and utilization is not None and utilization >= high_thread_threshold:
            try:
                process = psutil.Process(row["pid"])
                threads = process.threads()
                if threads:
                    top = max(threads, key=lambda item: item.user_time + item.system_time)
                    row["top_cpu_thread"] = {
                        "thread_id": int(top.id),
                        "cumulative_user_seconds": float(top.user_time),
                        "cumulative_kernel_seconds": float(top.system_time),
                    }
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, OSError):
                pass


def _terminate_tree(root: psutil.Process) -> None:
    try:
        descendants = root.children(recursive=True)
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        descendants = []
    for process in reversed(descendants):
        try:
            process.kill()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
    try:
        root.kill()
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass
    psutil.wait_procs(descendants + [root], timeout=10)


def _matching_observed_process(record: dict) -> psutil.Process | None:
    try:
        process = psutil.Process(int(record["pid"]))
        if abs(process.create_time() - float(record["create_time_utc_epoch"])) > 0.01:
            return None
        if os.path.normcase(process.exe()) != os.path.normcase(str(record["path"])):
            return None
        return process
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, OSError):
        return None


def _cleanup_observed_processes(observed: dict[tuple[int, float], dict], root_pid: int) -> dict:
    alive = []
    for record in observed.values():
        process = _matching_observed_process(record)
        if process is not None:
            alive.append(process)
    _, survivors = psutil.wait_procs(alive, timeout=2) if alive else ([], [])
    killed = []
    for process in survivors:
        try:
            process.kill()
            killed.append(process.pid)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
    if survivors:
        psutil.wait_procs(survivors, timeout=10)
    remaining = []
    for record in observed.values():
        process = _matching_observed_process(record)
        if process is not None:
            remaining.append({"pid": process.pid, "path": record["path"], "create_time_utc_epoch": record["create_time_utc_epoch"]})
    observed_before_cleanup = [
        {"pid": process.pid, "path": next(record["path"] for record in observed.values() if record["pid"] == process.pid)}
        for process in alive
    ]
    return {
        "root_pid": root_pid,
        "observed_alive_before_cleanup": observed_before_cleanup,
        "cleanup_required": bool(alive),
        "killed_pids": killed,
        "remaining": remaining,
        "all_observed_absent": not remaining,
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def run(arguments: argparse.Namespace) -> int:
    command = list(arguments.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("guarded command is required after --")
    for path in (arguments.trace, arguments.summary, arguments.stdout, arguments.stderr):
        path.parent.mkdir(parents=True, exist_ok=True)

    started = time.time()
    peaks: dict[str, int] = {"runner": 0, "kit": 0, "diagnostic": 0, "child": 0, "tree": 0}
    peak_rows: dict[str, dict | None] = {key: None for key in peaks}
    machine_minima = {
        "available_physical_bytes": None,
        "estimated_commit_headroom_bytes": None,
    }
    stop_reason = None
    exit_code = None
    sample_count = 0
    root: psutil.Process | None = None
    popen: subprocess.Popen | None = None
    logical_cpu_count = max(1, psutil.cpu_count(logical=True) or 1)
    previous_cpu: dict[tuple[int, float], tuple[float, float]] = {}
    cpu_peaks = {"runner": 0.0, "kit": 0.0, "diagnostic": 0.0, "child": 0.0}
    observed_processes: dict[tuple[int, float], dict] = {}
    gpu_popen: subprocess.Popen | None = None
    gpu_process: psutil.Process | None = None
    gpu_stdout = None
    gpu_stderr = None
    gpu_status = "not_requested"

    if arguments.gpu_csv is not None:
        arguments.gpu_csv.parent.mkdir(parents=True, exist_ok=True)
        gpu_stderr_path = arguments.gpu_csv.with_suffix(arguments.gpu_csv.suffix + ".stderr.log")
        gpu_stdout = arguments.gpu_csv.open("wb", buffering=0)
        gpu_stderr = gpu_stderr_path.open("wb", buffering=0)
        executable = shutil.which("nvidia-smi")
        if executable is None:
            gpu_status = "unavailable"
            gpu_stdout.close()
            gpu_stderr.close()
            gpu_stdout = None
            gpu_stderr = None
        else:
            gpu_popen = subprocess.Popen(
                [
                    executable,
                    "--query-gpu=timestamp,index,name,pci.bus_id,memory.used,utilization.gpu,power.draw,temperature.gpu",
                    "--format=csv,noheader,nounits",
                    f"--loop-ms={max(250, arguments.gpu_sample_ms)}",
                ],
                stdout=gpu_stdout,
                stderr=gpu_stderr,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            gpu_process = psutil.Process(gpu_popen.pid)
            gpu_status = "running"

    with arguments.stdout.open("wb", buffering=0) as stdout, arguments.stderr.open("wb", buffering=0) as stderr, arguments.trace.open("w", encoding="utf-8", buffering=1) as trace:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        popen = subprocess.Popen(command, stdout=stdout, stderr=stderr, creationflags=creationflags)
        root = psutil.Process(popen.pid)
        root_identity = {"pid": root.pid, "create_time_utc_epoch": root.create_time(), "path": root.exe()}
        while popen.poll() is None:
            timestamp = time.time()
            rows = _tree_rows(root, timestamp, arguments.cpu_telemetry)
            if gpu_process is not None and gpu_popen is not None and gpu_popen.poll() is None:
                gpu_row = _memory_row(gpu_process, root.pid, timestamp, arguments.cpu_telemetry)
                if gpu_row is not None:
                    rows.append(gpu_row)
            for row in rows:
                observed_processes[(row["pid"], row["create_time_utc_epoch"])] = {
                    "pid": row["pid"],
                    "create_time_utc_epoch": row["create_time_utc_epoch"],
                    "path": row["path"],
                    "role": row["role"],
                }
            if arguments.cpu_telemetry:
                _append_cpu_deltas(
                    rows,
                    previous_cpu,
                    timestamp,
                    logical_cpu_count,
                    arguments.cpu_high_thread_threshold_percent,
                )
            tree_private = sum(row["private_bytes"] for row in rows)
            virtual = psutil.virtual_memory()
            swap = psutil.swap_memory()
            commit_headroom = int(virtual.available + swap.free)
            machine_minima["available_physical_bytes"] = min(
                int(virtual.available),
                machine_minima["available_physical_bytes"]
                if machine_minima["available_physical_bytes"] is not None
                else int(virtual.available),
            )
            machine_minima["estimated_commit_headroom_bytes"] = min(
                commit_headroom,
                machine_minima["estimated_commit_headroom_bytes"]
                if machine_minima["estimated_commit_headroom_bytes"] is not None
                else commit_headroom,
            )
            record = {
                "schema": "campfire.phase6eg.resource-sample.v1",
                "sample_index": sample_count,
                "timestamp_utc_epoch": timestamp,
                "root": root_identity,
                "processes": rows,
                "tree_private_bytes": tree_private,
                "lifecycle_marker": _bounded_json_marker(arguments.lifecycle_path, "lifecycle_marker"),
                "diagnostic_marker": _last_jsonl_marker(arguments.diagnostic_marker_path),
                "machine": {
                    "available_physical_bytes": int(virtual.available),
                    "physical_total_bytes": int(virtual.total),
                    "swap_free_bytes": int(swap.free),
                    "swap_total_bytes": int(swap.total),
                    "estimated_commit_headroom_bytes": commit_headroom,
                },
            }
            record["current_execution_section"] = record["diagnostic_marker"] or record["lifecycle_marker"] or "process_startup"
            trace.write(json.dumps(record, separators=(",", ":")) + "\n")
            sample_count += 1
            for row in rows:
                role = row["role"]
                if row["private_bytes"] > peaks[role]:
                    peaks[role] = row["private_bytes"]
                    peak_rows[role] = row
                utilization = row.get("cpu_percent_of_logical_total")
                if utilization is not None:
                    cpu_peaks[role] = max(cpu_peaks[role], float(utilization))
            if tree_private > peaks["tree"]:
                peaks["tree"] = tree_private
                peak_rows["tree"] = {"timestamp_utc_epoch": timestamp, "processes": rows}

            runner_peak = max((row["private_bytes"] for row in rows if row["role"] == "runner"), default=0)
            kit_peak = max((row["private_bytes"] for row in rows if row["role"] == "kit"), default=0)
            diagnostic_peak = max((row["private_bytes"] for row in rows if row["role"] == "diagnostic"), default=0)
            if arguments.gpu_csv is not None and (gpu_popen is None or gpu_popen.poll() is not None):
                stop_reason = "gpu_telemetry_exit"
            elif runner_peak > arguments.runner_private_limit:
                stop_reason = "runner_private_limit"
            elif kit_peak > arguments.kit_private_limit:
                stop_reason = "kit_private_limit"
            elif diagnostic_peak > arguments.diagnostic_private_limit:
                stop_reason = "diagnostic_private_limit"
            elif tree_private > arguments.tree_private_limit:
                stop_reason = "tree_private_limit"
            elif virtual.available < arguments.available_memory_floor:
                stop_reason = "available_memory_floor"
            elif commit_headroom < arguments.commit_headroom_floor:
                stop_reason = "commit_headroom_floor"
            elif timestamp - started >= arguments.timeout_seconds:
                stop_reason = "timeout"
            if stop_reason:
                _terminate_tree(root)
                break
            time.sleep(arguments.sample_seconds)
        try:
            exit_code = popen.wait(timeout=10)
        except subprocess.TimeoutExpired:
            stop_reason = stop_reason or "exit_wait_timeout"
            _terminate_tree(root)
            exit_code = popen.poll()

    if gpu_popen is not None and gpu_process is not None:
        if gpu_popen.poll() is None:
            _terminate_tree(gpu_process)
        try:
            gpu_popen.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _terminate_tree(gpu_process)
    if gpu_stdout is not None:
        gpu_stdout.close()
    if gpu_stderr is not None:
        gpu_stderr.close()
    if arguments.gpu_csv is not None:
        gpu_status = "completed" if arguments.gpu_csv.is_file() and arguments.gpu_csv.stat().st_size > 0 else "missing_output"

    observed_cleanup = _cleanup_observed_processes(observed_processes, root_identity["pid"])
    process_absent = bool(observed_cleanup["all_observed_absent"])
    if observed_cleanup["cleanup_required"] and stop_reason is None:
        stop_reason = "observed_descendant_residual"
    summary = {
        "schema": "campfire.phase6eg.resource-guard.v1",
        "status": "ok" if stop_reason is None and exit_code == 0 and process_absent else "failed",
        "command": command,
        "root": root_identity,
        "exit_code": exit_code,
        "stop_reason": stop_reason,
        "process_absent": process_absent,
        "observed_process_cleanup": observed_cleanup,
        "duration_seconds": time.time() - started,
        "sample_count": sample_count,
        "peaks": peaks,
        "peak_evidence": peak_rows,
        "machine_minima": machine_minima,
        "cpu_telemetry": {
            "enabled": arguments.cpu_telemetry,
            "normalization": "100 percent equals all logical CPUs busy",
            "logical_cpu_count": logical_cpu_count,
            "sample_interval_seconds": arguments.sample_seconds,
            "missing_first_sample": True,
            "high_cpu_thread_capture_threshold_percent": arguments.cpu_high_thread_threshold_percent,
            "peak_percent_of_logical_total_by_role": cpu_peaks,
            "gpu_sampling": {
                "status": gpu_status,
                "csv_path": None if arguments.gpu_csv is None else str(arguments.gpu_csv.resolve()),
                "sample_interval_ms": None if arguments.gpu_csv is None else max(250, arguments.gpu_sample_ms),
                "scope": "system-wide per-adapter dedicated allocation, utilization, power, and temperature from isolated nvidia-smi",
                "shared_memory": "unavailable from this bounded public telemetry path; not estimated",
                "stdout_buffered_in_parent": False,
            },
        },
        "limits": {
            "runner_private_bytes": arguments.runner_private_limit,
            "kit_private_bytes": arguments.kit_private_limit,
            "diagnostic_private_bytes": arguments.diagnostic_private_limit,
            "tree_private_bytes": arguments.tree_private_limit,
            "available_memory_floor_bytes": arguments.available_memory_floor,
            "commit_headroom_floor_bytes": arguments.commit_headroom_floor,
            "timeout_seconds": arguments.timeout_seconds,
        },
        "trace_path": str(arguments.trace.resolve()),
        "stdout_path": str(arguments.stdout.resolve()),
        "stderr_path": str(arguments.stderr.resolve()),
        "deduplication_key": ["pid", "create_time_utc_epoch"],
        "large_output_buffered_in_parent": False,
    }
    _write_json(arguments.summary, summary)
    return 0 if summary["status"] == "ok" else 2


def main() -> int:
    return run(_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
