"""Derive the Phase 6HV two-condition probe from qualified Phase 6HU."""

from __future__ import annotations

from pathlib import Path

from phase6hu_probe_source import build_probe_source as build_phase6hu_source


def build_probe_source(source_path: Path) -> str:
    source = build_phase6hu_source(source_path)
    replacements = (
        (
            "from phase6hu_runtime_report import DurableOperationReporter",
            "from phase6hu_runtime_report import DurableOperationReporter\nfrom phase6hv_stage_contract import validate_stage",
        ),
        (
            '    condition = "collision_off"\n    collision_enabled = False',
            '    condition = settings.get_as_string("/phase6hv/condition")\n    if condition not in ("collision_off", "collision_on"):\n        raise RuntimeError("Phase 6HV condition invalid")\n    collision_enabled = condition == "collision_on"',
        ),
        (
            '        "diagnostic_phase": "phase6hu",',
            '        "diagnostic_phase": "phase6hv",',
        ),
        (
            '        if not all(gates.values()):\n            raise RuntimeError(f"Offline hierarchy gate failed: {gates}")\n        del baseline, candidate',
            '        if not all(gates.values()):\n            raise RuntimeError(f"Offline hierarchy gate failed: {gates}")\n        contract_path = Path(settings.get_as_string("/phase6hv/contract")).resolve()\n        contract = json.loads(contract_path.read_text(encoding="utf-8"))\n        stage_contract = validate_stage(stage_dir / "candidate.usda", contract, condition)\n        report["stage_contract"] = stage_contract\n        mark("stage_contract_complete", condition=condition, passed=stage_contract["passed"], stage_sha256=stage_contract["evidence"]["stage_sha256"], settings_sha256=stage_contract["evidence"]["settings_sha256"])\n        if not stage_contract["passed"]:\n            raise RuntimeError(f"Phase 6HV stage contract failed: {stage_contract[\'gates\']}")\n        del baseline, candidate',
        ),
    )
    for before, after in replacements:
        if source.count(before) != 1:
            raise RuntimeError("Phase 6HV probe replacement cardinality mismatch")
        source = source.replace(before, after)
    return source
