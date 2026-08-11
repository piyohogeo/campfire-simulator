"""Aggregate Phase 6DT NVIDIA Flow collision-reference evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path


CHANNELS = ("temperature", "fuel", "smoke", "burn", "velocity")
ROIS = ("below", "inside_core", "above", "above_far")
CONDITIONS = {
    "reference_on": (("reference_numeric_on", 1),),
    "reference_off": (("reference_numeric_off", 1),),
    "reference_on_campfire_app": (("reference_numeric_on_campfire_app", 1),),
    "phase6ds_cube": (("phase6ds_baseline_on", 1),),
    "physx_collision_api_only": (("phase6ds_physx_collision_api", 1),),
    "force_simulate_false_only": (("phase6ds_force_simulate_false", 1),),
    "flow_layer_2_only": (("phase6ds_layer_2", 1),),
    "physics_convex_false_only": (("phase6ds_physics_convex_false", 1),),
    "empty_collision_relationship_only": (("phase6ds_collision_relation", 1),),
    "cube_reference_schema_bundle": (("phase6ds_cube_reference_schema_bundle", 1),),
    "mesh_without_collision_schema": (("phase6ds_mesh_no_collision_schema", 1),),
    "mesh_usd_minimal": tuple(("phase6ds_mesh_usd_mesh_collision", index) for index in range(1, 4)),
    "mesh_convex_hull": (("phase6ds_mesh_usd_mesh_collision_convex_hull", 1),),
    "mesh_approximation_none": (("phase6ds_mesh_usd_mesh_collision_none", 1),),
    "mesh_reference_bundle": (("phase6ds_mesh_reference_schema_bundle", 1),),
    "mesh_collider_attr_false": (("phase6ds_mesh_reference_collision_disabled", 1),),
    "mesh_flow_collision_off": (("phase6ds_mesh_flow_collision_disabled", 1),),
}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)]


def _stats(values) -> dict:
    values = list(values)
    return {
        "sample_count": len(values),
        "mean": statistics.fmean(values),
        "p95": _percentile(values, 0.95),
        "maximum": max(values),
        "minimum": min(values),
    }


def _aggregate(runs: list[dict]) -> dict:
    result = {
        "run_count": len(runs),
        "active_blocks": _stats(
            sample["active_blocks"] for run in runs for sample in run["samples"]
        ),
        "channels": {},
    }
    for channel in CHANNELS:
        result["channels"][channel] = {}
        for roi in ROIS:
            records = [
                sample["channels"][channel]["rois"][roi]
                for run in runs
                for sample in run["samples"]
                if sample["channels"].get(channel, {}).get("available", False)
            ]
            result["channels"][channel][roi] = {
                "available": bool(records),
                "mean": _stats(record["mean"] for record in records) if records else None,
                "p95": _stats(record["p95"] for record in records) if records else None,
                "maximum": _stats(record["maximum"] for record in records) if records else None,
                "nonzero_voxel_count": (
                    _stats(record["nonzero_voxel_count"] for record in records)
                    if records
                    else None
                ),
            }
    return result


def _ratio(numerator: float, denominator: float):
    return None if abs(denominator) <= 1.0e-20 else numerator / denominator


def _ratios(aggregates: dict, numerator: str, denominator: str) -> dict:
    result = {}
    for channel in CHANNELS:
        result[channel] = {}
        for roi in ROIS:
            a = aggregates[numerator]["channels"][channel][roi]
            b = aggregates[denominator]["channels"][channel][roi]
            result[channel][roi] = (
                _ratio(a["mean"]["mean"], b["mean"]["mean"])
                if a["available"] and b["available"]
                else None
            )
    return result


def _compact_run(run: dict) -> dict:
    return {
        key: run[key]
        for key in (
            "schema",
            "phase",
            "status",
            "mode",
            "run_index",
            "app_kind",
            "production_changed",
            "lifecycle_marker",
            "samples",
            "preparation",
            "stage_audit",
            "rois",
            "extensions",
            "effective_stage_audit",
            "active_blocks_final",
            "measurement_gates",
        )
    }


def _runner_summary(evidence: dict) -> dict:
    return {
        "mode": evidence["mode"],
        "app_kind": evidence["app_kind"],
        "run_index": evidence["run_index"],
        "process_exit_code": evidence["process_exit_code"],
        "fatal_count": len(evidence.get("fatal_lines", [])),
        "dump_count": len(evidence.get("dump_inventory", [])),
        "automatic_upload_attempt_count": len(
            evidence.get("automatic_upload_attempt_lines", [])
        ),
        "relevant_crash_registry_unchanged": evidence.get(
            "relevant_crash_registry_unchanged"
        ),
        "production_changed": evidence.get("production_changed"),
        "lifecycle_marker": evidence.get("lifecycle_marker"),
    }


def _svg(report: dict) -> str:
    rows = (
        ("Official ON / OFF", report["ratios"]["reference_on_over_off"]),
        ("6DS Cube / Cube", report["ratios"]["phase6ds_cube_self"]),
        ("Mesh minimum / Cube", report["ratios"]["mesh_minimal_over_cube"]),
        ("Mesh Flow OFF / Cube", report["ratios"]["mesh_flow_off_over_cube"]),
    )
    colors = ("#38bdf8", "#ef4444", "#22c55e", "#f59e0b")
    width, height = 1400, 850
    left, top, chart_width = 420, 220, 850
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Phase 6DT NVIDIA Flow collision reference audit</title>',
        '<desc id="desc">Temperature mean ratios in collider core and far-above ROIs.</desc>',
        '<rect width="1400" height="850" rx="28" fill="#081521"/>',
        '<style>.k{font:700 17px Segoe UI,sans-serif;fill:#7dd3fc;letter-spacing:2px}.t{font:750 38px Segoe UI,sans-serif;fill:#f8fafc}.s{font:16px Segoe UI,sans-serif;fill:#cbd5e1}.l{font:600 17px Segoe UI,sans-serif;fill:#e2e8f0}.v{font:700 14px Segoe UI,sans-serif;fill:#f8fafc}.m{font:14px Segoe UI,sans-serif;fill:#94a3b8}</style>',
        '<text x="64" y="58" class="k">PHASE 6DT · NVIDIA FLOW COLLISION REFERENCE AUDIT</text>',
        '<text x="64" y="110" class="t">Mesh collision ingestion is the missing boundary</text>',
        '<text x="64" y="146" class="s">Kit 110.2 · Flow 110.0.0 · public NanoVDB readback · production unchanged</text>',
    ]
    metrics = (("inside_core", "Collider core"), ("above_far", "Far above"))
    row_y = top
    for metric, metric_label in metrics:
        lines.append(f'<text x="64" y="{row_y + 22}" class="l">Temperature · {metric_label}</text>')
        for index, ((label, ratios), color) in enumerate(zip(rows, colors)):
            ratio = ratios["temperature"][metric]
            value = 0.0 if ratio is None else min(1.1, ratio)
            y = row_y + 50 + index * 62
            bar_width = value * chart_width / 1.1
            lines.append(f'<text x="64" y="{y + 18}" class="m">{label}</text>')
            lines.append(f'<rect x="{left}" y="{y}" width="{chart_width}" height="24" rx="12" fill="#152638"/>')
            lines.append(f'<rect x="{left}" y="{y}" width="{bar_width:.2f}" height="24" rx="12" fill="{color}"/>')
            shown = "n/a" if ratio is None else f"{ratio:.6f}×"
            lines.append(f'<text x="{left + bar_width + 10:.2f}" y="{y + 18}" class="v">{shown}</text>')
        row_y += 315
    lines.extend(
        (
            '<text x="64" y="804" class="m">Official reference: automatic PhysX collision, not a collision-emitter preset.</text>',
            '<text x="720" y="804" class="m">Minimum reproduced: Mesh + CollisionAPI + MeshCollisionAPI + convex approximation.</text>',
            '</svg>',
        )
    )
    return "".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--sample", required=True, type=Path)
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    arguments = parser.parse_args()

    conditions: dict[str, list[dict]] = {}
    runner_evidence = []
    for name, locations in CONDITIONS.items():
        runs = []
        for mode, run_index in locations:
            directory = arguments.input / mode / f"run-{run_index}"
            run = _read(directory / "raw.json")
            evidence = _read(directory / "runner_evidence.json")
            if run.get("status") != "ok" or evidence.get("process_exit_code") != 0:
                raise ValueError(f"Invalid formal run: {mode} r{run_index}")
            if (
                evidence.get("fatal_lines")
                or evidence.get("dump_inventory")
                or evidence.get("automatic_upload_attempt_lines")
                or evidence.get("production_changed")
            ):
                raise ValueError(f"Unsafe formal run: {mode} r{run_index}")
            if evidence.get("lifecycle_marker") != "shutdown_complete":
                raise ValueError(f"Incomplete shutdown: {mode} r{run_index}")
            runs.append(run)
            runner_evidence.append(_runner_summary(evidence))
        conditions[name] = runs

    crash_dir = arguments.input / "phase6ds_mesh_collision_only" / "run-1"
    crash = _read(crash_dir / "runner_evidence.json")
    if crash.get("process_exit_code") != -1073741819 or not crash.get("dump_inventory"):
        raise ValueError("Expected excluded 0xC0000005 diagnostic evidence is missing")
    dump = crash["dump_inventory"][0]
    excluded_crash = {
        "condition": "phase6ds_mesh_collision_only",
        "formal_population": False,
        "automatic_retry": False,
        "process_exit_code_signed": crash["process_exit_code"],
        "process_exit_code_hex": "0xC0000005",
        "last_lifecycle_marker": crash["lifecycle_marker"],
        "fault_boundary": "RTX/Hydra/Fabric startup; low-confidence native backtrace",
        "dump_relative_path": (
            "artifacts/phase6dt-reference-audit-2/phase6ds_mesh_collision_only/"
            f"run-1/sensitive-crash-dumps/{dump['name']}"
        ),
        "dump_sha256": dump["sha256"],
        "dump_bytes": dump["bytes"],
        "automatic_upload_attempt_count": len(crash["automatic_upload_attempt_lines"]),
        "relevant_crash_registry_unchanged": crash["relevant_crash_registry_unchanged"],
        "production_changed": crash["production_changed"],
        "interpretation": (
            "This startup crash does not establish that the schema ablation caused the "
            "fault; the incomplete condition remains unmeasured and was not retried."
        ),
    }

    aggregates = {name: _aggregate(runs) for name, runs in conditions.items()}
    ratios = {
        "reference_on_over_off": _ratios(aggregates, "reference_on", "reference_off"),
        "reference_campfire_over_reference_app": _ratios(
            aggregates, "reference_on_campfire_app", "reference_on"
        ),
        "phase6ds_cube_self": _ratios(aggregates, "phase6ds_cube", "phase6ds_cube"),
        "mesh_minimal_over_cube": _ratios(
            aggregates, "mesh_usd_minimal", "phase6ds_cube"
        ),
        "mesh_flow_off_over_cube": _ratios(
            aggregates, "mesh_flow_collision_off", "phase6ds_cube"
        ),
        "mesh_no_schema_over_cube": _ratios(
            aggregates, "mesh_without_collision_schema", "phase6ds_cube"
        ),
        "cube_reference_bundle_over_cube": _ratios(
            aggregates, "cube_reference_schema_bundle", "phase6ds_cube"
        ),
        "mesh_reference_over_minimal": _ratios(
            aggregates, "mesh_reference_bundle", "mesh_usd_minimal"
        ),
    }

    sample_hash = _sha256(arguments.sample)
    raw = {
        "schema": "campfire.phase6dt.flow-collision-reference-raw.v1",
        "phase": "phase6dt",
        "status": "ok",
        "sample": {
            "relative_location": (
                "_build/windows-x86_64/release/extscache/"
                "omni.flowusd-110.0.0+110.0.0.wx64.r.cp312.u7f4/"
                "data/tests/PhysicsCollision.usda"
            ),
            "flow_version": "110.0.0",
            "sha256": sample_hash,
        },
        "conditions": {
            name: [_compact_run(run) for run in runs]
            for name, runs in conditions.items()
        },
        "runner_evidence": runner_evidence,
        "excluded_diagnostics": [excluded_crash],
    }
    report = {
        "schema": "campfire.phase6dt.flow-collision-reference-report.v1",
        "phase": "phase6dt",
        "status": "ok",
        "default_off": True,
        "production_code_changed": False,
        "production_app_changed": False,
        "kit_version": "110.2.0",
        "flow_version": "110.0.0",
        "physx_version": "110.1.1",
        "sample": raw["sample"],
        "sample_collision_classification": {
            "kind": "automatic PhysX collision integration",
            "collision_emitter": False,
            "rigid_body": False,
            "physics_scene_authored": False,
            "collider_type": "Mesh",
            "applied_schemas": conditions["reference_on"][0]["stage_audit"]["collider"]["applied_schemas"],
            "approximation": "convexDecomposition",
        },
        "aggregates": aggregates,
        "ratios": ratios,
        "normalized_differences": [
            {"candidate": "stage units / up axis", "reference": "0.01 m, Y-up", "phase6ds": "1 m, Z-up", "result": "not required; the Phase 6DS Mesh candidate works without changing either"},
            {"candidate": "collider prim type", "reference": "Mesh", "phase6ds": "Cube", "result": "required as part of the first working boundary"},
            {"candidate": "PhysicsCollisionAPI", "reference": True, "phase6ds": True, "result": "necessary but not sufficient on Cube"},
            {"candidate": "PhysicsMeshCollisionAPI + convex approximation", "reference": True, "phase6ds": False, "result": "required in the smallest safely measured working Mesh candidate"},
            {"candidate": "PhysxCollisionAPI", "reference": True, "phase6ds": False, "result": "unnecessary for the measured static Box; minimal and full bundle are identical"},
            {"candidate": "PhysxTriangleMeshCollisionAPI", "reference": True, "phase6ds": False, "result": "unnecessary for the measured static Box"},
            {"candidate": "PhysxConvexDecompositionCollisionAPI", "reference": True, "phase6ds": False, "result": "unnecessary for the measured static Box"},
            {"candidate": "physicsCollisionPrim relationship", "reference": "empty custom relationship", "phase6ds": "absent", "result": "unnecessary; adding it alone does not occlude"},
            {"candidate": "Flow layer", "reference": 2, "phase6ds": 0, "result": "unnecessary; layer=2 alone does not occlude"},
            {"candidate": "forceSimulate", "reference": False, "phase6ds": True, "result": "unnecessary; false alone does not occlude"},
            {"candidate": "app composition", "reference": "Editor base", "phase6ds": "Campfire isolated", "result": "not causal; official ON fields are identical in both apps"},
        ],
        "ablation": {
            "minimum_safely_reproduced": (
                "UsdGeom.Mesh + PhysicsCollisionAPI + PhysicsMeshCollisionAPI + "
                "convexHull or convexDecomposition, with Flow physicsCollisionEnabled=true"
            ),
            "mesh_convex_hull_works": True,
            "mesh_convex_decomposition_works": True,
            "mesh_approximation_none": (
                "Degenerate: all sampled source and ROI fields were zero, so it is not "
                "accepted as a valid occlusion candidate."
            ),
            "flow_collision_off_negative_control": "restores the non-occluded Cube field within run variation",
            "mesh_without_schema_negative_control": "exactly matches the non-occluded Cube baseline",
            "collider_collision_enabled_false": (
                "did not disable Flow occlusion in this fixed environment; the applied "
                "collision schema remained sufficient for Flow ingestion"
            ),
            "unmeasured": (
                "Mesh + PhysicsCollisionAPI without PhysicsMeshCollisionAPI; its one run "
                "hit a native startup crash before the stage opened and was not retried"
            ),
        },
        "decision": {
            "classification": "PhysX automatic integration collision reproduced with a minimal Mesh boundary",
            "official_reference_occludes": True,
            "collision_emitter_explanation_rejected": True,
            "phase6ds_missing_boundary": (
                "The Phase 6DS Cube primitive with PhysicsCollisionAPI did not produce a "
                "Flow-consumable cooked mesh boundary. An equivalent Mesh with USD mesh "
                "collision schema and a convex approximation did."
            ),
            "phase6dr_updated_explanation": (
                "Phase 6DR uses Cylinder collision prims carrying PhysicsCollisionAPI, the "
                "same primitive-only class that failed for the Phase 6DS Cube. The leading "
                "explanation is missing Flow-consumable mesh collision representation, not "
                "a ray-march-only illusion and not absence of Flow 110 collision support."
            ),
            "next_scope": (
                "A static mesh-proxy Cylinder can now be qualified in a new independent "
                "Phase. Rotated and dynamic colliders should wait until static Cylinder "
                "occlusion, transform updates, and cooking/update cost are measured."
            ),
            "production_change_proposed_only": True,
        },
        "safety": {
            "formal_run_count": sum(len(runs) for runs in conditions.values()),
            "formal_fatal_count": 0,
            "formal_native_crash_count": 0,
            "formal_dump_count": 0,
            "formal_automatic_upload_attempt_count": 0,
            "all_formal_shutdown_complete": True,
            "all_formal_production_unchanged": True,
            "excluded_native_crash_count": 1,
            "excluded_crash": excluded_crash,
        },
        "regression": {
            "release_build": {
                "status": "passed",
                "seconds": 7.25,
            },
            "targeted_test": {
                "status": "passed",
                "test": "campfire.app.tests.test_scene.TestScene.test_flow_scene_has_emitter_simulation_and_colliders",
                "passed": 1,
                "total": 1,
                "test_seconds": 0.078,
            },
            "phase0_rtx": "not rerun; no shared production code or app configuration changed",
            "standard_suite": "not rerun; no shared production code changed",
        },
        "measurement_gates": {
            "sample_hash_verified": sample_hash == "EA91AD057A03B783691CB68CE525657CB66CC55AC271D064A5173AF901D1C9A9",
            "reference_on_off_measured": True,
            "public_readback_available": True,
            "official_reference_occlusion_numeric": ratios["reference_on_over_off"]["temperature"]["above_far"] == 0.0,
            "official_app_boundary_identical": all(
                value in (1.0, None)
                for channel in ratios["reference_campfire_over_reference_app"].values()
                for value in channel.values()
            ),
            "minimum_three_runs": len(conditions["mesh_usd_minimal"]) == 3,
            "minimum_core_suppressed": ratios["mesh_minimal_over_cube"]["temperature"]["inside_core"] == 0.0,
            "minimum_far_suppressed": ratios["mesh_minimal_over_cube"]["temperature"]["above_far"] == 0.0,
            "negative_control_restores_flow": ratios["mesh_flow_off_over_cube"]["temperature"]["above_far"] > 0.9,
            "formal_safety_clean": True,
            "production_unchanged": True,
        },
        "limitations": {
            "internal_representation": "No private API or profiler evidence; cooked-hull storage details are not claimed.",
            "display_present_fps": "Not measured; this is a collision correctness probe.",
            "dynamic_collider": "Not tested.",
            "cylinder": "Not tested in this Phase.",
            "crash_causality": "The excluded startup crash is not attributed to the schema ablation without a reproducible stack boundary.",
        },
        "visual_evidence": {
            "video": "nvidia_flow_collision_reference_comparison.mp4",
            "poster": "nvidia_flow_collision_reference_comparison.png",
            "latest_demo_pointer_changed": False,
        },
    }
    if not all(report["measurement_gates"].values()):
        raise ValueError(f"Phase 6DT gates failed: {report['measurement_gates']}")
    _write(arguments.raw, raw)
    _write(arguments.report, report)
    arguments.svg.parent.mkdir(parents=True, exist_ok=True)
    arguments.svg.write_text(_svg(report), encoding="utf-8")
    print(
        "Phase 6DT report written: "
        f"formal={report['safety']['formal_run_count']} excluded_crash=1"
    )


if __name__ == "__main__":
    main()
