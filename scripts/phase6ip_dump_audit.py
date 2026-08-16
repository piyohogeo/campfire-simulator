from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import time
import zipfile

import psutil

from phase6hu_atomic_report import append_durable_jsonl, atomic_write_json
from phase6im_process_identity import capture_process_identity

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Path(__file__).with_name("phase6ip_dump_audit_contract.json")
SIDECAR = Path(__file__).with_name("phase6ip_dump_audit_contract.sha256")
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class AuditError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest().upper()


def file_evidence(path: Path) -> dict:
    stat = path.stat()
    return {"path": str(path), "bytes": stat.st_size, "sha256": sha256(path), "modified_utc_epoch": stat.st_mtime}


def validate_sources(policy: dict) -> list[dict]:
    evidence = []
    if len(policy["sources"]) != policy["limits"]["source_file_count"]:
        raise AuditError("source_count_invalid")
    for expected in policy["sources"]:
        path = ROOT / expected["path"]
        if not path.is_file():
            raise AuditError("source_missing:" + expected["path"])
        actual = file_evidence(path)
        if actual["bytes"] != expected["bytes"] or actual["sha256"] != expected["sha256"]:
            raise AuditError("source_integrity_mismatch:" + expected["path"])
        evidence.append(actual)
    return evidence


def inspect_archive(path: Path, limits: dict) -> list[dict]:
    rows = []
    total = 0
    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        if not infos or len(infos) > limits["archive_entry_count"]:
            raise AuditError("archive_entry_count_invalid")
        seen = set()
        for info in infos:
            pure = PurePosixPath(info.filename)
            if pure.is_absolute() or ".." in pure.parts or not pure.name or info.filename in seen:
                raise AuditError("archive_path_invalid")
            seen.add(info.filename)
            if info.file_size < 0 or info.file_size > limits["archive_entry_bytes"]:
                raise AuditError("archive_entry_oversize")
            total += info.file_size
            if total > limits["archive_total_bytes"]:
                raise AuditError("archive_total_oversize")
            rows.append({"name": info.filename, "compressed_bytes": info.compress_size, "bytes": info.file_size, "crc32": f"{info.CRC:08X}"})
    return rows


def extract_streaming(archive_path: Path, target: Path, limits: dict) -> list[dict]:
    inventory = inspect_archive(archive_path, limits)
    target.mkdir(parents=True)
    with zipfile.ZipFile(archive_path, "r") as archive:
        for row in inventory:
            destination = target / PurePosixPath(row["name"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(row["name"], "r") as source, destination.open("xb") as output:
                while True:
                    block = source.read(1024 * 1024)
                    if not block:
                        break
                    output.write(block)
            row["extracted_sha256"] = sha256(destination)
    return inventory


def _exact_stop(process: subprocess.Popen, identity: dict) -> dict:
    result = {"requested": False, "terminated": False, "killed": False, "identity_match": False}
    if process.poll() is not None:
        return result
    try:
        current = capture_process_identity(process.pid, expected_path=identity["executable_path"], expected_creation_ticks=identity["creation_time_filetime_ticks"])
        result["identity_match"] = current["pid"] == identity["pid"]
    except Exception as error:
        result["error"] = f"{type(error).__name__}:{error}"
        return result
    result["requested"] = True
    process.terminate()
    try:
        process.wait(timeout=5); result["terminated"] = True
    except subprocess.TimeoutExpired:
        process.kill(); process.wait(timeout=5); result["killed"] = True
    return result


def run_cdb(cdb: Path, dump: Path, output_root: Path, policy: dict) -> dict:
    stdout_path = output_root / "cdb.stdout.log"
    stderr_path = output_root / "cdb.stderr.log"
    progress_path = output_root / "cdb_progress.jsonl"
    symbol_path = ";".join(str((ROOT / item).resolve()) if not Path(item).is_absolute() else str(Path(item)) for item in policy["symbols"]["paths"])
    command_text = "; ".join(policy["commands"] + ["q"])
    command = [str(cdb), "-logo", str(output_root / "cdb.engine.log"), "-y", symbol_path, "-z", str(dump), "-c", command_text]
    started = time.monotonic()
    with stdout_path.open("wb", buffering=0) as stdout, stderr_path.open("wb", buffering=0) as stderr:
        process = subprocess.Popen(command, cwd=output_root, stdout=stdout, stderr=stderr, creationflags=CREATE_NO_WINDOW)
        identity = capture_process_identity(process.pid, expected_path=cdb)
        last_sizes = (-1, -1)
        last_output_progress = started
        timed_out = None
        while process.poll() is None:
            elapsed = time.monotonic() - started
            sizes = (stdout_path.stat().st_size if stdout_path.exists() else 0, stderr_path.stat().st_size if stderr_path.exists() else 0)
            output_grew = sizes != last_sizes
            if output_grew:
                last_output_progress = time.monotonic(); last_sizes = sizes
            append_durable_jsonl(progress_path, {"schema": "campfire.phase6ip.cdb-progress.v1", "elapsed_seconds": elapsed, "pid": identity["pid"], "creation_time_filetime_ticks": identity["creation_time_filetime_ticks"], "executable_path": identity["executable_path"], "process_alive": True, "stdout_bytes": sizes[0], "stderr_bytes": sizes[1], "output_grew": output_grew})
            if sizes[0] > policy["limits"]["cdb_stdout_bytes"] or sizes[1] > policy["limits"]["cdb_stderr_bytes"]:
                timed_out = "output_oversize"; break
            if elapsed >= policy["timeouts"]["absolute_seconds"]:
                timed_out = "absolute_timeout"; break
            if time.monotonic() - last_output_progress >= policy["timeouts"]["no_output_progress_seconds"] and not psutil.pid_exists(process.pid):
                timed_out = "no_progress_timeout"; break
            time.sleep(policy["timeouts"]["sample_seconds"])
        cleanup = _exact_stop(process, identity) if timed_out else {"requested": False, "terminated": False, "killed": False, "identity_match": True}
        exit_code = process.wait(timeout=5) if process.poll() is None else process.returncode
    return {"command": command, "identity": identity, "exit_code": exit_code, "timeout_reason": timed_out, "cleanup": cleanup, "elapsed_seconds": time.monotonic() - started, "stdout": file_evidence(stdout_path), "stderr": file_evidence(stderr_path), "progress": file_evidence(progress_path)}


def bounded_lines(path: Path, maximum: int):
    if path.stat().st_size > maximum:
        raise AuditError("text_oversize:" + path.name)
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        yield from stream


def run(root: Path) -> dict:
    if root.exists():
        raise AuditError("analysis_root_reuse")
    policy = json.loads(CONTRACT.read_text(encoding="utf-8"))
    digest = sha256(CONTRACT)
    if SIDECAR.read_text(encoding="ascii").split()[0].upper() != digest:
        raise AuditError("contract_digest_mismatch")
    root.mkdir(parents=True)
    atomic_write_json(root / "frozen_contract.json", policy)
    source_before = validate_sources(policy)
    copied = root / "source-copies"; copied.mkdir()
    copied_evidence = []
    for expected in policy["sources"]:
        source = ROOT / expected["path"]; destination = copied / source.name
        if destination.exists():
            destination = copied / (hashlib.sha256(expected["path"].encode()).hexdigest()[:8] + "-" + source.name)
        shutil.copy2(source, destination)
        item = file_evidence(destination); item["source_path"] = expected["path"]
        if item["bytes"] != expected["bytes"] or item["sha256"] != expected["sha256"]:
            raise AuditError("copy_integrity_mismatch")
        copied_evidence.append(item)
    archive = next(path for path in copied.iterdir() if path.name.endswith(".dmp.zip"))
    archive_inventory = extract_streaming(archive, root / "expanded", policy["limits"])
    dumps = list((root / "expanded").glob("*.dmp"))
    if len(dumps) != 1:
        raise AuditError("minidump_count_invalid")
    cdb = Path(policy["cdb"]["path"])
    if not cdb.is_file() or cdb.stat().st_size != policy["cdb"]["bytes"] or sha256(cdb) != policy["cdb"]["sha256"]:
        raise AuditError("cdb_identity_invalid")
    cdb_result = run_cdb(cdb, dumps[0], root, policy)
    source_after = validate_sources(policy)
    integrity_pass = all(a["bytes"] == b["bytes"] and a["sha256"] == b["sha256"] for a, b in zip(source_before, source_after))
    crash_metadata = {}
    toml = next(path for path in copied.iterdir() if path.name.endswith(".dmp.zip.toml"))
    for line in bounded_lines(toml, policy["limits"]["json_bytes"]):
        if "=" in line:
            key, value = line.split("=", 1); key = key.strip().strip('"'); value = value.strip().strip('"')
            if key in {"CrashTime", "UptimeSeconds", "appState", "terminatedByAbort", "UploadSuccessful", "Version", "buildHash"}:
                crash_metadata[key] = value
    result = {"schema": "campfire.phase6ip.raw-audit.v1", "phase": "phase6ip", "contract_sha256": digest, "source_before": source_before, "source_after": source_after, "source_integrity_qualified": integrity_pass, "copied_evidence": copied_evidence, "archive_inventory": archive_inventory, "dump_path": str(dumps[0]), "dump_bytes": dumps[0].stat().st_size, "dump_sha256": sha256(dumps[0]), "crash_metadata": crash_metadata, "cdb": cdb_result, "kit_launch_count": 0, "automatic_upload": False, "original_modified": not integrity_pass}
    atomic_write_json(root / "raw_audit.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--artifact-root", type=Path, required=True); args = parser.parse_args()
    value = run(args.artifact_root.resolve()); raise SystemExit(0 if value["source_integrity_qualified"] and value["cdb"]["timeout_reason"] is None else 1)
