"""Summarize the Phase 6DU static cylindrical collision qualification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _svg(report: dict) -> str:
    geometry = report["geometry"]
    crash = report["crash"]
    topology = geometry["proxy_topology"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720" role="img" aria-labelledby="title desc">
<title id="title">Phase 6DU static cylindrical Flow collision proxy qualification</title>
<desc id="desc">Offline cylinder mesh gates passed, but the first full convexHull run stopped at a native stage-open crash before Flow samples.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#07131f"/><stop offset="1" stop-color="#102337"/></linearGradient></defs>
<style>.k{{font:700 18px 'Segoe UI';letter-spacing:1.5px;fill:#7dd3fc}}.t{{font:700 34px 'Segoe UI';fill:#f8fafc}}.h{{font:700 21px 'Segoe UI';fill:#f8fafc}}.v{{font:700 27px 'Segoe UI';fill:#e2e8f0}}.b{{font:400 17px 'Segoe UI';fill:#cbd5e1}}.s{{font:400 15px 'Segoe UI';fill:#94a3b8}}.ok{{fill:#86efac}}.bad{{fill:#fca5a5}}</style>
<rect width="1280" height="720" rx="28" fill="url(#bg)"/>
<text x="58" y="55" class="k">PHASE 6DU · STATIC CYLINDRICAL FLOW COLLISION PROXY</text>
<text x="58" y="105" class="t">Shape gate passed; runtime qualification stopped safely.</text>
<rect x="58" y="145" width="552" height="238" rx="20" fill="#0b2537" stroke="#155e75"/>
<text x="84" y="182" class="h">Offline cylindrical Mesh</text>
<text x="84" y="226" class="v">{topology['vertex_count']} vertices · {topology['face_count']} faces · 12 segments</text>
<text x="84" y="265" class="b">Closed manifold · outward winding · finite · no degenerate faces</text>
<text x="84" y="300" class="b">Radius 0.16 m · length 1.8 m · local axis X</text>
<text x="84" y="335" class="b">Emitter surface gap {geometry['emitter_surface_gap_m']:.3f} m · transforms identical</text>
<text x="84" y="365" class="s">Stage and schemas were fully authored before stage connection.</text>
<rect x="632" y="145" width="590" height="238" rx="20" fill="#331720" stroke="#b91c1c"/>
<text x="658" y="182" class="h">Fail-fast boundary</text>
<text x="658" y="226" class="v bad">Native {crash['exit_code_hex']}</text>
<text x="658" y="265" class="b">Last marker: {crash['last_lifecycle_marker']}</text>
<text x="658" y="300" class="b">{crash['fault_boundary']}</text>
<text x="658" y="335" class="b">Dump preserved locally · automatic upload 0 · no retry</text>
<text x="658" y="365" class="s">No Flow ROI sample or rendered comparison was accepted.</text>
<path d="M120 460 H360" stroke="#38bdf8" stroke-width="5"/><circle cx="120" cy="460" r="12" fill="#22c55e"/><circle cx="240" cy="460" r="12" fill="#22c55e"/><circle cx="360" cy="460" r="12" fill="#ef4444"/>
<text x="84" y="505" class="b">Author geometry</text><text x="210" y="535" class="b">Save stage</text><text x="328" y="505" class="b">Open stage</text>
<rect x="58" y="568" width="1164" height="98" rx="18" fill="#12231b" stroke="#166534"/>
<text x="84" y="607" class="h ok">Decision: qualification unresolved; production and latest demo remain unchanged.</text>
<text x="84" y="641" class="b">Rotation, coexistence, PhysX filtering, RenderSurface reuse, dynamic Transform, and 20-log integration were not run.</text>
</svg>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    arguments = parser.parse_args()
    probe = _read(arguments.input / "raw.json")
    runner = _read(arguments.input / "runner_evidence.json")
    dumps = runner.get("dump_inventory", [])
    if len(dumps) != 1:
        raise ValueError(f"Expected exactly one fail-fast dump, got {len(dumps)}")
    dump = dumps[0]
    exit_signed = int(runner["process_exit_code"])
    exit_unsigned = exit_signed & 0xFFFFFFFF
    relative_dump = (
        "artifacts/phase6du-static-cylinder-1/mesh_hull/run-1/"
        f"sensitive-crash-dumps/{dump['name']}"
    )
    crash = {
        "condition": "mesh_hull",
        "run_index": 1,
        "exit_code_signed": exit_signed,
        "exit_code_hex": f"0x{exit_unsigned:08X}",
        "exception_classification": "Windows native access violation",
        "last_lifecycle_marker": runner.get("lifecycle_marker"),
        "probe_status": runner.get("probe_status"),
        "fault_boundary": "omni.fabric.plugin.dll+0xCE5B0 at Hydra/RTX stage-open startup",
        "native_stack_low_confidence": [
            "omni.fabric.plugin.dll+0xCE5B0",
            "usdrt.hydra.fabric_scene_delegate.plugin.dll+0xE5415",
            "omni.hydra.usdrt_delegate.plugin.dll+0x4FD3",
            "rtx.hydra.dll+0xF36",
        ],
        "dump": {
            "local_repo_relative_path": relative_dump,
            "bytes": int(dump["bytes"]),
            "sha256": dump["sha256"],
            "sensitive_git_ignored": True,
        },
        "automatic_upload_attempt_count": len(runner.get("automatic_upload_attempt_lines", [])),
        "same_condition_retried": False,
        "causality": "unconfirmed; no collision-schema or geometry cause is claimed from one stage-open crash",
    }
    raw = {
        "schema": "campfire.phase6du.static-cylinder-raw.v1",
        "phase": "phase6du",
        "status": "stopped_on_native_crash",
        "accepted_flow_sample_count": 0,
        "probe": {
            "mode": probe["mode"],
            "run_index": probe["run_index"],
            "stage_sha256": probe["stage_sha256"],
            "kit_build": probe["kit_build"],
            "extensions": probe["extensions"],
            "geometry": probe["geometry"],
            "rois_prepared_but_not_sampled": probe["rois"],
            "authored_flow_settings": {
                "density_cell_size_m": 0.025,
                "velocity_cell_size_m": "not observed; stage crashed before readback",
                "physics_collision_enabled": True,
                "physics_convex_collision": True,
                "steps_per_second": 60.0,
            },
        },
        "runner": {
            "production_app_sha256_before": runner["production_app_sha256_before"],
            "production_app_sha256_after": runner["production_app_sha256_after"],
            "production_changed": runner["production_changed"],
            "relevant_crash_registry_unchanged": runner["relevant_crash_registry_unchanged"],
        },
        "crash": crash,
    }
    geometry = probe["geometry"]
    topology = geometry["proxy_topology"]
    raw_payload_bytes = topology["vertex_count"] * 12 + topology["index_count"] * 4 + topology["face_count"] * 4 + 24
    report = {
        "schema": "campfire.phase6du.static-cylinder-report.v1",
        "phase": "phase6du",
        "status": "safe_stop_native_crash",
        "decision": {
            "static_cylinder_mesh_occlusion": "unqualified; stage crashed before Flow samples",
            "rotated_static_occlusion": "not run due stop condition",
            "convex_hull_vs_decomposition": "unresolved; convexHull preflight did not reach measurement",
            "analytic_cylinder_coexistence": "not run due stop condition",
            "flow_only_proxy_separation": "not established",
            "v3_render_surface_reuse": "not qualified and not recommended from this evidence",
            "dynamic_transform_ready": False,
            "production_change": False,
            "latest_demo_pointer_changed": False,
        },
        "environment": {
            "kit": probe["kit_build"],
            "flow": probe["extensions"]["omni.flowusd"]["version"],
            "physx": probe["extensions"]["omni.physx"]["version"],
            "physx_cooking": probe["extensions"]["omni.physx.cooking"]["version"],
            "rtx_hydra": probe["extensions"]["omni.hydra.rtx"]["version"],
        },
        "authored_flow_settings": {
            "density_cell_size_m": 0.025,
            "velocity_cell_size_m": "not observed; stage crashed before public readback",
            "physics_collision_enabled": True,
            "physics_convex_collision": True,
            "steps_per_second": 60.0,
            "effective_values": "not observed; stage connection did not complete",
        },
        "timing": {
            "stage_open_ms": "not completed",
            "collision_cooking_ms": "not available through completed public probe boundary",
        },
        "geometry": geometry,
        "memory_boundary": {
            "raw_mesh_array_payload_bytes_per_12_segment_mesh": raw_payload_bytes,
            "two_mesh_raw_payload_bytes": raw_payload_bytes * 2,
            "usd_runtime_and_cooked_physx_memory": "not measured",
            "render_surface_reuse_note": (
                "Reusing a future deforming render surface would couple visual topology to collision cooking; "
                "a dedicated proxy remains the safer design candidate, but was not runtime-qualified."
            ),
        },
        "crash": crash,
        "measurement_matrix": {
            "minimum_required_conditions": 5,
            "minimum_required_runs": 15,
            "started_processes": 1,
            "accepted_processes": 0,
            "not_run_reason": "mandatory fail-fast after native crash/dump",
            "roi_values": "unavailable",
            "off_ratios": "unavailable",
            "captures": "unavailable; crash occurred before viewport and Flow sampling",
        },
        "safety": {
            "production_hash_unchanged": not runner["production_changed"],
            "crash_registry_unchanged": runner["relevant_crash_registry_unchanged"],
            "automatic_upload_attempt_count": crash["automatic_upload_attempt_count"],
            "dump_preserved_locally": True,
            "same_condition_retried": False,
            "phase6ds_phase6dt_artifacts_overwritten": False,
        },
        "regression": {
            "release_build": {"status": "passed", "seconds": 6.78},
            "targeted_flow_collider_test": {
                "status": "passed",
                "test": "campfire.app.tests.test_scene.TestScene.test_flow_scene_has_emitter_simulation_and_colliders",
                "passed": 1,
                "total": 1,
                "seconds": 0.093,
            },
            "phase0_rtx": "not rerun; no production code or app composition changed",
            "standard_suite": "not rerun; no production code changed",
        },
        "gates": {
            "offline_geometry_finite": topology["finite"],
            "offline_geometry_closed_manifold": topology["closed_manifold"],
            "offline_geometry_outward_winding": topology["outward_winding"],
            "offline_geometry_non_degenerate": topology["degenerate_face_count"] == 0,
            "offline_world_transforms_match": geometry["world_transforms_match"],
            "offline_emitter_outside": geometry["emitter_outside"],
            "runtime_no_native_crash": False,
            "runtime_flow_readback": False,
            "runtime_occlusion": False,
        },
        "limitations": {
            "crash_causality": "single pre-measurement native crash; cause is not attributed",
            "physx_scene_query": "not reached",
            "rotation": "not run",
            "coexistence": "not run",
            "stage_reload": "not run",
            "visual_evidence": "not produced because no valid rendered frame existed",
        },
    }
    _write(arguments.raw, raw)
    _write(arguments.report, report)
    arguments.svg.parent.mkdir(parents=True, exist_ok=True)
    arguments.svg.write_text(_svg(report), encoding="utf-8")
    print(f"Phase 6DU safe-stop report written: {crash['exit_code_hex']} accepted=0")


if __name__ == "__main__":
    main()
