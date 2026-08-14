"""Pure-Python Phase 6GP metadata boundary and result classification."""

from __future__ import annotations


def type_name(value: object) -> str:
    kind = type(value)
    return f"{kind.__module__}.{kind.__qualname__}"


def bounded_slot_metadata(slot: int, value: object) -> dict:
    """Read only public, constant-size array metadata; never inspect elements."""
    shape = tuple(int(dimension) for dimension in value.shape)
    metadata = {
        "slot": int(slot),
        "python_type": type_name(value),
        "ndim": int(value.ndim),
        "shape": list(shape),
        "dtype": str(value.dtype),
        "size": int(value.size),
        "nbytes": int(value.nbytes),
        "empty": int(value.size) == 0,
    }
    if metadata["ndim"] != len(shape):
        raise ValueError("ndim/shape mismatch")
    if metadata["ndim"] < 0 or metadata["ndim"] > 8:
        raise ValueError("ndim outside bounded contract")
    if any(dimension < 0 for dimension in shape):
        raise ValueError("negative shape dimension")
    if metadata["size"] < 0 or metadata["nbytes"] < 0:
        raise ValueError("negative size metadata")
    return metadata


def classify(operation_complete: bool, lifecycle_normal_exit: bool) -> dict:
    if operation_complete and lifecycle_normal_exit:
        return {
            "operation_result": "pass",
            "lifecycle_result": "normal_exit",
            "classification": "qualified",
        }
    if operation_complete:
        return {
            "operation_result": "partial_operation_evidence",
            "lifecycle_result": "failure",
            "classification": "safe_stop",
        }
    return {
        "operation_result": "failure",
        "lifecycle_result": "not_qualified",
        "classification": "safe_stop",
    }
