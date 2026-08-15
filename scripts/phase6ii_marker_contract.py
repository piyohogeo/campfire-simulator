"""Durable bounded marker contract for Phase 6II."""
from __future__ import annotations

import inspect
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

EVENT_FIELDS = {
    "process_started": {"attempt_id": str, "condition": str},
    "kit_app_ready": {"attempt_id": str, "condition": str},
    "stage_open_requested": {"condition": str, "open_path": str},
    "stage_open_completed": {"condition": str, "elapsed_seconds": float},
    "opened_stage_identity_recorded": {"condition": str, "root_identifier": str},
    "stage_close_requested": {"condition": str},
    "stage_close_completed": {"condition": str, "elapsed_seconds": float},
    "context_empty_confirmed": {"condition": str},
    "shutdown_requested": {"condition": str},
    "shutdown_complete": {"condition": str},
}
ORDER = tuple(EVENT_FIELDS)
AUTO_KEYS = frozenset({"marker", "timestamp_utc", "path"})


def canonical_payload(event_name: str, payload: Mapping[str, object]) -> dict:
    if event_name not in EVENT_FIELDS:
        raise ValueError("unknown_marker_event:" + event_name)
    if not isinstance(payload, Mapping):
        raise TypeError("marker_payload_type_invalid")
    collision = sorted(set(payload) & RESERVED_KEYS)
    if collision:
        raise ValueError("reserved_marker_key_collision:" + collision[0])
    expected = EVENT_FIELDS[event_name]
    missing = sorted(set(expected) - set(payload))
    unknown = sorted(set(payload) - set(expected))
    if missing:
        raise ValueError("required_marker_key_missing:" + missing[0])
    if unknown:
        raise ValueError("unknown_marker_payload_key:" + unknown[0])
    result = {}
    for key, kind in expected.items():
        value = payload[key]
        valid = type(value) is kind if kind in (bool, int, float) else isinstance(value, kind)
        if not valid:
            raise TypeError("marker_payload_type_invalid:" + key)
        if kind is str and not value:
            raise ValueError("marker_payload_empty:" + key)
        result[key] = value
    return result


def append_marker(marker_file: Path, event_name: str, payload: Mapping[str, object]) -> dict:
    canonical = canonical_payload(event_name, payload)
    marker_file = Path(marker_file)
    marker_file.parent.mkdir(parents=True, exist_ok=True)
    row = {"marker": event_name, "timestamp_utc": datetime.now(timezone.utc).isoformat(), **canonical}
    with marker_file.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return row


RESERVED_KEYS = AUTO_KEYS | frozenset(inspect.signature(append_marker).parameters)


def produce_marker(event_name: str, **values: object):
    return event_name, canonical_payload(event_name, values)


def validate_sequence(rows: list[dict]) -> dict:
    names = [row.get("marker") for row in rows]
    reasons = []
    if len(names) != len(set(names)):
        reasons.append("marker_duplicate")
    if names != list(ORDER):
        reasons.append("marker_order_or_missing")
    return {"accepted": not reasons, "reasons": reasons}
