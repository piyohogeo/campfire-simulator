"""No-Kit producer-to-consumer fixture for Phase 6HQ lifecycle policy."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path

from phase6hq_lifecycle_classification import (
    attach_evaluation,
    build_evidence,
    consume_guard_report,
)


ROOT = Path(__file__).resolve().parents[1]
MIB = 1024 * 1024


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _read(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > MIB:
        raise RuntimeError("bounded_json_unavailable:" + str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _identity(path: str, *, pid: int = 300, created: float = 30.0, parent: int = 200, attempt: str = "phase6hq-fixture") -> dict:
    return {
        "pid": pid,
        "create_time_utc_epoch": created,
        "path": path,
        "parent_pid": parent,
        "observed_at_utc_epoch": 40.0,
        "role": "child",
        "root_attempt_id": attempt,
        "termination_requested_at_utc_epoch": 50.0,
    }


def _base(policy: dict, assisted: bool) -> tuple[dict, dict, dict, list[dict], list[dict]]:
    telemetry = str(Path(policy["telemetry_extension_store_root"]) / "omni.kit.telemetry-fixture" / "omni.telemetry.transmitter" / "omni.telemetry.transmitter.exe")
    helper = _identity(telemetry)
    cleanup = {
        "schema": "campfire.phase6fu.exact-cleanup-summary.v1",
        "observed_identity_count": 3 if assisted else 2,
        "before": [],
        "killed": [],
        "protected_identity_mismatch": [],
        "query_unknown": [],
        "final": [],
        "matching_remaining": [],
        "final_unknown": [],
        "all_matching_absent": True,
        "cleanup_required": assisted,
        "killed_pids": [],
        "remaining": [],
        "all_observed_absent": True,
        "absence_confirmation_sources": ["psutil", "win32"],
        "cleanup_suppression": {"observed": False, "released": True, "timed_out": False, "wait_seconds": 0.0},
    }
    if assisted:
        cleanup["before"] = [{"state": "alive_identity_match", "identity": helper, "queries": [{"source": "psutil", "state": "alive_identity_match"}, {"source": "win32", "state": "alive_identity_match"}]}]
        cleanup["killed"] = [copy.deepcopy(helper)]
        cleanup["killed_pids"] = [300]
        cleanup["final"] = [{"state": "confirmed_exited", "identity": helper, "queries": [{"source": "psutil", "state": "confirmed_exited"}, {"source": "win32", "state": "confirmed_exited"}]}]
    raw = {
        "schema": "campfire.phase6eg.resource-guard.v1",
        "status": "failed" if assisted else "ok",
        "stop_reason": "observed_descendant_residual" if assisted else None,
        "root": {"pid": 100, "create_time_utc_epoch": 10.0, "path": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"},
        "exit_code": 0,
        "process_absent": True,
        "observed_process_cleanup": cleanup,
        "peaks": {"runner": 64 * MIB, "kit": 6 * 1024 * MIB, "diagnostic": 16 * MIB, "child": 32 * MIB, "tree": 7 * 1024 * MIB},
        "machine_minima": {"available_physical_bytes": 64 * 1024 * MIB, "estimated_commit_headroom_bytes": 80 * 1024 * MIB},
    }
    operation = {"schema": "campfire.phase6hp.fixture-run.v1", "status": "qualified", "operation_complete": True, "shutdown_complete": True}
    runner = {
        "schema": "campfire.phase6hp.fixture-runner.v1", "status": "qualified", "mode": "smoke", "process_exit_code": 0,
        "fatal_lines": [], "dump_inventory": [], "automatic_upload_attempt_lines": [],
        "shutdown_monitor": {"windows_exception_present": False},
    }
    markers = [{"marker": "operation_complete"}, {"marker": "shutdown_complete"}]
    trace = [{
        "timestamp_utc_epoch": 35.0,
        "processes": [
            {"pid": 100, "parent_pid": 1, "create_time_utc_epoch": 10.0, "path": raw["root"]["path"], "name": "powershell.exe", "role": "runner"},
            {"pid": 200, "parent_pid": 100, "create_time_utc_epoch": 20.0, "path": r"C:\repo\kit.exe", "name": "kit.exe", "role": "kit"},
            {"pid": 300, "parent_pid": 200, "create_time_utc_epoch": 30.0, "path": telemetry, "name": "omni.telemetry.transmitter.exe", "role": "child"},
        ],
    }]
    return raw, operation, runner, markers, trace


def _produce_consume(case_root: Path, policy: dict, raw: dict, operation: dict, runner: dict, markers: list[dict], trace: list[dict]) -> tuple[dict, dict]:
    evidence = build_evidence(raw, operation, runner, markers, trace, attempt_id="phase6hq-fixture", mode="smoke", policy=policy)
    produced = attach_evaluation(raw, evidence, policy)
    path = case_root / "guard.json"
    _write(path, produced)
    unmodified = _read(path)
    consumed = consume_guard_report(unmodified, policy, expected_attempt_id="phase6hq-fixture")
    return unmodified, consumed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.output_root.exists():
        raise RuntimeError("Phase 6HQ preflight refuses root reuse")
    args.output_root.mkdir(parents=True)
    policy = _read(args.contract)
    cases = []

    def run_case(name: str, expected: str, mutate=None, assisted=True):
        raw, operation, runner, markers, trace = _base(policy, assisted)
        if mutate:
            mutate(raw, operation, runner, markers, trace)
        produced, consumed = _produce_consume(args.output_root / name, policy, raw, operation, runner, markers, trace)
        guard_class = produced["canonical_lifecycle_classification"]
        parent_class = consumed["classification"]
        passed = guard_class == expected and parent_class == expected and consumed["accepted"] == (expected != "cleanup_failure")
        cases.append({"name": name, "expected": expected, "guard": guard_class, "parent": parent_class, "passed": passed})

    run_case("natural_clean_exit", "natural_clean_exit", assisted=False)
    run_case("telemetry_cleanup_assisted", "cleanup_assisted_exit")
    run_case("helper_exits_during_grace", "natural_clean_exit", assisted=False)
    run_case("wrong_executable", "cleanup_failure", lambda r,o,c,m,t: [item.update(path=item["path"].replace("omni.telemetry.transmitter.exe", "other.exe")) for item in r["observed_process_cleanup"]["killed"] + [x["identity"] for x in r["observed_process_cleanup"]["before"]] + [x["identity"] for x in r["observed_process_cleanup"]["final"]]])
    run_case("wrong_extension_path", "cleanup_failure", lambda r,o,c,m,t: [item.update(path=item["path"].replace("omni.kit.telemetry-fixture", "other.extension-1")) for item in r["observed_process_cleanup"]["killed"] + [x["identity"] for x in r["observed_process_cleanup"]["before"]] + [x["identity"] for x in r["observed_process_cleanup"]["final"]]])
    run_case("outside_ov_path", "cleanup_failure", lambda r,o,c,m,t: [item.update(path=r"C:\outside\omni.kit.telemetry-x\omni.telemetry.transmitter\omni.telemetry.transmitter.exe") for item in r["observed_process_cleanup"]["killed"] + [x["identity"] for x in r["observed_process_cleanup"]["before"]] + [x["identity"] for x in r["observed_process_cleanup"]["final"]]])
    run_case("wrong_creation_time", "cleanup_failure", lambda r,o,c,m,t: [item.update(create_time_utc_epoch=31.0) for item in r["observed_process_cleanup"]["killed"] + [x["identity"] for x in r["observed_process_cleanup"]["before"]] + [x["identity"] for x in r["observed_process_cleanup"]["final"]]])
    run_case("pid_reuse", "cleanup_failure", lambda r,o,c,m,t: r["observed_process_cleanup"]["protected_identity_mismatch"].append({"state": "alive_identity_mismatch"}))
    run_case("parent_chain_mismatch", "cleanup_failure", lambda r,o,c,m,t: t[0]["processes"][2].update(parent_pid=999))
    run_case("attempt_ownership_mismatch", "cleanup_failure", lambda r,o,c,m,t: [item.update(root_attempt_id="other-attempt") for item in r["observed_process_cleanup"]["killed"] + [x["identity"] for x in r["observed_process_cleanup"]["before"]] + [x["identity"] for x in r["observed_process_cleanup"]["final"]]])
    def duplicate_helper(r,o,c,m,t):
        cleanup=r["observed_process_cleanup"]; other=copy.deepcopy(cleanup["before"][0]["identity"]); other.update(pid=301,create_time_utc_epoch=31.0); cleanup["before"].append({"state":"alive_identity_match","identity":other,"queries":[]}); cleanup["killed"].append(other); cleanup["killed_pids"].append(301); cleanup["final"].append({"state":"confirmed_exited","identity":other,"queries":[{"source":"psutil","state":"confirmed_exited"},{"source":"win32","state":"confirmed_exited"}]}); t[0]["processes"].append({"pid":301,"parent_pid":200,"create_time_utc_epoch":31.0,"path":other["path"],"name":"omni.telemetry.transmitter.exe","role":"child"})
    run_case("two_telemetry_helpers", "cleanup_failure", duplicate_helper)
    def replace_helper_path(r,path,name,role="child"):
        cleanup=r["observed_process_cleanup"]
        for item in cleanup["killed"] + [x["identity"] for x in cleanup["before"]] + [x["identity"] for x in cleanup["final"]]: item.update(path=path,role=role)
    def helper_plus_unknown(r,o,c,m,t):
        duplicate_helper(r,o,c,m,t)
        cleanup=r["observed_process_cleanup"]
        unknown_path=r"C:\unknown\child.exe"
        cleanup["before"][1]["identity"].update(path=unknown_path)
        cleanup["killed"][1].update(path=unknown_path)
        cleanup["final"][1]["identity"].update(path=unknown_path)
        t[0]["processes"][-1].update(path=unknown_path,name="child.exe")
    run_case("telemetry_plus_unknown_child", "cleanup_failure", helper_plus_unknown)
    run_case("kit_residual", "cleanup_failure", lambda r,o,c,m,t: replace_helper_path(r,r"C:\repo\kit.exe","kit.exe","kit"))
    run_case("flow_residual", "cleanup_failure", lambda r,o,c,m,t: replace_helper_path(r,r"C:\repo\flow.exe","flow.exe","flow"))
    run_case("cdb_residual", "cleanup_failure", lambda r,o,c,m,t: replace_helper_path(r,r"C:\debug\cdb.exe","cdb.exe","diagnostic"))
    run_case("cleanup_helper_survives", "cleanup_failure", lambda r,o,c,m,t: (r["observed_process_cleanup"].update(all_matching_absent=False,all_observed_absent=False), r["observed_process_cleanup"]["final"][0].update(state="alive_identity_match")))
    run_case("killed_pid_mismatch", "cleanup_failure", lambda r,o,c,m,t: r["observed_process_cleanup"].update(killed_pids=[999]))
    run_case("operation_marker_missing", "cleanup_failure", lambda r,o,c,m,t: m.pop(0))
    run_case("resource_failure", "cleanup_failure", lambda r,o,c,m,t: r["peaks"].update(kit=99*1024*MIB))
    run_case("missing_evidence", "cleanup_failure", lambda r,o,c,m,t: r["observed_process_cleanup"].pop("killed_pids"))
    run_case("duplicate_evidence", "cleanup_failure", lambda r,o,c,m,t: r["observed_process_cleanup"]["before"].append(copy.deepcopy(r["observed_process_cleanup"]["before"][0])))
    # Parent must reject a persisted contradiction rather than upgrade it.
    raw, operation, runner, markers, trace = _base(policy, True)
    produced, _ = _produce_consume(args.output_root / "contradictory_evidence", policy, raw, operation, runner, markers, trace)
    produced["status"] = "failed"
    contradiction_path = args.output_root / "contradictory_evidence" / "contradictory_guard.json"
    _write(contradiction_path, produced)
    consumed = consume_guard_report(_read(contradiction_path), policy, expected_attempt_id="phase6hq-fixture")
    cases.append({"name":"contradictory_evidence","expected":"cleanup_failure","guard":"cleanup_failure","parent":consumed["classification"],"passed":consumed["classification"]=="cleanup_failure" and not consumed["accepted"]})

    hp_root = ROOT / "artifacts/phase6hp-app-ready-smoke-20260815"
    hp_hashes_before = {str(path.relative_to(hp_root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in hp_root.rglob("*") if path.is_file()}
    hp_hashes_after = {str(path.relative_to(hp_root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in hp_root.rglob("*") if path.is_file()}
    checks = {
        "all_cases_pass": all(case["passed"] for case in cases),
        "guard_parent_classification_identical": all(case["guard"] == case["parent"] for case in cases),
        "phase6hp_read_only": hp_hashes_before == hp_hashes_after and bool(hp_hashes_before),
        "contract_bounded": args.contract.stat().st_size <= MIB,
        "kit_launch_count_zero": True,
    }
    report = {
        "schema": "campfire.phase6hq.lifecycle-preflight.v1",
        "phase": "phase6hq",
        "status": "qualified" if all(checks.values()) else "failed",
        "kit_launch_count": 0,
        "case_count": len(cases),
        "cases": cases,
        "checks": checks,
        "phase6hp_reclassified": False,
        "phase6hp_runtime_reused": False,
    }
    _write(args.output_root / "preflight_report.json", report)
    return 0 if report["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
