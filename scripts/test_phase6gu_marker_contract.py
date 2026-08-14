"""No-Kit fixtures for the Phase 6GU marker and save-only boundary."""

from __future__ import annotations

import ast
import json
import os
import tempfile
from pathlib import Path

from phase6gt_temporary_nvdb_contract import (
    MAXIMUM_FILE_BYTES,
    TEMPORARY_FILENAME,
    delete_exact_temporary,
    exact_temporary_path,
    poll_nonempty_file,
    require_absent,
)
from phase6gu_resource_marker import (
    AUTO_GENERATED_MARKER_KEYS,
    _append_resource_marker,
    canonical_marker_payload,
    marker_reserved_keys,
)


PHASE6GT_SOURCE_PAYLOAD = {
    "slot": 0,
    "channel": "temperature",
    "python_type": "numpy.ndarray",
    "ndim": 1,
    "shape": [11910336],
    "dtype": "uint32",
    "size": 11910336,
    "nbytes": 47641344,
    "empty": False,
    "temporary_file_path": "phase6gt_slot0_temperature_once.nvdb",
}


def rejected(function, text: str | None = None) -> bool:
    try:
        function()
    except (FileExistsError, RuntimeError, TypeError, ValueError, TimeoutError) as error:
        return text is None or text in str(error)
    return False


def main() -> int:
    cases: list[dict] = []

    def check(name: str, passed: bool, observed=None) -> None:
        cases.append({"name": name, "passed": bool(passed), "observed": observed})

    reserved = marker_reserved_keys(_append_resource_marker)
    check("signature_keys_reserved", {"path", "marker", "synchronous_memory", "values"} <= reserved, sorted(reserved))
    check("automatic_keys_reserved", AUTO_GENERATED_MARKER_KEYS <= reserved, sorted(reserved))
    canonical = canonical_marker_payload(_append_resource_marker, PHASE6GT_SOURCE_PAYLOAD)
    check("temporary_file_path_payload_valid", canonical == PHASE6GT_SOURCE_PAYLOAD, canonical)
    check("path_collision_rejected", rejected(lambda: canonical_marker_payload(_append_resource_marker, {"path": "x"}), "path"))
    check("other_signature_collision_rejected", rejected(lambda: canonical_marker_payload(_append_resource_marker, {"synchronous_memory": False}), "synchronous_memory"))
    check("marker_auto_collision_rejected", rejected(lambda: canonical_marker_payload(_append_resource_marker, {"marker": "x"}), "marker"))
    check("timestamp_auto_collision_rejected", rejected(lambda: canonical_marker_payload(_append_resource_marker, {"timestamp_utc": "x"}), "timestamp_utc"))
    same = canonical_marker_payload(_append_resource_marker, {"channel": "temperature"}, {"channel": "temperature"})
    check("duplicate_equal_canonicalized_once", same == {"channel": "temperature"}, same)
    check("duplicate_conflict_rejected", rejected(lambda: canonical_marker_payload(_append_resource_marker, {"channel": "temperature"}, {"channel": "fuel"}), "channel"))

    with tempfile.TemporaryDirectory(prefix="phase6gu-fixture-") as raw_root:
        root = Path(raw_root).resolve()
        marker_path = root / "actual_resource_markers.jsonl"
        marker_payload = dict(PHASE6GT_SOURCE_PAYLOAD)
        marker_payload["temporary_file_path"] = str(root / TEMPORARY_FILENAME)
        _append_resource_marker(marker_path, "phase6gu_fixture_marker", **marker_payload)
        rows = [json.loads(line) for line in marker_path.read_text(encoding="utf-8").splitlines()]
        check("actual_helper_writes_one_jsonl_row", len(rows) == 1, len(rows))
        check("temporary_file_path_persisted", rows[0].get("temporary_file_path") == marker_payload["temporary_file_path"], rows[0])
        check("legacy_path_not_persisted", "path" not in rows[0], sorted(rows[0]))

        temporary_path = exact_temporary_path(root)
        require_absent(temporary_path)
        outside = root.parent / TEMPORARY_FILENAME
        check("outside_artifact_path_rejected", rejected(lambda: delete_exact_temporary(outside, root)))
        temporary_path.touch()
        check("preexisting_file_rejected", rejected(lambda: require_absent(temporary_path)))
        temporary_path.unlink()
        temporary_path.touch()
        os.truncate(temporary_path, MAXIMUM_FILE_BYTES + 1)
        check("maximum_256_mib_enforced", rejected(lambda: poll_nonempty_file(temporary_path, timeout_seconds=0.1, interval_seconds=0.01)))
        temporary_path.unlink()
        temporary_path.touch()
        os.truncate(temporary_path, 4096)
        neighbor = root / "neighbor-must-survive.txt"
        neighbor.write_bytes(b"x")
        deletion = delete_exact_temporary(temporary_path, root)
        check("cleanup_exact_one_file", deletion["deleted"] and not temporary_path.exists(), deletion)
        check("cleanup_preserves_neighbor", neighbor.exists(), str(neighbor))

    probe_path = Path(__file__).with_name("probe_phase6gt_temporary_nvdb.py")
    source = probe_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(probe_path))
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)
            elif isinstance(node.func, ast.Name):
                calls.append(node.func.id)
    check("save_api_exactly_once_static", calls.count("save_volume") == 1, calls.count("save_volume"))
    check("content_read_hash_reload_zero_static", all(token not in source for token in ("read_bytes", "ReadAllBytes", "mmap", "hashlib", "load_volume")))
    check(
        "phase6gt_marker_uses_canonical_temporary_key",
        "temporary_file_path=str(TEMPORARY_PATH)" in source
        and "\n            path=str(TEMPORARY_PATH)" not in source,
    )

    passed = all(row["passed"] for row in cases)
    report = {
        "schema": "campfire.phase6gu.marker-contract-fixture.v1",
        "passed": passed,
        "case_count": len(cases),
        "kit_started": False,
        "actual_resource_marker_helper_called": True,
        "actual_phase6gt_payload_shape": PHASE6GT_SOURCE_PAYLOAD,
        "safe_stop_incremental_state": {
            "status": "safe_stop",
            "terminal": True,
            "operation_result": "fixture_safe_stop",
            "lifecycle_result": "not_started",
        },
        "cases": cases,
    }
    output = Path(os.environ["PHASE6GU_FIXTURE_REPORT"]) if os.environ.get("PHASE6GU_FIXTURE_REPORT") else None
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not passed:
        raise SystemExit(f"Phase 6GU fixtures failed: {[row['name'] for row in cases if not row['passed']]}")
    print(f"Phase 6GU marker fixtures passed: {len(cases)}/{len(cases)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
