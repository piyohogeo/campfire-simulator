"""Pure-Python harness contracts for Phase 6GS."""

from __future__ import annotations


ACCESSORS = (
    "get_num_grids",
    "get_grid_type",
    "get_short_grid_name",
    "get_grid_class",
    "get_index_bounding_box",
    "get_world_bounding_box",
)


def canonical_source_marker_payload(
    source_metadata: dict,
    *,
    expected_slot: int = 0,
    canonical_channel: str = "temperature",
) -> dict:
    """Return one marker payload with exactly one canonical channel key."""
    if not isinstance(source_metadata, dict):
        raise TypeError("source metadata must be an object")
    metadata_channel = source_metadata.get("channel")
    if metadata_channel is not None and metadata_channel != canonical_channel:
        raise ValueError(
            f"conflicting channel: canonical={canonical_channel!r} metadata={metadata_channel!r}"
        )
    if source_metadata.get("slot") != expected_slot:
        raise ValueError(f"unexpected source slot: {source_metadata.get('slot')!r}")
    payload = {key: value for key, value in source_metadata.items() if key != "channel"}
    payload["channel"] = canonical_channel
    if list(payload).count("channel") != 1:
        raise AssertionError("canonical marker payload did not contain exactly one channel key")
    return payload


def validate_qualified_temperature_slot(candidate: dict, qualification: dict) -> dict:
    candidate_rows = [row for row in candidate.get("handles", []) if row.get("index") == 0]
    qualified = qualification.get("public_channel_schema", {})
    qualified_rows = [row for row in qualified.get("handles", []) if row.get("index") == 0]
    passed = (
        qualification.get("status") == "qualified"
        and candidate.get("schema_id") == qualified.get("schema_id")
        and len(candidate_rows) == 1
        and len(qualified_rows) == 1
        and candidate_rows[0].get("channel") == "temperature"
        and candidate_rows[0].get("state") == "nonempty"
        and qualified_rows[0].get("channel") == "temperature"
        and qualified_rows[0].get("state") == "nonempty"
    )
    return {
        "pass": passed,
        "schema_id": qualified.get("schema_id"),
        "slot": 0,
        "channel": qualified_rows[0].get("channel") if len(qualified_rows) == 1 else None,
        "state": qualified_rows[0].get("state") if len(qualified_rows) == 1 else None,
    }


def bounded_public_value(value, *, maximum_items: int = 16, maximum_text: int = 512):
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, str) and len(value) > maximum_text:
            raise ValueError("public metadata string exceeded bounded length")
        return value
    if isinstance(value, (tuple, list)):
        if len(value) > maximum_items:
            raise ValueError("public metadata sequence exceeded bounded length")
        return [bounded_public_value(item, maximum_items=maximum_items, maximum_text=maximum_text) for item in value]
    text = str(value)
    if len(text) > maximum_text:
        raise ValueError("public metadata text exceeded bounded length")
    return {"python_type": f"{type(value).__module__}.{type(value).__qualname__}", "text": text}
