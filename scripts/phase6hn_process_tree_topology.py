"""Phase 6HN launch topology, reusing the frozen Phase 6HM validators."""

from __future__ import annotations

from pathlib import Path

from phase6hm_process_tree_topology import (  # noqa: F401
    APP,
    KIT,
    POWERSHELL,
    ROOT,
    SCRIPTS,
    build_powershell_target,
    norm_path,
    validate_trace_roles,
)


CASE_RUNNER = SCRIPTS / "run_phase6hn_flow_proxy_case.ps1"
PROBE = SCRIPTS / "probe_phase6hn_flow_proxy_boundary.py"


def build_formal_target(paths: dict, stage_close_timeout_seconds: int) -> list:
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


def validate_formal_target(target: list) -> tuple:
    if not target:
        return False, "target_command_too_short"
    if norm_path(target[0]) != norm_path(POWERSHELL):
        if Path(target[0]).name.lower() == "kit.exe":
            return False, "direct_kit_guarded_root_forbidden"
        return False, "guarded_root_path_mismatch"
    try:
        expected = (
            (target[target.index("-File") + 1], CASE_RUNNER, "case_runner_path_mismatch"),
            (target[target.index("-KitPath") + 1], KIT, "kit_child_path_mismatch"),
            (target[target.index("-AppPath") + 1], APP, "app_path_mismatch"),
            (target[target.index("-ProbePath") + 1], PROBE, "probe_path_mismatch"),
        )
    except (ValueError, IndexError):
        return False, "formal_target_required_argument_missing"
    for observed, required, reason in expected:
        if norm_path(observed) != norm_path(required):
            return False, reason
    return True, "pass"

