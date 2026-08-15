"""No-Kit Phase 6HP junction-aware validator and exact-command fixture."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from phase6hl_guard_preflight import build_guard_command
from phase6ho_app_ready_environment import write_json
from phase6hp_junction_module_path import (
    EXPECTED_MODULE_FILE,
    JUNCTION_PATH,
    actual_no_kit_evidence,
    collect_module_path_evidence,
    validate_evidence_population,
    validate_module_path_evidence,
)
from phase6hp_process_tree_topology import ROOT, build_target, validate_target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.artifact_root.absolute()
    if root.exists():
        raise RuntimeError("Phase 6HP preflight refuses root reuse")
    root.mkdir(parents=True)

    contract = ROOT / "scripts/phase6hp_junction_app_ready_contract.json"
    sidecar = ROOT / "scripts/phase6hp_junction_app_ready_contract.sha256"
    digest = hashlib.sha256(contract.read_bytes()).hexdigest().upper()
    expected_digest = sidecar.read_text(encoding="ascii").split()[0].upper()
    actual = actual_no_kit_evidence()
    write_json(root / "actual_junction_evidence.json", actual)
    cases: list[dict] = []

    def check(name: str, value: dict, expected: tuple[bool, str]) -> None:
        observed = validate_module_path_evidence(value)
        cases.append(
            {
                "name": name,
                "status": "pass" if observed == expected else "fail",
                "expected": list(expected),
                "observed": list(observed),
            }
        )

    check("actual_source_spelling_positive", actual, (True, "pass"))
    lexical_module = collect_module_path_evidence(
        extension_id="campfire.app-0.1.0",
        extension_root=JUNCTION_PATH.parent,
        module_name="campfire.app",
        package_name="campfire",
        module_file=JUNCTION_PATH / "app/__init__.py",
    )
    check("lexical_junction_spelling_positive", lexical_module, (True, "pass"))

    mutations = (
        ("repository_external_target", "junction_target_resolved", r"c:\windows", "junction_target_resolved_mismatch"),
        ("different_extension_target", "junction_target_resolved", str(ROOT / "source/extensions/other/campfire"), "junction_target_resolved_mismatch"),
        ("wrong_junction_name", "junction_relative_path", "campfire_wrong", "junction_relative_path_mismatch"),
        ("wrong_extension_root", "extension_root_lexical", str(ROOT / "source/extensions/campfire.app"), "extension_root_lexical_mismatch"),
        ("wrong_extension_id", "extension_id", "other.app-0.1.0", "extension_id_mismatch"),
        ("wrong_extension_version", "extension_version", "0.2.0", "extension_version_mismatch"),
        ("broken_junction", "junction_exists", False, "junction_missing_or_broken"),
        ("non_junction_directory", "junction_is_reparse_point", False, "junction_not_reparse_point"),
        ("wrong_reparse_tag", "junction_reparse_tag", 0, "junction_reparse_tag_mismatch"),
        ("path_traversal", "junction_relative_path", "../campfire", "junction_relative_path_mismatch"),
        ("nested_junction_chain", "junction_chain_depth", 2, "junction_chain_not_allowed"),
        ("resolved_module_outside_target", "module_file_resolved", r"c:\windows\__init__.py", "module_resolved_outside_expected_target"),
        ("contradictory_membership", "module_file_under_resolved_target", False, "module_resolved_target_membership_false"),
        ("extension_root_reparse", "extension_root_is_reparse_point", True, "extension_root_unexpected_reparse_point"),
    )
    for name, key, value, reason in mutations:
        row = copy.deepcopy(actual)
        row[key] = value
        check(name, row, (False, reason))

    missing = copy.deepcopy(actual)
    del missing["module_file_resolved"]
    check("missing_evidence", missing, (False, "evidence_missing:module_file_resolved"))
    unknown = copy.deepcopy(actual)
    unknown["unexpected"] = True
    check("unknown_evidence", unknown, (False, "evidence_unknown:unexpected"))
    invalid_type = copy.deepcopy(actual)
    invalid_type["junction_chain_depth"] = True
    check("invalid_type", invalid_type, (False, "evidence_int_invalid:junction_chain_depth"))
    duplicate_observed = validate_evidence_population((actual, copy.deepcopy(actual)))
    cases.append(
        {
            "name": "duplicate_evidence",
            "status": "pass" if duplicate_observed == (False, "evidence_population_duplicate") else "fail",
            "expected": [False, "evidence_population_duplicate"],
            "observed": list(duplicate_observed),
        }
    )
    missing_population = validate_evidence_population(())
    cases.append(
        {
            "name": "missing_evidence_population",
            "status": "pass" if missing_population == (False, "evidence_population_missing") else "fail",
            "expected": [False, "evidence_population_missing"],
            "observed": list(missing_population),
        }
    )

    path_names = ("output", "markers", "runner_evidence", "kit_log", "kit_stdout", "kit_stderr")
    paths = {name: root / (name + ".json") for name in path_names}
    target = build_target("smoke", paths)
    target_observed = validate_target(target, "smoke")
    cases.append(
        {
            "name": "exact_lexical_smoke_command",
            "status": "pass" if target_observed == (True, "pass") else "fail",
            "expected": [True, "pass"],
            "observed": list(target_observed),
            "kit_launch_count": 0,
        }
    )
    safety = json.loads(contract.read_text(encoding="utf-8"))["safety"]
    guard_paths = {
        "trace": root / "guard-shape-resource.jsonl",
        "summary": root / "guard-shape-summary.json",
        "child_stdout": root / "guard-shape.stdout.log",
        "child_stderr": root / "guard-shape.stderr.log",
        "cleanup": root / "guard-shape-cleanup.jsonl",
        "lifecycle": paths["output"],
        "gpu": root / "guard-shape-gpu.csv",
    }
    guard_command = build_guard_command(
        Path(r"C:\Python38\python.exe"),
        ROOT / "scripts/phase6fu_resource_guard.py",
        guard_paths,
        target,
        attempt_id="phase6hp-shape",
        safety=safety,
        include_gpu=True,
    )
    guard_shape_ok = guard_command[-len(target) :] == target and guard_command[guard_command.index("--") + 1 :] == target
    cases.append(
        {
            "name": "actual_guard_builder_binding",
            "status": "pass" if guard_shape_ok else "fail",
            "target_preserved": guard_shape_ok,
            "kit_launch_count": 0,
        }
    )

    status = "pass" if digest == expected_digest and all(case["status"] == "pass" for case in cases) else "fail"
    summary = {
        "schema": "campfire.phase6hp.preflight.v1",
        "status": status,
        "contract_sha256": digest,
        "case_count": len(cases),
        "cases": cases,
        "kit_launch_count": 0,
        "phase6ho_preserved": True,
        "root_reused": False,
        "filesystem_changes": False,
        "actual_evidence_path": str(root / "actual_junction_evidence.json"),
    }
    write_json(root / "summary.json", summary)
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
