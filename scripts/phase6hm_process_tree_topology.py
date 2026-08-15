"""Shared Phase 6HM process-tree command and role validation.

The resource guard intentionally remains frozen.  This module only restores the
Phase 6FZ-qualified launch topology: the guarded root is a small PowerShell case
runner, and Kit is that runner's child.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
POWERSHELL = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
KIT = ROOT / "_build/windows-x86_64/release/kit/kit.exe"
APP = ROOT / "_build/windows-x86_64/release/apps/campfire.simulator.kit"
CASE_RUNNER = SCRIPTS / "run_phase6hm_flow_proxy_case.ps1"
PROBE = SCRIPTS / "probe_phase6hm_flow_proxy_boundary.py"


def norm_path(value: str | Path) -> str:
    return os.path.normcase(str(Path(value).resolve()))


def build_powershell_target(script: Path, arguments: list[str]) -> list[str]:
    return [
        str(POWERSHELL.resolve()),
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script.resolve()),
        *arguments,
    ]


def build_formal_target(paths: dict[str, Path], stage_close_timeout_seconds: int) -> list[str]:
    arguments = [
        "-OutputPath", str(paths["output"]),
        "-MarkersPath", str(paths["markers"]),
        "-RunnerEvidencePath", str(paths["runner_evidence"]),
        "-KitLogPath", str(paths["kit_log"]),
        "-KitStdoutPath", str(paths["kit_stdout"]),
        "-KitStderrPath", str(paths["kit_stderr"]),
        "-KitPath", str(KIT.resolve()),
        "-AppPath", str(APP.resolve()),
        "-ProbePath", str(PROBE.resolve()),
        "-StageCloseTimeoutSeconds", str(int(stage_close_timeout_seconds)),
    ]
    return build_powershell_target(CASE_RUNNER, arguments)


def validate_formal_target(target: list[str]) -> tuple[bool, str]:
    if not target:
        return False, "target_command_too_short"
    if norm_path(target[0]) != norm_path(POWERSHELL):
        if Path(target[0]).name.lower() == "kit.exe":
            return False, "direct_kit_guarded_root_forbidden"
        return False, "guarded_root_path_mismatch"
    if len(target) < 8:
        return False, "target_command_too_short"
    try:
        script = target[target.index("-File") + 1]
        kit = target[target.index("-KitPath") + 1]
        app = target[target.index("-AppPath") + 1]
        probe = target[target.index("-ProbePath") + 1]
    except (ValueError, IndexError):
        return False, "formal_target_required_argument_missing"
    expected = (
        (script, CASE_RUNNER, "case_runner_path_mismatch"),
        (kit, KIT, "kit_child_path_mismatch"),
        (app, APP, "app_path_mismatch"),
        (probe, PROBE, "probe_path_mismatch"),
    )
    for observed, required, reason in expected:
        if norm_path(observed) != norm_path(required):
            return False, reason
    return True, "pass"


def validate_trace_roles(samples: list[dict[str, Any]], expected_root: Path = POWERSHELL) -> tuple[bool, list[str], dict]:
    failures: list[str] = []
    runner_rows: dict[tuple[int, float], dict] = {}
    kit_rows: dict[tuple[int, float], dict] = {}
    diagnostic_rows: dict[tuple[int, float], dict] = {}
    duplicate_identities = 0
    for sample in samples:
        seen: set[tuple[int, float]] = set()
        tree_sum = 0
        for row in sample.get("processes") or []:
            identity = (int(row["pid"]), float(row["create_time_utc_epoch"]))
            if identity in seen:
                duplicate_identities += 1
            seen.add(identity)
            tree_sum += int(row["private_bytes"])
            role = row.get("role")
            if role == "runner":
                runner_rows[identity] = row
            elif role == "kit":
                kit_rows[identity] = row
            elif role == "diagnostic":
                diagnostic_rows[identity] = row
        if tree_sum != int(sample.get("tree_private_bytes", -1)):
            failures.append("tree_private_sum_mismatch")
    if duplicate_identities:
        failures.append("duplicate_pid_creation_identity")
    if not runner_rows:
        failures.append("runner_role_missing")
    if not kit_rows:
        failures.append("kit_role_missing")
    if not diagnostic_rows:
        failures.append("diagnostic_role_missing")
    root_pids = {identity[0] for identity in runner_rows}
    if any(norm_path(row.get("path", "missing")) != norm_path(expected_root) for row in runner_rows.values()):
        failures.append("runner_path_mismatch")
    if any(Path(row.get("path", "")).name.lower() != "kit.exe" for row in kit_rows.values()):
        failures.append("kit_image_name_mismatch")
    if root_pids and any(int(row.get("parent_pid", -1)) not in root_pids for row in kit_rows.values()):
        failures.append("kit_not_direct_child_of_runner")
    if set(runner_rows).intersection(kit_rows):
        failures.append("runner_kit_identity_overlap")
    evidence = {
        "runner_identities": sorted([list(value) for value in runner_rows]),
        "kit_identities": sorted([list(value) for value in kit_rows]),
        "diagnostic_identities": sorted([list(value) for value in diagnostic_rows]),
        "runner_paths": sorted({str(row.get("path")) for row in runner_rows.values()}),
        "kit_paths": sorted({str(row.get("path")) for row in kit_rows.values()}),
        "diagnostic_paths": sorted({str(row.get("path")) for row in diagnostic_rows.values()}),
        "duplicate_identity_count": duplicate_identities,
    }
    return not failures, sorted(set(failures)), evidence
