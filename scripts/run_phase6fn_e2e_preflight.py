"""Create real-shaped Phase 6FN artifacts and exercise the complete analyzer."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts/phase6fn_routed_settled_contract.json"
BASE = ROOT / "scripts/phase6fg_paired_readback_contract.json"
ANALYZER = ROOT / "scripts/analyze_phase6fn_routed_settled.py"
ORDERS = [
    ["R0_control", "R1_readback", "R2_fuel_alias"],
    ["R1_readback", "R2_fuel_alias", "R0_control"],
    ["R2_fuel_alias", "R0_control", "R1_readback"],
]


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")


def stamp(seconds: float) -> str:
    return (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)).isoformat()


def memory(private: int) -> dict:
    return {"available": True, "private_bytes": private, "working_set_bytes": private // 2, "peak_working_set_bytes": private}


def pointer_boundary(frame: int, condition: str) -> dict:
    calls = {"public_readback_calls": 1, "numpy_asarray_calls": int(condition == "R2_fuel_alias"), "field_persistence_calls": 0}
    boundary = {"frame": frame, "operation_counts": calls, "weak_reference_alive_after_scope_count": 0, "converted_weak_reference_alive_immediately_after_release": False}
    if condition == "R2_fuel_alias":
        metadata = {"identity": 1234 + frame, "shape": [10349504], "dtype": "uint32", "strides": [4], "size": 10349504, "nbytes": 41398016}
        boundary.update({
            "fuel_source": dict(metadata), "fuel_array": dict(metadata),
            "observable_copy_contract": {"source_data_pointer": 4096 + frame, "converted_data_pointer": 4096 + frame, "same_data_pointer": True, "same_identity": True, "shares_memory": True},
        })
    return boundary


def artifact(condition: str, sequence: int, attempt_id: str, payload_sha: str) -> dict:
    private = 10 * 1024**3
    samples = []
    markers = []
    outer = []
    operation_frames = [120, 360, 540]
    settling_frames = [360, 540, 620]
    start_times = [10.0, 20.0, 30.0]
    for iteration, (frame, settling_frame, start) in enumerate(zip(operation_frames, settling_frames, start_times), 1):
        for offset, name in enumerate(("pre_operation", "operation_completed", "release_completed", "settling_started")):
            row = {"schema": "campfire.phase6et.resource-marker.v1", "timestamp_utc": stamp(start + offset * .05), "marker": name, "frame": frame, "kit_update_index": 100 * iteration, "process_memory": memory(private + iteration * 1024**2)}
            markers.append(row)
        if condition != "R0_control":
            markers.extend([
                {"timestamp_utc": stamp(start + .01), "marker": "readback_call_before", "frame": frame, "process_memory": memory(private)},
                {"timestamp_utc": stamp(start + .02), "marker": "readback_call_after", "frame": frame, "process_memory": memory(private + 1024**2)},
                {"timestamp_utc": stamp(start + .03), "marker": "original_tuple_and_all_handle_aliases_released", "frame": frame, "process_memory": memory(private)},
            ])
        if condition == "R2_fuel_alias":
            markers.extend([
                {"timestamp_utc": stamp(start + .025), "marker": "fuel_conversion_before", "frame": frame, "process_memory": memory(private + 1024**2)},
                {"timestamp_utc": stamp(start + .026), "marker": "fuel_conversion_after", "frame": frame, "process_memory": memory(private + 2 * 1024**2)},
                {"timestamp_utc": stamp(start + .04), "marker": "converted_buffer_released", "frame": frame, "process_memory": memory(private)},
            ])
        end = start + 5.0
        field_bytes = None if condition == "R0_control" else 41398016
        markers.append({"schema": "campfire.phase6et.resource-marker.v1", "timestamp_utc": stamp(end), "marker": "settling_end", "frame": settling_frame, "settling_iteration": iteration, "kit_update_index": 100 * iteration + 80, "active_blocks": 1000 + iteration, "field_element_count": None if field_bytes is None else 10349504, "field_logical_bytes": field_bytes, "field_measurement_source": "unavailable_without_public_readback" if field_bytes is None else "public_readback_metadata", "process_memory": memory(private + iteration * 1024**2)})
        for sample_index in range(9):
            when = start + .25 + sample_index * .5
            outer.append({"timestamp_utc_epoch": datetime.fromisoformat(stamp(when)).timestamp(), "tree_private_bytes": private + 4 * 1024**2, "processes": [{"role": "kit", "private_bytes": private}]})
        sample = {"frame": frame, "active_blocks": 1000 + iteration, "operation": True, "sentinel": False}
        if condition != "R0_control": sample["readback_boundary"] = pointer_boundary(frame, condition)
        samples.append(sample)
    samples.append({"frame": 620, "active_blocks": 1003, "operation": False, "sentinel": True})
    markers.extend([
        {"timestamp_utc": stamp(40), "marker": "stage_close_request_before", "process_memory": memory(private)},
        {"timestamp_utc": stamp(41), "marker": "stage_close_request_after", "process_memory": memory(private)},
    ])
    raw = {"schema": "campfire.phase6fk.point-collision-run.v1", "phase": "phase6fk", "startup_liveness_gate": {"classification": "representative_ingestion", "source_ok": True, "telemetry_fresh": True, "identity_and_exact_source": {"pass": True}}, "point_payload": {"payload_sha256": payload_sha}, "samples": samples, "completion_contract": {"stage_closed": True, "timeline_stopped": True, "renderer_drained": True, "shutdown_requested": True}}
    evidence = {"shutdown_monitor": {"lifecycle_candidate": "normal_exit", "exit_code": 0, "windows_exception_present": False}, "fatal_lines": [], "dump_inventory": [], "automatic_upload_attempt_lines": [], "device_lost_lines": [], "tdr_lines": []}
    guard = {"status": "ok", "peaks": {"kit_private_bytes": private, "tree_private_bytes": private + 4 * 1024**2}, "machine_minima": {"available_physical_memory_bytes": 32 * 1024**3, "commit_headroom_bytes": 32 * 1024**3}, "observed_process_cleanup": {"remaining": [], "all_observed_absent": True}}
    return {"condition": condition, "sequence": sequence, "attempt_id": attempt_id, "raw": raw, "markers": markers, "outer": outer, "extension": [{"name": "extension_on_shutdown_begin"}, {"name": "extension_on_shutdown_end"}], "evidence": evidence, "guard": guard}


def materialize(root: Path, items: list[dict]) -> None:
    for position, item in enumerate(items, 1):
        attempt = root / item["attempt_id"]
        label = item["condition"]
        metadata = {"schema": "campfire.phase6fn.attempt-metadata.v1", "phase": "phase6fn", "attempt_id": item["attempt_id"], "sequence": item["sequence"], "position": position, "condition": label}
        write_json(attempt / "attempt_metadata.json", metadata)
        write_json(attempt / label / "raw.json", item["raw"])
        write_json(attempt / label / "runner_evidence.json", item["evidence"])
        write_jsonl(attempt / label / "resource_markers.jsonl", item["markers"])
        write_jsonl(attempt / label / "extension_lifecycle_markers.jsonl", item["extension"])
        write_json(attempt / "runner-logs" / f"{label}.guard.json", item["guard"])
        write_jsonl(attempt / "runner-logs" / f"{label}.resource.jsonl", item["outer"])


def invoke(root: Path, output: Path) -> dict:
    command = [sys.executable, str(ANALYZER), "--root", str(root), "--contract", str(CONTRACT), "--base-contract", str(BASE), "--output", str(output)]
    completed = subprocess.run(command, check=False, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not output.is_file(): return {"analyzer_process_exit": completed.returncode, "qualified": False, "analyzer_failure": "output_missing"}
    result = json.loads(output.read_text(encoding="utf-8")); result["analyzer_process_exit"] = completed.returncode
    return result


def mutate(item: dict, name: str) -> None:
    markers, raw = item["markers"], item["raw"]
    if name == "missing_iteration3_settling_end": markers[:] = [m for m in markers if not (m.get("marker") == "settling_end" and m.get("settling_iteration") == 3)]
    elif name == "settling_iteration_mismatch": next(m for m in markers if m.get("marker") == "settling_end" and m.get("settling_iteration") == 3)["settling_iteration"] = 9
    elif name == "short_settling_time": next(m for m in markers if m.get("marker") == "settling_end")["timestamp_utc"] = stamp(11)
    elif name == "few_resource_samples": item["outer"] = item["outer"][:4] + item["outer"][9:]
    elif name == "few_renderer_updates": next(m for m in markers if m.get("marker") == "settling_end")["kit_update_index"] = 120
    elif name == "fourth_operation_at_620": markers.append({"timestamp_utc": stamp(36), "marker": "sample_started", "frame": 620, "process_memory": memory(10 * 1024**3)})
    elif name == "call_count_mismatch": raw["samples"][0]["readback_boundary"]["operation_counts"]["public_readback_calls"] = 2
    elif name == "pointer_missing": raw["samples"][0]["readback_boundary"].pop("observable_copy_contract", None)
    elif name == "pointer_zero": raw["samples"][0]["readback_boundary"]["observable_copy_contract"]["source_data_pointer"] = 0
    elif name == "pointer_mismatch": raw["samples"][0]["readback_boundary"]["observable_copy_contract"]["converted_data_pointer"] += 4; raw["samples"][0]["readback_boundary"]["observable_copy_contract"]["same_data_pointer"] = False
    elif name == "weak_reference_residual": raw["samples"][0]["readback_boundary"]["weak_reference_alive_after_scope_count"] = 1
    elif name == "lifecycle_incomplete": raw["completion_contract"]["stage_closed"] = False
    elif name == "cleanup_residual": item["guard"]["observed_process_cleanup"] = {"remaining": [999], "all_observed_absent": False}
    elif name == "ceiling_exceeded": item["guard"]["status"] = "resource_limit"; item["guard"]["stop_reason"] = "kit_private_limit"


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(); output = args.output_root.resolve()
    if output.exists(): raise SystemExit(f"Phase 6FN preflight refuses root reuse: {output}")
    output.mkdir(parents=True)
    base = json.loads(BASE.read_text(encoding="utf-8")); payload = base["expected_stage"]["payload_sha256"]
    checks = []
    population = []
    attempt_number = 0
    for sequence, order in enumerate(ORDERS, 1):
        for condition in order:
            attempt_number += 1; population.append(artifact(condition, sequence, f"attempt{attempt_number:02d}", payload))
    pass_root = output / "pass_population"; materialize(pass_root, population)
    passed = invoke(pass_root, pass_root / "analyzer_report.json")
    checks.append({"name": "complete_pass_population", "pass": passed.get("qualified") is True and all(a["classification"] == "representative_pass" for a in passed.get("attempts", []))})
    mutations = [
        ("missing_iteration3_settling_end", "R0_control", "explicit_settling_integrity"), ("settling_iteration_mismatch", "R0_control", "explicit_settling_integrity"),
        ("short_settling_time", "R0_control", "explicit_settling_integrity"), ("few_resource_samples", "R0_control", "explicit_settling_integrity"),
        ("few_renderer_updates", "R0_control", "explicit_settling_integrity"), ("fourth_operation_at_620", "R0_control", "operation_integrity"),
        ("call_count_mismatch", "R1_readback", "operation_integrity"), ("pointer_missing", "R2_fuel_alias", "pointer_alias_integrity"),
        ("pointer_zero", "R2_fuel_alias", "pointer_alias_integrity"), ("pointer_mismatch", "R2_fuel_alias", "pointer_alias_integrity"),
        ("weak_reference_residual", "R2_fuel_alias", "pointer_alias_integrity"), ("lifecycle_incomplete", "R0_control", "lifecycle"),
        ("cleanup_residual", "R0_control", "cleanup"), ("ceiling_exceeded", "R0_control", "absolute_resource_safety"),
    ]
    for name, condition, layer in mutations:
        case = artifact(condition, 1, "attempt01", payload); mutate(case, name)
        fixture = output / name; materialize(fixture, [case]); report = invoke(fixture, fixture / "analyzer_report.json")
        attempt = report.get("attempts", [{}])[0]; layer_result = (attempt.get("layers") or {}).get(layer, {})
        checks.append({"name": name, "expected_layer": layer, "classification": attempt.get("classification"), "pass": layer_result.get("gate_pass") is False and attempt.get("replaceable_startup_prerequisite") is not True})
    for name, kind in (("raw_missing", "missing"), ("raw_parse_failure", "parse"), ("unknown_phase_schema", "route")):
        case = artifact("R0_control", 1, "attempt01", payload); fixture = output / name; materialize(fixture, [case])
        raw_path = fixture / "attempt01/R0_control/raw.json"
        if kind == "missing": raw_path.unlink()
        elif kind == "parse": raw_path.write_text("{", encoding="utf-8")
        else:
            value = json.loads(raw_path.read_text(encoding="utf-8")); value["phase"] = "unknown"; write_json(raw_path, value)
        report = invoke(fixture, fixture / "analyzer_report.json"); attempt = report.get("attempts", [{}])[0]
        checks.append({"name": name, "classification": attempt.get("classification"), "pass": attempt.get("classification") == "diagnostic_harness_failure" and attempt.get("replaceable_startup_prerequisite") is not True})
    stop_root = output / "nonreplaceable_stop_sequence"
    first = artifact("R0_control", 1, "attempt01", payload); mutate(first, "fourth_operation_at_620")
    second = artifact("R1_readback", 1, "attempt02", payload); materialize(stop_root, [first, second])
    report = invoke(stop_root, stop_root / "analyzer_report.json")
    checks.append({"name": "later_launch_detected_after_nonreplaceable", "pass": report.get("attempts_after_required_stop") == ["attempt02"]})
    contract_sha = hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper()
    manifest = {"schema": "campfire.phase6fn.e2e-preflight.v1", "phase": "phase6fn", "contract_sha256": contract_sha, "checks": checks, "all_pass": all(item["pass"] for item in checks), "fixture_count": len(checks), "formal_runtime_started": False}
    write_json(output / "preflight_manifest.json", manifest)
    return 0 if manifest["all_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
