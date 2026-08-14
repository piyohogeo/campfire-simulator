"""No-Kit fixtures for the Phase 6GQ single conversion boundary."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from phase6gq_temperature_volume_contract import classify, validate_temperature_slot


def main() -> int:
    here = Path(__file__).resolve().parent
    contract = json.loads((here / "phase6gq_temperature_volume_contract.json").read_text(encoding="utf-8"))
    schema = json.loads((here / "phase6gh_public_channel_schema_candidate.json").read_text(encoding="utf-8"))
    checks = []
    mapping = validate_temperature_slot(schema)
    checks.extend([mapping["pass"], mapping["slot"] == 0, mapping["channel"] == "temperature"])
    wrong = {"handles": [dict(schema["handles"][0], channel="fuel")]}
    checks.append(not validate_temperature_slot(wrong)["pass"])
    missing = {"handles": [row for row in schema["handles"] if row["index"] != 0]}
    checks.append(not validate_temperature_slot(missing)["pass"])
    checks.append(classify(True, True, True)["classification"] == "qualified")
    checks.append(classify(True, True, False)["operation_result"] == "partial_operation_evidence")
    checks.append(classify(False, False, True)["operation_result"] == "conversion_boundary_failure")
    checks.extend([
        contract["selected_slot"] == 0,
        contract["selected_channel"] == "temperature",
        contract["population"]["maximum_launches"] == 1,
        contract["scope"]["later_operations_authorized"] is False,
        contract["lifecycle"]["low_level_diagnostic_allowed"] is False,
    ])

    probe_path = here / "probe_phase6gq_temperature_volume.py"
    tree = ast.parse(probe_path.read_text(encoding="utf-8"), filename=str(probe_path))
    call_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                call_names.add(node.func.attr)
            elif isinstance(node.func, ast.Name):
                call_names.add(node.func.id)
    checks.extend([
        "get_latest_nanovdb_readback" in call_names,
        "buffer_to_volume" in call_names,
        "asarray" not in call_names,
        "_volume_metadata" not in call_names,
        "save_volume" not in call_names,
        "_save_and_sample" not in call_names,
    ])
    if not all(checks):
        raise SystemExit("Phase 6GQ offline fixture failed")
    print(f"Phase 6GQ offline fixtures passed: {len(checks)}/{len(checks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
