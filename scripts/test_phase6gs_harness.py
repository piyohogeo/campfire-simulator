"""No-Kit child-side and fixture-emission tests for Phase 6GS."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

from phase6gs_harness_contract import ACCESSORS, canonical_source_marker_payload


SOURCE = {
    "slot": 0,
    "channel": "temperature",
    "python_type": "numpy.ndarray",
    "ndim": 1,
    "shape": [11910336],
    "dtype": "uint32",
    "size": 11910336,
    "nbytes": 47641344,
    "empty": False,
}


def emit_parent_fixtures(path: Path) -> None:
    payload = {
        "schema": "campfire.phase6gs.parent-input-fixtures.v1",
        "source_metadata": SOURCE,
        "marker": {
            "positive": canonical_source_marker_payload(dict(SOURCE)),
            "duplicate_same_value": canonical_source_marker_payload(dict(SOURCE), canonical_channel="temperature"),
            "conflicting_rejected": True,
        },
        "operations": {
            "normal_string": {"last_successful_accessor": "get_grid_class"},
            "explicit_null": {"last_successful_accessor": None},
            "empty_string": {"last_successful_accessor": "   "},
            "missing": {"operation_result": "metadata_accessor_failure"},
            "invalid_type": {"last_successful_accessor": ["get_grid_class"]},
            "phase6gr_zero": {
                "operation_result": "metadata_accessor_failure",
                "accessor_calls": {name: 0 for name in ACCESSORS},
            },
            "partial": {
                "operation_result": "metadata_accessor_failure",
                "last_successful_accessor": "get_grid_type",
                "accessor_calls": {name: int(index < 2) for index, name in enumerate(ACCESSORS)},
            },
            "complete": {
                "operation_result": "pass",
                "last_successful_accessor": "get_world_bounding_box",
                "accessor_calls": {name: 1 for name in ACCESSORS},
            },
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--emit-parent-fixtures", type=Path)
    args = parser.parse_args()
    positive = canonical_source_marker_payload(dict(SOURCE))
    duplicate = canonical_source_marker_payload(dict(SOURCE), canonical_channel="temperature")
    conflict_rejected = False
    try:
        canonical_source_marker_payload(dict(SOURCE, channel="fuel"), canonical_channel="temperature")
    except ValueError:
        conflict_rejected = True
    checks = [
        positive == SOURCE,
        list(positive).count("channel") == 1,
        duplicate == SOURCE,
        list(duplicate).count("channel") == 1,
        conflict_rejected,
        positive["shape"] == [11910336],
        positive["nbytes"] == 47641344,
    ]
    probe_path = Path(__file__).with_name("probe_phase6gs_volume_metadata.py")
    if probe_path.exists():
        source = probe_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(probe_path))
        calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    calls.append(node.func.attr)
                elif isinstance(node.func, ast.Name):
                    calls.append(node.func.id)
        checks.extend([
            calls.count("get_latest_nanovdb_readback") == 1,
            calls.count("buffer_to_volume") == 1,
            "canonical_source_marker_payload" in calls,
            all(source.count(f".{name}(") == 1 for name in ACCESSORS),
            "_volume_metadata" not in calls,
            "save_volume" not in calls,
            "asarray" not in calls,
        ])
    if not all(checks):
        raise SystemExit(f"Phase 6GS child harness fixture failed: {[i for i, ok in enumerate(checks, 1) if not ok]}")
    if args.emit_parent_fixtures:
        emit_parent_fixtures(args.emit_parent_fixtures)
    print(f"Phase 6GS child harness fixtures passed: {len(checks)}/{len(checks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
