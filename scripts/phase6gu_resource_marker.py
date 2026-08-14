"""No-Kit-safe durable resource marker contract introduced by Phase 6GU."""

from __future__ import annotations

import inspect
import json
import os
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path

from phase6eu_process_memory import process_memory_snapshot


AUTO_GENERATED_MARKER_KEYS = frozenset(
    {
        "schema",
        "timestamp_utc",
        "perf_counter_ns",
        "pid",
        "marker",
        "process_memory",
        "python_memory",
    }
)


def marker_reserved_keys(marker_helper) -> frozenset[str]:
    """Return signature and automatically generated keys that payloads may not own."""
    signature_keys = set(inspect.signature(marker_helper).parameters)
    return frozenset(signature_keys | set(AUTO_GENERATED_MARKER_KEYS))


def canonical_marker_payload(marker_helper, *sources: dict) -> dict:
    """Merge bounded payload sources once and reject reserved/conflicting keys."""
    reserved = marker_reserved_keys(marker_helper)
    merged: dict = {}
    for source in sources:
        if not isinstance(source, dict):
            raise TypeError("marker payload source must be an object")
        collisions = sorted(set(source) & set(reserved))
        if collisions:
            raise ValueError(f"reserved marker payload key collision: {', '.join(collisions)}")
        for key, value in source.items():
            if not isinstance(key, str) or not key:
                raise TypeError("marker payload keys must be nonempty strings")
            if key in merged and merged[key] != value:
                raise ValueError(f"conflicting canonical marker payload key: {key}")
            merged[key] = value
    return merged


def _python_memory_snapshot() -> dict:
    if not tracemalloc.is_tracing():
        return {"available": False}
    current, peak = tracemalloc.get_traced_memory()
    return {"available": True, "current_bytes": int(current), "peak_bytes": int(peak)}


def _append_resource_marker(path, marker, synchronous_memory=False, **values):
    """Append one fsync'd JSONL row after rejecting marker-owned payload keys."""
    if path is None:
        return
    canonical_values = canonical_marker_payload(_append_resource_marker, values)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "campfire.phase6et.resource-marker.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "perf_counter_ns": time.perf_counter_ns(),
        "pid": os.getpid(),
        "marker": marker,
        **canonical_values,
    }
    if synchronous_memory:
        payload["process_memory"] = process_memory_snapshot()
        payload["python_memory"] = _python_memory_snapshot()
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
