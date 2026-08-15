"""No-Kit preflight for the Phase 6IE bounded live-stage Prim policy."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import phase6ic_exact_dependency_loader as dependency_loader
from phase6hu_atomic_fixture import run_fixture as run_atomic
from phase6hx_point_policy_fixture import run_fixture as run_point
from phase6hy_exact_import_fixture import run_fixture as run_exact
from phase6ic_no_kit_fixture import run_fixture as run_dependencies
from phase6id_float3_fixture import run_fixture as run_float3
from phase6ie_marker_fixture import run_fixture as run_markers
from phase6ie_runtime_prim_fixture import run_fixture as run_runtime_policy


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CONTRACT = SCRIPTS / "phase6ie_stage_open_contract.json"
SIDECAR = SCRIPTS / "phase6ie_stage_open_contract.sha256"
MANIFEST = SCRIPTS / "phase6ie_authoring_dependencies.json"
MANIFEST_SHA = SCRIPTS / "phase6ie_authoring_dependencies.sha256"
OLD_MANIFEST = SCRIPTS / "phase6id_authoring_dependencies.json"
OLD_MANIFEST_SHA = SCRIPTS / "phase6id_authoring_dependencies.sha256"
FROZEN = SCRIPTS / "phase6hx_single_log_occlusion_contract.json"
POINT = SCRIPTS / "phase6hx_point_policy_source_set.json"
POINT_SHA = SCRIPTS / "phase6hx_point_policy_source_set.sha256"
REPORT_SCHEMA = SCRIPTS / "phase6hs_operation_report_schema.json"
PROJECTION = SCRIPTS / "phase6ie_phase6id_runtime_projection.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_root.absolute()
    if root.exists():
        raise RuntimeError("Phase 6IE preflight refuses root reuse")
    root.mkdir(parents=True)
    policy = json.loads(CONTRACT.read_text(encoding="utf-8"))
    digest = sha(CONTRACT)

    runtime_policy = run_runtime_policy(root / "runtime-policy", PROJECTION)
    markers = run_markers(root / "markers")
    float3 = run_float3(root / "float3", FROZEN)
    dependencies = run_dependencies(root / "phase6id-dependencies", OLD_MANIFEST, OLD_MANIFEST_SHA, ROOT, FROZEN)
    exact = run_exact(root / "exact")
    point = run_point(root / "point", POINT, POINT_SHA, ROOT)
    atomic = run_atomic(root / "atomic", FROZEN, REPORT_SCHEMA)

    manifest, manifest_audit = dependency_loader.read_manifest(MANIFEST, MANIFEST_SHA, ROOT)
    selected = ["stage_builder", "atomic_report", "stage_authoring", "runtime_prim_policy"]
    modules, loaded_audit = dependency_loader.load_dependencies(manifest, manifest_audit, module_ids=selected)
    modules["stage_authoring"].configure_repository_dependencies(modules["stage_builder"].topology)
    manifest_loaded = (
        [item["module_id"] for item in loaded_audit] == selected
        and callable(modules["runtime_prim_policy"].validate_projection)
        and len(manifest_audit["modules"]) == 5
    )
    dependency_loader.unload_dependencies(loaded_audit)

    checks = {
        "contract_digest": digest == SIDECAR.read_text(encoding="ascii").split()[0].upper(),
        "manifest_digest": sha(MANIFEST) == MANIFEST_SHA.read_text(encoding="ascii").split()[0].upper() == policy["dependency_manifest"]["sha256"],
        "new_manifest_exact_load": manifest_loaded,
        "phase6id_frozen": policy["frozen_history"]["phase6id"]["status"] == "safe_stop_live_stage_prim_set_validation_failure" and policy["frozen_history"]["reclassified"] is False,
        "runtime_policy_fixture": runtime_policy["status"] == "qualified",
        "marker_fixture": markers["status"] == "qualified",
        "float3_fixture": float3["status"] == "qualified",
        "dependency_fixture": dependencies["status"] == "qualified",
        "exact_loader": exact["status"] == "qualified",
        "point_policy": point["status"] == "qualified",
        "atomic_report": atomic["status"] == "qualified",
        "kit_not_launched": all(item["kit_launch_count"] == 0 for item in (runtime_policy, markers, float3, dependencies, exact, point, atomic)),
        "one_runtime_launch": policy["smoke"]["launches"] == 1 and policy["smoke"]["retry"] == policy["smoke"]["replacement"] == 0,
        "forbidden_zero": all(policy["smoke"][name] == 0 for name in ("timeline_play_calls", "flow_update_calls", "flow_interface_calls", "readback_calls", "capture_calls")),
        "bounded_policy": policy["runtime_prim_policy"]["maximum_runtime_prims"] == 14 and policy["runtime_prim_policy"]["maximum_evidence_bytes"] == 524288,
    }
    report = {
        "schema": "campfire.phase6ie.preflight.v1",
        "phase": "phase6ie",
        "status": "qualified" if all(checks.values()) else "failed",
        "contract_sha256": digest,
        "manifest_sha256": sha(MANIFEST),
        "kit_launch_count": 0,
        "checks": checks,
        "fixture_counts": {
            "runtime_policy": runtime_policy["case_count"],
            "markers": markers["case_count"],
            "float3": float3["case_count"],
            "dependencies": dependencies["case_count"],
            "exact": [exact["case_count"], exact["case_count"]],
            "point": [point["case_count"], point["case_count"]],
            "atomic": [sum(item["passed"] for item in atomic["cases"]), len(atomic["cases"])],
            "new_manifest_modules": [len(loaded_audit), len(manifest_audit["modules"]) - 1],
        },
        "phase6id_reclassified": False,
        "phase6id_artifact_or_runtime_reused": False,
    }
    (root / "preflight_report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return 0 if report["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
