"""Evaluate the predeclared Phase 6EF static-Y40 qualification contract."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import shutil
import zipfile

import numpy as np


CONDITIONS = ("A_axis_on", "B_rotate_y40_on", "C_rotate_y40_off")
FRAMES = (60, 120, 180, 200)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def finite(value: float) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("non-finite Phase 6EF statistic")
    return result


def summarize(values: np.ndarray, thresholds: tuple[float, ...]) -> dict:
    values = np.asarray(values, dtype=np.float64)
    if not values.size:
        return {
            "available": False,
            "voxel_count": 0,
            "mean": 0.0,
            "p50": 0.0,
            "p95": 0.0,
            "maximum": 0.0,
            "threshold_counts": {f"{value:.12g}": 0 for value in thresholds},
        }
    return {
        "available": True,
        "voxel_count": int(values.size),
        "mean": finite(np.mean(values)),
        "p50": finite(np.percentile(values, 50)),
        "p95": finite(np.percentile(values, 95)),
        "maximum": finite(np.max(values)),
        "threshold_counts": {
            f"{value:.12g}": int(np.count_nonzero(values > value)) for value in thresholds
        },
    }


def region_masks(payload) -> dict[str, np.ndarray]:
    inside = payload["mesh_inside"].astype(bool)
    depth = -payload["mesh_distance_voxels"].astype(np.float64)
    voxel = float(np.mean(payload["voxel_size_xyz"]))
    axis_inside = payload["axis_reference_mesh_inside"].astype(bool)
    axis_depth = -payload["axis_reference_mesh_signed_distance_m"].astype(np.float64) / voxel
    rotated_deep = inside & (depth > 1.0)
    axis_deep = axis_inside & (axis_depth > 1.0)
    return {
        "outside_halo": ~inside,
        "boundary_0_to_1_voxel": inside & (depth >= 0.0) & (depth <= 1.0),
        "deep_interior": rotated_deep,
        "center_axis_near": rotated_deep
        & (payload["axis_radial_distance_m"].astype(np.float64) <= 0.5 * voxel),
        "axis_reference_deep": axis_deep,
        "rotated_only": rotated_deep & ~axis_inside,
        "axis_only": axis_deep & ~inside,
        "overlap": rotated_deep & axis_deep,
    }


def sample_stats(path: Path, thresholds: tuple[float, ...]) -> tuple[dict, dict]:
    with np.load(path, allow_pickle=False) as payload:
        magnitude = payload["magnitude"].astype(np.float64)
        masks = region_masks(payload)
        stats = {name: summarize(magnitude[mask], thresholds) for name, mask in masks.items()}
        metadata = {
            "path": str(path),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
            "velocity_voxel_size_m": finite(np.mean(payload["voxel_size_xyz"])),
            "actual_mesh_vs_ideal_cylinder_disagreement_count": int(
                np.count_nonzero(payload["analytic_mesh_classification_differs"])
            ),
            "geometry_labels_are_flow_occupancy": bool(
                payload["flow_collision_occupancy_mask_available"][0]
            ),
        }
    return stats, metadata


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0.0:
        return None
    return finite(numerator / denominator)


def evaluate_samples(samples: dict, contract: dict) -> tuple[dict, list[dict]]:
    limits = contract["thresholds"]
    velocity_limit = float(limits["existing_velocity_limit_m_s"])
    positive = float(limits["collision_off_positive_minimum_m_s"])
    suppression = float(limits["rotated_on_to_off_deep_maximum_ratio"])
    axis_positive = float(limits["axis_only_comparison_minimum_off_m_s"])
    axis_ratio_min = float(limits["axis_only_on_to_off_minimum_ratio"])
    checks: list[dict] = []
    ratios = {}
    for run_index in range(1, 4):
        run_key = str(run_index)
        ratios[run_key] = {}
        for frame in FRAMES:
            frame_key = str(frame)
            a = samples[run_key]["A_axis_on"][frame_key]
            b = samples[run_key]["B_rotate_y40_on"][frame_key]
            c = samples[run_key]["C_rotate_y40_off"][frame_key]
            values = {
                "A_deep": a["deep_interior"]["maximum"],
                "A_center": a["center_axis_near"]["maximum"],
                "B_deep": b["deep_interior"]["maximum"],
                "B_center": b["center_axis_near"]["maximum"],
                "C_deep": c["deep_interior"]["maximum"],
                "C_center": c["center_axis_near"]["maximum"],
                "B_axis_only": b["axis_only"]["maximum"],
                "C_axis_only": c["axis_only"]["maximum"],
            }
            deep_ratio = _ratio(values["B_deep"], values["C_deep"])
            axis_ratio = _ratio(values["B_axis_only"], values["C_axis_only"])
            ratios[run_key][frame_key] = {
                "B_over_C_deep_maximum": deep_ratio,
                "B_over_C_axis_only_maximum": axis_ratio,
                "values_m_s": values,
            }
            predicates = {
                "A_deep_at_or_below_limit": values["A_deep"] <= velocity_limit,
                "A_center_at_or_below_limit": values["A_center"] <= velocity_limit,
                "B_deep_at_or_below_limit": values["B_deep"] <= velocity_limit,
                "B_center_at_or_below_limit": values["B_center"] <= velocity_limit,
                "C_deep_positive": values["C_deep"] >= positive,
                "C_center_positive": values["C_center"] >= positive,
                "B_over_C_deep_suppressed": deep_ratio is not None and deep_ratio <= suppression,
                "axis_only_C_comparable": values["C_axis_only"] >= axis_positive,
                "axis_only_not_stale_suppressed": axis_ratio is not None
                and axis_ratio >= axis_ratio_min,
            }
            checks.append(
                {
                    "run": run_index,
                    "frame": frame,
                    "values_m_s": values,
                    "ratios": ratios[run_key][frame_key],
                    "predicates": predicates,
                    "pass": all(predicates.values()),
                }
            )
    return ratios, checks


def make_svg(report: dict, root: Path) -> str:
    datasets = []
    global_max = 1.0e-9
    for condition in CONDITIONS:
        path = root / "spatial" / "run_1" / condition / f"{condition}_f0200_velocity.npz"
        with np.load(path, allow_pickle=False) as payload:
            local = payload["local_xyz"].astype(np.float64)
            magnitude = payload["magnitude"].astype(np.float64)
            depth = -payload["mesh_distance_voxels"].astype(np.float64)
            inside = payload["mesh_inside"].astype(bool)
            voxel = float(np.mean(payload["voxel_size_xyz"]))
            section = np.abs(local[:, 0]) <= voxel * 0.55
            datasets.append((local[section], magnitude[section], depth[section], inside[section], voxel))
            global_max = max(global_max, float(np.max(magnitude[section])))
    names = ("A axis ON", "B Y40 ON", "C Y40 OFF")
    elements = []
    for panel, (name, data) in enumerate(zip(names, datasets)):
        local, magnitude, depth, inside, voxel = data
        x0, y0, width, height = 28 + panel * 338, 120, 300.0, 350.0
        for row in range(local.shape[0]):
            px = x0 + (local[row, 1] + 0.35) / 0.70 * width
            py = y0 + height - local[row, 2] / 2.05 * height
            norm = min(1.0, math.log10(1.0 + 999.0 * magnitude[row] / global_max) / 3.0)
            color = f"rgb({int(40 + 215 * norm)},70,{int(220 - 180 * norm)})"
            if inside[row] and depth[row] <= 1.0:
                stroke, radius = "#ffd166", 2.3
            elif inside[row] and depth[row] > 1.0:
                stroke, radius = "#f7fafc", 2.6
            else:
                stroke, radius = "none", 1.3
            elements.append(
                f'<circle cx="{px:.2f}" cy="{py:.2f}" r="{radius}" fill="{color}" '
                f'stroke="{stroke}" stroke-width="0.7"/>'
            )
        cy = y0 + height - 1.035 / 2.05 * height
        elements.append(f'<circle cx="{x0 + width / 2:.2f}" cy="{cy:.2f}" r="5" fill="none" stroke="#5eead4" stroke-width="2"/>')
        elements.append(f'<text x="{x0}" y="98" class="label">{html.escape(name)}</text>')
    worst = report["qualification"]["worst_case"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1050" height="560" viewBox="0 0 1050 560"><style>.bg{{fill:#10161f}}.title{{fill:#f5f7fb;font:700 25px sans-serif}}.sub{{fill:#afbdcf;font:14px sans-serif}}.label{{fill:#edf2f7;font:700 16px sans-serif}}.pass{{fill:#86efac;font:700 16px sans-serif}}</style><rect width="1050" height="560" class="bg"/><text x="28" y="40" class="title">Phase 6EF — static Y40 Mesh CollisionProxy qualification</text><text x="28" y="68" class="sub">Run 1, frame 200, common velocity scale. Yellow: boundary ≤1 voxel; white: deep interior; cyan: center-axis marker.</text>{''.join(elements)}<text x="28" y="515" class="pass">QUALIFIED · worst B deep {worst['B_deep_maximum_m_s']:.4g} m/s · worst B/C ratio {worst['B_over_C_deep_ratio']:.4g}</text><text x="28" y="540" class="sub">Geometry labels use the authored Mesh, not an internal Flow occupancy mask.</text></svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    contract = load_json(args.contract.resolve())
    thresholds = tuple(float(value) for value in contract["thresholds"]["reported_velocity_thresholds_m_s"])
    samples: dict[str, dict] = {}
    files = []
    runtime = {}
    all_present = True
    lifecycle_ok = True
    functional_ok = True
    safety_ok = True
    active_fuel_ok = True
    condition_inputs = {}
    condition_difference_ok = True
    expected_modes = {
        "A_axis_on": "phase6ec_rotated_mesh",
        "B_rotate_y40_on": "phase6ec_rotated_mesh",
        "C_rotate_y40_off": "phase6ec_rotated_mesh_collision_off",
    }
    for run_index in range(1, 4):
        run_key = str(run_index)
        samples[run_key] = {}
        runtime[run_key] = {}
        for condition in CONDITIONS:
            raw_path = root / "formal" / f"run_{run_index}" / condition / "raw.json"
            evidence_path = root / "formal" / f"run_{run_index}" / condition / "runner_evidence.json"
            all_present &= raw_path.is_file() and evidence_path.is_file()
            if not all_present:
                continue
            raw, evidence = load_json(raw_path), load_json(evidence_path)
            outcome = evidence.get("outcome") or {}
            lifecycle_ok &= outcome.get("lifecycle_status") == "normal_exit" and evidence.get("process_exit_code") == 0
            functional_ok &= outcome.get("functional_status") == "pass" and raw.get("status") == "ok"
            safety_ok &= not any((
                evidence.get("timed_out"),
                evidence.get("fatal_lines"),
                evidence.get("dump_inventory"),
                evidence.get("automatic_upload_attempt_lines"),
                not evidence.get("relevant_crash_registry_unchanged", False),
                evidence.get("production_changed", False),
            ))
            fuel = float(raw["stage_audit"]["emitter"]["fuel"])
            active = int(raw["active_blocks_final"])
            active_fuel_ok &= active > 0 and math.isclose(
                fuel,
                float(contract["fixed_environment"]["emitter_fuel"]),
                abs_tol=float(contract["thresholds"]["fuel_absolute_tolerance"]),
            )
            stage_audit = raw["stage_audit"]
            input_record = {
                "mode": raw["mode"],
                "source_sha256": raw["preparation"]["source_sha256"],
                "collider": stage_audit["collider"],
                "emitter": stage_audit["emitter"],
                "simulate": stage_audit["simulate"],
            }
            prior = condition_inputs.get(condition)
            condition_difference_ok &= prior is None or prior == input_record
            condition_inputs[condition] = input_record
            condition_difference_ok &= raw["mode"] == expected_modes[condition]
            condition_difference_ok &= bool(stage_audit["simulate"]["physicsCollisionEnabled"]) == (
                condition != "C_rotate_y40_off"
            )
            runtime[run_key][condition] = {
                "active_blocks_final": active,
                "source_fuel": fuel,
                "outcome": outcome,
                "runner_peak_private_bytes": None,
                "spatial_peak_rss_bytes": raw.get("phase6ee_spatial", {}).get("peak_rss_bytes"),
                "spatial_peak_rss_delta_bytes": raw.get("phase6ee_spatial", {}).get("peak_rss_delta_bytes"),
            }
            samples[run_key][condition] = {}
            for frame in FRAMES:
                path = root / "spatial" / f"run_{run_index}" / condition / f"{condition}_f{frame:04d}_velocity.npz"
                all_present &= path.is_file()
                if not path.is_file():
                    continue
                stats, metadata = sample_stats(path, thresholds)
                metadata["path"] = path.relative_to(root).as_posix()
                samples[run_key][condition][str(frame)] = stats
                files.append({"run": run_index, "condition": condition, "frame": frame, **metadata})
    ratios, sample_checks = evaluate_samples(samples, contract) if all_present else ({}, [])
    prepared = load_json(root / "prepared_stages.json")
    geometry = prepared["cases"]["axis_control"]["audit"]["geometry"]
    rotated = prepared["cases"]["rotate_y40"]["audit"]
    prep_gates_ok = prepared.get("status") == "ok" and all(prepared["gates"].values())
    geometry_ok = (
        geometry["vertex_count"] == contract["fixed_environment"]["geometry"]["vertex_count"]
        and geometry["face_count"] == contract["fixed_environment"]["geometry"]["face_count"]
        and geometry["index_count"] == contract["fixed_environment"]["geometry"]["face_index_count"]
        and geometry["closed_manifold"]
        and math.isclose(float(prepared["cases"]["rotate_y40"]["rotation_y_deg"]), 40.0)
        and rotated["flow"]["physics_collision_enabled"]
    )
    if all(condition in condition_inputs for condition in CONDITIONS):
        a_input = condition_inputs["A_axis_on"]
        b_input = condition_inputs["B_rotate_y40_on"]
        c_input = condition_inputs["C_rotate_y40_off"]
        condition_difference_ok &= a_input["emitter"] == b_input["emitter"] == c_input["emitter"]
        common_simulate = lambda value: {
            key: item for key, item in value["simulate"].items() if key != "physicsCollisionEnabled"
        }
        condition_difference_ok &= common_simulate(a_input) == common_simulate(b_input) == common_simulate(c_input)
        condition_difference_ok &= b_input["collider"] == c_input["collider"]
        condition_difference_ok &= b_input["source_sha256"] == c_input["source_sha256"]
        condition_difference_ok &= a_input["source_sha256"] != b_input["source_sha256"]
    else:
        condition_difference_ok = False
    sample_gate = bool(sample_checks) and all(item["pass"] for item in sample_checks)
    gates = {
        "all_nine_processes_and_36_velocity_samples_present": all_present and len(files) == 36,
        "predeclared_contract_used_without_runtime_threshold_derivation": bool(contract["declared_before_formal_runs"]),
        "exact_mesh_and_only_declared_stage_differences": prep_gates_ok and geometry_ok and condition_difference_ok,
        "all_sample_numeric_gates_pass": sample_gate,
        "active_blocks_and_source_fuel_preserved": active_fuel_ok,
        "functional_pass": functional_ok,
        "normal_os_exit_only": lifecycle_ok,
        "fatal_dump_upload_residual_zero": safety_ok,
        "public_flow_occupancy_mask_not_claimed": all(not item["geometry_labels_are_flow_occupancy"] for item in files),
        "phase6ec_history_unchanged": not contract["history_contract"]["phase6ec_gate_changed"] and not contract["history_contract"]["phase6ec_failure_reinterpreted"],
    }
    qualification_pass = all(gates.values())
    worst = {
        "A_deep_maximum_m_s": max((item["values_m_s"]["A_deep"] for item in sample_checks), default=0.0),
        "A_center_maximum_m_s": max((item["values_m_s"]["A_center"] for item in sample_checks), default=0.0),
        "B_deep_maximum_m_s": max((item["values_m_s"]["B_deep"] for item in sample_checks), default=0.0),
        "B_center_maximum_m_s": max((item["values_m_s"]["B_center"] for item in sample_checks), default=0.0),
        "C_deep_minimum_m_s": min((item["values_m_s"]["C_deep"] for item in sample_checks), default=0.0),
        "C_center_minimum_m_s": min((item["values_m_s"]["C_center"] for item in sample_checks), default=0.0),
        "B_over_C_deep_ratio": max((item["ratios"]["B_over_C_deep_maximum"] for item in sample_checks if item["ratios"]["B_over_C_deep_maximum"] is not None), default=0.0),
        "C_axis_only_minimum_m_s": min((item["values_m_s"]["C_axis_only"] for item in sample_checks), default=0.0),
        "B_over_C_axis_only_ratio_minimum": min((item["ratios"]["B_over_C_axis_only_maximum"] for item in sample_checks if item["ratios"]["B_over_C_axis_only_maximum"] is not None), default=0.0),
    }
    archive = None
    if args.archive is not None:
        args.archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(args.archive, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as output:
            for record in files:
                source = root / record["path"]
                info = zipfile.ZipInfo(
                    f"run_{record['run']}/{record['condition']}/{source.name}",
                    date_time=(1980, 1, 1, 0, 0, 0),
                )
                info.compress_type = zipfile.ZIP_STORED
                with source.open("rb") as input_stream, output.open(info, "w", force_zip64=True) as output_stream:
                    shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
        archive = {"path": args.archive.name, "bytes": args.archive.stat().st_size, "sha256": sha256(args.archive), "entry_count": len(files)}
    report = {
        "schema": "campfire.phase6ef.static-y40-qualification-report.v1",
        "phase": "phase6ef",
        "contract": {"path": args.contract.name, "sha256": sha256(args.contract.resolve()), "thresholds": contract["thresholds"], "run_order": contract["run_order"]},
        "scope": contract["history_contract"]["qualification_scope_if_pass"],
        "flow_collision_occupancy": {"public_api_available": False, "geometry_labels_are_flow_occupancy": False, "label_source": contract["geometry_contract"]["primary_distance"]},
        "samples": samples,
        "ratios": ratios,
        "sample_checks": sample_checks,
        "runtime": runtime,
        "condition_input_audit": condition_inputs,
        "files": files,
        "storage": {"npz_bytes": sum(item["bytes"] for item in files), "raw_archive": archive},
        "gates": gates,
        "qualification": {"pass": qualification_pass, "worst_case": worst, "phase6ec_gate_changed": False, "phase6ec_failure_reinterpreted": False, "arbitrary_axis_rotation_qualified": False, "dynamic_transform_qualified": False, "render_surface_qualified": False, "physx_shared_proxy_qualified": False, "twenty_log_performance_qualified": False},
        "production_change": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if qualification_pass:
        args.svg.write_text(make_svg(report, root), encoding="utf-8")
    elif args.svg.exists():
        raise RuntimeError("refusing to retain a qualification SVG for failed numeric gates")
    return 0 if qualification_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
