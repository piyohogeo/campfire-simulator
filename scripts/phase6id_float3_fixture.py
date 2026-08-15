"""No-Kit fixture for the actual Phase 6ID canonical float3 validator."""

from __future__ import annotations

from __future__ import annotations

import json
import struct
from pathlib import Path

import phase6hw_stage_builder as stage_builder
import phase6ib_stage_authoring as authoring


class Vector3:
    """Small sequence wrapper used only to exercise representation independence."""
    def __init__(self, *values): self._values = values
    def __iter__(self): return iter(self._values)
    def __len__(self): return len(self._values)


def _f32(value: float) -> float:
    return struct.unpack(">f", struct.pack(">f", value))[0]


def _from_bits(bits: int) -> float:
    return struct.unpack(">f", struct.pack(">I", bits))[0]


def run_fixture(output_root: Path, frozen_path: Path) -> dict:
    if output_root.exists(): raise RuntimeError("Phase 6ID float3 fixture refuses root reuse")
    output_root.mkdir(parents=True)
    authoring.configure_repository_dependencies(stage_builder.topology)
    cases = []
    def case(name: str, expected, actual, accepted: bool, declared_type: str = "float3", budget: int = 0, reason: str | None = None):
        evidence = authoring.canonical_float3_evidence("/World/Flow/Emitter.position", declared_type, expected, actual, budget)
        passed = evidence["accepted"] is accepted and (reason is None or evidence["reason"] == reason)
        cases.append({"name":name,"passed":passed,"expected_acceptance":accepted,"evidence":evidence})

    source = [0.0, 0.0, 0.48]
    quantized = [0.0, 0.0, _f32(0.48)]
    case("source_list_to_vector", source, Vector3(*quantized), True)
    case("source_tuple_to_vector", tuple(source), Vector3(*quantized), True)
    case("positive_negative_values", [-1.25, 2.5, -3.75], Vector3(-1.25, 2.5, -3.75), True)
    case("signed_zero_equivalent", [0.0, -0.0, 0.0], Vector3(-0.0, 0.0, -0.0), True)
    case("exact_binary32", [0.5, 1.0, 2.0], Vector3(0.5, 1.0, 2.0), True)
    case("binary32_rounding", [0.1, 0.2, 0.3], Vector3(_f32(0.1), _f32(0.2), _f32(0.3)), True)
    case("zero_ulp_boundary", source, Vector3(*quantized), True, budget=0)
    case("component_count_two", source, Vector3(0.0, 0.0), False, reason="actual_component_count_invalid")
    case("component_count_four", source, Vector3(0.0, 0.0, _f32(0.48), 1.0), False, reason="actual_component_count_invalid")
    case("geometry_shift_one_mm", source, Vector3(0.0, 0.0, _f32(0.481)), False, reason="float3_ulp_budget_exceeded")
    expected_bit = struct.unpack(">I", struct.pack(">f", _f32(0.48)))[0]
    case("one_ulp_exceeds_zero_budget", source, Vector3(0.0, 0.0, _from_bits(expected_bit + 1)), False, reason="float3_ulp_budget_exceeded")
    case("nan_rejected", source, Vector3(0.0, 0.0, float("nan")), False, reason="actual_component_nonfinite")
    case("positive_inf_rejected", source, Vector3(0.0, 0.0, float("inf")), False, reason="actual_component_nonfinite")
    case("negative_inf_rejected", source, Vector3(0.0, 0.0, float("-inf")), False, reason="actual_component_nonfinite")
    case("string_rejected", source, Vector3(0.0, 0.0, "0.48"), False, reason="actual_component_type_invalid")
    case("bool_rejected", source, Vector3(0.0, False, _f32(0.48)), False, reason="actual_component_type_invalid")
    case("nested_rejected", source, Vector3(0.0, [0.0], _f32(0.48)), False, reason="actual_component_type_invalid")
    case("declared_type_rejected", source, Vector3(*quantized), False, declared_type="double3", reason="declared_type_not_float3")
    case("actual_missing", source, None, False, reason="actual_missing")
    case("expected_missing", None, Vector3(*quantized), False, reason="expected_missing")
    case("budget_type_invalid", source, Vector3(*quantized), False, budget=True, reason="ulp_budget_invalid")

    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    spec = authoring.stage_spec(frozen, "collision_off")
    cases.append({"name":"frozen_source_unchanged","passed":spec["scene"]["source_center_m"] == source,"value":spec["scene"]["source_center_m"]})
    report = {
        "schema":"campfire.phase6id.float3-fixture.v1","phase":"phase6id",
        "status":"qualified" if all(item["passed"] for item in cases) else "failed",
        "kit_launch_count":0,"case_count":[sum(item["passed"] for item in cases),len(cases)],
        "ulp_budget":authoring.FLOAT3_ULP_BUDGET,"signed_zero_policy":"equivalent","cases":cases,
    }
    (output_root / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    return report
