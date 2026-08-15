"""Phase 6HP topology: Phase 6HO launch shape with a new frozen identity."""

from __future__ import annotations

from pathlib import Path

from phase6hm_process_tree_topology import ROOT, SCRIPTS, build_powershell_target
from phase6ho_process_tree_topology import ANIM, APP, CAMPFIRE, KIT, POWERSHELL, norm


CASE = SCRIPTS / "run_phase6hp_kit_case.ps1"


def build_target(mode: str, paths: dict[str, Path]) -> list[str]:
    probe = SCRIPTS / (
        "probe_phase6hp_app_ready_smoke.py"
        if mode == "smoke"
        else "probe_phase6hp_flow_proxy_boundary.py"
    )
    arguments = [
        "-Mode", mode,
        "-OutputPath", str(paths["output"]),
        "-MarkersPath", str(paths["markers"]),
        "-RunnerEvidencePath", str(paths["runner_evidence"]),
        "-KitLogPath", str(paths["kit_log"]),
        "-KitStdoutPath", str(paths["kit_stdout"]),
        "-KitStderrPath", str(paths["kit_stderr"]),
        "-KitPath", str(KIT),
        "-AppPath", str(APP),
        "-ProbePath", str(probe),
        "-ExpectedCampfirePath", str(CAMPFIRE),
        "-ExpectedAnimPath", str(ANIM),
        "-StageCloseTimeoutSeconds", "180",
    ]
    return build_powershell_target(CASE, arguments)


def validate_target(target: list[str], mode: str) -> tuple[bool, str]:
    expected_probe = SCRIPTS / (
        "probe_phase6hp_app_ready_smoke.py"
        if mode == "smoke"
        else "probe_phase6hp_flow_proxy_boundary.py"
    )
    checks = (
        (target[0], POWERSHELL, "root"),
        (target[target.index("-KitPath") + 1], KIT, "kit"),
        (target[target.index("-AppPath") + 1], APP, "app"),
        (target[target.index("-ProbePath") + 1], expected_probe, "probe"),
    )
    for actual, expected, name in checks:
        if norm(actual) != norm(expected):
            return False, name + "_path_mismatch"
    if norm(target[target.index("-KitPath") + 1]) == norm(KIT.resolve()):
        return False, "kit_path_was_resolved"
    if norm(target[target.index("-AppPath") + 1]) == norm(APP.resolve()):
        return False, "app_path_was_resolved"
    return True, "pass"
