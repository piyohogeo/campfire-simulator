"""Stream and durably commit a bounded Phase 6FZ memory artifact pre-close."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

try:
    import psutil
except ImportError:  # pragma: no cover - runtime environment includes psutil
    psutil = None


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    data = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    with partial.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(partial, path)
    _fsync_directory(path.parent)


def _append_jsonl(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab", buffering=0) as stream:
        stream.write((json.dumps(value, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8"))
        os.fsync(stream.fileno())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest().upper()


def _copy_streaming(source: Path, destination: Path) -> dict:
    partial = destination.with_suffix(destination.suffix + ".partial")
    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as incoming, partial.open("wb") as outgoing:
        while True:
            block = incoming.read(1024 * 1024)
            if not block:
                break
            outgoing.write(block)
            digest.update(block)
            size += len(block)
        outgoing.flush()
        os.fsync(outgoing.fileno())
    os.replace(partial, destination)
    return {"path": str(destination), "bytes": size, "sha256": digest.hexdigest().upper()}


def _copy_valid_jsonl(source: Path, destination: Path) -> tuple[dict, dict | None, int]:
    partial = destination.with_suffix(destination.suffix + ".partial")
    digest = hashlib.sha256()
    size = 0
    count = 0
    last = None
    with source.open("r", encoding="utf-8-sig", errors="strict") as incoming, partial.open("wb") as outgoing:
        for line in incoming:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                break
            if not isinstance(row, dict):
                continue
            encoded = (json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
            outgoing.write(encoded)
            digest.update(encoded)
            size += len(encoded)
            count += 1
            last = row
        outgoing.flush()
        os.fsync(outgoing.fileno())
    os.replace(partial, destination)
    return (
        {"path": str(destination), "bytes": size, "sha256": digest.hexdigest().upper()},
        last,
        count,
    )


def _markers(path: Path) -> list[dict]:
    rows = []
    if not path.is_file():
        return rows
    with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
        for line in stream:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def _private_bytes() -> int:
    if psutil is None:
        return 0
    info = psutil.Process(os.getpid()).memory_info()
    return int(getattr(info, "private", getattr(info, "private_bytes", getattr(info, "rss", 0))))


def _roles(last_resource: dict | None, rows: list[dict] | None = None) -> set[str]:
    result = set()
    candidates = ([last_resource] if last_resource else []) if rows is None else rows
    for sample in candidates:
        for process in (sample or {}).get("processes") or []:
            role = process.get("role")
            if role:
                result.add(str(role))
    return result


def commit(arguments: argparse.Namespace) -> dict:
    destination = arguments.output_dir
    destination.mkdir(parents=True, exist_ok=True)
    begin_markers = _markers(arguments.marker_path)
    begin_names = [str(row.get("marker")) for row in begin_markers]
    measurement = next((row for row in reversed(begin_markers) if row.get("marker") == "measurement_complete"), None)
    if measurement is None:
        raise RuntimeError("measurement_complete marker missing")
    if "stage_close_request_before" in begin_names:
        raise RuntimeError("stage close began before artifact commit")
    if not all(path.is_file() for path in (
        arguments.raw_path, arguments.resource_path, arguments.marker_path,
        arguments.attempt_metadata, arguments.contract,
    )):
        raise RuntimeError("required measurement source missing")

    files: dict[str, dict] = {}
    files["raw"] = _copy_streaming(arguments.raw_path, destination / "measurement_raw_snapshot.json")
    files["attempt_metadata"] = _copy_streaming(
        arguments.attempt_metadata, destination / "attempt_metadata_snapshot.json"
    )
    files["contract"] = _copy_streaming(arguments.contract, destination / "contract_snapshot.json")
    files["markers"], last_marker, marker_count = _copy_valid_jsonl(
        arguments.marker_path, destination / "measurement_markers_snapshot.jsonl"
    )
    files["resource"], last_resource, resource_count = _copy_valid_jsonl(
        arguments.resource_path, destination / "measurement_resource_snapshot.jsonl"
    )
    if arguments.gpu_path.is_file():
        files["gpu"] = _copy_streaming(arguments.gpu_path, destination / "measurement_gpu_snapshot.csv")

    end_markers = _markers(arguments.marker_path)
    end_names = [str(row.get("marker")) for row in end_markers]
    close_started = "stage_close_request_before" in end_names
    raw = json.loads((destination / "measurement_raw_snapshot.json").read_text(encoding="utf-8-sig"))
    metadata = json.loads((destination / "attempt_metadata_snapshot.json").read_text(encoding="utf-8-sig"))
    roles_seen = set()
    # Re-read the compact snapshot without retaining the full trace.
    with (destination / "measurement_resource_snapshot.jsonl").open("r", encoding="utf-8") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            roles_seen.update(_roles(row))
    machine = (last_resource or {}).get("machine") or {}
    telemetry = {
        "resource_sample_count": resource_count,
        "resource_marker_count": marker_count,
        "roles_observed": sorted(roles_seen),
        "kit_observed": "kit" in roles_seen,
        "runner_observed": "runner" in roles_seen,
        "diagnostic_observed": "diagnostic" in roles_seen,
        "tree_private_present": (last_resource or {}).get("tree_private_bytes") is not None,
        "available_physical_present": machine.get("available_physical_bytes") is not None,
        "commit_headroom_present": machine.get("estimated_commit_headroom_bytes") is not None,
        "last_resource_timestamp_utc_epoch": (last_resource or {}).get("timestamp_utc_epoch"),
        "last_resource_sample_index": (last_resource or {}).get("sample_index"),
    }
    committed_at = _utc()
    summary = {
        "schema": "campfire.phase6fz.preclose-memory-commit.v1",
        "status": "committed_before_stage_close" if not close_started else "stage_close_race",
        "committed_at_utc": committed_at,
        "attempt_id": metadata.get("attempt_id"),
        "condition": metadata.get("condition"),
        "slot_id": metadata.get("slot_id"),
        "slot_kind": metadata.get("slot_kind", "basic"),
        "replacement_for": metadata.get("replacement_for"),
        "measurement_marker_timestamp_utc": measurement.get("timestamp_utc"),
        "last_marker_in_snapshot": (last_marker or {}).get("marker"),
        "stage_close_observed_during_commit": close_started,
        "raw_status": raw.get("status"),
        "raw_lifecycle_marker": raw.get("lifecycle_marker"),
        "completion_contract": raw.get("completion_contract"),
        "files": files,
        "telemetry": telemetry,
        "committer": {
            "pid": os.getpid(),
            "private_bytes_at_commit": _private_bytes(),
            "private_limit_bytes": arguments.private_limit_bytes,
        },
    }
    _atomic_json(destination / "memory_measurement_commit.json", summary)
    _append_jsonl(
        destination / "measurement_commit_markers.jsonl",
        {
            "schema": "campfire.phase6fz.measurement-commit-marker.v1",
            "marker": "memory_measurement_artifact_committed",
            "timestamp_utc": committed_at,
            "attempt_id": metadata.get("attempt_id"),
            "condition": metadata.get("condition"),
            "committed_before_stage_close": not close_started,
            "summary_sha256": _sha256(destination / "memory_measurement_commit.json"),
        },
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-path", type=Path, required=True)
    parser.add_argument("--resource-path", type=Path, required=True)
    parser.add_argument("--gpu-path", type=Path, required=True)
    parser.add_argument("--marker-path", type=Path, required=True)
    parser.add_argument("--attempt-metadata", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--stop-file", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    parser.add_argument("--private-limit-bytes", type=int, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    peak = 0
    result = None
    failure = None
    while time.monotonic() - started < args.timeout_seconds:
        peak = max(peak, _private_bytes())
        if peak > args.private_limit_bytes:
            failure = "committer_private_limit_exceeded"
            break
        names = [str(row.get("marker")) for row in _markers(args.marker_path)]
        if "measurement_complete" in names:
            try:
                result = commit(args)
            except Exception as error:  # fail closed; bounded summary below
                failure = f"{type(error).__name__}: {error}"
            break
        if args.stop_file.exists():
            failure = "parent_stopped_before_measurement_commit"
            break
        time.sleep(0.02)
    else:
        failure = "committer_timeout"

    status = {
        "schema": "campfire.phase6fz.preclose-committer-summary.v1",
        "status": "ok" if result and result.get("status") == "committed_before_stage_close" else "failed",
        "failure": failure,
        "peak_private_bytes": peak,
        "private_limit_bytes": args.private_limit_bytes,
        "duration_seconds": time.monotonic() - started,
        "measurement_commit": result,
        "completed_at_utc": _utc(),
    }
    _atomic_json(args.output_dir / "committer_summary.json", status)
    signal = args.output_dir / ("measurement_commit.ack" if status["status"] == "ok" else "measurement_commit.failed")
    with signal.open("wb") as stream:
        stream.write((status["status"] + "\n").encode("ascii"))
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({"status": status["status"], "failure": failure}, separators=(",", ":")))
    return 0 if status["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
