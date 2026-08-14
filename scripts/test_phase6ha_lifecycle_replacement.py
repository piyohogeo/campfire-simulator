"""No-Kit Phase 6HA replacement and operation-boundary fixtures."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from phase6ha_lifecycle_replacement_contract import (
    REQUIRED_LIFECYCLE_MARKERS, REQUIRED_OPERATION_MARKERS, classify_attempt, population_decision,
)

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "scripts/probe_phase6ha_temperature_volume.py"
CONTRACT = ROOT / "scripts/phase6ha_temperature_volume_contract.json"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def valid_evidence(**updates) -> dict:
    value = {
        "markers": sorted(REQUIRED_OPERATION_MARKERS | REQUIRED_LIFECYCLE_MARKERS),
        "operation_result": "pass",
        "temperature_conversion_calls": 1,
        "forbidden_content_access_calls": 0,
        "resource_pass": True,
        "temporary_cleanup_pass": True,
        "process_cleanup_pass": True,
        "residual_process_count": 0,
        "python_exception": False,
        "native_exception": False,
        "cleanup_failure": False,
        "natural_os_exit": True,
        "process_exit_code": 0,
        "raw_classification": "normal_exit",
        "last_lifecycle_marker": "shutdown_complete",
    }
    value.update(updates)
    return value


def main() -> int:
    cases = []

    def check(name: str, evidence: dict, classification: str, replacement: bool) -> None:
        result = classify_attempt(evidence)
        require(result["classification"] == classification, f"{name}: {result}")
        require(result["replacement_allowed"] is replacement, f"{name}: replacement")
        cases.append({"name": name, "result": result})

    check("normal_exit", valid_evidence(), "qualified_normal_exit", False)
    check("post_shutdown_os_exit_only", valid_evidence(
        natural_os_exit=False, process_exit_code=None, raw_classification="os_exit_timeout"),
        "replaceable_post_shutdown_os_exit_failure", True)
    check("operation_failure", valid_evidence(operation_result="failure"), "nonreplaceable_failure", False)
    missing = set(REQUIRED_OPERATION_MARKERS | REQUIRED_LIFECYCLE_MARKERS) - {"phase6ha_operation_complete"}
    check("operation_marker_missing", valid_evidence(markers=sorted(missing)), "nonreplaceable_failure", False)
    missing = set(REQUIRED_OPERATION_MARKERS | REQUIRED_LIFECYCLE_MARKERS) - {"shutdown_complete"}
    check("shutdown_marker_missing", valid_evidence(markers=sorted(missing)), "nonreplaceable_failure", False)
    check("resource_failure", valid_evidence(resource_pass=False), "nonreplaceable_failure", False)
    check("temporary_cleanup_failure", valid_evidence(temporary_cleanup_pass=False), "nonreplaceable_failure", False)
    check("process_cleanup_failure", valid_evidence(process_cleanup_pass=False), "nonreplaceable_failure", False)
    check("native_exception", valid_evidence(native_exception=True, natural_os_exit=False,
        process_exit_code=3221225477, raw_classification="windows_native_exception"), "nonreplaceable_failure", False)
    check("python_exception", valid_evidence(python_exception=True, natural_os_exit=False,
        process_exit_code=1, raw_classification="operation_failure"), "nonreplaceable_failure", False)
    check("wrong_conversion_count", valid_evidence(temperature_conversion_calls=0), "nonreplaceable_failure", False)
    check("forbidden_content_access", valid_evidence(forbidden_content_access_calls=1), "nonreplaceable_failure", False)

    lifecycle_only = classify_attempt(valid_evidence(
        natural_os_exit=False, process_exit_code=None, raw_classification="os_exit_timeout"))
    require(population_decision([lifecycle_only])["action"] == "launch_single_replacement", "one replacement")
    require(population_decision([lifecycle_only, lifecycle_only])["action"] == "stop_safe", "second failure stops")
    normal = classify_attempt(valid_evidence())
    require(population_decision([normal])["action"] == "stop_qualified", "normal qualifies")
    require(population_decision([lifecycle_only, normal])["qualified"], "replacement may qualify")

    source = PROBE.read_text(encoding="utf-8")
    ast.parse(source)
    for token in (
        "phase6ha_temperature_conversion_before", "phase6ha_temperature_conversion_after",
        "phase6ha_volume_release_before", "phase6ha_volume_release_after",
        "phase6ha_handles_release_before", "phase6ha_handles_release_after", "phase6ha_operation_complete",
    ):
        require(token in source, f"missing marker {token}")
    for forbidden in ("_bounded_temperature_volume_metadata(", "save_volume(temperature", "np.asarray(",
                      "phase6ha_temperature_sampling_before", "phase6ha_temperature_collector_before"):
        require(forbidden not in source, f"forbidden temperature operation: {forbidden}")
    require(source.count("temperature_volume = flow.buffer_to_volume(source)") == 1, "one temperature conversion site")
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    require(contract["replacement"]["maximum_replacements"] == 1, "replacement budget")
    require(contract["replacement"]["maximum_launches"] == 2, "launch budget")
    require(contract["phase6gz"]["frozen"] and not contract["phase6gz"]["reclassified"], "GZ frozen")
    print(json.dumps({"passed": True, "cases": len(cases) + 15, "kit_started": False,
                      "classifications": cases}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
