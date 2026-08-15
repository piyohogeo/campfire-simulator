"""Canonical Point-policy source-set producer and parent validator for Phase 6HX."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath


MANIFEST_SCHEMA = "campfire.phase6hx.point-policy-source-set.v1"
REPORT_SCHEMA = "campfire.phase6hx.point-policy-invariant-report.v1"
SOURCE_ROOT = "source/extensions/campfire.app"
LEGACY_PATH = f"{SOURCE_ROOT}/campfire/app/point_emitter.py"
MAX_MANIFEST_BYTES = 64 * 1024
MAX_REPORT_BYTES = 128 * 1024
ENTRY_KEYS = {"order", "path", "role", "sha256"}


class InvariantError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def canonical_bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def read_bounded_json(path: Path, maximum: int) -> tuple[dict, bytes]:
    if not path.is_file():
        raise InvariantError(f"bounded_json_missing:{path}")
    size = path.stat().st_size
    if size <= 0 or size > maximum:
        raise InvariantError(f"bounded_json_size_invalid:{size}")
    data = path.read_bytes()
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvariantError(f"bounded_json_invalid:{error}") from error
    if not isinstance(value, dict):
        raise InvariantError("bounded_json_root_type_invalid")
    return value, data


def _is_reparse(path: Path) -> bool:
    info = os.lstat(str(path))
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _ordered_digest(entries: list[dict]) -> str:
    return sha256_bytes(canonical_bytes([{"path": entry["path"], "role": entry["role"]} for entry in entries]))


def _manifest_sidecar_digest(sidecar_path: Path) -> str:
    if not sidecar_path.is_file():
        raise InvariantError("manifest_sidecar_missing")
    token = sidecar_path.read_text(encoding="ascii").split()
    if not token or len(token[0]) != 64:
        raise InvariantError("manifest_sidecar_invalid")
    return token[0].upper()


def validate_manifest(manifest_path: Path, sidecar_path: Path, repo_root: Path) -> dict:
    manifest, raw = read_bounded_json(manifest_path, MAX_MANIFEST_BYTES)
    manifest_sha = sha256_bytes(raw)
    if manifest_sha != _manifest_sidecar_digest(sidecar_path):
        raise InvariantError("manifest_sha256_mismatch")
    if manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("version") != 1:
        raise InvariantError("manifest_schema_mismatch")
    if manifest.get("source_root") != SOURCE_ROOT:
        raise InvariantError("manifest_source_root_mismatch")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries or len(entries) > 32:
        raise InvariantError("manifest_entries_invalid")
    if _ordered_digest(entries) != manifest.get("ordered_entries_sha256"):
        raise InvariantError("manifest_order_digest_mismatch")
    source_root = (repo_root / SOURCE_ROOT).resolve(strict=True)
    if not source_root.is_dir() or _is_reparse(source_root):
        raise InvariantError("source_root_identity_invalid")
    paths: set[str] = set()
    evidence = []
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != ENTRY_KEYS:
            raise InvariantError(f"manifest_entry_shape_invalid:{position}")
        if isinstance(entry["order"], bool) or entry["order"] != position:
            raise InvariantError(f"manifest_entry_order_invalid:{position}")
        relative = entry["path"]
        role = entry["role"]
        expected_sha = entry["sha256"]
        if not isinstance(relative, str) or not isinstance(role, str) or not role.strip():
            raise InvariantError(f"manifest_entry_type_invalid:{position}")
        if not isinstance(expected_sha, str) or len(expected_sha) != 64:
            raise InvariantError(f"manifest_entry_sha_invalid:{position}")
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or relative != pure.as_posix() or not relative.startswith(SOURCE_ROOT + "/"):
            raise InvariantError(f"manifest_entry_path_invalid:{position}")
        if relative == LEGACY_PATH:
            raise InvariantError("legacy_point_emitter_path_forbidden")
        key = relative.casefold()
        if key in paths:
            raise InvariantError(f"manifest_entry_duplicate:{position}")
        paths.add(key)
        lexical = repo_root / Path(*pure.parts)
        if not lexical.exists():
            raise InvariantError(f"manifest_entry_missing:{position}")
        resolved = lexical.resolve(strict=True)
        try:
            resolved.relative_to(source_root)
        except ValueError as error:
            raise InvariantError(f"manifest_entry_source_root_escape:{position}") from error
        current = source_root
        for part in resolved.relative_to(source_root).parts:
            current = current / part
            if _is_reparse(current):
                raise InvariantError(f"manifest_entry_reparse_forbidden:{position}")
        if not resolved.is_file() or not stat.S_ISREG(resolved.stat().st_mode):
            raise InvariantError(f"manifest_entry_not_regular:{position}")
        actual_sha = sha256_bytes(resolved.read_bytes())
        if actual_sha != expected_sha.upper():
            raise InvariantError(f"manifest_entry_sha_mismatch:{position}")
        evidence.append({"order": position, "path": relative, "role": role, "exists": True, "regular_file": True, "resolved_path": str(resolved), "inside_source_root": True, "reparse": False, "sha256": actual_sha})
    return {"manifest_sha256": manifest_sha, "ordered_entries_sha256": manifest["ordered_entries_sha256"], "source_root": str(source_root), "entry_count": len(evidence), "entries": evidence}


def produce_report(manifest_path: Path, sidecar_path: Path, repo_root: Path, attempt_id: str) -> dict:
    if not isinstance(attempt_id, str) or not attempt_id:
        raise InvariantError("attempt_identity_invalid")
    validated = validate_manifest(manifest_path, sidecar_path, repo_root)
    return {"schema": REPORT_SCHEMA, "attempt_id": attempt_id, "status": "qualified", **validated}


def write_report(path: Path, report: dict) -> None:
    data = json.dumps(report, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    if len(data) > MAX_REPORT_BYTES:
        raise InvariantError(f"invariant_report_oversize:{len(data)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists():
        raise InvariantError("invariant_report_temporary_collision")
    with temporary.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def consume_report(report_path: Path, manifest_path: Path, sidecar_path: Path, repo_root: Path, attempt_id: str) -> dict:
    report, _ = read_bounded_json(report_path, MAX_REPORT_BYTES)
    expected = produce_report(manifest_path, sidecar_path, repo_root, attempt_id)
    if report.get("schema") != REPORT_SCHEMA:
        raise InvariantError("invariant_report_schema_mismatch")
    if report.get("attempt_id") != attempt_id:
        raise InvariantError("invariant_report_attempt_mismatch")
    if report != expected:
        raise InvariantError("producer_runner_source_set_mismatch")
    return report


def append_marker(path: Path, name: str, **payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"marker": name, **payload}
    data = canonical_bytes(record) + b"\n"
    with path.open("ab", buffering=0) as stream:
        stream.write(data)
        os.fsync(stream.fileno())
