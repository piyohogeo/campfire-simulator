"""No-Kit cross-contract and producer-to-consumer preflight for Phase 6IA."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from phase6hu_atomic_fixture import run_fixture as run_atomic_fixture
from phase6hx_point_policy_fixture import run_fixture as run_point_fixture
from phase6hx_stage_fixture import run_fixture as run_stage_fixture
from phase6hy_exact_import_fixture import run_fixture as run_exact_import_fixture
from phase6hy_probe_source import build_probe_source
from phase6hz_marker_fixture import run_fixture as run_marker_fixture


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PARENT = SCRIPTS / "phase6ia_single_log_occlusion_contract.json"
PARENT_SIDECAR = SCRIPTS / "phase6ia_single_log_occlusion_contract.sha256"
CHILD = SCRIPTS / "phase6hx_single_log_occlusion_contract.json"
SCHEMA = SCRIPTS / "phase6hs_operation_report_schema.json"
MANIFEST = SCRIPTS / "phase6hx_point_policy_source_set.json"
MANIFEST_SIDECAR = SCRIPTS / "phase6hx_point_policy_source_set.sha256"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_root.absolute()
    if root.exists():
        raise RuntimeError("Phase 6IA preflight refuses root reuse")
    root.mkdir(parents=True)
    parent = json.loads(PARENT.read_text(encoding="utf-8"))
    child = json.loads(CHILD.read_text(encoding="utf-8"))
    parent_sha = sha(PARENT)
    exact = run_exact_import_fixture(root / "exact_import")
    marker = run_marker_fixture(root / "marker")
    point = run_point_fixture(root / "point_policy", MANIFEST, MANIFEST_SIDECAR, ROOT)
    atomic = run_atomic_fixture(root / "atomic", CHILD, SCHEMA)
    stage = run_stage_fixture(root / "stage", CHILD)
    operation_source = build_probe_source(SCRIPTS / "probe_phase6hw_single_log_occlusion.py")
    compile(operation_source, str(SCRIPTS / "probe_phase6ia_single_log_occlusion.py"), "exec")
    exact_policy = parent["exact_import"]
    child_ref = parent["frozen_probe_contract"]
    wrapper = SCRIPTS / Path(exact_policy["wrapper"]).name
    source_checks = {
        "parent_contract_digest": parent_sha == PARENT_SIDECAR.read_text(encoding="ascii").split()[0].upper(),
        "child_contract_digest": sha(CHILD) == child_ref["sha256"],
        "operation_schema_digest": sha(SCHEMA) == child_ref["operation_schema_sha256"],
        "phase6hz_contract_digest": sha(SCRIPTS / exact_policy["qualified_phase6hz_contract"]["path"].split("scripts/", 1)[1]) == exact_policy["qualified_phase6hz_contract"]["sha256"],
        "loader_digest": sha(SCRIPTS / Path(exact_policy["loader"]["path"]).name) == exact_policy["loader"]["sha256"],
        "marker_contract_digest": sha(SCRIPTS / Path(exact_policy["marker_contract"]["path"]).name) == exact_policy["marker_contract"]["sha256"],
        "wrapper_digest": sha(wrapper) == exact_policy["wrapper_sha256"],
        "probe_builder_digest": sha(SCRIPTS / Path(exact_policy["probe_builder"]["path"]).name) == exact_policy["probe_builder"]["sha256"],
    }
    stage_cases = {case["name"]: case["passed"] for case in stage["cases"]}
    fixed = child["fixed_scene"]
    scene_checks = {
        "closed_proxy_topology": fixed["proxy_closed_outward"] is True and [fixed["proxy_vertices"], fixed["proxy_faces"], fixed["proxy_indices"]] == [26, 36, 120],
        "emitter_directly_below": fixed["source_center_m"][:2] == fixed["log_center_m"][:2] and fixed["source_center_m"][2] < fixed["log_center_m"][2],
        "end_clearance_fixed": fixed["source_to_nearest_end_clearance_m"] == 1.6 and fixed["end_clearance_in_velocity_voxels"] == 32.0,
        "camera_end_on": fixed["log_axis"] == "X" and fixed["camera_eye_m"][1:] == fixed["camera_target_m"][1:] and fixed["camera_image_up"] == "world Z",
        "stable_window_fixed": fixed["stable_capture_frames"] == child["temporal_measurement"]["stable_window_frames"],
        "readback_zero": fixed["readback_calls"] == 0 and all(token not in operation_source for token in ("get_latest_nanovdb_readback", "buffer_to_volume", "save_volume", "_sample_grid")),
        "one_variable_stage_diff": stage_cases.get("one_variable_usd_diff") is True,
        "normalized_stage_identity": stage_cases.get("normalized_stage_identity") is True,
        "accepted_lifecycle_policy": child["accepted_classifications"] == ["natural_clean_exit", "cleanup_assisted_telemetry_exit", "cleanup_assisted_ngx_exit"],
        "resource_limits": child["safety"]["kit_private_limit_bytes"] == 16 * 1024**3 and child["safety"]["unique_tree_private_limit_bytes"] == 17 * 1024**3,
    }
    checks = {
        **source_checks,
        **scene_checks,
        "phase6hz_exact_import_fixture": exact["status"] == "qualified",
        "phase6hz_marker_fixture": marker["status"] == "qualified",
        "point_policy_fixture": point["status"] == "qualified" and point["canonical_entry_count"] == 13,
        "atomic_report_fixture": atomic["status"] == "qualified",
        "generated_stage_fixture": stage["status"] == "qualified",
        "operation_source_compiles": True,
        "kit_not_launched": all(item["kit_launch_count"] == 0 for item in (exact, marker, point, atomic, stage)),
    }
    report = {
        "schema": "campfire.phase6ia.no-kit-preflight.v1",
        "phase": "phase6ia",
        "status": "qualified" if all(checks.values()) else "failed",
        "contract_sha256": parent_sha,
        "frozen_probe_contract_sha256": sha(CHILD),
        "kit_launch_count": 0,
        "checks": checks,
        "fixture_counts": {"exact_import": exact["case_count"], "marker": marker["case_count"], "point_policy": point["case_count"], "atomic": len(atomic["cases"]), "stage": len(stage["cases"])},
        "phase6hv_reclassified": False,
        "phase6hw_hx_hy_hz_artifacts_reused": False,
    }
    (root / "preflight_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())

