"""No-Kit fixtures for the Phase 6GZ frozen boundary ladder."""

from __future__ import annotations

import ast
import json
import tempfile
from pathlib import Path

from phase6gz_boundary_contract import (
    LADDER, REQUIRED_BOUNDARY_MARKERS, candidate_level, classify_boundary,
    classify_historical_candidate, validate_ladder, validate_temporary_path,
)
from run_phase6gz_boundary_ladder import build_command

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/probe_phase6gz_candidate_boundary.py"
CONTRACT = ROOT / "scripts/phase6gz_boundary_contract.json"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def main() -> int:
    source = SCRIPT.read_text(encoding="utf-8")
    ast.parse(source)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    result = validate_ladder(contract["ladder"])
    require(result["pass"], str(result))
    require([candidate_level(f"R{i}") for i in range(7)] == list(range(7)), "candidate levels")
    require(contract["execution"]["retries"] == 0 and contract["execution"]["replacements"] == 0,
            "retry/replacement disabled")
    require(contract["execution"]["stop_after_first_non_normal_result"], "fail closed ladder")
    policy = contract["historical_evidence_policy"]
    require(policy["primary_unintervened_candidate_timeouts"]["total"] == 31, "primary population")
    require(policy["phase6gy_launch23"]["classification_for_mechanism_inference"] ==
            "user-intervention-contaminated", "launch23 contamination")
    require(not policy["phase6gy_launch23"]["natural_second_outcome_claim_allowed"], "no natural AV claim")
    require(classify_historical_candidate("phase6gy", 23) == "user-intervention-contaminated", "classifier")
    require(classify_historical_candidate("phase6gy", 22) == "primary-unintervened", "primary classifier")
    for marker in REQUIRED_BOUNDARY_MARKERS:
        require(marker in source, f"missing marker: {marker}")
    for forbidden in ("gc.collect(", "np.asarray(", "ReadAllBytes", "Get-Content"):
        require(forbidden not in source, f"forbidden operation in probe: {forbidden}")
    boundary_start = source.index("def _phase6gz_boundary")
    positions = [source.index(token, boundary_start) for token in (
        'marker("phase6gz_temperature_entry"',
        "if LEVEL >= 1:",
        "if LEVEL >= 2:",
        "if LEVEL >= 3:",
        "if LEVEL >= 4:",
        "if LEVEL >= 5:",
        "if LEVEL >= 6:",
    )]
    require(positions == sorted(positions), "temperature prefix operation order")
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder).resolve()
        require(validate_temporary_path(root, root / "p3_f0180_temperature.nvdb")["pass"], "allowlisted temp")
        require(not validate_temporary_path(root, root / "unknown.nvdb")["pass"], "unknown temp rejected")
        require(not validate_temporary_path(root, root.parent / "p3_f0180_temperature.nvdb")["pass"], "outside temp rejected")
        command = build_command("candidate_temperature_save", "candidate", "R3", root / "attempt", contract)
        command_text = "\n".join(command)
        require("probe_phase6gz_candidate_boundary.py" in command_text, "exact candidate probe")
        require("phase6gz" in command and "R3" in command, "runtime token and mode")
        require("-SkipLowLevelShutdownDiagnostic" not in command, "progress-aware CDB retained")
        require(command.count("180") >= 3, "frame/readback/stage-close values")
    require(classify_boundary(["readback", "save"], 0, False)["classification"] == "normal_exit", "normal classify")
    require(classify_boundary(["readback"], 3221225477, False)["classification"] ==
            "windows_native_exception", "native classify")
    require(classify_boundary(["readback"], None, True)["classification"] == "timeout", "timeout classify")
    print(json.dumps({"passed": True, "cases": 42, "kit_started": False,
                      "ladder": [name for name, _, _, _ in LADDER]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
