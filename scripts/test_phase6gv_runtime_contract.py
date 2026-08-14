"""No-Kit qualification for every Phase 6GV marker family and fixed path."""

from __future__ import annotations

import ast
import json
import os
import tempfile
from pathlib import Path

from phase6gu_resource_marker import _append_resource_marker, canonical_marker_payload, marker_reserved_keys
from phase6gv_runtime_contract import CANONICAL_TEMPORARY_FILENAME, canonical_temporary_path


SCRIPTS = Path(__file__).resolve().parent
RUNTIME_FILES = (
    "probe_phase6gc_shared_supply_comparison.py",
    "probe_phase6gs_volume_metadata.py",
    "probe_phase6gl_supply_comparison.py",
    "probe_phase6gn_supply_comparison.py",
    "probe_phase6gt_temporary_nvdb.py",
)

FULL_PAYLOADS = {
    "startup": {"frame": 60, "sample_perf_counter_ns": 1, "timeline_time": 1.0,
                "kit_update_number": 120, "active_blocks": 128, "timeline_playing": True,
                "point_payload_revision": 1, "point_count": 1440, "active_point_count": 1344,
                "fuel_sum": 1075.2000160217285, "temperature_sum": 2688.0,
                "smoke_sum": 107.51999899744987},
    "readback": {"frame": 180, "active_blocks": 900, "returned_channel_count": 7,
                 "operation_state": "readback_complete"},
    "conversion": {"frame": 180, "active_blocks": 900, "slot": 0,
                   "channel": "temperature", "volume_conversion_calls": 1},
    "metadata": {"frame": 180, "active_blocks": 900, "accessor": "get_num_grids",
                 "grid_count": 1, "metadata_complete": True},
    "save": {"frame": 180, "active_blocks": 900, "temporary_file_path": CANONICAL_TEMPORARY_FILENAME,
             "save_volume_calls": 1, "file_size_bytes": 4096},
    "release": {"frame": 180, "active_blocks": 900, "weak_reference_alive_count": 0,
                "ownership_residual": 0},
    "shutdown": {"timeline_playing": False, "stage_identity": None, "flow_reference_alive": False,
                 "volume_reference_alive": False, "emitter_reference_alive": False,
                 "collector_count": 0},
}


def _explicit_payload_collisions(path: Path, reserved: set[str]) -> list[dict]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else (
            node.func.attr if isinstance(node.func, ast.Attribute) else "")
        if name not in {"mark", "marker", "_append_resource_marker"}:
            continue
        keys = {kw.arg for kw in node.keywords if kw.arg}
        if name == "_append_resource_marker":
            keys -= {"synchronous_memory"}
        collision = sorted(keys & reserved)
        if collision:
            found.append({"line": node.lineno, "call": name, "keys": collision})
    return found


def main() -> int:
    cases = []
    def check(name, passed, observed=None):
        cases.append({"name": name, "passed": bool(passed), "observed": observed})

    reserved = set(marker_reserved_keys(_append_resource_marker))
    for family, payload in FULL_PAYLOADS.items():
        try:
            canonical = canonical_marker_payload(_append_resource_marker, payload)
            ok = canonical == payload
            observed = sorted(canonical)
        except Exception as exc:  # fixture records fail-closed diagnostics
            ok, observed = False, str(exc)
        check(f"complete_{family}_payload", ok, observed)

    for filename in RUNTIME_FILES:
        collisions = _explicit_payload_collisions(SCRIPTS / filename, reserved)
        check(f"static_reserved_keys_{filename}", not collisions, collisions)

    check("old_perf_counter_key_absent",
          '"perf_counter_ns": int(time.perf_counter_ns())' not in
          (SCRIPTS / "probe_phase6gc_shared_supply_comparison.py").read_text(encoding="utf-8"))
    check("sample_perf_counter_key_present",
          '"sample_perf_counter_ns": int(time.perf_counter_ns())' in
          (SCRIPTS / "probe_phase6gc_shared_supply_comparison.py").read_text(encoding="utf-8"))
    try:
        canonical_marker_payload(_append_resource_marker, {"perf_counter_ns": 1})
        collision_rejected = False
    except ValueError:
        collision_rejected = True
    check("reserved_perf_counter_rejected", collision_rejected)

    probe_text = (SCRIPTS / "probe_phase6gt_temporary_nvdb.py").read_text(encoding="utf-8")
    check("probe_uses_canonical_path_definition", "canonical_temporary_path(REPORT_PATH.parent)" in probe_text)
    check("phase_named_filename_not_in_probe", "phase6gt_slot0_temperature_once.nvdb" not in probe_text)
    with tempfile.TemporaryDirectory(prefix="phase6gv-path-") as raw:
        root = Path(raw).resolve()
        exact = canonical_temporary_path(root)
        check("canonical_filename_exact", exact.name == CANONICAL_TEMPORARY_FILENAME, str(exact))
        try:
            canonical_temporary_path(root / "..")
            inside = True  # a different artifact root is legal; only resolved child is returned
        except ValueError:
            inside = False
        check("canonical_path_is_direct_child", exact.parent == root, str(exact.parent))

        marker_path = root / "markers.jsonl"
        for family, payload in FULL_PAYLOADS.items():
            _append_resource_marker(marker_path, f"fixture_{family}", **payload)
        rows = [json.loads(line) for line in marker_path.read_text(encoding="utf-8").splitlines()]
        check("actual_helper_all_families", len(rows) == len(FULL_PAYLOADS), len(rows))
        check("actual_helper_marker_order", [r["marker"] for r in rows] ==
              [f"fixture_{name}" for name in FULL_PAYLOADS], [r["marker"] for r in rows])

    passed = all(case["passed"] for case in cases)
    report = {"schema": "campfire.phase6gv.runtime-contract-fixture.v1", "passed": passed,
              "case_count": len(cases), "kit_started": False,
              "canonical_temporary_filename": CANONICAL_TEMPORARY_FILENAME,
              "reserved_keys": sorted(reserved), "cases": cases}
    output = Path(os.environ.get("PHASE6GV_FIXTURE_REPORT", "phase6gv_fixture_report.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not passed:
        raise SystemExit([case["name"] for case in cases if not case["passed"]])
    print(f"Phase 6GV runtime fixtures passed: {len(cases)}/{len(cases)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
