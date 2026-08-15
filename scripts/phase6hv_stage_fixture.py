"""No-Kit generated-USD/settings fixture for Phase 6HV."""

from __future__ import annotations

import difflib
import json
from pathlib import Path

from phase6hv_stage_contract import TOKEN_OFF, TOKEN_ON, validate_stage, validate_stage_bytes


def _case(cases: list[dict], name: str, passed: bool, **evidence) -> None:
    cases.append({"name": name, "passed": bool(passed), **evidence})


def _rejected(data: bytes, contract: dict, condition: str) -> tuple[bool, str | None]:
    try:
        result = validate_stage_bytes(data, contract, condition)
        return not result["passed"], None
    except (ValueError, KeyError) as error:
        return True, f"{type(error).__name__}: {error}"


def run_fixture(output_root: Path, contract_path: Path, reference_off_stage: Path) -> dict:
    if output_root.exists():
        raise RuntimeError("Phase 6HV stage fixture refuses root reuse")
    output_root.mkdir(parents=True)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    source = reference_off_stage.read_bytes()
    if source.count(TOKEN_OFF) != 1 or source.count(TOKEN_ON) != 0:
        raise RuntimeError("Phase 6HU stage reference collision token mismatch")
    generated = output_root / "generated_usd"
    generated.mkdir()
    off_path = generated / "collision_off.usda"
    on_path = generated / "collision_on.usda"
    off_path.write_bytes(source)
    on_path.write_bytes(source.replace(TOKEN_OFF, TOKEN_ON))
    cases: list[dict] = []
    off = validate_stage(off_path, contract, "collision_off")
    on = validate_stage(on_path, contract, "collision_on")
    _case(cases, "generated_collision_off_exact", off["passed"], validation=off)
    _case(cases, "generated_collision_on_exact", on["passed"], validation=on)
    changes = [line for line in difflib.ndiff(off_path.read_text(encoding="utf-8").splitlines(), on_path.read_text(encoding="utf-8").splitlines()) if line.startswith(("- ", "+ "))]
    _case(cases, "one_variable_usd_diff", len(changes) == 2 and all("physicsCollisionEnabled" in line for line in changes), changed_lines=changes)
    _case(cases, "common_stage_digest_equal", off["evidence"]["normalized_common_stage_sha256"] == on["evidence"]["normalized_common_stage_sha256"] == contract["stage_authoring"]["normalized_common_stage_sha256"])
    _case(cases, "settings_common_digest_equal", off["evidence"]["settings_common_sha256"] == on["evidence"]["settings_common_sha256"] == contract["stage_authoring"]["settings_common_sha256"])
    _case(cases, "settings_condition_digests_distinct", off["evidence"]["settings_sha256"] != on["evidence"]["settings_sha256"])
    wrong_condition = validate_stage_bytes(source, contract, "collision_on")
    _case(cases, "wrong_condition_rejected", not wrong_condition["passed"], validation=wrong_condition)
    rejected, reason = _rejected(source.replace(TOKEN_OFF, b"bool unrelated = 0"), contract, "collision_off")
    _case(cases, "missing_collision_attribute_rejected", rejected, reason=reason)
    rejected, reason = _rejected(source + b"\n" + TOKEN_OFF + b"\n", contract, "collision_off")
    _case(cases, "duplicate_collision_attribute_rejected", rejected, reason=reason)
    mutation = source.replace(b"float radius = 0.2", b"float radius = 0.21")
    mutated = validate_stage_bytes(mutation, contract, "collision_off")
    _case(cases, "non_collision_stage_mutation_rejected", not mutated["passed"], validation=mutated)
    _case(cases, "bounded_fixture_files", all(path.stat().st_size < 1024 * 1024 for path in generated.iterdir()))
    report = {
        "schema": "campfire.phase6hv.stage-authoring-fixture.v1",
        "phase": "phase6hv",
        "status": "qualified" if all(case["passed"] for case in cases) else "failed",
        "kit_launch_count": 0,
        "reference_stage": str(reference_off_stage),
        "reference_use": "authoring fixture only; not reused as a formal OFF runtime result",
        "generated_usd": {"collision_off": str(off_path), "collision_on": str(on_path)},
        "cases": cases,
    }
    (output_root / "stage_fixture_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
