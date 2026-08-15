"""Phase 6IJ session-aware Stage composition producer/consumer."""
from __future__ import annotations

import copy
import re

import phase6ii_stage_composition_ladder as base

SCHEMA = "campfire.phase6ij.stage-open-operation.v1"
IDENTITY_SCHEMA = "campfire.phase6ij.opened-stage-identity.v1"
CONDITIONS = base.CONDITIONS
PROTECTED_FILENAME = base.PROTECTED_FILENAME
RUNTIME_FILENAME = base.RUNTIME_FILENAME
CONTAINER_FILENAME = base.CONTAINER_FILENAME
EMPTY_RUNTIME_TEXT = base.EMPTY_RUNTIME_TEXT
MAX_DOCUMENT_BYTES = base.MAX_DOCUMENT_BYTES
SESSION_RUNTIME_ID_MAX_LENGTH = 32
SESSION_IDENTIFIER_RE = re.compile(r"^anon:([0-9A-Fa-f]{1,32})$")

sha256_file = base.sha256_file
create_condition_files = base.create_condition_files
validate_composition_files = base.validate_composition_files
validate_plan = base.validate_plan
read_bounded = base.read_bounded


def normalize_session_identifier(value) -> dict:
    result = {
        "raw": value if isinstance(value, str) else None,
        "accepted": False,
        "normalized": None,
        "runtime_id": None,
        "runtime_id_length": None,
        "runtime_id_charset": "ascii_hex",
        "maximum_runtime_id_length": SESSION_RUNTIME_ID_MAX_LENGTH,
        "reason": None,
    }
    if not isinstance(value, str):
        result["reason"] = "session_identifier_type_invalid"
        return result
    match = SESSION_IDENTIFIER_RE.fullmatch(value)
    if match is None:
        result["reason"] = "session_identifier_format_invalid"
        return result
    runtime_id = match.group(1)
    result.update({
        "accepted": True,
        "normalized": "anon:" + runtime_id.upper(),
        "runtime_id": runtime_id.upper(),
        "runtime_id_length": len(runtime_id),
    })
    return result


def expected_identity(files: dict) -> dict:
    value = base.expected_identity(files)
    value.pop("session_suffix", None)
    value["session_contract"] = {
        "identifier_format": "anon:<ascii-hex-runtime-id>",
        "runtime_id_min_length": 1,
        "runtime_id_max_length": SESSION_RUNTIME_ID_MAX_LENGTH,
        "anonymous_required": True,
        "file_backed_forbidden": True,
        "single_session_layer_required": True,
        "stable_until_close_request": True,
        "distinct_from_root_runtime_protected": True,
    }
    return value


def produce_session_evidence(
    *, session_layer, session_layer_at_close_request, root_layer,
    runtime_layer, protected_layer, layer_stack, raw_identifier,
    close_request_identifier, real_path, resolved_path,
) -> dict:
    normalized = normalize_session_identifier(raw_identifier)
    close_normalized = normalize_session_identifier(close_request_identifier)
    return {
        "session_present": session_layer is not None,
        "session_identifier_raw": raw_identifier,
        "session_identifier_normalized": normalized,
        "session_identifier_at_close_request_raw": close_request_identifier,
        "session_identifier_at_close_request_normalized": close_normalized,
        "session_anonymous": bool(getattr(session_layer, "anonymous", False)) if session_layer is not None else False,
        "session_real_path": str(real_path or ""),
        "session_resolved_path": str(resolved_path or ""),
        "session_is_get_session_layer": session_layer is not None and session_layer == session_layer_at_close_request,
        "session_python_identity_stable": session_layer is not None and session_layer is session_layer_at_close_request,
        "session_distinct_from_root": session_layer is not None and session_layer != root_layer,
        "session_distinct_from_runtime": runtime_layer is None or (session_layer is not None and session_layer != runtime_layer),
        "session_distinct_from_protected": session_layer is not None and session_layer != protected_layer,
        "session_layer_count": sum(1 for layer in layer_stack if session_layer is not None and layer == session_layer),
        "session_identifier_stable_until_close_request": raw_identifier == close_request_identifier,
        "session_object_stable_until_close_request": session_layer is not None and session_layer == session_layer_at_close_request,
        "session_python_object_id_initial": id(session_layer) if session_layer is not None else None,
        "session_python_object_id_close_request": id(session_layer_at_close_request) if session_layer_at_close_request is not None else None,
    }


def produce_operation_report(attempt_id: str, condition: str, expected: dict) -> dict:
    value = base.produce_operation_report(attempt_id, condition, expected)
    value["schema"] = SCHEMA
    value["phase"] = "phase6ij"
    return value


def validate_session_evidence(observed: dict) -> dict:
    reasons = []
    normalized = observed.get("session_identifier_normalized")
    close_normalized = observed.get("session_identifier_at_close_request_normalized")
    if not isinstance(normalized, dict) or normalized.get("accepted") is not True:
        reasons.append("session_identifier_invalid")
    if not isinstance(close_normalized, dict) or close_normalized.get("accepted") is not True:
        reasons.append("session_close_identifier_invalid")
    for key in (
        "session_present", "session_anonymous", "session_is_get_session_layer",
        "session_python_identity_stable",
        "session_distinct_from_root", "session_distinct_from_runtime",
        "session_distinct_from_protected", "session_identifier_stable_until_close_request",
        "session_object_stable_until_close_request",
    ):
        if observed.get(key) is not True:
            reasons.append(key + "_invalid")
    for key in ("session_real_path", "session_resolved_path"):
        if observed.get(key) != "":
            reasons.append(key + "_file_backed")
    if type(observed.get("session_layer_count")) is not int or observed.get("session_layer_count") != 1:
        reasons.append("session_layer_count_invalid")
    if isinstance(normalized, dict) and isinstance(close_normalized, dict):
        if normalized.get("normalized") != close_normalized.get("normalized"):
            reasons.append("session_normalized_identifier_changed")
    return {"accepted": not reasons, "reasons": reasons}


def validate_identity(observed: dict, expected: dict) -> dict:
    reasons = []
    for key in ("condition", "open_path", "open_sha256", "root_identifier", "sublayer_identifiers", "edit_target_identifier"):
        if observed.get(key) != expected.get(key):
            reasons.append(key + "_mismatch")
    if observed.get("protected_sha256") != expected.get("protected_sha256"):
        reasons.append("protected_hash_mismatch")
    if observed.get("runtime_empty") is not expected.get("runtime_must_be_empty"):
        reasons.append("runtime_empty_state_mismatch")
    reasons.extend(validate_session_evidence(observed)["reasons"])
    return {"accepted": not reasons, "reasons": reasons}


def validate_operation(report: dict, expected_attempt_id: str, expected_condition: str) -> dict:
    value = copy.deepcopy(report)
    value["schema"] = base.SCHEMA
    value["phase"] = "phase6ii"
    result = base.validate_operation(value, expected_attempt_id, expected_condition)
    reasons = [reason for reason in result["reasons"] if reason != "layer_identity_mismatch"]
    if report.get("schema") != SCHEMA:
        reasons.append("schema_mismatch")
    if report.get("phase") != "phase6ij":
        reasons.append("phase_mismatch")
    expected = report.get("expected_identity")
    observed = report.get("observed_identity")
    if not isinstance(expected, dict) or not isinstance(observed, dict):
        reasons.append("layer_identity_missing")
    else:
        identity = validate_identity(observed, expected)
        if not identity["accepted"]:
            reasons.extend("layer_identity:" + reason for reason in identity["reasons"])
    return {"accepted": not reasons, "reasons": sorted(set(reasons))}


def validate_marker_identity_consistency(rows: list[dict], report: dict) -> dict:
    reasons = []
    observed = report.get("observed_identity") if isinstance(report, dict) else None
    identity_rows = [row for row in rows if row.get("marker") == "opened_stage_identity_recorded"]
    if not isinstance(observed, dict) or len(identity_rows) != 1:
        reasons.append("marker_layer_evidence_missing_or_duplicate")
    else:
        row = identity_rows[0]
        if row.get("condition") != report.get("condition"):
            reasons.append("marker_condition_evidence_conflict")
        if row.get("root_identifier") != observed.get("root_identifier"):
            reasons.append("marker_root_identity_evidence_conflict")
    return {"accepted": not reasons, "reasons": reasons}
