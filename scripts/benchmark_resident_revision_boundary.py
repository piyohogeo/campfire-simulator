"""Measure the Phase 6AZ explicit revision/dirty resident-state boundary."""

from __future__ import annotations

import argparse
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
PUBLISH_BENCHMARK = ROOT / "scripts" / "benchmark_native_publish_boundary.py"
WOOD_BUDGET_MS = 4.0
STATE_FIELDS = (
    "temperature_k",
    "moisture_mass_kg",
    "dry_wood_mass_kg",
    "volatile_potential_kg",
    "char_mass_kg",
    "ash_mass_kg",
    "oxygen_factor",
    "surface_exposure",
    "external_area_m2",
    "dry_wood_specific_heat_j_kg_k",
    "phase",
)
REBUILD_FIELDS = ("volume_m3", "dry_wood_specific_heat_model")


def _load_publish_benchmark():
    specification = importlib.util.spec_from_file_location(
        "campfire_phase6ay_revision_base", PUBLISH_BENCHMARK
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Unable to load Phase 6AY benchmark: {PUBLISH_BENCHMARK}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


publish = _load_publish_benchmark()
arrhenius = publish.arrhenius
piecewise = publish.piecewise
base = publish.base
np = publish.np
PHASE_TO_CODE = base.PHASE_TO_CODE


@dataclass
class RevisionState:
    revision: int = 0
    imported_revision: int = 0
    dirty_kind: str = "clean"


class ResidentRevisionBoundary:
    """Explicit ownership ledger; it intentionally does not scan public cells."""

    def __init__(self, log_count: int):
        self._states = [RevisionState() for _ in range(log_count)]
        self.import_count = 0
        self.rebuild_count = 0

    def mark_dirty(self, log_index: int, kind: str = "state") -> int:
        if kind not in ("state", "rebuild"):
            raise ValueError("kind must be 'state' or 'rebuild'")
        state = self._states[log_index]
        state.revision += 1
        if kind == "rebuild" or state.dirty_kind == "rebuild":
            state.dirty_kind = "rebuild"
        else:
            state.dirty_kind = "state"
        return state.revision

    def edit_cell(self, models, log_index: int, cell_index: int, field: str, value):
        if field not in STATE_FIELDS and field not in REBUILD_FIELDS:
            raise ValueError(f"Unsupported public cell field: {field}")
        setattr(models[log_index].cells[cell_index], field, value)
        kind = "rebuild" if field in REBUILD_FIELDS else "state"
        return self.mark_dirty(log_index, kind)

    def classify(self):
        state_dirty = []
        rebuild = []
        for index, state in enumerate(self._states):
            if state.revision == state.imported_revision:
                continue
            if state.dirty_kind == "rebuild":
                rebuild.append(index)
            else:
                state_dirty.append(index)
        return state_dirty, rebuild

    def accept_import(self, log_indices):
        for index in log_indices:
            state = self._states[index]
            state.imported_revision = state.revision
            state.dirty_kind = "clean"
            self.import_count += 1

    def accept_rebuild(self, log_indices):
        for index in log_indices:
            state = self._states[index]
            state.imported_revision = state.revision
            state.dirty_kind = "clean"
            self.rebuild_count += 1

    def revisions(self):
        return tuple(state.revision for state in self._states)

    def imported_revisions(self):
        return tuple(state.imported_revision for state in self._states)


def _sync_log(model, arrays, log_index: int, cells_per_log: int, default_cp: float):
    begin = log_index * cells_per_log
    end = begin + cells_per_log
    cells = model.cells
    mappings = {
        "temperature_k": "temperature_k",
        "moisture_mass_kg": "moisture_mass_kg",
        "dry_wood_mass_kg": "dry_wood_mass_kg",
        "volatile_potential_kg": "volatile_potential_kg",
        "char_mass_kg": "char_mass_kg",
        "ash_mass_kg": "ash_mass_kg",
        "oxygen_factor": "oxygen_factor",
        "surface_exposure": "surface_exposure",
        "external_area_m2": "external_area_m2",
    }
    for array_name, field in mappings.items():
        arrays[array_name][begin:end] = np.fromiter(
            (getattr(cell, field) for cell in cells),
            dtype=np.float64,
            count=cells_per_log,
        )
    arrays["dry_specific_heat_j_kg_k"][begin:end] = np.fromiter(
        (
            cell.dry_wood_specific_heat_j_kg_k
            if cell.dry_wood_specific_heat_j_kg_k is not None
            else default_cp
            for cell in cells
        ),
        dtype=np.float64,
        count=cells_per_log,
    )
    arrays["phase_code"][begin:end] = np.fromiter(
        (PHASE_TO_CODE[cell.phase] for cell in cells),
        dtype=np.int32,
        count=cells_per_log,
    )


def _sync_dirty(boundary, models, arrays, cells_per_log: int, default_cp: float):
    state_dirty, rebuild = boundary.classify()
    if rebuild:
        return {"imported": (), "rebuild_required": tuple(rebuild)}
    for index in state_dirty:
        _sync_log(models[index], arrays, index, cells_per_log, default_cp)
    boundary.accept_import(state_dirty)
    return {"imported": tuple(state_dirty), "rebuild_required": ()}


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


def _measure(operation, iterations: int):
    samples = []
    for _ in range(iterations):
        started = time.perf_counter()
        operation()
        samples.append((time.perf_counter() - started) * 1000.0)
    return _timing_summary(samples)


def _prepare_models(log_count: int):
    combustion = base._load_combustion_module()
    templates = {
        "dry": arrhenius._precondition_template(combustion, "revision_dry", 0.12, 300),
        "wet": arrhenius._precondition_template(combustion, "revision_wet", 0.60, 800),
    }
    models = piecewise._clone_models(combustion, templates, log_count)
    cells = piecewise._combined_cells(models)
    arrays = piecewise._extract_complete_arrays(
        cells, models[0].parameters.wood_specific_heat_j_kg_k
    )
    return models, cells, arrays


def _array_equivalence(reference, candidate):
    float_fields = [name for name in reference if name != "phase_code"]
    maximum = max(
        float(np.max(np.abs(reference[name] - candidate[name])))
        for name in float_fields
    )
    phase_mismatches = int(np.count_nonzero(reference["phase_code"] != candidate["phase_code"]))
    return {
        "maximum_absolute_float_error": maximum,
        "phase_mismatch_count": phase_mismatches,
        "passed": maximum == 0.0 and phase_mismatches == 0,
    }


def run_benchmark(log_count: int, iterations: int, runs: int):
    models, cells, arrays = _prepare_models(log_count)
    cells_per_log = len(models[0].cells)
    default_cp = models[0].parameters.wood_specific_heat_j_kg_k

    proof_boundary = ResidentRevisionBoundary(log_count)
    proof_log = 7 % log_count
    proof_cell = 42
    original_temperature = models[proof_log].cells[proof_cell].temperature_k
    revision = proof_boundary.edit_cell(
        models,
        proof_log,
        proof_cell,
        "temperature_k",
        original_temperature + 1.0,
    )
    dirty_before, rebuild_before = proof_boundary.classify()
    sync_result = _sync_dirty(
        proof_boundary, models, arrays, cells_per_log, default_cp
    )
    expected = piecewise._extract_complete_arrays(cells, default_cp)
    equivalence = _array_equivalence(expected, arrays)
    if not equivalence["passed"]:
        raise RuntimeError(f"Dirty log import mismatch: {equivalence}")

    structural_original = models[proof_log].cells[proof_cell].volume_m3
    structural_revision = proof_boundary.edit_cell(
        models,
        proof_log,
        proof_cell,
        "volume_m3",
        structural_original * 1.001,
    )
    _, structural_rebuild = proof_boundary.classify()
    models[proof_log].cells[proof_cell].volume_m3 = structural_original
    proof_boundary.accept_rebuild(structural_rebuild)

    unmarked_original = models[0].cells[0].temperature_k
    models[0].cells[0].temperature_k = unmarked_original + 1.0
    unmarked_dirty, unmarked_rebuild = proof_boundary.classify()
    models[0].cells[0].temperature_k = unmarked_original

    timing_models, timing_cells, timing_arrays = _prepare_models(log_count)
    timing_boundary = ResidentRevisionBoundary(log_count)
    timing_cell_index = 13
    direction = 1.0

    def clean_revision_check():
        return timing_boundary.classify()

    def one_log_dirty_sync():
        nonlocal direction
        cell = timing_models[0].cells[timing_cell_index]
        timing_boundary.edit_cell(
            timing_models,
            0,
            timing_cell_index,
            "temperature_k",
            cell.temperature_k + direction * 0.001,
        )
        direction = -direction
        return _sync_dirty(
            timing_boundary,
            timing_models,
            timing_arrays,
            cells_per_log,
            default_cp,
        )

    def full_twenty_log_import():
        return piecewise._extract_complete_arrays(timing_cells, default_cp)

    methods = {
        "clean_revision_check": clean_revision_check,
        "one_log_dirty_sync": one_log_dirty_sync,
        "full_twenty_log_import": full_twenty_log_import,
    }
    orders = [
        list(methods),
        ["one_log_dirty_sync", "full_twenty_log_import", "clean_revision_check"],
        ["full_twenty_log_import", "clean_revision_check", "one_log_dirty_sync"],
    ]
    raw_runs = []
    for run_index in range(runs):
        gc.collect()
        order = orders[run_index % len(orders)]
        timings = {}
        for name in order:
            timings[name] = _measure(methods[name], iterations)
        raw_runs.append({"run": run_index + 1, "order": order, "methods": timings})

    source_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return {
        "schema_version": 1,
        "phase": "phase6az",
        "status": "ok",
        "runtime": {
            "python": platform.python_version(),
            "executable": sys.executable,
            "kit_python": "_build/windows-x86_64/release/kit/python/python.exe"
            in sys.executable.replace("\\", "/"),
            "numpy": np.__version__,
        },
        "source_sha256": source_sha256,
        "measurement": {
            "log_count": log_count,
            "cells_per_log": cells_per_log,
            "combined_cell_count": len(cells),
            "iterations_per_method": iterations,
            "runs": runs,
            "balanced_method_order": True,
        },
        "contract": {
            "state_import_fields": list(STATE_FIELDS),
            "rebuild_fields": list(REBUILD_FIELDS),
            "explicit_mark_required": True,
            "unmarked_public_write_is_supported_in_native_mode": False,
            "production_public_fields_or_schema_changed": False,
        },
        "proof": {
            "state_mutation": {
                "log_index": proof_log,
                "cell_index": proof_cell,
                "field": "temperature_k",
                "delta_k": 1.0,
                "revision": revision,
                "dirty_before_sync": dirty_before,
                "rebuild_before_sync": rebuild_before,
                "imported_logs": list(sync_result["imported"]),
                "rebuild_required": list(sync_result["rebuild_required"]),
                "array_equivalence": equivalence,
            },
            "structural_mutation": {
                "field": "volume_m3",
                "scale": 1.001,
                "revision": structural_revision,
                "rebuild_required_logs": structural_rebuild,
                "restored_after_probe": True,
            },
            "unmarked_legacy_mutation": {
                "field": "temperature_k",
                "delta_k": 1.0,
                "detected_by_revision_check": bool(unmarked_dirty or unmarked_rebuild),
                "restored_after_probe": True,
            },
        },
        "budget_ms": WOOD_BUDGET_MS,
        "boundary": {
            "included": [
                "clean_revision_check",
                "one_log_state_import",
                "twenty_log_full_import_reference",
                "structural_rebuild_classification",
                "unmarked_write_limitation",
            ],
            "excluded": [
                "production_cell_setter_instrumentation",
                "native_step_execution",
                "immutable_output_publication",
                "5_hz_scheduler_integration",
                "consumer_revision_fanout",
                "Flow/USD/rendering/PhysX",
            ],
            "production_model_changed": False,
        },
        "runs": raw_runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--logs", type=int, default=20)
    parser.add_argument("--iterations", type=int, default=300)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    if arguments.logs <= 0 or arguments.iterations < 40 or arguments.runs < 3:
        parser.error("Require positive logs, at least 40 iterations, and three runs")
    report = run_benchmark(arguments.logs, arguments.iterations, arguments.runs)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
