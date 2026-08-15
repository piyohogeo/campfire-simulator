"""Bounded Stage-composition producer/consumer for Phase 6II."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

SCHEMA = "campfire.phase6ii.stage-open-operation.v1"
CONDITIONS = ("A", "B", "C")
PROTECTED_FILENAME = "protected_diagnostic.usda"
RUNTIME_FILENAME = "runtime_opinions.usda"
CONTAINER_FILENAME = "container.usda"
EMPTY_RUNTIME_TEXT = "#usda 1.0\n"
MAX_DOCUMENT_BYTES = 262144


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def _write_new(path: Path, text: str) -> None:
    path = Path(path)
    if path.exists():
        raise RuntimeError("composition_file_preexisting:" + path.name)
    path.write_bytes(text.encode("utf-8"))


def create_condition_files(stage_root: Path, condition: str) -> dict:
    """Create only the composition files added by the selected condition."""
    if condition not in CONDITIONS:
        raise ValueError("condition_unknown")
    stage_root = Path(stage_root).resolve()
    protected = stage_root / PROTECTED_FILENAME
    if not protected.is_file():
        raise RuntimeError("protected_layer_missing")
    result = {
        "condition": condition,
        "protected": protected,
        "runtime": None,
        "container": None,
        "open_path": protected,
    }
    if condition == "A":
        return result
    container = stage_root / CONTAINER_FILENAME
    if condition == "B":
        text = "#usda 1.0\n(\n    subLayers = [\n        @protected_diagnostic.usda@\n    ]\n)\n"
    else:
        runtime = stage_root / RUNTIME_FILENAME
        _write_new(runtime, EMPTY_RUNTIME_TEXT)
        result["runtime"] = runtime
        text = "#usda 1.0\n(\n    subLayers = [\n        @runtime_opinions.usda@,\n        @protected_diagnostic.usda@\n    ]\n)\n"
    _write_new(container, text)
    result["container"] = container
    result["open_path"] = container
    return result


def expected_identity(files: dict) -> dict:
    condition = files["condition"]
    open_path = Path(files["open_path"]).resolve()
    protected = Path(files["protected"]).resolve()
    sublayers = []
    if condition == "B":
        sublayers = [str(protected)]
    elif condition == "C":
        sublayers = [str(Path(files["runtime"]).resolve()), str(protected)]
    return {
        "condition": condition,
        "open_path": str(open_path),
        "open_sha256": sha256_file(open_path),
        "root_identifier": str(open_path),
        "sublayer_identifiers": sublayers,
        "session_required": True,
        "session_suffix": open_path.stem + "-session.usda",
        "edit_target_identifier": str(open_path),
        "protected_sha256": sha256_file(protected),
        "runtime_must_be_empty": condition == "C",
    }


def validate_composition_files(files: dict, contract: dict) -> dict:
    reasons = []
    condition = files.get("condition")
    if condition not in CONDITIONS:
        return {"accepted": False, "reasons": ["condition_unknown"]}
    protected = Path(files["protected"]).resolve()
    stage_root = protected.parent
    for key in ("protected", "runtime", "container", "open_path"):
        value = files.get(key)
        if value is None:
            continue
        resolved = Path(value).resolve()
        if resolved.parent != stage_root:
            reasons.append("unknown_path:" + key)
    if not protected.is_file() or sha256_file(protected) != contract["protected_file_sha256"]:
        reasons.append("protected_hash_mismatch")
    if condition == "A":
        if files.get("runtime") is not None or files.get("container") is not None or Path(files["open_path"]).resolve() != protected:
            reasons.append("condition_A_files_invalid")
    if condition == "B":
        container = Path(files["container"])
        if files.get("runtime") is not None:
            reasons.append("condition_B_runtime_unexpected")
        if not container.is_file() or sha256_file(container) != contract["container_B_file_sha256"]:
            reasons.append("condition_B_container_invalid")
    if condition == "C":
        container = Path(files["container"])
        runtime = Path(files["runtime"])
        if not container.is_file() or sha256_file(container) != contract["container_C_file_sha256"]:
            reasons.append("condition_C_container_invalid")
        if not runtime.is_file() or sha256_file(runtime) != contract["runtime_file_sha256"] or runtime.read_text(encoding="utf-8") != EMPTY_RUNTIME_TEXT:
            reasons.append("runtime_layer_nonempty_or_invalid")
    return {"accepted": not reasons, "reasons": reasons}


def produce_operation_report(attempt_id: str, condition: str, expected: dict) -> dict:
    return {
        "schema": SCHEMA,
        "phase": "phase6ii",
        "attempt_id": attempt_id,
        "condition": condition,
        "status": "running",
        "operation_complete": False,
        "references_released": False,
        "context_empty": False,
        "shutdown_complete": False,
        "open_stage_async_calls": 0,
        "close_stage_async_calls": 0,
        "timeline_play_calls": 0,
        "flow_simulation_update_calls": 0,
        "flow_interface_calls": 0,
        "readback_calls": 0,
        "renderer_update_calls": 0,
        "capture_calls": 0,
        "expected_identity": expected,
        "observed_identity": None,
        "open_elapsed_seconds": None,
        "close_elapsed_seconds": None,
        "first_failure_boundary": None,
        "error": None,
    }


def read_bounded(path: Path) -> dict:
    path = Path(path)
    size = path.stat().st_size
    if size <= 0 or size > MAX_DOCUMENT_BYTES:
        raise ValueError("bounded_json_size_invalid")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise TypeError("bounded_json_root_invalid")
    return value


def validate_operation(report: dict, expected_attempt_id: str, expected_condition: str) -> dict:
    reasons = []
    if report.get("schema") != SCHEMA:
        reasons.append("schema_mismatch")
    if report.get("phase") != "phase6ii":
        reasons.append("phase_mismatch")
    if report.get("attempt_id") != expected_attempt_id:
        reasons.append("attempt_identity_mismatch")
    if report.get("condition") != expected_condition:
        reasons.append("condition_mismatch")
    for key in (
        "operation_complete", "references_released", "context_empty", "shutdown_complete"
    ):
        if type(report.get(key)) is not bool:
            reasons.append("boolean_type_invalid:" + key)
    for key in (
        "open_stage_async_calls", "close_stage_async_calls", "timeline_play_calls",
        "flow_simulation_update_calls", "flow_interface_calls", "readback_calls",
        "renderer_update_calls", "capture_calls",
    ):
        value = report.get(key)
        if type(value) is not int:
            reasons.append("call_count_type_invalid:" + key)
    if report.get("open_stage_async_calls") != 1:
        reasons.append("open_call_count_invalid")
    if report.get("close_stage_async_calls") != 1:
        reasons.append("close_call_count_invalid")
    for key in (
        "timeline_play_calls", "flow_simulation_update_calls", "flow_interface_calls",
        "readback_calls", "renderer_update_calls", "capture_calls",
    ):
        if report.get(key) != 0:
            reasons.append("forbidden_call_nonzero:" + key)
    for key in ("open_elapsed_seconds", "close_elapsed_seconds"):
        value = report.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
            reasons.append("elapsed_invalid:" + key)
    if report.get("status") != "stage_open_close_qualified":
        reasons.append("status_not_qualified")
    if not all(report.get(key) is True for key in ("operation_complete", "references_released", "context_empty", "shutdown_complete")):
        reasons.append("operation_or_lifecycle_incomplete")
    expected = report.get("expected_identity")
    observed = report.get("observed_identity")
    if not isinstance(expected, dict) or not isinstance(observed, dict):
        reasons.append("layer_identity_missing")
    elif validate_identity(observed, expected)["accepted"] is not True:
        reasons.append("layer_identity_mismatch")
    return {"accepted": not reasons, "reasons": reasons}


def validate_identity(observed: dict, expected: dict) -> dict:
    reasons = []
    for key in ("condition", "open_path", "open_sha256", "root_identifier", "sublayer_identifiers", "edit_target_identifier"):
        if observed.get(key) != expected.get(key):
            reasons.append(key + "_mismatch")
    if observed.get("protected_sha256") != expected.get("protected_sha256"):
        reasons.append("protected_hash_mismatch")
    if observed.get("session_present") is not True:
        reasons.append("session_missing")
    identifier = observed.get("session_identifier")
    if not isinstance(identifier, str) or not identifier.endswith(expected.get("session_suffix", "<invalid>")):
        reasons.append("session_identifier_mismatch")
    if observed.get("runtime_empty") is not expected.get("runtime_must_be_empty"):
        reasons.append("runtime_empty_state_mismatch")
    return {"accepted": not reasons, "reasons": reasons}


def validate_plan(plan: list[dict]) -> dict:
    reasons = []
    if [row.get("condition") for row in plan] != list(CONDITIONS):
        reasons.append("condition_order_invalid")
    if len({row.get("open_path") for row in plan}) != 3:
        reasons.append("open_path_duplicate")
    if plan:
        hashes = {row.get("protected_sha256") for row in plan}
        if len(hashes) != 1:
            reasons.append("protected_hash_varies")
    expected_sublayers = [[], ["protected"], ["runtime", "protected"]]
    if [row.get("sublayer_roles") for row in plan] != expected_sublayers:
        reasons.append("one_variable_sublayer_ladder_invalid")
    return {"accepted": not reasons, "reasons": reasons}
