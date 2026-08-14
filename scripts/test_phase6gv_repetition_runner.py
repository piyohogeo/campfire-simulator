"""No-Kit classification and fixed-sequence fixtures for Phase 6GV."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import run_phase6gv_repetition as runner


def main() -> int:
    contract_path = Path(os.environ.get("PHASE6GV_RUNNER_FIXTURE_CONTRACT",
                                        Path(__file__).with_name("phase6gv_repetition_contract.json")))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    cases = []
    def check(name, passed, observed=None): cases.append({"name":name,"passed":bool(passed),"observed":observed})
    order = [x for _ in range(contract["population"]["pattern_repetitions"])
             for x in contract["population"]["fixed_order_pattern"]]
    check("fixed_abba_48", len(order) == 48 and order[:8] == list("ABBAABBA"), order[:8])
    check("balanced_24_each", order.count("A") == order.count("B") == 24, {"A":order.count("A"),"B":order.count("B")})
    with tempfile.TemporaryDirectory(prefix="phase6gw-command-") as raw:
        attempt = Path(raw) / "attempt"
        attempt.mkdir()
        command, metadata = runner.command_for("A", attempt, "fixture_A", contract)
        check("parent_leaves_child_case_absent", not metadata["case"].exists(), str(metadata["case"]))
        check("parent_owns_only_runner_logs", metadata["logs"].is_dir(), str(metadata["logs"]))
        check("actual_command_targets_absent_case", str(metadata["case"]) in command, command[-20:])
        allowed = attempt / "case" / "p3_f0180_temperature.nvdb"
        allowed.parent.mkdir()
        allowed.write_bytes(b"partial")
        neighbor = allowed.parent / "neighbor.txt"
        neighbor.write_text("keep", encoding="utf-8")
        cleanup = runner.cleanup_attempt_temporary_files(attempt)
        check("allowlisted_temporary_deleted", cleanup["pass"] and not allowed.exists(), cleanup)
        check("neighbor_preserved", neighbor.exists(), str(neighbor))
        unknown = allowed.parent / "unexpected.nvdb"
        unknown.write_bytes(b"x")
        cleanup = runner.cleanup_attempt_temporary_files(attempt)
        check("unknown_temporary_fail_closed", not cleanup["pass"] and unknown.exists(), cleanup)
    normal_runner = {"process_exit_code":0,"outcome":{"lifecycle_status":"normal_exit","normal_exit_sample_accepted":True}}
    normal_guard = {"observed_process_cleanup":{"all_observed_absent":True}}
    value = runner.classify(normal_guard, normal_runner, {}, {}, 0)[0]
    check("normal_exit", value == "normal_exit", value)
    value = runner.classify({"stop_reason":"kit_private_limit","observed_process_cleanup":{"all_observed_absent":True}}, {}, {}, {}, 1)[0]
    check("resource_limit", value == "resource_limit", value)
    value = runner.classify({"observed_process_cleanup":{"all_observed_absent":False}}, {}, {}, {}, 1)[0]
    check("cleanup_failure", value == "cleanup_failure", value)
    value = runner.classify(normal_guard, {"process_exit_code":3221225477}, {}, {"last_operation_marker":"readback_after"}, 1)
    check("windows_native_exception", value[0] == "windows_native_exception" and "0xC0000005" in value[1], value)
    value = runner.classify(normal_guard, {"process_exit_code":1,"shutdown_monitor":{"last_lifecycle_marker":"stage_close_timeout"}}, {}, {}, 1)[0]
    check("stage_close_timeout", value == "stage_close_timeout", value)
    value = runner.classify(normal_guard, {}, {}, {}, 1)[0]
    check("os_exit_timeout", value == "os_exit_timeout", value)
    value = runner.classify(normal_guard, {"process_exit_code":1}, {"error":"startup liveness prerequisite not met"}, {}, 1)[0]
    check("startup_prerequisite_not_met", value == "startup_prerequisite_not_met", value)
    value = runner.classify(normal_guard, {"process_exit_code":1}, {"error":"TypeError reserved marker payload"}, {}, 1)[0]
    check("python_or_harness_failure", value == "python_or_harness_failure", value)
    value = runner.classify(normal_guard, {"process_exit_code":1}, {"status":"failed"}, {"last_operation_marker":"conversion_before"}, 1)[0]
    check("operation_failure", value == "operation_failure", value)
    value = runner.classify(normal_guard, None, None, {}, 1, "Phase 6EP refuses output reuse: x")
    check("pre_kit_output_reuse_is_harness", value == ("python_or_harness_failure", "pre_kit_output_root_reuse"), value)
    check("wilson_bounded", runner.wilson(1, 10)[0] < .1 < runner.wilson(1,10)[1], runner.wilson(1,10))
    check("rule_of_three_contract", contract["statistics"]["zero_failure_upper_bound"] == "rule of three")
    report = {"schema":f"campfire.{contract['phase']}.runner-fixture.v1","passed":all(x["passed"] for x in cases),
              "case_count":len(cases),"kit_started":False,"cases":cases}
    print(json.dumps(report, separators=(",",":")))
    if not report["passed"]: raise SystemExit([x["name"] for x in cases if not x["passed"]])
    return 0


if __name__ == "__main__": raise SystemExit(main())
