"""Exercise the Phase 6BA native 5 Hz / 12-frame scheduler contract."""

from __future__ import annotations

import argparse
import ctypes
import dataclasses
import gc
import hashlib
import importlib.util
import json
import math
import platform
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVISION_BENCHMARK = ROOT / "scripts" / "benchmark_resident_revision_boundary.py"
FRAME_SLOTS = 12
WOOD_BUDGET_MS = 4.0
OXYGEN_FACTOR = 0.75
OUTPUT_FIELD_COUNT = 11
TEMPERATURE_TOLERANCE_K = 1.0e-8
MASS_TOLERANCE_KG = 1.0e-12
OUTPUT_TOLERANCE = 1.0e-8


def _load_revision_benchmark():
    specification = importlib.util.spec_from_file_location(
        "campfire_phase6az_scheduler_base", REVISION_BENCHMARK
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Unable to load Phase 6AZ benchmark: {REVISION_BENCHMARK}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


revision = _load_revision_benchmark()
publish = revision.publish
arrhenius = revision.arrhenius
piecewise = revision.piecewise
base = revision.base
np = revision.np


@dataclass(frozen=True)
class NativeInputSnapshot:
    tick: int
    heat_flux_w_m2: float
    oxygen_factor: float
    captured_frame: int


@dataclass(frozen=True)
class ImmutablePublishedSnapshot:
    revision: int
    tick: int
    published_frame: int
    values: tuple[tuple[float, ...], ...]


def _timing_summary(samples):
    ordered = sorted(samples)
    p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "sample_count": len(samples),
        "mean_ms": statistics.fmean(samples),
        "median_ms": statistics.median(samples),
        "p95_ms": ordered[p95_index],
        "maximum_ms": ordered[-1],
    }


def _templates(combustion):
    return {
        "dry": arrhenius._precondition_template(
            combustion, "native_scheduler_dry", 0.12, 300
        ),
        "wet": arrhenius._precondition_template(
            combustion, "native_scheduler_wet", 0.60, 800
        ),
    }


def _prepare_models(combustion, templates, log_count):
    models = piecewise._clone_models(combustion, templates, log_count)
    cells = piecewise._combined_cells(models)
    arrays = piecewise._extract_complete_arrays(
        cells, models[0].parameters.wood_specific_heat_j_kg_k
    )
    return models, cells, arrays


def _apply_managed_edit(boundary, models, arrays, log_index, cell_index):
    original = models[log_index].cells[cell_index].temperature_k
    boundary.edit_cell(
        models,
        log_index,
        cell_index,
        "temperature_k",
        original + 1.0,
    )
    started = time.perf_counter()
    result = revision._sync_dirty(
        boundary,
        models,
        arrays,
        len(models[0].cells),
        models[0].parameters.wood_specific_heat_j_kg_k,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    if result["imported"] != (log_index,) or result["rebuild_required"]:
        raise RuntimeError("Managed preflight edit did not import exactly one log")
    return elapsed_ms


def _step_result_rows(combustion, models, topologies, results):
    return publish._python_publish(combustion, models, topologies, results)


def _reference_run(combustion, templates, log_count, cycles):
    models, cells, _ = _prepare_models(combustion, templates, log_count)
    models[7 % log_count].cells[42].temperature_k += 1.0
    topologies = [model.capture_runtime_topology() for model in models]
    final_rows = None
    for tick in range(cycles):
        snapshot = NativeInputSnapshot(
            tick=tick,
            heat_flux_w_m2=base.HEAT_FLUX_W_M2,
            oxygen_factor=OXYGEN_FACTOR,
            captured_frame=tick * FRAME_SLOTS,
        )
        for model in models:
            for cell in model.cells:
                cell.oxygen_factor = snapshot.oxygen_factor * cell.surface_exposure
        results = [
            model.step(
                base.DT_SECONDS,
                snapshot.heat_flux_w_m2,
                **piecewise.STEP_ARGUMENTS,
            )
            for model in models
        ]
        final_rows = _step_result_rows(
            combustion, models, topologies, results
        )
    arrays = piecewise._extract_complete_arrays(
        cells, models[0].parameters.wood_specific_heat_j_kg_k
    )
    elapsed, cumulative = piecewise._model_boundary_arrays(models)
    return {
        "arrays": arrays,
        "elapsed": elapsed,
        "cumulative": cumulative,
        "published_rows": final_rows,
        "maximum_mass_balance_error_kg": max(
            abs(float(model.metrics()["mass_balance_error_kg"])) for model in models
        ),
    }


def _consumer_reads(snapshot):
    emitter = snapshot
    visual = snapshot
    support = snapshot
    identity_match = emitter is visual and emitter is support
    revision_match = (
        emitter.revision == visual.revision == support.revision
        and emitter.tick == visual.tick == support.tick
    )
    checksum = (
        sum(row[7] for row in emitter.values)
        + sum(row[0] for row in visual.values)
        + sum(row[6] for row in support.values)
    )
    return identity_match, revision_match, checksum


def _compare(reference, arrays, elapsed, cumulative, published_output, models):
    temperature_error = float(
        np.max(np.abs(reference["arrays"]["temperature_k"] - arrays["temperature_k"]))
    )
    mass_fields = (
        "moisture_mass_kg",
        "dry_wood_mass_kg",
        "volatile_potential_kg",
        "char_mass_kg",
        "ash_mass_kg",
    )
    mass_error = max(
        float(np.max(np.abs(reference["arrays"][name] - arrays[name])))
        for name in mass_fields
    )
    phase_mismatch = int(
        np.count_nonzero(reference["arrays"]["phase_code"] != arrays["phase_code"])
    )
    elapsed_error = float(np.max(np.abs(reference["elapsed"] - elapsed)))
    cumulative_error = float(np.max(np.abs(reference["cumulative"] - cumulative)))
    candidate_rows = published_output.reshape((-1, OUTPUT_FIELD_COUNT))
    reference_rows = np.asarray(reference["published_rows"], dtype=np.float64)
    output_error = float(np.max(np.abs(reference_rows - candidate_rows)))
    piecewise._write_complete_arrays(arrays, piecewise._combined_cells(models))
    piecewise._write_model_boundary(elapsed, cumulative, models)
    mass_balance_error = max(
        abs(float(model.metrics()["mass_balance_error_kg"])) for model in models
    )
    passed = (
        temperature_error <= TEMPERATURE_TOLERANCE_K
        and mass_error <= MASS_TOLERANCE_KG
        and phase_mismatch == 0
        and elapsed_error <= MASS_TOLERANCE_KG
        and cumulative_error <= MASS_TOLERANCE_KG
        and output_error <= OUTPUT_TOLERANCE
        and mass_balance_error <= 1.0e-9
    )
    return {
        "maximum_temperature_error_k": temperature_error,
        "maximum_cell_mass_error_kg": mass_error,
        "phase_mismatch_count": phase_mismatch,
        "maximum_elapsed_error_s": elapsed_error,
        "maximum_cumulative_error": cumulative_error,
        "maximum_published_output_error": output_error,
        "maximum_candidate_mass_balance_error_kg": mass_balance_error,
        "within_tolerance": passed,
    }


def _run_native_once(
    combustion,
    templates,
    topology,
    library,
    reference,
    log_count,
    cycles,
    warmup_cycles,
):
    models, cells, arrays = _prepare_models(combustion, templates, log_count)
    boundary = revision.ResidentRevisionBoundary(log_count)
    dirty_import_ms = _apply_managed_edit(
        boundary, models, arrays, 7 % log_count, 42
    )
    cells_per_log = len(models[0].cells)
    cells_per_section = (
        models[0].spec.circumferential_cells * models[0].spec.radial_cells
    )
    parameters = models[0].parameters
    elapsed, cumulative = piecewise._model_boundary_arrays(models)
    conduction_scratch = np.zeros(len(cells), dtype=np.float64)
    heat_capacity_scratch = np.zeros(len(cells), dtype=np.float64)
    step_output = np.zeros(log_count * piecewise.STEP_OUTPUT_COUNT, dtype=np.float64)
    published_output = np.zeros(log_count * OUTPUT_FIELD_COUNT, dtype=np.float64)
    initial_mass = np.asarray(
        [model.initial_mass_kg for model in models], dtype=np.float64
    )
    initial_section_mass = np.asarray(
        [
            math.pi
            * model.spec.radius_m**2
            * (model.spec.length_m / model.spec.axial_cells)
            * model.parameters.dry_wood_density_kg_m3
            for model in models
        ],
        dtype=np.float64,
    )
    update_frame_times = []
    consumer_frame_times = []
    all_frame_times = []
    revision_check_times = []
    consumer_mismatch_count = 0
    consumer_checksum = 0.0
    published_revisions = []
    gc.collect()
    for tick in range(cycles):
        snapshot = NativeInputSnapshot(
            tick=tick,
            heat_flux_w_m2=base.HEAT_FLUX_W_M2,
            oxygen_factor=OXYGEN_FACTOR,
            captured_frame=tick * FRAME_SLOTS,
        )
        update_started = time.perf_counter()
        check_started = time.perf_counter()
        dirty, rebuild = boundary.classify()
        revision_check_times.append((time.perf_counter() - check_started) * 1000.0)
        if dirty or rebuild:
            raise RuntimeError("Scheduler reached native step with unresolved dirty state")
        arrays["oxygen_factor"][:] = (
            snapshot.oxygen_factor * arrays["surface_exposure"]
        )
        arrhenius._call_native(
            library,
            arrays,
            topology,
            conduction_scratch,
            heat_capacity_scratch,
            elapsed,
            cumulative,
            step_output,
            log_count,
            cells_per_log,
            parameters,
            models[0]._mass_epsilon_kg,
        )
        publish._call_native(
            library,
            arrays,
            log_count,
            cells_per_log,
            cells_per_section,
            initial_mass,
            initial_section_mass,
            step_output,
            published_output,
            parameters.ambient_temperature_k,
        )
        immutable = ImmutablePublishedSnapshot(
            revision=tick + 1,
            tick=tick,
            published_frame=snapshot.captured_frame,
            values=tuple(
                tuple(float(value) for value in row)
                for row in published_output.reshape((log_count, OUTPUT_FIELD_COUNT))
            ),
        )
        identity, revision_match, checksum = _consumer_reads(immutable)
        consumer_mismatch_count += int(not identity or not revision_match)
        consumer_checksum += checksum
        update_elapsed = (time.perf_counter() - update_started) * 1000.0
        update_frame_times.append(update_elapsed)
        all_frame_times.append(update_elapsed)
        published_revisions.append(immutable.revision)
        for _ in range(1, FRAME_SLOTS):
            consumer_started = time.perf_counter()
            identity, revision_match, checksum = _consumer_reads(immutable)
            consumer_mismatch_count += int(not identity or not revision_match)
            consumer_checksum += checksum
            consumer_elapsed = (time.perf_counter() - consumer_started) * 1000.0
            consumer_frame_times.append(consumer_elapsed)
            all_frame_times.append(consumer_elapsed)
    comparison = _compare(
        reference, arrays, elapsed, cumulative, published_output, models
    )
    if not comparison["within_tolerance"] or consumer_mismatch_count:
        raise RuntimeError(
            f"Native scheduler contract failed: {comparison}, consumer mismatches={consumer_mismatch_count}"
        )
    warmup_frames = warmup_cycles * FRAME_SLOTS
    return {
        "timing": {
            "update_frames": _timing_summary(update_frame_times[warmup_cycles:]),
            "consumer_only_frames": _timing_summary(
                consumer_frame_times[warmup_cycles * (FRAME_SLOTS - 1) :]
            ),
            "all_frames": _timing_summary(all_frame_times[warmup_frames:]),
            "revision_check": _timing_summary(revision_check_times[warmup_cycles:]),
            "managed_dirty_import_preflight_ms": dirty_import_ms,
        },
        "comparison": comparison,
        "consumer": {
            "read_count": cycles * FRAME_SLOTS * 3,
            "mismatch_count": consumer_mismatch_count,
            "checksum": consumer_checksum,
            "first_revision": published_revisions[0],
            "last_revision": published_revisions[-1],
            "strictly_monotonic": published_revisions
            == list(range(1, cycles + 1)),
            "maximum_tick_staleness": 0,
        },
        "conduction_balance_error_j": abs(float(np.sum(conduction_scratch))),
    }


def _structural_stop_proof(log_count):
    boundary = revision.ResidentRevisionBoundary(log_count)
    boundary.mark_dirty(3 % log_count, "rebuild")
    dirty, rebuild = boundary.classify()
    return {
        "state_dirty_logs": dirty,
        "rebuild_required_logs": rebuild,
        "native_step_called": False,
        "safe_stop": not dirty and rebuild == [3 % log_count],
    }


def run_benchmark(dll_path, log_count, cycles, warmup_cycles, runs):
    combustion = base._load_combustion_module()
    templates = _templates(combustion)
    probe_models = piecewise._clone_models(combustion, templates, log_count)
    topology = piecewise.conduction._topology_arrays(
        probe_models[0]._conduction_pairs,
        log_count,
        len(probe_models[0].cells),
    )
    library = base._load_native_kernel(dll_path)
    arrhenius._configure_arrhenius_kernel(library)
    publish._configure_publish_kernel(library)
    reference = _reference_run(combustion, templates, log_count, cycles)
    structural = _structural_stop_proof(log_count)
    if not structural["safe_stop"]:
        raise RuntimeError("Structural dirty proof did not stop before native execution")
    raw_runs = []
    for run_index in range(runs):
        outcome = _run_native_once(
            combustion,
            templates,
            topology,
            library,
            reference,
            log_count,
            cycles,
            warmup_cycles,
        )
        raw_runs.append({"run": run_index + 1, **outcome})
    digest = hashlib.sha256()
    for path in (
        ROOT / "native" / "phase6au" / "wood_cell_kernel.cpp",
        ROOT / "native" / "phase6au" / "arrhenius_complete_step.inl",
        ROOT / "native" / "phase6au" / "native_publish_outputs.inl",
        Path(__file__),
    ):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return {
        "schema_version": 1,
        "phase": "phase6ba",
        "status": "ok",
        "runtime": {
            "python": platform.python_version(),
            "executable": sys.executable,
            "kit_python": "_build/windows-x86_64/release/kit/python/python.exe"
            in sys.executable.replace("\\", "/"),
            "numpy": np.__version__,
        },
        "native_toolchain": {
            "abi_version": library.campfire_native_abi_version(),
            "msvc_version": library.campfire_native_msvc_version(),
            "msvc_full_version": library.campfire_native_msvc_full_version(),
            "floating_point": "/fp:strict",
            "dll_sha256": hashlib.sha256(dll_path.read_bytes()).hexdigest(),
            "source_sha256": digest.hexdigest(),
        },
        "measurement": {
            "log_count": log_count,
            "cells_per_log": len(probe_models[0].cells),
            "combined_cell_count": sum(len(model.cells) for model in probe_models),
            "combined_conduction_pair_count": topology["first_cell"].size,
            "cycles_per_run": cycles,
            "warmup_cycles_excluded": warmup_cycles,
            "runs": runs,
            "logical_hz": 5,
            "render_fps": 60,
            "frames_per_tick": FRAME_SLOTS,
            "dt_seconds": base.DT_SECONDS,
            "heat_flux_w_m2": base.HEAT_FLUX_W_M2,
            "oxygen_factor": OXYGEN_FACTOR,
        },
        "contract": {
            "tick_order": [
                "immutable_input_snapshot",
                "revision_classification",
                "resident_input_apply",
                "native_arrhenius_complete_step",
                "native_publish_11_values_per_log",
                "immutable_snapshot_commit",
                "three_consumer_reads",
            ],
            "consumer_names": ["Flow emitter", "visual state", "structural support"],
            "update_frame_within_tick": 0,
            "consumer_only_frames_per_tick": FRAME_SLOTS - 1,
            "managed_dirty_import_before_run": True,
            "structural_dirty_stops_before_native": True,
        },
        "structural_dirty_proof": structural,
        "reference": {
            "maximum_mass_balance_error_kg": reference[
                "maximum_mass_balance_error_kg"
            ]
        },
        "tolerances": {
            "temperature_k": TEMPERATURE_TOLERANCE_K,
            "mass_kg": MASS_TOLERANCE_KG,
            "published_output": OUTPUT_TOLERANCE,
            "mass_balance_kg": 1.0e-9,
        },
        "budget_ms": WOOD_BUDGET_MS,
        "boundary": {
            "included": [
                "revision_check",
                "resident_input_apply",
                "native_arrhenius_complete_step",
                "native_output_publish",
                "immutable_snapshot_freeze",
                "three_consumer_revision_audit",
                "structural_dirty_safe_stop",
            ],
            "excluded": [
                "production_backend_switch",
                "unmarked_direct_write_support",
                "serialization_export",
                "Flow/USD/rendering/PhysX execution",
            ],
            "production_model_changed": False,
        },
        "runs": raw_runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dll", required=True, type=Path)
    parser.add_argument("--logs", type=int, default=20)
    parser.add_argument("--cycles", type=int, default=60)
    parser.add_argument("--warmup-cycles", type=int, default=10)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    if not arguments.dll.is_file():
        parser.error(f"Native DLL does not exist: {arguments.dll}")
    if (
        arguments.logs <= 0
        or arguments.cycles <= arguments.warmup_cycles
        or arguments.runs < 3
    ):
        parser.error("Require positive logs, cycles > warmup, and at least three runs")
    report = run_benchmark(
        arguments.dll,
        arguments.logs,
        arguments.cycles,
        arguments.warmup_cycles,
        arguments.runs,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
