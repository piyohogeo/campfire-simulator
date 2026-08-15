"""No-Kit end-to-end fixture for the real Phase 6HZ marker producer/helper."""

from __future__ import annotations

import json
from pathlib import Path

import phase6hz_exact_kit_import as exact
import phase6hz_marker_contract as marker_contract


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
WRAPPER = SCRIPTS / "probe_phase6hz_import_smoke.py"
CONTRACT = SCRIPTS / "phase6hz_import_smoke_contract.json"
SIDECAR = SCRIPTS / "phase6hz_import_smoke_contract.sha256"


def _case(name: str, expected: str, action) -> dict:
    try:
        evidence = action()
        observed = "pass"
    except Exception as error:
        evidence = {"error": f"{type(error).__name__}: {error}"}
        observed = str(error)
    passed = observed == "pass" if expected == "pass" else expected in observed
    return {"name": name, "expected": expected, "observed": observed, "passed": passed, "evidence": evidence}


def _round_trip(root: Path) -> dict:
    marker_file = root / "actual-wrapper-markers.jsonl"
    events = marker_contract.representative_wrapper_events(ROOT)
    records = [marker_contract.append_marker(marker_file, name, payload) for name, payload in events]
    rows = [json.loads(line) for line in marker_file.read_text(encoding="utf-8").splitlines()]
    expected_names = list(marker_contract.EVENT_FIELDS)
    if [row["marker"] for row in rows] != expected_names or records != rows:
        raise RuntimeError("actual_producer_marker_round_trip_mismatch")
    if any("path" in row for row in rows):
        raise RuntimeError("legacy_path_payload_persisted")
    return {"event_count": len(rows), "marker_names": expected_names, "jsonl_size": marker_file.stat().st_size}


def run_fixture(output_root: Path) -> dict:
    if output_root.exists():
        raise RuntimeError("Phase 6HZ marker fixture refuses root reuse")
    output_root.mkdir(parents=True)
    policy, boundary = exact.read_contract(WRAPPER, CONTRACT, SIDECAR)
    probe = policy["sources"]["probe_builder"]
    module, audit = exact.load_exact_module(
        ROOT / probe["path"], SCRIPTS, probe["sha256"], "phase6hz_fixture_probe_exact", probe["required_callables"]
    )
    cases = [
        _case("actual_wrapper_payloads_end_to_end", "pass", lambda: _round_trip(output_root)),
        _case("normal_resolved_path_payload", "pass", lambda: marker_contract.canonical_payload("probe_resolution_complete", [{"module_path": str(SCRIPTS / "phase6hy_probe_source.py")}])) ,
        _case("legacy_path_reserved_collision", "reserved_marker_key_collision:path", lambda: marker_contract.canonical_payload("kit_app_ready", [{"attempt_id": "x", "path": "legacy"}])),
        _case("helper_argument_reserved_collision", "reserved_marker_key_collision:marker_file", lambda: marker_contract.canonical_payload("kit_app_ready", [{"attempt_id": "x", "marker_file": "wrong"}])),
        _case("automatic_marker_reserved_collision", "reserved_marker_key_collision:marker", lambda: marker_contract.canonical_payload("kit_app_ready", [{"attempt_id": "x", "marker": "wrong"}])),
        _case("required_key_missing", "required_marker_key_missing:attempt_id", lambda: marker_contract.canonical_payload("kit_app_ready", [{}])),
        _case("duplicate_same_value", "duplicate_marker_key:attempt_id", lambda: marker_contract.canonical_payload("kit_app_ready", [{"attempt_id": "x"}, {"attempt_id": "x"}])),
        _case("duplicate_conflicting_value", "conflicting_marker_value:attempt_id", lambda: marker_contract.canonical_payload("kit_app_ready", [{"attempt_id": "x"}, {"attempt_id": "y"}])),
        _case("invalid_type", "marker_payload_type_invalid:attempt_id", lambda: marker_contract.canonical_payload("kit_app_ready", [{"attempt_id": 1}])),
        _case("unknown_payload_key", "unknown_marker_payload_key:extra", lambda: marker_contract.canonical_payload("kit_app_ready", [{"attempt_id": "x", "extra": True}])),
        _case("actual_repository_exact_loader", "pass", lambda: {"boundary": boundary, "audit": audit, "callable": callable(module.build_probe_source)}),
    ]
    report = {
        "schema": "campfire.phase6hz.marker-fixture.v1",
        "phase": "phase6hz",
        "status": "qualified" if all(case["passed"] for case in cases) else "failed",
        "case_count": len(cases),
        "kit_launch_count": 0,
        "reserved_keys": sorted(marker_contract.RESERVED_KEYS),
        "actual_wrapper_event_count": len(marker_contract.EVENT_FIELDS),
        "cases": cases,
        "contract_sha256": exact.sha256_file(CONTRACT),
    }
    (output_root / "fixture_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report

