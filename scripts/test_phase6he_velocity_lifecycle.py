"""No-Kit producer/consumer and velocity-path fixture for Phase 6HE."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from phase6he_operation_schema import (
    CONDITIONS,
    COUNTER_KEYS,
    complete_operation,
    expected_counts,
    increment_counter,
    new_counter_values,
    new_runtime_report,
    validate_operation_files,
    write_operation_report,
)
from run_phase6he_velocity_lifecycle import build_command


def produce_report(root: Path, condition: str) -> Path:
    report = new_runtime_report(condition=condition, attempt_id=condition)
    for key, value in expected_counts(condition).items():
        if value:
            increment_counter(report, key, value)
    report["references_released"] = True
    report["weak_reference_alive_after_release_count"] = 0
    complete_operation(report)
    path = root / "post_readback_isolation.json"
    write_operation_report(path, report)
    return path


def rewrite(path: Path, mutate) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def selected_order(source: str, final_token: str) -> list[int]:
    tokens = (
        "grid_data = flow.buffer_to_volume(buffer)",
        "parameters = omni.volume.SaveVolumeParameters()",
        "volume.save_volume(grid_data, str(path), parameters)",
        "nanovdb.io.readGrid(str(path))",
        "handle.vec3fGrid()",
        "voxel_size = grid.voxelSize()",
        "grid.activeVoxelCount()",
        "_sample_grid(grid, roi, vector)",
        "_profile_grid(grid, rois[\"scene\"], vector, profile_threshold)",
        final_token,
    )
    positions = []
    for index, token in enumerate(tokens):
        position = source.rfind(token) if index == len(tokens) - 1 else source.find(token)
        positions.append(position)
    return positions


def main() -> int:
    results = []

    def check(name: str, passed: bool, detail=None) -> None:
        results.append({"name": name, "pass": bool(passed), "detail": detail})

    defaults = new_counter_values()
    check("factory_exact_key_order", tuple(defaults) == COUNTER_KEYS)
    check("factory_all_explicit_integer_zero", all(type(value) is int and value == 0 for value in defaults.values()))

    with tempfile.TemporaryDirectory(prefix="phase6he-e2e-") as temporary:
        root = Path(temporary)
        resource = root / "resource_markers.jsonl"
        resource.write_text("", encoding="utf-8")

        for row in CONDITIONS:
            condition = row["name"]
            report_path = produce_report(root, condition)
            verdict = validate_operation_files(
                report_path,
                resource,
                expected_condition=condition,
                expected_attempt_id=condition,
                resource_pass=True,
                cleanup_pass=True,
            )
            check(f"actual_producer_to_consumer_{row['mode']}", verdict["pass"], verdict["reasons"])

        baseline = CONDITIONS[0]["name"]
        for key in COUNTER_KEYS:
            report_path = produce_report(root, baseline)
            rewrite(report_path, lambda value, key=key: value["calls"].pop(key))
            verdict = validate_operation_files(
                report_path, resource, expected_condition=baseline, expected_attempt_id=baseline,
                resource_pass=True, cleanup_pass=True,
            )
            check(
                f"missing_{key}",
                f"forbidden_call_missing:{key}" in verdict["reasons"],
                verdict["reasons"],
            )

        forbidden_key = "velocity_profile"
        for value, label in ((1, "nonzero"), (True, "bool"), (None, "null"), ("0", "string"), (0.0, "float")):
            report_path = produce_report(root, baseline)
            rewrite(report_path, lambda payload, value=value: payload["calls"].__setitem__(forbidden_key, value))
            verdict = validate_operation_files(
                report_path, resource, expected_condition=baseline, expected_attempt_id=baseline,
                resource_pass=True, cleanup_pass=True,
            )
            wanted = f"forbidden_call_nonzero:{forbidden_key}" if label == "nonzero" else f"call_count_type_invalid:{forbidden_key}"
            check(f"{label}_{forbidden_key}", wanted in verdict["reasons"], verdict["reasons"])

        report_path = produce_report(root, baseline)
        rewrite(report_path, lambda value: value["calls"].__setitem__("unknown_velocity_step", 0))
        verdict = validate_operation_files(
            report_path, resource, expected_condition=baseline, expected_attempt_id=baseline,
            resource_pass=True, cleanup_pass=True,
        )
        check("unknown_counter", "call_count_unknown:unknown_velocity_step" in verdict["reasons"], verdict["reasons"])

        for field, wanted in (("schema", "canonical_schema_mismatch"), ("condition", "canonical_condition_mismatch")):
            report_path = produce_report(root, baseline)
            rewrite(report_path, lambda value, field=field: value.__setitem__(field, "wrong"))
            verdict = validate_operation_files(
                report_path, resource, expected_condition=baseline, expected_attempt_id=baseline,
                resource_pass=True, cleanup_pass=True,
            )
            check(f"{field}_mismatch", wanted in verdict["reasons"], verdict["reasons"])

        report_path = produce_report(root, baseline)
        rewrite(report_path, lambda value: value["attempt_identity"].__setitem__("attempt_id", "wrong"))
        verdict = validate_operation_files(
            report_path, resource, expected_condition=baseline, expected_attempt_id=baseline,
            resource_pass=True, cleanup_pass=True,
        )
        check("attempt_mismatch", "attempt_identity_mismatch" in verdict["reasons"], verdict["reasons"])

        report_path = produce_report(root, baseline)
        rewrite(report_path, lambda value: value.__setitem__("operation_complete", False))
        verdict = validate_operation_files(
            report_path, resource, expected_condition=baseline, expected_attempt_id=baseline,
            resource_pass=True, cleanup_pass=True,
        )
        check("operation_incomplete", "canonical_operation_incomplete" in verdict["reasons"], verdict["reasons"])

        report_path = produce_report(root, baseline)
        rewrite(report_path, lambda value: value.__setitem__("references_released", False))
        verdict = validate_operation_files(
            report_path, resource, expected_condition=baseline, expected_attempt_id=baseline,
            resource_pass=True, cleanup_pass=True,
        )
        check("references_incomplete", "references_not_released" in verdict["reasons"], verdict["reasons"])

        report_path = produce_report(root, baseline)
        verdict = validate_operation_files(
            report_path, resource, expected_condition=baseline, expected_attempt_id=baseline,
            resource_pass=False, cleanup_pass=True,
        )
        check("resource_failure", "resource_gate_failed" in verdict["reasons"], verdict["reasons"])
        verdict = validate_operation_files(
            report_path, resource, expected_condition=baseline, expected_attempt_id=baseline,
            resource_pass=True, cleanup_pass=False,
        )
        check("cleanup_failure", "cleanup_gate_failed" in verdict["reasons"], verdict["reasons"])

    current = (SCRIPT_DIR / "probe_phase6dt_flow_collision_reference.py").read_text(encoding="utf-8")
    frozen = subprocess.check_output(
        ["git", "-c", f"safe.directory={REPO.as_posix()}", "show", "cefa061:scripts/probe_phase6dt_flow_collision_reference.py"],
        cwd=REPO,
        text=True,
        encoding="utf-8",
    )
    current_positions = selected_order(current, "delete_temporary()")
    frozen_positions = selected_order(frozen, "path.unlink(missing_ok=True)")
    check("current_full_path_selected_order", all(value >= 0 for value in current_positions) and current_positions == sorted(current_positions), current_positions)
    check("frozen_phase6hd_selected_order", all(value >= 0 for value in frozen_positions) and frozen_positions == sorted(frozen_positions), frozen_positions)
    check("diagnostic_stop_default_none", "diagnostic_stop_after: str | None = None" in current)
    check("existing_callers_do_not_set_diagnostic_stop", current.count("diagnostic_stop_after=") == 0)

    probe = (SCRIPT_DIR / "probe_phase6he_velocity_lifecycle.py").read_text(encoding="utf-8")
    check("probe_uses_actual_save_and_sample", "hb.shared._save_and_sample(" in probe)
    check("probe_uses_exact_velocity_channel", '"velocity",' in probe)
    check("probe_uses_existing_rois", "hb.shared._p3_world_rois()" in probe)
    check("probe_uses_frozen_threshold", "profile_threshold=0.01" in probe)
    check("probe_disables_collector", "spatial_collector=None" in probe)
    check("probe_has_no_temperature_conversion", "buffer_to_volume(temperature" not in probe)
    check("probe_uses_shared_report_factory", "new_runtime_report(" in probe and "COUNTER_KEYS =" not in probe)

    contract = json.loads((SCRIPT_DIR / "phase6he_velocity_lifecycle_contract.json").read_text(encoding="utf-8"))
    check("contract_ladder_matches_shared_schema", contract["ladder"] == [
        {key: row[key] for key in ("name", "mode", "stop_after", "adds")} for row in CONDITIONS
    ])
    with tempfile.TemporaryDirectory(prefix="phase6he-command-") as temporary:
        command = build_command(CONDITIONS[0]["name"], "V0", Path(temporary), contract)
        check("command_uses_phase6he_probe", any(value.endswith("probe_phase6he_velocity_lifecycle.py") for value in command), command)
        check("command_uses_phase6he_report_phase", "phase6he" in command)
        check("command_uses_frozen_r2_prefix", "R2" in command)

    report = {
        "schema": "campfire.phase6he.producer-consumer-fixture.v1",
        "pass": all(row["pass"] for row in results),
        "count": len(results),
        "counter_schema": list(COUNTER_KEYS),
        "results": results,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
