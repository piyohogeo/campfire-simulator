"""Synthetic evidence payloads frozen for the Phase 6FW policy fixtures."""

from __future__ import annotations

import copy
from typing import Any


ORIGINAL = {
    "pid": 4200,
    "create_time_utc_epoch": 1000.0,
    "path": r"C:\Windows\System32\conhost.exe",
    "parent_pid": 4000,
    "observed_at_utc_epoch": 1010.0,
    "role": "child",
    "root_attempt_id": "fixture-attempt",
}


def query(
    source: str,
    *,
    create_time: float | None = 1100.0,
    path: str | None = r"C:\Windows\System32\wbem\WmiPrvSE.exe",
    state: str = "alive_identity_mismatch",
) -> dict[str, Any]:
    result: dict[str, Any] = {"state": state, "source": source, "pid": ORIGINAL["pid"]}
    if create_time is not None:
        result["create_time_utc_epoch"] = create_time
    if path is not None:
        result["path"] = path
    return result


def row(state: str, queries: list[dict[str, Any]] | None = None, identity: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "state": state,
        "identity": copy.deepcopy(identity or ORIGINAL),
        "queries": copy.deepcopy(queries or []),
        "observed_at_utc_epoch": 1200.0,
    }


def exited(identity: dict[str, Any] | None = None) -> dict[str, Any]:
    return row("confirmed_exited", identity=identity)


def payload(final: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "campfire.phase6fw.fixture-input.v1",
        "cleanup": {
            "schema": "campfire.phase6fu.exact-cleanup-summary.v1",
            "final": copy.deepcopy(final),
            "matching_remaining": [],
            "final_unknown": [],
            "all_matching_absent": True,
            "all_observed_absent": True,
            "absence_confirmation_sources": ["psutil", "win32"],
            "protected_identity_mismatch": [copy.deepcopy(item) for item in final if item["state"] == "alive_identity_mismatch"],
            "killed_pids": [],
            "cleanup_suppression": {"observed": False, "released": True, "timed_out": False},
        },
        "cleanup_markers": [
            {"marker": "cleanup_suppression_released"},
            {"marker": "exact_cleanup_started"},
            {"marker": "exact_cleanup_complete", "all_matching_absent": True},
        ],
        "termination_requests": [],
        "post_summary_rediscovered": [],
    }


def fixture_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    def add(name: str, data: dict[str, Any], qualified: bool, classification: str) -> None:
        cases.append({"name": name, "payload": data, "expected_qualified": qualified, "expected_classification": classification})

    add("01_reuse_after_original_exit", payload([row("alive_identity_mismatch", [query("psutil"), query("win32")])]), True, "protected_pid_reuse_non_residual")
    add("02_same_pid_time_and_path_mismatch", payload([row("alive_identity_mismatch", [query("psutil")])]), True, "protected_pid_reuse_non_residual")
    add(
        "03_time_mismatch_path_same",
        payload([row("alive_identity_mismatch", [query("psutil", path=ORIGINAL["path"])])]),
        True,
        "protected_pid_reuse_non_residual",
    )
    add(
        "04_time_same_path_mismatch",
        payload([row("alive_identity_mismatch", [query("psutil", create_time=ORIGINAL["create_time_utc_epoch"])])]),
        True,
        "protected_pid_reuse_non_residual",
    )
    exact = payload([row("alive_identity_match", [query("psutil", create_time=1000.0, path=ORIGINAL["path"], state="alive_identity_match")])])
    exact["cleanup"]["all_matching_absent"] = False
    exact["cleanup"]["all_observed_absent"] = False
    exact["cleanup"]["matching_remaining"] = [copy.deepcopy(ORIGINAL)]
    add("05_both_identity_components_same", exact, False, "attempt_owned_residual")

    add("06_creation_time_unknown", payload([row("alive_identity_mismatch", [query("psutil", create_time=None)])]), False, "unresolved_identity_failure")
    add("07_path_unknown", payload([row("alive_identity_mismatch", [query("psutil", path=None)])]), False, "unresolved_identity_failure")
    denied = {"state": "access_denied_unknown", "source": "win32", "win32_error": 5}
    add("08_psutil_mismatch_win32_access_denied", payload([row("alive_identity_mismatch", [query("psutil"), denied])]), True, "protected_pid_reuse_non_residual")
    conflict = payload([row("alive_identity_mismatch", [query("psutil"), query("win32", create_time=1300.0, path=r"C:\Windows\System32\notepad.exe")])])
    add("09_psutil_win32_conflict", conflict, False, "unresolved_identity_failure")

    original_alive = payload([row("alive_identity_match", [query("psutil", create_time=1000.0, path=ORIGINAL["path"], state="alive_identity_match")])])
    original_alive["cleanup"]["all_matching_absent"] = False
    original_alive["cleanup"]["all_observed_absent"] = False
    original_alive["cleanup"]["matching_remaining"] = [copy.deepcopy(ORIGINAL)]
    add("10_original_identity_still_alive", original_alive, False, "attempt_owned_residual")

    child = {**ORIGINAL, "pid": 4201, "create_time_utc_epoch": 1001.0, "path": r"C:\Windows\System32\notepad.exe"}
    protected_and_clean = payload([row("alive_identity_mismatch", [query("psutil")]), exited(child)])
    protected_and_clean["termination_requests"] = [
        {"marker": "exact_identity_stop_requested", "identity": copy.deepcopy(child)}
    ]
    protected_and_clean["cleanup"]["killed_pids"] = [child["pid"]]
    add("11_protected_reuse_and_clean_matching_child", protected_and_clean, True, "protected_pid_reuse_non_residual")

    attempted = payload([row("alive_identity_mismatch", [query("psutil")])])
    attempted["termination_requests"] = [{"marker": "exact_identity_stop_requested", "identity": copy.deepcopy(ORIGINAL)}]
    add("12_attempted_mismatch_stop", attempted, False, "unresolved_identity_failure")

    rediscovered = payload([row("alive_identity_mismatch", [query("psutil")])])
    rediscovered["post_summary_rediscovered"] = [copy.deepcopy(ORIGINAL)]
    add("13_attempt_identity_rediscovered_after_summary", rediscovered, False, "attempt_owned_residual")

    add("14_normal_exit_without_pid_reuse", payload([exited()]), True, "attempt_identity_absent")

    parent = {**ORIGINAL, "pid": 4100, "path": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "role": "root"}
    reused_child = row("alive_identity_mismatch", [query("psutil")])
    add("15_parent_exit_then_child_pid_reused", payload([exited(parent), reused_child]), True, "protected_pid_reuse_non_residual")
    return cases
