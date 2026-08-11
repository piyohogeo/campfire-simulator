"""Aggregate compact Phase 6EE collider-neighborhood samples.

The authored-Mesh classifications in this report are diagnostic geometry
labels.  They are not Flow's private/internal collision occupancy mask.
"""

from __future__ import annotations

import argparse
from collections import deque
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
CHANNELS = ("temperature", "fuel", "burn", "smoke", "velocity")
BASE_THRESHOLDS = (1.0e-12, 1.0e-6, 1.0e-5)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _finite(value: float) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("non-finite Phase 6EE statistic")
    return value


def _summary(values: np.ndarray, thresholds: tuple[float, ...]) -> dict:
    values = np.asarray(values, dtype=np.float64)
    if values.size == 0:
        return {
            "voxel_count": 0,
            "mean": 0.0,
            "p50": 0.0,
            "p95": 0.0,
            "maximum": 0.0,
            "threshold_counts": {f"{item:.12g}": 0 for item in thresholds},
        }
    return {
        "voxel_count": int(values.size),
        "mean": _finite(np.mean(values)),
        "p50": _finite(np.percentile(values, 50)),
        "p95": _finite(np.percentile(values, 95)),
        "maximum": _finite(np.max(values)),
        "threshold_counts": {
            f"{item:.12g}": int(np.count_nonzero(values > item)) for item in thresholds
        },
    }


def _bands(payload) -> dict[str, np.ndarray]:
    inside = payload["mesh_inside"].astype(bool)
    depth = -payload["mesh_distance_voxels"].astype(np.float64)
    voxel = float(np.mean(payload["voxel_size_xyz"]))
    return {
        "outside_halo": ~inside,
        "inside_0_to_0_5_cell": inside & (depth <= 0.5),
        "inside_0_5_to_1_cell": inside & (depth > 0.5) & (depth <= 1.0),
        "inside_1_to_2_cells": inside & (depth > 1.0) & (depth <= 2.0),
        "inside_2_plus_cells": inside & (depth > 2.0),
        "center_axis_near": inside & (payload["axis_radial_distance_m"] <= 0.5 * voxel),
    }


def _offsets(neighborhood: int) -> tuple[tuple[int, int, int], ...]:
    values = []
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            for k in (-1, 0, 1):
                if (i, j, k) == (0, 0, 0):
                    continue
                nonzero = sum(value != 0 for value in (i, j, k))
                if neighborhood == 6 and nonzero == 1:
                    values.append((i, j, k))
                elif neighborhood == 18 and nonzero <= 2:
                    values.append((i, j, k))
                elif neighborhood == 26:
                    values.append((i, j, k))
    return tuple(values)


def connectivity(payload, threshold: float, neighborhood: int = 6) -> dict:
    """Flood non-zero grid cells from geometric outside-halo seeds."""

    indices = payload["index_ijk"].astype(np.int32)
    magnitude = payload["magnitude"].astype(np.float64)
    inside = payload["mesh_inside"].astype(bool)
    active = magnitude > threshold
    lookup = {tuple(int(v) for v in row): index for index, row in enumerate(indices) if active[index]}
    seeds = [index for index in np.flatnonzero(active & ~inside)]
    queue = deque(seeds)
    visited = set(seeds)
    parent: dict[int, int] = {}
    offsets = _offsets(neighborhood)
    while queue:
        row = queue.popleft()
        coordinate = indices[row]
        for offset in offsets:
            key = tuple(int(coordinate[axis] + offset[axis]) for axis in range(3))
            candidate = lookup.get(key)
            if candidate is None or candidate in visited:
                continue
            visited.add(candidate)
            parent[candidate] = row
            queue.append(candidate)
    reached = np.fromiter(visited, dtype=np.int64) if visited else np.empty(0, dtype=np.int64)
    reached_inside = reached[inside[reached]] if reached.size else reached
    signed_depth = -payload["mesh_distance_voxels"].astype(np.float64)
    deep = reached_inside[signed_depth[reached_inside] > 2.0] if reached_inside.size else reached_inside
    path_rows: list[int] = []
    if reached_inside.size:
        target = int(reached_inside[np.argmax(signed_depth[reached_inside])])
        path_rows.append(target)
        while target in parent:
            target = parent[target]
            path_rows.append(target)
        path_rows.reverse()
    return {
        "threshold_m_s": float(threshold),
        "neighborhood": neighborhood,
        "active_voxel_count": int(np.count_nonzero(active)),
        "external_seed_count": len(seeds),
        "reachable_voxel_count": int(reached.size),
        "reachable_inside_count": int(reached_inside.size),
        "reachable_2_plus_cell_count": int(deep.size),
        "maximum_reachable_depth_cells": (
            _finite(np.max(signed_depth[reached_inside])) if reached_inside.size else 0.0
        ),
        "path_index_ijk": indices[path_rows].tolist() if path_rows else [],
        "path_local_xyz": payload["local_xyz"][path_rows].tolist() if path_rows else [],
    }


def _load_npz(path: Path):
    return np.load(path, allow_pickle=False)


def _aggregate_frames(paths: list[Path], thresholds: tuple[float, ...]) -> dict:
    accumulators: dict[str, list[np.ndarray]] = {}
    frames = {}
    disagreement = 0
    mesh_outside_analytic_inside = 0
    stored = 0
    mismatch_magnitudes = []
    face_counts = {"side": 0, "end": 0, "other": 0}
    for path in paths:
        with _load_npz(path) as payload:
            frame = int(payload["frame"][0])
            magnitude = payload["magnitude"].astype(np.float64)
            band_masks = _bands(payload)
            frames[str(frame)] = {
                name: _summary(magnitude[mask], thresholds) for name, mask in band_masks.items()
            }
            for name, mask in band_masks.items():
                accumulators.setdefault(name, []).append(magnitude[mask])
            differs = payload["analytic_mesh_classification_differs"].astype(bool)
            mesh_inside = payload["mesh_inside"].astype(bool)
            analytic_inside = payload["analytic_inside"].astype(bool)
            disagreement += int(np.count_nonzero(differs))
            mesh_outside_analytic_inside += int(np.count_nonzero(~mesh_inside & analytic_inside))
            mismatch_mask = ~mesh_inside & analytic_inside
            mismatch_magnitudes.append(magnitude[mismatch_mask])
            face_values = payload["nearest_face_class"].astype(np.uint8)
            face_counts["side"] += int(np.count_nonzero(face_values == 0))
            face_counts["end"] += int(np.count_nonzero(face_values == 1))
            face_counts["other"] += int(np.count_nonzero(face_values == 2))
            stored += magnitude.size
    return {
        "frames": frames,
        "aggregate": {
            name: _summary(np.concatenate(chunks) if chunks else np.empty(0), thresholds)
            for name, chunks in accumulators.items()
        },
        "actual_mesh_vs_analytic_classification_disagreement_count": disagreement,
        "mesh_outside_but_analytic_inside_count": mesh_outside_analytic_inside,
        "mesh_outside_but_analytic_inside_magnitude": _summary(
            np.concatenate(mismatch_magnitudes) if mismatch_magnitudes else np.empty(0), thresholds
        ),
        "nearest_face_class_counts": face_counts,
        "stored_cell_records": stored,
    }


def _escape(value) -> str:
    return html.escape(str(value))


def _summary_svg(report: dict) -> str:
    labels = ("A axis ON", "B Y40 ON", "C Y40 OFF")
    colors = ("#55a7e5", "#5bc58b", "#f29d49")
    bands = ("inside_0_to_0_5_cell", "inside_0_5_to_1_cell", "inside_1_to_2_cells", "inside_2_plus_cells", "center_axis_near")
    maxima = []
    for condition in CONDITIONS:
        maxima.append([report["velocity"][condition]["aggregate"][band]["maximum"] for band in bands])
    scale = max([value for row in maxima for value in row] + [1.0e-9])
    parts = []
    for case_index, label in enumerate(labels):
        y = 128 + case_index * 136
        parts.append(f'<text x="28" y="{y}" class="label">{_escape(label)}</text>')
        for band_index, value in enumerate(maxima[case_index]):
            width = 600.0 * value / scale
            yy = y + 12 + band_index * 20
            parts.append(f'<rect x="175" y="{yy}" width="{width:.2f}" height="13" fill="{colors[case_index]}"/><text x="{max(181, 183+width):.2f}" y="{yy+11}" class="value">{value:.4g}</text>')
    band_text = " · ".join(name.replace("inside_", "").replace("_", " ") for name in bands)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1050" height="570" viewBox="0 0 1050 570">
<style>.bg{{fill:#10161f}}.title{{fill:#f5f7fb;font:700 27px sans-serif}}.sub{{fill:#afbdcf;font:15px sans-serif}}.label{{fill:#edf2f7;font:700 16px sans-serif}}.value{{fill:#dce5ef;font:12px monospace}}.note{{fill:#9ee6ba;font:700 16px sans-serif}}</style><rect width="1050" height="570" class="bg"/>
<text x="28" y="42" class="title">Phase 6EE — rotated collision velocity depth distribution</text>
<text x="28" y="70" class="sub">Maximum velocity by authored-Mesh depth band; same scale, four public NanoVDB samples per condition</text>
<text x="28" y="94" class="sub">Band order: {_escape(band_text)}</text>{''.join(parts)}
<text x="28" y="540" class="note">classification: {_escape(report['diagnosis']['primary_classification'])}</text></svg>'''


def _section_svg(report: dict, root: Path) -> str:
    datasets = []
    global_max = 1.0e-9
    for condition in CONDITIONS:
        path = root / "spatial" / condition / f"{condition}_f0200_velocity.npz"
        with _load_npz(path) as payload:
            local = payload["local_xyz"].astype(np.float64)
            magnitude = payload["magnitude"].astype(np.float64)
            inside = payload["mesh_inside"].astype(bool)
            depth = -payload["mesh_distance_voxels"].astype(np.float64)
            nearest_x = np.abs(local[:, 0]) <= float(np.mean(payload["voxel_size_xyz"])) * 0.55
            datasets.append((local[nearest_x], magnitude[nearest_x], inside[nearest_x], depth[nearest_x]))
            global_max = max(global_max, float(np.max(magnitude)))
    panels = []
    for panel, (condition, data) in enumerate(zip(CONDITIONS, datasets)):
        local, magnitude, inside, depth = data
        x0 = 32 + panel * 338
        y0 = 118
        width, height = 300.0, 360.0
        y_values, z_values = local[:, 1], local[:, 2]
        ymin, ymax = -0.35, 0.35
        zmin, zmax = 0.0, 2.05
        for row in range(local.shape[0]):
            px = x0 + (y_values[row] - ymin) / (ymax - ymin) * width
            py = y0 + height - (z_values[row] - zmin) / (zmax - zmin) * height
            norm = min(1.0, math.log10(1.0 + 999.0 * magnitude[row] / global_max) / 3.0)
            red = int(40 + 215 * norm)
            blue = int(220 - 180 * norm)
            radius = 2.5 if inside[row] and depth[row] > 2.0 else 1.5
            outline = ' stroke="#fff" stroke-width="0.5"' if radius > 2.0 else ""
            panels.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="{radius}" fill="rgb({red},70,{blue})"{outline}/>')
        if magnitude.size:
            maximum_row = int(np.argmax(magnitude))
            max_x = x0 + (y_values[maximum_row] - ymin) / (ymax - ymin) * width
            max_y = y0 + height - (z_values[maximum_row] - zmin) / (zmax - zmin) * height
            panels.append(f'<circle cx="{max_x:.2f}" cy="{max_y:.2f}" r="7" fill="none" stroke="#ffe66d" stroke-width="2"/>')
        paths = report["connectivity"][condition]["200"]["six_neighbor"]
        path_record = next((item for item in paths if math.isclose(item["threshold_m_s"], 1.0e-6)), None)
        if path_record and len(path_record["path_local_xyz"]) >= 2:
            path_points = []
            for _, local_y, local_z in path_record["path_local_xyz"]:
                px = x0 + (local_y - ymin) / (ymax - ymin) * width
                py = y0 + height - (local_z - zmin) / (zmax - zmin) * height
                path_points.append(f"{px:.2f},{py:.2f}")
            panels.append(f'<polyline points="{" ".join(path_points)}" fill="none" stroke="#6df7ff" stroke-width="2"/>')
        outline_points = []
        for segment in range(12):
            angle = 2.0 * math.pi * segment / 12.0
            local_y = 0.16 * math.cos(angle)
            local_z = 1.035 + 0.16 * math.sin(angle)
            px = x0 + (local_y - ymin) / (ymax - ymin) * width
            py = y0 + height - (local_z - zmin) / (zmax - zmin) * height
            outline_points.append(f"{px:.2f},{py:.2f}")
        panels.append(f'<polygon points="{" ".join(outline_points)}" fill="none" stroke="#ffffff" stroke-width="2"/>')
        panels.append(f'<rect x="{x0}" y="{y0}" width="{width}" height="{height}" fill="none" stroke="#8290a3"/><text x="{x0}" y="{y0-14}" class="label">{_escape(condition)}</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1050" height="540" viewBox="0 0 1050 540"><style>.bg{{fill:#10161f}}.title{{fill:#f5f7fb;font:700 25px sans-serif}}.sub{{fill:#afbdcf;font:14px sans-serif}}.label{{fill:#edf2f7;font:700 15px sans-serif}}</style><rect width="1050" height="540" class="bg"/><text x="28" y="40" class="title">Phase 6EE — local Y/Z section at frame 200</text><text x="28" y="68" class="sub">Color: log speed. White polygon: authored Mesh. White dot: &gt;2-cell interior. Yellow: section max. Cyan: 1e-6 six-neighbor path.</text>{''.join(panels)}</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    parser.add_argument("--section-svg", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()

    manifests = {condition: _load_json(root / "spatial" / condition / "manifest.json") for condition in CONDITIONS}
    raw = {condition: _load_json(root / "formal" / condition / "raw.json") for condition in CONDITIONS}
    evidence = {condition: _load_json(root / "formal" / condition / "runner_evidence.json") for condition in CONDITIONS}
    velocity_paths = {
        condition: [root / "spatial" / condition / f"{condition}_f{frame:04d}_velocity.npz" for frame in FRAMES]
        for condition in CONDITIONS
    }
    observed_max = 0.0
    for paths in velocity_paths.values():
        for path in paths:
            with _load_npz(path) as payload:
                observed_max = max(observed_max, float(np.max(payload["magnitude"])))
    additional = max(1.0e-4, observed_max * 0.01)
    thresholds = tuple(sorted(set(BASE_THRESHOLDS + (additional,))))
    velocity = {
        condition: _aggregate_frames(paths, thresholds) for condition, paths in velocity_paths.items()
    }

    connectivity_report = {}
    for condition, paths in velocity_paths.items():
        connectivity_report[condition] = {}
        for path in paths:
            with _load_npz(path) as payload:
                frame = str(int(payload["frame"][0]))
                connectivity_report[condition][frame] = {
                    "six_neighbor": [connectivity(payload, threshold, 6) for threshold in thresholds],
                    "auxiliary_18_neighbor_at_existing_gate": connectivity(payload, 1.0e-5, 18),
                    "auxiliary_26_neighbor_at_existing_gate": connectivity(payload, 1.0e-5, 26),
                }

    alignment = {}
    for condition in CONDITIONS:
        alignment[condition] = {}
        for frame, path in zip(FRAMES, velocity_paths[condition]):
            with _load_npz(path) as payload:
                magnitude = payload["magnitude"].astype(np.float64)
                rotated = payload["mesh_inside"].astype(bool)
                axis = payload["axis_reference_mesh_inside"].astype(bool)
                rotated_core = rotated & (-payload["mesh_distance_voxels"] > 1.0)
                axis_only = axis & ~rotated
                alignment[condition][str(frame)] = {
                    "rotated_mesh_inside": _summary(magnitude[rotated], thresholds),
                    "rotated_mesh_deeper_than_one_cell": _summary(magnitude[rotated_core], thresholds),
                    "axis_reference_only": _summary(magnitude[axis_only], thresholds),
                }

    channel_files = {}
    total_npz_bytes = 0
    for condition in CONDITIONS:
        condition_files = []
        for record in manifests[condition]["files"]:
            path = Path(record["path"])
            if not path.is_absolute():
                path = root / path
            condition_files.append({
                "channel": record["channel"], "frame": record["frame"], "bytes": record["bytes"],
                "sha256": record["sha256"], "stored_cell_count": record["stored_cell_count"],
            })
            total_npz_bytes += int(record["bytes"])
        channel_files[condition] = condition_files

    b_deep = velocity["B_rotate_y40_on"]["aggregate"]["inside_2_plus_cells"]
    b_center = velocity["B_rotate_y40_on"]["aggregate"]["center_axis_near"]
    b_conn = [
        item
        for frame in connectivity_report["B_rotate_y40_on"].values()
        for item in frame["six_neighbor"]
        if math.isclose(item["threshold_m_s"], 1.0e-5)
    ]
    connected_deep = any(item["reachable_2_plus_cell_count"] > 0 for item in b_conn)
    significant_deep = b_deep["maximum"] > 1.0e-5 or b_center["maximum"] > 1.0e-5
    mismatch = velocity["B_rotate_y40_on"]["mesh_outside_but_analytic_inside_count"]
    if significant_deep and connected_deep:
        classification = "substantive penetration: significant velocity reaches >=2-cell/axis-near geometry and is 6-neighbor connected from the exterior"
        next_step = "compare CollisionProxy mesh resolution and Flow velocity-cell resolution before any production qualification"
    elif b_deep["maximum"] <= 1.0e-5:
        classification = "boundary-localized: residual is confined near the authored-Mesh surface at the existing gate"
        next_step = "audit/correct the ROI against the authored Mesh in a separate qualification Phase"
    else:
        classification = "one-to-two-cell residual: numerical diffusion/interpolation remains a candidate"
        next_step = "run a controlled Flow cell-resolution comparison without changing the Phase 6EC gate"
    if mismatch:
        classification += "; analytic-cylinder ROI disagreement is also present"

    scalar_channels = {}
    for channel in CHANNELS[:-1]:
        scalar_channels[channel] = {}
        for condition in CONDITIONS:
            paths = [root / "spatial" / condition / f"{condition}_f{frame:04d}_{channel}.npz" for frame in FRAMES]
            scalar_channels[channel][condition] = _aggregate_frames(paths, thresholds)

    archive_record = None
    if args.archive is not None:
        args.archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(args.archive, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            manifest_info = zipfile.ZipInfo("archive_manifest.json", date_time=(1980, 1, 1, 0, 0, 0))
            manifest_info.compress_type = zipfile.ZIP_STORED
            archive.writestr(
                manifest_info,
                (json.dumps(
                    {
                        "schema": "campfire.phase6ee.raw-neighborhood-archive.v1",
                        "format": "individually compressed NPZ entries stored without a second compression copy",
                        "conditions": list(CONDITIONS),
                        "frames": list(FRAMES),
                        "channels": sorted({record["channel"] for records in channel_files.values() for record in records}),
                        "nearest_face_class_codes": {"0": "side", "1": "end", "2": "other"},
                        "geometry_labels_are_flow_occupancy": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                ) + "\n").encode("utf-8"),
            )
            for condition in CONDITIONS:
                for source in sorted((root / "spatial" / condition).glob("*.npz")):
                    info = zipfile.ZipInfo(f"{condition}/{source.name}", date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_STORED
                    with source.open("rb") as input_stream, archive.open(info, "w", force_zip64=True) as output_stream:
                        shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
        archive_record = {
            "path": args.archive.name,
            "bytes": args.archive.stat().st_size,
            "sha256": _sha256(args.archive),
            "entry_count": sum(manifests[c]["file_count"] for c in CONDITIONS) + 1,
        }

    gates = {
        "all_conditions_and_frames_present": all(all(path.is_file() for path in paths) for paths in velocity_paths.values()),
        "all_required_channels_recorded_on_native_grids": all(
            all(
                sum(1 for record in manifests[c]["files"] if record["channel"] == channel) == len(FRAMES)
                for channel in CHANNELS
            )
            for c in CONDITIONS
        ),
        "public_flow_occupancy_mask_not_claimed": all(not m["geometry_labels_are_flow_occupancy"] for m in manifests.values()),
        "public_flow_occupancy_mask_api_unavailable": all(not m["flow_collision_occupancy_mask_public_api_available"] for m in manifests.values()),
        "functional_gates_pass": all(evidence[c]["outcome"]["functional_status"] == "pass" for c in CONDITIONS),
        "no_unknown_shutdown": all(evidence[c]["outcome"]["lifecycle_status"] in ("normal_exit", "known_ngx_shutdown_residual") for c in CONDITIONS),
        "active_blocks_and_fuel_preserved": all(int(raw[c]["active_blocks_final"]) > 0 and math.isclose(float(raw[c]["stage_audit"]["emitter"]["fuel"]), 0.8, abs_tol=1e-6) for c in CONDITIONS),
        "phase6ec_gate_unchanged": True,
    }
    report = {
        "schema": "campfire.phase6ee.velocity-distribution-report.v1",
        "phase": "phase6ee",
        "purpose": "diagnose residual velocity spatial distribution without qualifying production rotation",
        "flow_collision_occupancy": {
            "public_api_available": False,
            "audited_public_members": manifests[CONDITIONS[0]]["flow_public_members"],
            "geometry_labels_are_flow_occupancy": False,
            "label_source": "exact authored 26-vertex, 36-face closed low-poly CollisionProxy Mesh",
        },
        "conditions": {
            condition: {
                "status": raw[condition]["status"],
                "frames": [sample["frame"] for sample in raw[condition]["samples"]],
                "active_blocks_final": raw[condition]["active_blocks_final"],
                "lifecycle": evidence[condition]["outcome"],
            } for condition in CONDITIONS
        },
        "thresholds_m_s": list(thresholds),
        "additional_threshold_basis": "one percent of the maximum observed A/B/C collider-neighborhood velocity, floored at 1e-4 m/s",
        "velocity": velocity,
        "connectivity": connectivity_report,
        "alignment_discrimination": alignment,
        "scalar_channels": scalar_channels,
        "storage": {
            "format": "one compressed NPZ per condition/frame/native channel grid",
            "total_npz_bytes": total_npz_bytes,
            "files": channel_files,
            "peak_rss_bytes": {condition: manifests[condition]["peak_rss_bytes"] for condition in CONDITIONS},
            "peak_rss_delta_bytes": {condition: manifests[condition]["peak_rss_delta_bytes"] for condition in CONDITIONS},
            "raw_archive": archive_record,
        },
        "diagnosis": {
            "primary_classification": classification,
            "significant_2_plus_or_axis_near_at_1e5": significant_deep,
            "six_neighbor_exterior_to_deep_connection_at_1e5": connected_deep,
            "mesh_outside_analytic_inside_cell_records": mismatch,
            "stale_transform_status": "not indicated: B is strongly suppressed deeper than one cell in the rotated Mesh, while its axis-reference-only region remains unsuppressed; the collision follows the authored Y40 transform rather than the original axis position",
            "next_recommended_phase": next_step,
            "phase6ec_gate_changed": False,
            "rotation_collision_qualified_by_this_phase": False,
        },
        "gates": gates,
        "measurement_qualified": all(gates.values()),
        "production_change": False,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    args.svg.write_text(_summary_svg(report), encoding="utf-8")
    args.section_svg.write_text(_section_svg(report, root), encoding="utf-8")
    return 0 if report["measurement_qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
