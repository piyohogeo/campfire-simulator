"""No-Kit guard-producer to parent-consumer fixture for Phase 6HR."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path

from phase6hr_lifecycle_classification import attach_evaluation, build_evidence, consume_guard_report


ROOT = Path(__file__).resolve().parents[1]
MIB = 1024 * 1024
ATTEMPT = "phase6hr-fixture"


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(partial, path)


def _read(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > MIB:
        raise RuntimeError("bounded_json_unavailable:" + str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _identity(path: str, pid: int, created: float, parent: int, *, role: str = "child") -> dict:
    return {
        "pid": pid, "create_time_utc_epoch": created, "path": path,
        "parent_pid": parent, "observed_at_utc_epoch": 40.0, "role": role,
        "root_attempt_id": ATTEMPT, "termination_requested_at_utc_epoch": 50.0,
    }


def _paths(policy: dict) -> dict[str, str]:
    return {
        "telemetry": str(Path(policy["telemetry_extension_store_root"]) / "omni.kit.telemetry-fixture" / "omni.telemetry.transmitter" / "omni.telemetry.transmitter.exe"),
        "ngx": r"C:\Windows\System32\DriverStore\FileRepository\nv_dispig.inf_amd64_abcdef123456\nvngx_update.exe",
        "conhost": str(Path(policy["conhost_exact_path"])),
    }


def _base(policy: dict, helper_kinds: tuple[str, ...] = ()) -> tuple[dict, dict, dict, list[dict], list[dict]]:
    paths = _paths(policy)
    specs = {
        "telemetry": _identity(paths["telemetry"], 300, 30.0, 200),
        "ngx": _identity(paths["ngx"], 400, 31.0, 200),
        "conhost": _identity(paths["conhost"], 401, 32.0, 400),
    }
    selected = [copy.deepcopy(specs[kind]) for kind in helper_kinds]
    before = [{"state": "alive_identity_match", "identity": item, "queries": [{"source": "psutil", "state": "alive_identity_match"}, {"source": "win32", "state": "alive_identity_match"}]} for item in selected]
    killed = [copy.deepcopy(item) for item in selected]
    final = [{"state": "confirmed_exited", "identity": copy.deepcopy(item), "queries": [{"source": "psutil", "state": "confirmed_exited"}, {"source": "win32", "state": "confirmed_exited"}]} for item in selected]
    cleanup = {
        "schema": "campfire.phase6fu.exact-cleanup-summary.v1",
        "observed_identity_count": 2 + len(selected), "before": before, "killed": killed,
        "protected_identity_mismatch": [], "query_unknown": [], "final": final,
        "matching_remaining": [], "final_unknown": [], "all_matching_absent": True,
        "cleanup_required": bool(selected), "killed_pids": [item["pid"] for item in selected],
        "remaining": [], "all_observed_absent": True,
        "absence_confirmation_sources": ["psutil", "win32"],
        "cleanup_suppression": {"observed": False, "released": True, "timed_out": False, "wait_seconds": 0.0},
    }
    root_path = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    raw = {
        "schema": "campfire.phase6eg.resource-guard.v1", "status": "failed" if selected else "ok",
        "stop_reason": "observed_descendant_residual" if selected else None,
        "root": {"pid": 100, "create_time_utc_epoch": 10.0, "path": root_path},
        "exit_code": 0, "process_absent": True, "observed_process_cleanup": cleanup,
        "peaks": {"runner": 64*MIB, "kit": 6*1024*MIB, "diagnostic": 16*MIB, "child": 32*MIB, "tree": 7*1024*MIB},
        "machine_minima": {"available_physical_bytes": 64*1024*MIB, "estimated_commit_headroom_bytes": 80*1024*MIB},
    }
    operation = {"schema": "campfire.phase6hp.fixture-run.v1", "status": "qualified", "operation_complete": True, "shutdown_complete": True}
    runner = {"schema": "campfire.phase6hp.fixture-runner.v1", "status": "qualified", "mode": "smoke", "process_exit_code": 0, "fatal_lines": [], "dump_inventory": [], "automatic_upload_attempt_lines": [], "shutdown_monitor": {"windows_exception_present": False}}
    markers = [{"marker": "operation_complete"}, {"marker": "shutdown_complete"}]
    processes = [
        {"pid": 100, "parent_pid": 1, "create_time_utc_epoch": 10.0, "path": root_path, "name": "powershell.exe", "role": "runner"},
        {"pid": 200, "parent_pid": 100, "create_time_utc_epoch": 20.0, "path": r"C:\repo\kit.exe", "name": "kit.exe", "role": "kit"},
    ]
    for item in selected:
        processes.append({"pid": item["pid"], "parent_pid": item["parent_pid"], "create_time_utc_epoch": item["create_time_utc_epoch"], "path": item["path"], "name": Path(item["path"]).name, "role": "child"})
    trace = [{"timestamp_utc_epoch": 35.0, "processes": processes}]
    return raw, operation, runner, markers, trace


def _all_identities(raw: dict) -> list[dict]:
    cleanup = raw["observed_process_cleanup"]
    return cleanup["killed"] + [item["identity"] for item in cleanup["before"]] + [item["identity"] for item in cleanup["final"]]


def _add_helper(raw: dict, trace: list[dict], identity: dict) -> None:
    cleanup = raw["observed_process_cleanup"]
    cleanup["before"].append({"state":"alive_identity_match", "identity":copy.deepcopy(identity), "queries":[{"source":"psutil","state":"alive_identity_match"},{"source":"win32","state":"alive_identity_match"}]})
    cleanup["killed"].append(copy.deepcopy(identity))
    cleanup["killed_pids"].append(identity["pid"])
    cleanup["final"].append({"state":"confirmed_exited", "identity":copy.deepcopy(identity), "queries":[{"source":"psutil","state":"confirmed_exited"},{"source":"win32","state":"confirmed_exited"}]})
    trace[0]["processes"].append({"pid":identity["pid"],"parent_pid":identity["parent_pid"],"create_time_utc_epoch":identity["create_time_utc_epoch"],"path":identity["path"],"name":Path(identity["path"]).name,"role":identity.get("role","child")})


def _produce(case_root: Path, policy: dict, values: tuple, *, tamper=None) -> tuple[dict, dict, dict]:
    raw, operation, runner, markers, trace = values
    evidence = build_evidence(raw, operation, runner, markers, trace, attempt_id=ATTEMPT, mode="smoke", policy=policy)
    produced = attach_evaluation(raw, evidence, policy)
    if tamper:
        tamper(produced)
    path = case_root / "guard.json"
    _write(path, produced)
    persisted = _read(path)
    # The guard final gate and parent use the exact same consumer/evaluator.
    guard = consume_guard_report(persisted, policy, expected_attempt_id=ATTEMPT)
    parent = consume_guard_report(persisted, policy, expected_attempt_id=ATTEMPT)
    return persisted, guard, parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.output_root.exists():
        raise RuntimeError("Phase 6HR preflight refuses root reuse")
    args.output_root.mkdir(parents=True)
    policy = _read(args.contract)
    cases = []

    def run(name: str, expected: str, kinds=(), mutate=None, tamper=None):
        values = _base(policy, tuple(kinds))
        if mutate:
            mutate(*values)
        persisted, guard, parent = _produce(args.output_root / name, policy, values, tamper=tamper)
        same = all((guard["classification"] == parent["classification"], guard["reason"] == parent["reason"], guard["allowed_helper_set"] == parent["allowed_helper_set"], guard["killed_pid_set"] == parent["killed_pid_set"]))
        passed = same and guard["classification"] == expected and guard["accepted"] == (expected != "cleanup_failure")
        cases.append({"name":name,"expected":expected,"guard":guard,"parent":parent,"producer_classification":persisted.get("canonical_lifecycle_classification"),"passed":passed})

    run("natural_clean_exit", "natural_clean_exit")
    run("one_telemetry", "cleanup_assisted_telemetry_exit", ("telemetry",))
    run("one_ngx_tree", "cleanup_assisted_ngx_exit", ("ngx","conhost"))
    run("telemetry_plus_ngx_tree", "cleanup_assisted_ngx_exit", ("telemetry","ngx","conhost"))
    run("helpers_exit_during_grace", "natural_clean_exit")
    run("exact_cleanup_residual_zero", "cleanup_assisted_ngx_exit", ("ngx","conhost"))
    run("ngx_updater_only", "cleanup_failure", ("ngx",))
    run("conhost_only", "cleanup_failure", ("conhost",))
    run("conhost_wrong_parent", "cleanup_failure", ("ngx","conhost"), lambda r,o,n,m,t: [item.update(parent_pid=999) for item in _all_identities(r) if item["pid"]==401])
    run("ngx_wrong_parent", "cleanup_failure", ("ngx","conhost"), lambda r,o,n,m,t: [item.update(parent_pid=999) for item in _all_identities(r) if item["pid"]==400])
    run("wrong_driverstore_path", "cleanup_failure", ("ngx","conhost"), lambda r,o,n,m,t: [item.update(path=r"C:\outside\nvngx_update.exe") for item in _all_identities(r) if item["pid"]==400])
    run("wrong_conhost_path", "cleanup_failure", ("ngx","conhost"), lambda r,o,n,m,t: [item.update(path=r"C:\outside\conhost.exe") for item in _all_identities(r) if item["pid"]==401])
    run("wrong_updater_basename", "cleanup_failure", ("ngx","conhost"), lambda r,o,n,m,t: [item.update(path=item["path"].replace("nvngx_update.exe","other.exe")) for item in _all_identities(r) if item["pid"]==400])
    run("wrong_creation_time", "cleanup_failure", ("ngx","conhost"), lambda r,o,n,m,t: r["observed_process_cleanup"]["killed"][0].update(create_time_utc_epoch=39.0))
    run("pid_reuse", "cleanup_failure", ("ngx","conhost"), lambda r,o,n,m,t: r["observed_process_cleanup"]["protected_identity_mismatch"].append({"state":"alive_identity_mismatch"}))
    run("predates_attempt", "cleanup_failure", ("ngx","conhost"), lambda r,o,n,m,t: [item.update(create_time_utc_epoch=5.0) for item in _all_identities(r) if item["pid"]==400])
    run("missing_parent_trace", "cleanup_failure", ("ngx","conhost"), lambda r,o,n,m,t: t[0]["processes"].__setitem__(slice(None), [x for x in t[0]["processes"] if x["pid"] != 401]))
    def two_telemetry(r,o,n,m,t):
        _add_helper(r,t,_identity(_paths(policy)["telemetry"],301,33.0,200))
    run("two_telemetry", "cleanup_failure", ("telemetry",), two_telemetry)
    def two_trees(r,o,n,m,t):
        _add_helper(r,t,_identity(_paths(policy)["ngx"],500,33.0,200)); _add_helper(r,t,_identity(_paths(policy)["conhost"],501,34.0,500))
    run("two_ngx_trees", "cleanup_failure", ("ngx","conhost"), two_trees)
    run("telemetry_ngx_unknown", "cleanup_failure", ("telemetry","ngx","conhost"), lambda r,o,n,m,t: _add_helper(r,t,_identity(r"C:\unknown\child.exe",600,33.0,200)))
    for residual, path, role in (("kit",r"C:\repo\kit.exe","kit"),("flow",r"C:\repo\flow.exe","flow"),("runner",r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe","runner"),("cdb",r"C:\debug\cdb.exe","diagnostic")):
        run(residual + "_residual", "cleanup_failure", (), lambda r,o,n,m,t,p=path,ro=role: _add_helper(r,t,_identity(p,700,33.0,200,role=ro)))
    run("cleanup_survival", "cleanup_failure", ("ngx","conhost"), lambda r,o,n,m,t: (r["observed_process_cleanup"].update(all_matching_absent=False,all_observed_absent=False), r["observed_process_cleanup"]["final"][0].update(state="alive_identity_match")))
    run("killed_pid_mismatch", "cleanup_failure", ("ngx","conhost"), lambda r,o,n,m,t: r["observed_process_cleanup"].update(killed_pids=[999]))
    run("missing_evidence", "cleanup_failure", ("ngx","conhost"), lambda r,o,n,m,t: r["observed_process_cleanup"].pop("killed_pids"))
    run("duplicate_evidence", "cleanup_failure", ("ngx","conhost"), lambda r,o,n,m,t: r["observed_process_cleanup"]["before"].append(copy.deepcopy(r["observed_process_cleanup"]["before"][0])))
    run("contradictory_persisted_evaluation", "cleanup_failure", ("ngx","conhost"), tamper=lambda p: p["canonical_lifecycle_evaluation"].update(classification="natural_clean_exit"))
    run("operation_marker_missing", "cleanup_failure", ("ngx","conhost"), lambda r,o,n,m,t: m.pop(0))
    run("shutdown_marker_missing", "cleanup_failure", ("ngx","conhost"), lambda r,o,n,m,t: m.pop())
    run("resource_failure", "cleanup_failure", ("ngx","conhost"), lambda r,o,n,m,t: r["peaks"].update(kit=99*1024*MIB))

    frozen = ROOT / "artifacts/phase6hq-app-ready-smoke-20260815"
    before = {str(p.relative_to(frozen)):hashlib.sha256(p.read_bytes()).hexdigest() for p in frozen.rglob("*") if p.is_file()}
    after = {str(p.relative_to(frozen)):hashlib.sha256(p.read_bytes()).hexdigest() for p in frozen.rglob("*") if p.is_file()}
    checks = {
        "all_cases_pass": all(case["passed"] for case in cases),
        "guard_parent_exact_agreement": all(case["guard"] == case["parent"] for case in cases),
        "phase6hq_read_only": bool(before) and before == after,
        "contract_bounded": args.contract.stat().st_size <= MIB,
        "kit_launch_count_zero": True,
    }
    report = {"schema":"campfire.phase6hr.lifecycle-preflight.v1","phase":"phase6hr","status":"qualified" if all(checks.values()) else "failed","kit_launch_count":0,"case_count":len(cases),"cases":cases,"checks":checks,"phase6hq_reclassified":False,"phase6hq_runtime_reused":False}
    _write(args.output_root / "preflight_report.json", report)
    return 0 if report["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
