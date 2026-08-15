"""Bounded Phase 6FZ process-role projection for Phase 6HN.

The historical aggregate is a read-only source.  Only this deliberately small
projection is admitted to the shared bounded JSON consumer.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from phase6hl_guard_preflight import _read_bounded, _write


ROOT = Path(__file__).resolve().parents[1]
FZ_ROOT = ROOT / "artifacts/phase6fz-three-axis-memory-2"
SCHEMA = "campfire.phase6hn.phase6fz-process-role-projection.v1"
PROJECTION_MAX_BYTES = 128 * 1024
BOUNDED_READER_MAX_BYTES = 1024 * 1024
EXPECTED_ATTEMPT_IDS = ["attempt%02d" % index for index in range(1, 10)]
ROLE_KEYS = ("runner", "kit", "diagnostic", "unknown_child")
TOP_LEVEL_KEYS = {
    "schema", "source", "projection_contract", "attempt_count", "attempts",
    "population", "source_modified", "phase6fz_reclassified",
}
ATTEMPT_KEYS = {
    "attempt_id", "condition", "final_classification", "exit_state",
    "guarded_root", "kit_direct_child", "roles", "deduplication",
    "pid_reuse_protection", "cleanup",
}
IDENTITY_KEYS = {"pid", "creation_time_utc_epoch", "normalized_executable_path", "role", "parent_pid"}


class ProjectionError(ValueError):
    """A stable fail-closed projection or validation failure."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _normalise_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ProjectionError("identity_path_type_invalid")
    return os.path.normcase(os.path.normpath(os.path.abspath(value)))


def _identity(row: Dict[str, Any], role: str) -> Dict[str, Any]:
    try:
        pid = int(row["pid"])
        creation = float(row["create_time_utc_epoch"])
        parent = int(row["parent_pid"]) if row.get("parent_pid") is not None else None
    except (KeyError, TypeError, ValueError):
        raise ProjectionError("identity_field_invalid:%s" % role)
    if pid <= 0 or creation <= 0:
        raise ProjectionError("identity_value_invalid:%s" % role)
    return {
        "pid": pid,
        "creation_time_utc_epoch": creation,
        "normalized_executable_path": _normalise_path(row.get("path")),
        "role": role,
        "parent_pid": parent,
    }


def _iter_trace(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.is_file():
        raise ProjectionError("resource_trace_missing:%s" % path)
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ProjectionError("resource_trace_json_invalid:%d" % line_number) from exc
            if not isinstance(row, dict):
                raise ProjectionError("resource_trace_row_type_invalid:%d" % line_number)
            yield row


def _trace_projection(path: Path, root_pid: int) -> Dict[str, Any]:
    role_identities = {key: {} for key in ROLE_KEYS}  # type: Dict[str, Dict[Tuple[int, float], Dict[str, Any]]]
    duplicate_in_sample = 0
    pid_creations = {}  # type: Dict[int, set]
    sample_count = 0
    kit_parent_mismatch = 0
    for sample in _iter_trace(path):
        sample_count += 1
        seen = set()  # type: set
        for row in sample.get("processes") or []:
            if not isinstance(row, dict):
                raise ProjectionError("resource_process_type_invalid")
            try:
                key = (int(row["pid"]), float(row["create_time_utc_epoch"]))
            except (KeyError, TypeError, ValueError):
                raise ProjectionError("resource_process_identity_invalid")
            if key in seen:
                duplicate_in_sample += 1
            seen.add(key)
            pid_creations.setdefault(key[0], set()).add(key[1])
            raw_role = row.get("role")
            role = "unknown_child" if raw_role == "child" else raw_role
            if role not in role_identities:
                raise ProjectionError("unknown_role:%s" % raw_role)
            canonical = _identity(row, role)
            role_identities[role][key] = canonical
            if role == "kit" and canonical["parent_pid"] != root_pid:
                kit_parent_mismatch += 1
    if sample_count == 0:
        raise ProjectionError("resource_trace_empty")
    roles = {}
    for role in ROLE_KEYS:
        identities = list(role_identities[role].values())
        identities.sort(key=lambda item: (item["creation_time_utc_epoch"], item["pid"]))
        roles[role] = {
            "identity_count": len(identities),
            "representative_identity": identities[0] if identities else None,
            "normalized_executable_paths": sorted({item["normalized_executable_path"] for item in identities})[:8],
        }
    return {
        "roles": roles,
        "sample_count": sample_count,
        "duplicate_identity_within_sample_count": duplicate_in_sample,
        "pid_reuse_observed_count": sum(1 for values in pid_creations.values() if len(values) > 1),
        "kit_parent_mismatch_count": kit_parent_mismatch,
    }


def _read_source_json(path: Path) -> Dict[str, Any]:
    """Read a historical source, not a bounded-consumer input."""
    if not path.is_file():
        raise ProjectionError("source_json_missing:%s" % path)
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ProjectionError("source_json_type_invalid:%s" % path)
    return value


def build_projection(source_root: Path = FZ_ROOT) -> Dict[str, Any]:
    aggregate_path = source_root / "three_axis_memory_qualification_report.json"
    aggregate = _read_source_json(aggregate_path)
    aggregate_rows = aggregate.get("attempts")
    if not isinstance(aggregate_rows, list):
        raise ProjectionError("aggregate_attempts_type_invalid")
    by_id = {}
    for row in aggregate_rows:
        if not isinstance(row, dict) or not isinstance(row.get("attempt_id"), str):
            raise ProjectionError("aggregate_attempt_identity_invalid")
        attempt_id = row["attempt_id"]
        if attempt_id in by_id:
            raise ProjectionError("aggregate_attempt_duplicate:%s" % attempt_id)
        by_id[attempt_id] = row
    if sorted(by_id) != EXPECTED_ATTEMPT_IDS:
        raise ProjectionError("aggregate_attempt_population_mismatch")

    attempts = []
    for attempt_id in EXPECTED_ATTEMPT_IDS:
        attempt_root = source_root / "attempts" / attempt_id
        guard_path = attempt_root / "runner-logs" / "guard.json"
        trace_path = attempt_root / "runner-logs" / "resource.jsonl"
        guard = _read_source_json(guard_path)
        root_identity = _identity(guard.get("root") or {}, "runner")
        trace = _trace_projection(trace_path, root_identity["pid"])
        kit_role = trace["roles"]["kit"]
        kit_identity = kit_role["representative_identity"]
        cleanup = guard.get("observed_process_cleanup") or {}
        row = by_id[attempt_id]
        attempts.append({
            "attempt_id": attempt_id,
            "condition": row.get("condition"),
            "final_classification": row.get("classification"),
            "exit_state": {
                "guard_status": guard.get("status"),
                "guard_stop_reason": guard.get("stop_reason"),
                "child_exit_code": guard.get("exit_code"),
                "normal_os_exit": row.get("classification") == "memory_valid_lifecycle_normal" and guard.get("exit_code") == 0,
            },
            "guarded_root": root_identity,
            "kit_direct_child": {
                "identity": kit_identity,
                "verified": bool(kit_identity and kit_identity["parent_pid"] == root_identity["pid"] and trace["kit_parent_mismatch_count"] == 0),
            },
            "roles": trace["roles"],
            "deduplication": {
                "key": guard.get("deduplication_key"),
                "sample_count": trace["sample_count"],
                "duplicate_identity_within_sample_count": trace["duplicate_identity_within_sample_count"],
            },
            "pid_reuse_protection": {
                "identity_key_includes_creation_time": guard.get("deduplication_key") == ["pid", "create_time_utc_epoch"],
                "pid_reuse_observed_count": trace["pid_reuse_observed_count"],
                "protected_identity_mismatch_count": len(cleanup.get("protected_identity_mismatch") or []),
                "unknown_identity_count": len(cleanup.get("final_unknown") or []),
            },
            "cleanup": {
                "process_absent": guard.get("process_absent") is True,
                "all_observed_absent": cleanup.get("all_observed_absent") is True,
                "residual_process_count": len(cleanup.get("matching_remaining") or []) + len(cleanup.get("final_unknown") or []),
            },
        })
    return {
        "schema": SCHEMA,
        "source": {
            "phase": "phase6fz",
            "root": str(source_root.resolve()),
            "aggregate_path": str(aggregate_path.resolve()),
            "aggregate_size_bytes": aggregate_path.stat().st_size,
            "aggregate_sha256": _sha256(aggregate_path),
        },
        "projection_contract": {
            "maximum_bytes": PROJECTION_MAX_BYTES,
            "shared_bounded_reader_maximum_bytes": BOUNDED_READER_MAX_BYTES,
            "required_attempt_ids": EXPECTED_ATTEMPT_IDS,
            "full_samples_embedded": False,
            "stdout_stderr_embedded": False,
            "gpu_timeseries_embedded": False,
        },
        "attempt_count": len(attempts),
        "attempts": attempts,
        "population": {
            "memory_valid_lifecycle_normal": sum(item["final_classification"] == "memory_valid_lifecycle_normal" for item in attempts),
            "normal_os_exit": sum(item["exit_state"]["normal_os_exit"] for item in attempts),
            "cleanup_residual_process_count": sum(item["cleanup"]["residual_process_count"] for item in attempts),
        },
        "source_modified": False,
        "phase6fz_reclassified": False,
    }


def write_projection(source_root: Path, output_path: Path) -> Dict[str, Any]:
    projection = build_projection(source_root)
    _write(output_path, projection)
    size = output_path.stat().st_size
    if size > PROJECTION_MAX_BYTES:
        output_path.unlink()
        raise ProjectionError("projection_oversize:%d" % size)
    return projection


def read_projection(path: Path) -> Dict[str, Any]:
    try:
        payload = _read_bounded(path, maximum_bytes=PROJECTION_MAX_BYTES)
    except ValueError as exc:
        raise ProjectionError("projection_oversize") from exc
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ProjectionError("projection_unavailable_or_invalid") from exc
    return payload


def _validate_identity(value: Any, expected_role: str) -> None:
    if not isinstance(value, dict) or set(value) != IDENTITY_KEYS:
        raise ProjectionError("identity_schema_mismatch:%s" % expected_role)
    if type(value.get("pid")) is not int or value["pid"] <= 0:
        raise ProjectionError("identity_pid_type_invalid:%s" % expected_role)
    if type(value.get("creation_time_utc_epoch")) not in (int, float) or isinstance(value.get("creation_time_utc_epoch"), bool):
        raise ProjectionError("identity_creation_type_invalid:%s" % expected_role)
    if not isinstance(value.get("normalized_executable_path"), str) or not value["normalized_executable_path"]:
        raise ProjectionError("identity_path_type_invalid:%s" % expected_role)
    if value.get("role") != expected_role:
        raise ProjectionError("role_contradiction:%s" % expected_role)
    if value.get("parent_pid") is not None and type(value.get("parent_pid")) is not int:
        raise ProjectionError("identity_parent_type_invalid:%s" % expected_role)


def validate_projection(payload: Dict[str, Any]) -> Tuple[bool, str]:
    try:
        if not isinstance(payload, dict) or set(payload) != TOP_LEVEL_KEYS:
            raise ProjectionError("projection_top_level_schema_mismatch")
        if payload.get("schema") != SCHEMA:
            raise ProjectionError("projection_schema_mismatch")
        attempts = payload.get("attempts")
        if not isinstance(attempts, list) or type(payload.get("attempt_count")) is not int:
            raise ProjectionError("projection_attempts_type_invalid")
        if payload["attempt_count"] != 9 or len(attempts) != 9:
            raise ProjectionError("projection_attempt_count_mismatch")
        ids = [row.get("attempt_id") if isinstance(row, dict) else None for row in attempts]
        if sorted(ids) != EXPECTED_ATTEMPT_IDS or len(set(ids)) != 9:
            raise ProjectionError("projection_attempt_identity_mismatch")
        for row in attempts:
            if set(row) != ATTEMPT_KEYS:
                raise ProjectionError("projection_attempt_schema_mismatch:%s" % row.get("attempt_id"))
            _validate_identity(row["guarded_root"], "runner")
            kit_direct = row.get("kit_direct_child")
            if not isinstance(kit_direct, dict) or set(kit_direct) != {"identity", "verified"}:
                raise ProjectionError("kit_direct_child_schema_mismatch")
            _validate_identity(kit_direct["identity"], "kit")
            if kit_direct.get("verified") is not True or kit_direct["identity"]["parent_pid"] != row["guarded_root"]["pid"]:
                raise ProjectionError("kit_direct_child_not_verified")
            roles = row.get("roles")
            if not isinstance(roles, dict) or set(roles) != set(ROLE_KEYS):
                raise ProjectionError("role_set_mismatch")
            for role in ROLE_KEYS:
                role_row = roles[role]
                if not isinstance(role_row, dict) or set(role_row) != {"identity_count", "representative_identity", "normalized_executable_paths"}:
                    raise ProjectionError("role_schema_mismatch:%s" % role)
                if type(role_row["identity_count"]) is not int or role_row["identity_count"] < 0:
                    raise ProjectionError("role_count_type_invalid:%s" % role)
                if role_row["identity_count"]:
                    _validate_identity(role_row["representative_identity"], role)
                elif role_row["representative_identity"] is not None:
                    raise ProjectionError("role_representative_contradiction:%s" % role)
            if row["roles"]["runner"]["identity_count"] < 1 or row["roles"]["kit"]["identity_count"] < 1:
                raise ProjectionError("required_role_missing")
            if row["roles"]["diagnostic"]["identity_count"] < 1:
                raise ProjectionError("diagnostic_role_missing")
            dedup = row.get("deduplication") or {}
            if dedup.get("key") != ["pid", "create_time_utc_epoch"] or dedup.get("duplicate_identity_within_sample_count") != 0:
                raise ProjectionError("deduplication_failed")
            reuse = row.get("pid_reuse_protection") or {}
            if reuse.get("identity_key_includes_creation_time") is not True or reuse.get("unknown_identity_count") != 0:
                raise ProjectionError("pid_reuse_protection_failed")
            cleanup = row.get("cleanup") or {}
            if cleanup.get("process_absent") is not True or cleanup.get("all_observed_absent") is not True or cleanup.get("residual_process_count") != 0:
                raise ProjectionError("cleanup_failed")
            exit_state = row.get("exit_state") or {}
            if exit_state.get("normal_os_exit") is not True or exit_state.get("child_exit_code") != 0:
                raise ProjectionError("exit_state_failed")
            if row.get("final_classification") != "memory_valid_lifecycle_normal":
                raise ProjectionError("final_classification_mismatch")
        if payload.get("phase6fz_reclassified") is not False or payload.get("source_modified") is not False:
            raise ProjectionError("frozen_source_policy_mismatch")
        contract = payload.get("projection_contract") or {}
        if contract.get("maximum_bytes") != PROJECTION_MAX_BYTES or contract.get("shared_bounded_reader_maximum_bytes") != BOUNDED_READER_MAX_BYTES:
            raise ProjectionError("projection_size_contract_mismatch")
        if any(contract.get(key) is not False for key in ("full_samples_embedded", "stdout_stderr_embedded", "gpu_timeseries_embedded")):
            raise ProjectionError("projection_forbidden_content_declared")
        population = payload.get("population") or {}
        if population.get("memory_valid_lifecycle_normal") != 9 or population.get("normal_os_exit") != 9 or population.get("cleanup_residual_process_count") != 0:
            raise ProjectionError("projection_population_mismatch")
        return True, "pass"
    except (ProjectionError, TypeError, KeyError) as exc:
        return False, str(exc)

