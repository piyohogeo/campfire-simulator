"""Pure helpers for Phase 6FK public NumPy pointer evidence."""

from __future__ import annotations


def public_array_data_pointer(value) -> int | None:
    """Return the public NumPy-compatible data pointer without inferring ownership."""
    try:
        interface = value.__array_interface__
        data = interface.get("data")
        pointer = data[0] if data else None
    except Exception:
        return None
    return pointer if type(pointer) is int else None


def pointer_evidence_from_boundary(boundary: dict) -> dict:
    """Normalize the raw C boundary into a fail-closed pointer contract."""
    observable = boundary.get("observable_copy_contract") or {}
    source_metadata = boundary.get("fuel_source") or {}
    converted_metadata = boundary.get("fuel_array") or {}
    source = observable.get("source_data_pointer")
    converted = observable.get("converted_data_pointer")
    failures = []
    if type(source) is not int or source <= 0:
        failures.append("source_data_pointer_not_positive_integer")
    if type(converted) is not int or converted <= 0:
        failures.append("converted_data_pointer_not_positive_integer")
    if not failures and source != converted:
        failures.append("source_converted_data_pointer_mismatch")
    if observable.get("same_data_pointer") is not True:
        failures.append("same_data_pointer_not_true")
    if observable.get("same_identity") is not True:
        failures.append("same_python_identity_not_true")
    if observable.get("shares_memory") is not True:
        failures.append("shares_memory_not_true")
    metadata_fields = ("shape", "dtype", "strides", "size", "nbytes")
    mismatched_metadata = [
        name for name in metadata_fields
        if source_metadata.get(name) != converted_metadata.get(name)
    ]
    if mismatched_metadata:
        failures.append("source_converted_metadata_mismatch")
    source_identity = source_metadata.get("identity")
    converted_identity = converted_metadata.get("identity")
    if type(source_identity) is not int or source_identity <= 0:
        failures.append("source_python_identity_not_positive_integer")
    if type(converted_identity) is not int or converted_identity <= 0:
        failures.append("converted_python_identity_not_positive_integer")
    if source_identity != converted_identity:
        failures.append("source_converted_python_identity_mismatch")
    weak_residual = boundary.get("weak_reference_alive_after_scope_count")
    converted_weak_alive = boundary.get("converted_weak_reference_alive_immediately_after_release")
    if weak_residual != 0:
        failures.append("channel_weak_reference_residual_not_zero")
    if converted_weak_alive is not False:
        failures.append("converted_weak_reference_alive_after_release")
    return {
        "source_python_identity": source_identity,
        "converted_python_identity": converted_identity,
        "source_data_pointer": source,
        "converted_data_pointer": converted,
        "same_data_pointer": observable.get("same_data_pointer"),
        "same_python_identity": observable.get("same_identity"),
        "shares_memory": observable.get("shares_memory"),
        "shape": converted_metadata.get("shape"),
        "dtype": converted_metadata.get("dtype"),
        "strides": converted_metadata.get("strides"),
        "element_count": converted_metadata.get("size"),
        "logical_bytes": converted_metadata.get("nbytes"),
        "metadata_mismatches": mismatched_metadata,
        "channel_weak_reference_residual": weak_residual,
        "converted_weak_reference_alive_after_release": converted_weak_alive,
        "failures": failures,
        "complete": not failures,
    }
