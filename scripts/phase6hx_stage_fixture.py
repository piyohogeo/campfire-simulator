"""No-Kit generated-stage fixture for Phase 6HX."""

from __future__ import annotations

import difflib
import json
from pathlib import Path

from phase6hx_stage_builder import TOKEN_OFF, TOKEN_ON, write_stage
from phase6hx_stage_contract import validate_stage, validate_stage_bytes


def _case(cases: list[dict], name: str, passed: bool, **evidence) -> None:
    cases.append({"name": name, "passed": bool(passed), **evidence})


def _rejected(data: bytes, contract: dict, condition: str) -> tuple[bool, str | None]:
    try:
        return not validate_stage_bytes(data, contract, condition)["passed"], None
    except (ValueError, KeyError) as error:
        return True, f"{type(error).__name__}: {error}"


def run_fixture(output_root: Path, contract_path: Path) -> dict:
    if output_root.exists():
        raise RuntimeError("Phase 6HX stage fixture refuses root reuse")
    output_root.mkdir(parents=True)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    generated = output_root / "generated_usd"
    generated.mkdir()
    off_path, on_path = generated / "collision_off.usda", generated / "collision_on.usda"
    write_stage(off_path, contract, "collision_off")
    write_stage(on_path, contract, "collision_on")
    off, on = validate_stage(off_path, contract, "collision_off"), validate_stage(on_path, contract, "collision_on")
    cases: list[dict] = []
    _case(cases, "generated_collision_off_exact", off["passed"], validation=off)
    _case(cases, "generated_collision_on_exact", on["passed"], validation=on)
    changes = [line for line in difflib.ndiff(off_path.read_text(encoding="utf-8").splitlines(), on_path.read_text(encoding="utf-8").splitlines()) if line.startswith(("- ", "+ "))]
    _case(cases, "one_variable_usd_diff", len(changes) == 2 and all("physicsCollisionEnabled" in line for line in changes), changed_lines=changes)
    _case(cases, "normalized_stage_identity", off["evidence"]["normalized_common_stage_sha256"] == on["evidence"]["normalized_common_stage_sha256"] == contract["stage_authoring"]["normalized_common_stage_sha256"])
    _case(cases, "settings_common_identity", off["evidence"]["settings_common_sha256"] == on["evidence"]["settings_common_sha256"] == contract["stage_authoring"]["settings_common_sha256"])
    _case(cases, "phase_identity", off["gates"]["independent_phase_identity"] and on["gates"]["independent_phase_identity"])
    wrong = validate_stage_bytes(off_path.read_bytes(), contract, "collision_on")
    _case(cases, "wrong_condition_rejected", not wrong["passed"])
    rejected, reason = _rejected(off_path.read_bytes().replace(TOKEN_OFF, b"bool unrelated = 0"), contract, "collision_off")
    _case(cases, "missing_collision_attribute_rejected", rejected, reason=reason)
    rejected, reason = _rejected(off_path.read_bytes() + b"\n" + TOKEN_OFF + b"\n", contract, "collision_off")
    _case(cases, "duplicate_collision_attribute_rejected", rejected, reason=reason)
    mutation = validate_stage_bytes(off_path.read_bytes().replace(b"float radius = 0.2", b"float radius = 0.21"), contract, "collision_off")
    _case(cases, "non_collision_mutation_rejected", not mutation["passed"])
    _case(cases, "bounded_fixture_files", all(path.stat().st_size < 1024 * 1024 for path in generated.iterdir()))
    report = {"schema": "campfire.phase6hx.stage-authoring-fixture.v1", "phase": "phase6hx", "status": "qualified" if all(case["passed"] for case in cases) else "failed", "kit_launch_count": 0, "cases": cases}
    (output_root / "stage_fixture_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
