"""No-Kit fixtures for the Phase 6GR bounded public metadata boundary."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from phase6gr_volume_metadata_contract import ACCESSORS, bounded_public_value, classify, validate_qualified_temperature_slot


def main() -> int:
    here = Path(__file__).resolve().parent
    root = here.parent
    contract = json.loads((here / "phase6gr_volume_metadata_contract.json").read_text(encoding="utf-8"))
    schema = json.loads((here / "phase6gh_public_channel_schema_candidate.json").read_text(encoding="utf-8"))
    qualification = json.loads((root / "docs/devlog/assets/phase6/phase6gk_public_channel_preflight_qualified.json").read_text(encoding="utf-8"))
    checks = []
    mapping = validate_qualified_temperature_slot(schema, qualification)
    checks.extend([mapping["pass"], mapping["slot"] == 0, mapping["channel"] == "temperature"])
    wrong_qualification = json.loads(json.dumps(qualification))
    wrong_qualification["public_channel_schema"]["handles"][0]["channel"] = "fuel"
    checks.append(not validate_qualified_temperature_slot(schema, wrong_qualification)["pass"])
    checks.extend([
        bounded_public_value((1, 2, 3)) == [1, 2, 3],
        bounded_public_value("Flow") == "Flow",
        classify(True, True, True)["classification"] == "qualified",
        classify(True, True, False)["operation_result"] == "partial_operation_evidence",
        classify(False, False, True)["operation_result"] == "metadata_accessor_failure",
        contract["selected_slot"] == 0,
        contract["selected_channel"] == "temperature",
        contract["volume_metadata"]["accessors_in_exact_order"] == list(ACCESSORS),
        contract["volume_metadata"]["selected_grid_index"] == 0,
        contract["volume_metadata"]["maximum_grid_count"] == 4,
        contract["population"]["maximum_launches"] == 1,
        contract["scope"]["later_operations_authorized"] is False,
        contract["lifecycle"]["low_level_diagnostic_allowed"] is False,
    ])
    try:
        bounded_public_value(list(range(17)))
        checks.append(False)
    except ValueError:
        checks.append(True)

    probe_path = here / "probe_phase6gr_volume_metadata.py"
    source = probe_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(probe_path))
    call_names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                call_names.append(node.func.attr)
            elif isinstance(node.func, ast.Name):
                call_names.append(node.func.id)
    checks.extend([
        call_names.count("get_latest_nanovdb_readback") == 1,
        call_names.count("buffer_to_volume") == 1,
        all(name in source for name in ACCESSORS),
        "_volume_metadata" not in call_names,
        "save_volume" not in call_names,
        "asarray" not in call_names,
        "_save_and_sample" not in call_names,
        "temporary NanoVDB" not in source,
    ])
    if not all(checks):
        failed = [index for index, passed in enumerate(checks, start=1) if not passed]
        raise SystemExit(f"Phase 6GR offline fixture failed checks: {failed}")
    print(f"Phase 6GR offline fixtures passed: {len(checks)}/{len(checks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
