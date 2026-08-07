"""Default-off USD transport spike for future Flow emitter layouts.

This probe deliberately stops at the USD notification boundary.  It measures
source assembly, NumPy-to-Vt conversion, UsdAttribute.Set calls, and
ObjectsChanged delivery separately.  Flow ingestion, rasterization, solver,
and rendering require a second real-Kit/Flow spike and are never inferred from
these numbers.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = (
    ROOT
    / "docs"
    / "devlog"
    / "assets"
    / "phase6"
    / "emitter_transport_scalability_report.json"
)
DEFAULT_SVG = (
    ROOT
    / "docs"
    / "devlog"
    / "assets"
    / "phase6"
    / "emitter_transport_scalability_report.svg"
)
_DLL_DIRECTORY_HANDLES = []


def _load_local_packages():
    ext_cache = ROOT / "_build" / "windows-x86_64" / "release" / "extscache"
    pip_archives = sorted(ext_cache.glob("omni.kit.pip_archive-*"))
    if pip_archives:
        sys.path.insert(0, str(pip_archives[-1] / "pip_prebundle"))
    usd_packages = sorted(ext_cache.glob("omni.usd.libs-*"))
    if not usd_packages:
        raise RuntimeError("The built Kit USD Python package was not found")
    usd_package = usd_packages[-1]
    _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(usd_package / "bin")))
    sys.path.insert(0, str(usd_package))
    import numpy
    import psutil
    from pxr import Gf, Sdf, Tf, Usd, Vt

    return numpy, psutil, Gf, Sdf, Tf, Usd, Vt, usd_package.name


np, psutil, Gf, Sdf, Tf, Usd, Vt, USD_PACKAGE = _load_local_packages()
_PROCESS = psutil.Process()


def _working_set_bytes():
    return int(_PROCESS.memory_info().rss)


def _p95(values):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]


def _summary(values):
    return {
        "sample_count": len(values),
        "mean_ms": statistics.fmean(values),
        "p95_ms": _p95(values),
        "maximum_ms": max(values),
    }


def _empty_timings():
    return {
        "source_generation_ms": [],
        "python_cpp_boundary_ms": [],
        "usd_attribute_set_ms": [],
        "change_block_exit_and_notice_ms": [],
        "publication_total_ms": [],
        "update_frame_total_ms": [],
    }


def _publish_in_change_block(setter):
    block = Sdf.ChangeBlock()
    block.__enter__()
    set_started = time.perf_counter_ns()
    try:
        setter()
    except BaseException:
        block.__exit__(*sys.exc_info())
        raise
    set_ms = (time.perf_counter_ns() - set_started) / 1_000_000.0
    exit_started = time.perf_counter_ns()
    block.__exit__(None, None, None)
    exit_ms = (time.perf_counter_ns() - exit_started) / 1_000_000.0
    return set_ms, exit_ms


def _make_point_stage(emitter_count):
    stage = Usd.Stage.CreateInMemory()
    stage.DefinePrim("/World")
    emitters = []
    for index in range(emitter_count):
        prim = stage.DefinePrim(f"/World/Emitter{index}")
        emitters.append(
            {
                "positions": prim.CreateAttribute(
                    "pointPositions", Sdf.ValueTypeNames.Float3Array
                ),
                "fuels": prim.CreateAttribute(
                    "pointFuels", Sdf.ValueTypeNames.FloatArray
                ),
                "temperatures": prim.CreateAttribute(
                    "pointTemperatures", Sdf.ValueTypeNames.FloatArray
                ),
                "smokes": prim.CreateAttribute(
                    "pointSmokes", Sdf.ValueTypeNames.FloatArray
                ),
                "revision": prim.CreateAttribute(
                    "campfire:residentRevision", Sdf.ValueTypeNames.Int64
                ),
            }
        )
    return stage, tuple(emitters)


def _source_arrays(point_count, revision, include_positions):
    positions = None
    if include_positions:
        indices = np.arange(point_count, dtype=np.float32)
        positions = np.empty((point_count, 3), dtype=np.float32)
        positions[:, 0] = (indices % 360.0) * np.float32(0.001)
        positions[:, 1] = ((indices // 360.0) % 20.0) * np.float32(0.02)
        positions[:, 2] = (indices % 12.0) * np.float32(0.0015)
    offset = np.float32(revision * 0.000001)
    fuels = np.full(point_count, np.float32(0.4) + offset, dtype=np.float32)
    temperatures = np.full(
        point_count, np.float32(850.0) + offset, dtype=np.float32
    )
    smokes = np.full(point_count, np.float32(0.1) + offset, dtype=np.float32)
    return positions, fuels, temperatures, smokes


def _convert_point_arrays(arrays, slices, include_positions):
    positions, fuels, temperatures, smokes = arrays
    converted = []
    for start, stop in slices:
        item = {
            "fuels": Vt.FloatArray.FromNumpy(fuels[start:stop]),
            "temperatures": Vt.FloatArray.FromNumpy(temperatures[start:stop]),
            "smokes": Vt.FloatArray.FromNumpy(smokes[start:stop]),
        }
        if include_positions:
            item["positions"] = Vt.Vec3fArray.FromNumpy(positions[start:stop])
        converted.append(item)
    return tuple(converted)


def _make_slices(point_count, emitter_count):
    base, remainder = divmod(point_count, emitter_count)
    slices = []
    start = 0
    for index in range(emitter_count):
        stop = start + base + (1 if index < remainder else 0)
        slices.append((start, stop))
        start = stop
    return tuple(slices)


def _seed_positions(emitters, point_count, slices):
    arrays = _source_arrays(point_count, 1, True)
    converted = _convert_point_arrays(arrays, slices, True)
    with Sdf.ChangeBlock():
        for emitter, values in zip(emitters, converted):
            emitter["positions"].Set(values["positions"])


def _check_point_equivalence(emitters, source, revision, include_positions):
    _positions, fuels, temperatures, smokes = source
    published_fuels = []
    published_temperatures = []
    published_smokes = []
    revisions = []
    position_count = 0
    for emitter in emitters:
        published_fuels.extend(float(value) for value in emitter["fuels"].Get())
        published_temperatures.extend(
            float(value) for value in emitter["temperatures"].Get()
        )
        published_smokes.extend(float(value) for value in emitter["smokes"].Get())
        position_count += len(emitter["positions"].Get())
        revisions.append(int(emitter["revision"].Get()))
    return {
        "point_count_exact": len(published_fuels) == len(fuels),
        "position_count_exact": position_count == len(fuels),
        "fuel_sum_close": bool(
            np.isclose(sum(published_fuels), float(fuels.sum()), rtol=1.0e-6)
        ),
        "temperature_sum_close": bool(
            np.isclose(
                sum(published_temperatures),
                float(temperatures.sum()),
                rtol=1.0e-6,
            )
        ),
        "smoke_sum_close": bool(
            np.isclose(sum(published_smokes), float(smokes.sum()), rtol=1.0e-6)
        ),
        "consumer_revisions": revisions,
        "consumer_revision_consistent": (
            len(set(revisions)) == 1 and revisions[0] == revision
        ),
        "positions_updated_this_frame": include_positions,
    }


def benchmark_point_layout(
    point_count, emitter_count, update_mode, iterations, warmup_iterations
):
    include_positions = update_mode == "all_arrays"
    stage, emitters = _make_point_stage(emitter_count)
    slices = _make_slices(point_count, emitter_count)
    if not include_positions:
        _seed_positions(emitters, point_count, slices)

    notice_count = 0
    notice_callback_ms = []
    notice_revision_consistent = True
    active_revision = 0

    def observe_notice(notice, _sender):
        nonlocal notice_count, notice_revision_consistent
        started = time.perf_counter_ns()
        notice.GetChangedInfoOnlyPaths()
        revisions = tuple(int(item["revision"].Get()) for item in emitters)
        notice_revision_consistent = notice_revision_consistent and (
            len(set(revisions)) == 1 and revisions[0] == active_revision
        )
        notice_count += 1
        notice_callback_ms.append(
            (time.perf_counter_ns() - started) / 1_000_000.0
        )

    listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, observe_notice, stage)
    timings = _empty_timings()
    baseline_working_set = _working_set_bytes()
    peak_working_set = baseline_working_set
    last_source = None
    final_revision = 0
    total_iterations = warmup_iterations + iterations
    for offset in range(total_iterations):
        frame_started = time.perf_counter_ns()
        final_revision = offset + 2
        active_revision = final_revision
        source_started = time.perf_counter_ns()
        source = _source_arrays(point_count, final_revision, include_positions)
        source_ms = (time.perf_counter_ns() - source_started) / 1_000_000.0
        conversion_started = time.perf_counter_ns()
        converted = _convert_point_arrays(source, slices, include_positions)
        conversion_ms = (
            time.perf_counter_ns() - conversion_started
        ) / 1_000_000.0

        def set_values():
            for emitter, values in zip(emitters, converted):
                if include_positions:
                    if not emitter["positions"].Set(values["positions"]):
                        raise RuntimeError("pointPositions Set failed")
                for name in ("fuels", "temperatures", "smokes"):
                    if not emitter[name].Set(values[name]):
                        raise RuntimeError(f"{name} Set failed")
            for emitter in emitters:
                if not emitter["revision"].Set(final_revision):
                    raise RuntimeError("revision Set failed")

        set_ms, exit_ms = _publish_in_change_block(set_values)
        frame_ms = (time.perf_counter_ns() - frame_started) / 1_000_000.0
        current_working_set = _working_set_bytes()
        if current_working_set is not None:
            peak_working_set = max(peak_working_set or 0, current_working_set)
        if offset >= warmup_iterations:
            timings["source_generation_ms"].append(source_ms)
            timings["python_cpp_boundary_ms"].append(conversion_ms)
            timings["usd_attribute_set_ms"].append(set_ms)
            timings["change_block_exit_and_notice_ms"].append(exit_ms)
            timings["publication_total_ms"].append(set_ms + exit_ms)
            timings["update_frame_total_ms"].append(frame_ms)
        last_source = source
    listener.Revoke()
    expected_notice_count = total_iterations
    if notice_count != expected_notice_count:
        raise RuntimeError(
            f"ObjectsChanged count {notice_count} != {expected_notice_count}"
        )
    equivalence = _check_point_equivalence(
        emitters, last_source, final_revision, include_positions
    )
    if not all(
        value
        for key, value in equivalence.items()
        if key.endswith("_exact") or key.endswith("_close") or key.endswith("_consistent")
    ):
        raise RuntimeError(f"Point output equivalence failed: {equivalence}")
    arrays_per_emitter = 4 if include_positions else 3
    array_bytes = point_count * (24 if include_positions else 12)
    return {
        "layout": "one_point_emitter" if emitter_count == 1 else "point_emitter_per_log",
        "point_count": point_count,
        "emitter_count": emitter_count,
        "points_per_emitter": [stop - start for start, stop in slices],
        "update_mode": update_mode,
        "attribute_update_count_per_frame": emitter_count * (arrays_per_emitter + 1),
        "array_attribute_update_count_per_frame": emitter_count * arrays_per_emitter,
        "revision_update_count_per_frame": emitter_count,
        "logical_array_transfer_bytes_per_frame": array_bytes,
        "logical_revision_bytes_per_frame": emitter_count * 8,
        "logical_transfer_bytes_per_frame": array_bytes + emitter_count * 8,
        "timings": {name: _summary(values) for name, values in timings.items()},
        "objects_changed": {
            "count_total": notice_count,
            "count_per_frame": 1,
            "callback_cpu_ms": _summary(notice_callback_ms[warmup_iterations:]),
            "revision_consistent_for_every_notice": notice_revision_consistent,
        },
        "memory": {
            "working_set_baseline_bytes": baseline_working_set,
            "working_set_peak_bytes": peak_working_set,
            "working_set_peak_delta_bytes": (
                peak_working_set - baseline_working_set
                if peak_working_set is not None and baseline_working_set is not None
                else None
            ),
            "scope": "whole process; native USD allocations are not isolated",
        },
        "equivalence": equivalence,
    }


def _make_sphere_stage():
    stage = Usd.Stage.CreateInMemory()
    emitter = stage.DefinePrim("/World/Emitter")
    logs = tuple(stage.DefinePrim(f"/World/Logs/Log{index}") for index in range(2))
    payload = []
    for name in (
        "fuel",
        "temperature",
        "smoke",
        "coupleRateFuel",
        "coupleRateTemperature",
        "coupleRateSmoke",
    ):
        payload.append(emitter.CreateAttribute(name, Sdf.ValueTypeNames.Float))
    revisions = [
        emitter.CreateAttribute("campfire:residentRevision", Sdf.ValueTypeNames.Int64)
    ]
    for prim in logs:
        payload.append(
            prim.CreateAttribute(
                "primvars:displayColor", Sdf.ValueTypeNames.Color3fArray
            )
        )
        for name in (
            "campfire:surfaceTemperatureK",
            "campfire:charFraction",
            "campfire:remainingMassRatio",
            "campfire:weakestSupportRatio",
        ):
            payload.append(prim.CreateAttribute(name, Sdf.ValueTypeNames.Double))
        revisions.append(
            prim.CreateAttribute("campfire:residentRevision", Sdf.ValueTypeNames.Int64)
        )
    return stage, tuple(payload), tuple(revisions)


def benchmark_current_sphere(iterations, warmup_iterations):
    stage, payload, revisions = _make_sphere_stage()
    notice_count = 0
    callback_ms = []
    active_revision = 0
    notice_revision_consistent = True

    def observe_notice(notice, _sender):
        nonlocal notice_count, notice_revision_consistent
        started = time.perf_counter_ns()
        notice.GetChangedInfoOnlyPaths()
        values = tuple(int(attribute.Get()) for attribute in revisions)
        notice_revision_consistent = notice_revision_consistent and (
            len(set(values)) == 1 and values[0] == active_revision
        )
        notice_count += 1
        callback_ms.append((time.perf_counter_ns() - started) / 1_000_000.0)

    listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, observe_notice, stage)
    timings = _empty_timings()
    total_iterations = warmup_iterations + iterations
    for offset in range(total_iterations):
        frame_started = time.perf_counter_ns()
        active_revision = offset + 2
        source_started = time.perf_counter_ns()
        scalars = tuple(float(index + 1) + active_revision * 0.001 for index in range(14))
        colors = tuple(
            (0.3 + active_revision * 0.000001, 0.12, 0.045) for _index in range(2)
        )
        source_ms = (time.perf_counter_ns() - source_started) / 1_000_000.0
        conversion_started = time.perf_counter_ns()
        values = []
        scalar_index = 0
        color_index = 0
        for attribute in payload:
            if attribute.GetTypeName() == Sdf.ValueTypeNames.Color3fArray:
                values.append(Vt.Vec3fArray([Gf.Vec3f(*colors[color_index])]))
                color_index += 1
            else:
                values.append(scalars[scalar_index])
                scalar_index += 1
        conversion_ms = (
            time.perf_counter_ns() - conversion_started
        ) / 1_000_000.0

        def set_values():
            for attribute, value in zip(payload, values):
                if not attribute.Set(value):
                    raise RuntimeError("Sphere payload Set failed")
            for attribute in revisions:
                if not attribute.Set(active_revision):
                    raise RuntimeError("Sphere revision Set failed")

        set_ms, exit_ms = _publish_in_change_block(set_values)
        frame_ms = (time.perf_counter_ns() - frame_started) / 1_000_000.0
        if offset >= warmup_iterations:
            timings["source_generation_ms"].append(source_ms)
            timings["python_cpp_boundary_ms"].append(conversion_ms)
            timings["usd_attribute_set_ms"].append(set_ms)
            timings["change_block_exit_and_notice_ms"].append(exit_ms)
            timings["publication_total_ms"].append(set_ms + exit_ms)
            timings["update_frame_total_ms"].append(frame_ms)
    listener.Revoke()
    return {
        "layout": "current_sphere_resident_snapshot",
        "log_count": 2,
        "emitter_count": 1,
        "payload_attribute_count": 16,
        "revision_attribute_count": 3,
        "attribute_update_count_per_frame": 19,
        "logical_transfer_bytes_per_frame": 136,
        "timings": {name: _summary(values) for name, values in timings.items()},
        "objects_changed": {
            "count_total": notice_count,
            "count_per_frame": 1,
            "callback_cpu_ms": _summary(callback_ms[warmup_iterations:]),
            "revision_consistent_for_every_notice": notice_revision_consistent,
        },
        "scope_note": (
            "The current 19 attributes cover one Sphere emitter plus two log "
            "visual/diagnostic snapshots; this is a control, not an equal-payload "
            "20-log Point comparison."
        ),
    }


def _verify_numpy_to_vt_copy():
    source = np.asarray([1.0, 2.0], dtype=np.float32)
    converted = Vt.FloatArray.FromNumpy(source)
    source[0] = np.float32(9.0)
    return {
        "source_after_mutation": float(source[0]),
        "vt_after_source_mutation": float(converted[0]),
        "observed_zero_copy": float(converted[0]) == float(source[0]),
    }


def analyze(iterations, warmup_iterations):
    point_counts = (360, 1800, 3600, 7200)
    sphere = benchmark_current_sphere(iterations, warmup_iterations)
    point_results = []
    for point_count in point_counts:
        log_count = point_count // 360
        emitter_counts = (1,) if log_count == 1 else (1, log_count)
        for emitter_count in emitter_counts:
            for update_mode in ("all_arrays", "dynamic_channels_only"):
                point_results.append(
                    benchmark_point_layout(
                        point_count,
                        emitter_count,
                        update_mode,
                        iterations,
                        warmup_iterations,
                    )
                )
    target = [
        result
        for result in point_results
        if result["point_count"] == 7200
    ]
    return {
        "schema_version": 1,
        "phase": "phase6bo",
        "status": "usd_transport_probe_complete_flow_probe_pending",
        "default_off": True,
        "production_code_changed": False,
        "environment": {
            "usd_package": USD_PACKAGE,
            "numpy_version": np.__version__,
            "stage": "Usd.Stage.CreateInMemory",
            "flow_version": "omni.flowusd 110.0.0",
            "iterations": iterations,
            "warmup_iterations": warmup_iterations,
        },
        "target_scale": {
            "log_count": 20,
            "cells_per_log": 1152,
            "grid": [24, 12, 4],
            "surface_candidates_per_log": 360,
            "surface_candidate_derivation": "24*12 + 2*4*12 - 2*12",
            "surface_candidate_count": 7200,
            "point_counts_measured": list(point_counts),
        },
        "schema_capability_audit": {
            "point_emitter": {
                "verified": True,
                "source": (
                    "omni.usd.schema.flow 110.0.0 generatedSchema.usda and "
                    "omni.flowusd PointCloud/Native.usda"
                ),
                "one_prim_arrays": [
                    "pointPositions",
                    "pointFuels",
                    "pointTemperatures",
                    "pointSmokes",
                ],
                "prim_per_surface_point_rejected": True,
            },
            "nano_vdb_emitter": {
                "verified": True,
                "source": "omni.usd.schema.flow 110.0.0 generatedSchema.usda",
                "word_array_channels": [
                    "nanoVdbFuels",
                    "nanoVdbTemperatures",
                    "nanoVdbSmokes",
                ],
                "channel_generation_measured": False,
            },
            "flow_voxelize_points_omnigraph": {
                "verified": True,
                "implementation": "bundled C++ OgnFlowVoxelizePoints",
                "input_memory_type": "CPU",
                "output_channels": [
                    "redNanoVdb",
                    "greenNanoVdb",
                    "blueNanoVdb",
                    "alphaNanoVdb",
                ],
                "observed_readback_behavior": (
                    "mapVoxelizePointsOutputReadback followed by resize and an "
                    "element-by-element copy into four OmniGraph uint arrays"
                ),
            },
            "public_native_boundary": {
                "python_api": ["PublicExtension", "register_all_flow_commands"],
                "bundled_cpp_uses": "omni::flowusd::IFlowUsd::voxelizePoints",
                "public_header_shipped_in_build": False,
                "fabric_direct_dynamic_emitter_api_verified": False,
                "adoption_assumed": False,
            },
            "numpy_to_vt": _verify_numpy_to_vt_copy(),
        },
        "current_sphere_control": sphere,
        "point_measurements": point_results,
        "target_point_measurements": target,
        "unmeasured_boundaries": {
            "source_or_nanovdb_generation": "Point measured; NanoVDB pending real OmniGraph run",
            "omni_flowusd_ingestion": "not exposed by the in-memory USD probe",
            "flow_emitter_or_rasterization": "pending real Flow instrumentation",
            "flow_solver_or_render": "pending real Flow instrumentation",
            "gpu_memory": "pending real Flow instrumentation",
        },
        "decision": {
            "production_emitter_changed": False,
            "physics_changed": False,
            "json_schema_changed": False,
            "defaults_changed": False,
            "usd_set_count_and_payload_bytes_are_separate_axes": True,
            "change_block_scope": (
                "Coalesces USD notices only; it does not remove source generation, "
                "NumPy/Vt copying, USD authoring, omni.flowusd ingestion, or Flow "
                "rasterization."
            ),
            "next_experiment": (
                "Run a default-off real-Kit/Flow matrix for Sphere, one Point emitter, "
                "up to 20 per-log Point emitters, and one/few NanoVDB emitters. Use "
                "OgnFlowVoxelizePoints only as a measured candidate, retain the fixed "
                "Flow version, and mark ingest/raster stages unavailable rather than "
                "inferring them when no public timer exists."
            ),
        },
    }


def render_svg(report):
    dynamic = {
        (item["layout"], item["point_count"]): item
        for item in report["point_measurements"]
        if item["update_mode"] == "dynamic_channels_only"
    }
    counts = report["target_scale"]["point_counts_measured"]
    one_values = [
        dynamic[("one_point_emitter", count)]["timings"]["publication_total_ms"][
            "p95_ms"
        ]
        for count in counts
    ]
    per_log_values = [
        dynamic[("point_emitter_per_log", count)]["timings"]["publication_total_ms"][
            "p95_ms"
        ]
        if ("point_emitter_per_log", count) in dynamic
        else one_values[index]
        for index, count in enumerate(counts)
    ]
    max_value = max(one_values + per_log_values) or 1.0
    x_positions = (155, 355, 555, 755)

    def points(values):
        return " ".join(
            f"{x},{470.0 - (value / max_value) * 230.0:.1f}"
            for x, value in zip(x_positions, values)
        )

    one_target = dynamic[("one_point_emitter", 7200)]
    split_target = dynamic[("point_emitter_per_log", 7200)]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6BO emitter transport scalability probe</title>
  <desc id="desc">USD-only Point emitter scaling separates constant Set counts from increasing array bytes; Flow timing remains pending.</desc>
  <rect width="1200" height="680" rx="32" fill="#111820"/>
  <text x="70" y="68" fill="#f4b860" font-family="Segoe UI, sans-serif" font-size="22" font-weight="700">PHASE 6BO · DEFAULT-OFF TRANSPORT SPIKE</text>
  <text x="70" y="116" fill="#fff" font-family="Segoe UI, sans-serif" font-size="35" font-weight="700">Set count is not payload cost</text>
  <text x="70" y="150" fill="#a8beca" font-family="Segoe UI, sans-serif" font-size="17">20 logs × 1,152 cells · 360 exposed candidates/log · 7,200 points at target</text>
  <rect x="70" y="185" width="760" height="335" rx="20" fill="#182128"/>
  <line x1="115" y1="470" x2="790" y2="470" stroke="#506678"/>
  <polyline points="{points(one_values)}" fill="none" stroke="#65c18c" stroke-width="5"/>
  <polyline points="{points(per_log_values)}" fill="none" stroke="#f4b860" stroke-width="5"/>
  {''.join(f'<circle cx="{x}" cy="{470.0 - (value / max_value) * 230.0:.1f}" r="7" fill="#65c18c"/>' for x, value in zip(x_positions, one_values))}
  {''.join(f'<circle cx="{x}" cy="{470.0 - (value / max_value) * 230.0:.1f}" r="7" fill="#f4b860"/>' for x, value in zip(x_positions, per_log_values))}
  {''.join(f'<text x="{x - 22}" y="500" fill="#a8beca" font-family="Consolas, monospace" font-size="15">{count}</text>' for x, count in zip(x_positions, counts))}
  <text x="115" y="220" fill="#65c18c" font-family="Segoe UI, sans-serif" font-size="16">one Point emitter · 4 Set/frame with static positions</text>
  <text x="115" y="246" fill="#f4b860" font-family="Segoe UI, sans-serif" font-size="16">per-log Point emitters · up to 80 Set/frame</text>
  <text x="115" y="545" fill="#a8beca" font-family="Segoe UI, sans-serif" font-size="15">p95 covers USD Set + ChangeBlock exit/notice; source and NumPy→Vt are reported separately in JSON.</text>
  <rect x="860" y="185" width="270" height="335" rx="20" fill="#192734" stroke="#315269"/>
  <text x="890" y="225" fill="#fff" font-family="Segoe UI, sans-serif" font-size="20" font-weight="700">7,200-point target</text>
  <text x="890" y="270" fill="#65c18c" font-family="Consolas, monospace" font-size="16">1 emitter</text>
  <text x="890" y="298" fill="#d7e1e8" font-family="Consolas, monospace" font-size="15">{one_target['logical_transfer_bytes_per_frame']:,} B/frame</text>
  <text x="890" y="326" fill="#d7e1e8" font-family="Consolas, monospace" font-size="15">p95 {one_target['timings']['publication_total_ms']['p95_ms']:.4f} ms</text>
  <text x="890" y="380" fill="#f4b860" font-family="Consolas, monospace" font-size="16">20 emitters</text>
  <text x="890" y="408" fill="#d7e1e8" font-family="Consolas, monospace" font-size="15">{split_target['logical_transfer_bytes_per_frame']:,} B/frame</text>
  <text x="890" y="436" fill="#d7e1e8" font-family="Consolas, monospace" font-size="15">p95 {split_target['timings']['publication_total_ms']['p95_ms']:.4f} ms</text>
  <text x="890" y="482" fill="#a8beca" font-family="Segoe UI, sans-serif" font-size="14">fuel + temp + smoke</text>
  <rect x="70" y="575" width="1060" height="62" rx="18" fill="#3a2d18" stroke="#f4b860"/>
  <text x="100" y="613" fill="#f4b860" font-family="Segoe UI, sans-serif" font-size="18" font-weight="700">USD-ONLY RESULT · NanoVDB generation, flowusd ingest, raster, solver and render remain unmeasured.</text>
</svg>
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=120)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    if arguments.iterations < 20 or arguments.warmup < 1:
        raise ValueError("Use at least 20 measured iterations and one warmup")
    report = analyze(arguments.iterations, arguments.warmup)
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    arguments.svg.write_text(render_svg(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
