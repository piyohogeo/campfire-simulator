"""Exercise the Phase 6BB resident backend lifecycle contract."""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import importlib.util
import json
import math
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_BENCHMARK = ROOT / "scripts" / "benchmark_native_scheduler_contract.py"
OUTPUT_FIELD_COUNT = 11


def _load_scheduler_benchmark():
    specification = importlib.util.spec_from_file_location(
        "campfire_phase6ba_lifecycle_base", SCHEDULER_BENCHMARK
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Unable to load Phase 6BA benchmark: {SCHEDULER_BENCHMARK}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


scheduler = _load_scheduler_benchmark()
revision = scheduler.revision
publish = scheduler.publish
arrhenius = scheduler.arrhenius
piecewise = scheduler.piecewise
base = scheduler.base
np = scheduler.np


class RevisionConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class EditSession:
    log_index: int
    resident_revision: int
    model_snapshot: dict


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


class ResidentBackendProbe:
    """Transactional probe around the already-qualified resident array boundary."""

    def __init__(self, combustion, templates, library, log_count):
        self.combustion = combustion
        self.library = library
        self.log_count = log_count
        self.models, self.cells, self.arrays = scheduler._prepare_models(
            combustion, templates, log_count
        )
        self.cells_per_log = len(self.models[0].cells)
        self.cells_per_section = (
            self.models[0].spec.circumferential_cells
            * self.models[0].spec.radial_cells
        )
        self.parameters = self.models[0].parameters
        self.topology = piecewise.conduction._topology_arrays(
            self.models[0]._conduction_pairs,
            log_count,
            self.cells_per_log,
        )
        self.elapsed, self.cumulative = piecewise._model_boundary_arrays(self.models)
        self.boundary = revision.ResidentRevisionBoundary(log_count)
        self.resident_revision = 0
        self.exported_revisions = [-1] * log_count
        self.closed = False
        self._allocate_scratch()

    def _allocate_scratch(self):
        self.conduction_scratch = np.zeros(len(self.cells), dtype=np.float64)
        self.heat_capacity_scratch = np.zeros(len(self.cells), dtype=np.float64)
        self.step_output = np.zeros(
            self.log_count * piecewise.STEP_OUTPUT_COUNT, dtype=np.float64
        )
        self.published_output = np.zeros(
            self.log_count * OUTPUT_FIELD_COUNT, dtype=np.float64
        )
        self.initial_mass = np.asarray(
            [model.initial_mass_kg for model in self.models], dtype=np.float64
        )
        self.initial_section_mass = np.asarray(
            [
                math.pi
                * model.spec.radius_m**2
                * (model.spec.length_m / model.spec.axial_cells)
                * model.parameters.dry_wood_density_kg_m3
                for model in self.models
            ],
            dtype=np.float64,
        )

    def _require_open(self):
        if self.closed:
            raise RuntimeError("Resident backend is closed")

    def _native_snapshot(self):
        return {
            "arrays": {name: values.copy() for name, values in self.arrays.items()},
            "elapsed": self.elapsed.copy(),
            "cumulative": self.cumulative.copy(),
            "step_output": self.step_output.copy(),
            "published_output": self.published_output.copy(),
            "resident_revision": self.resident_revision,
        }

    def _restore_native_snapshot(self, snapshot):
        for name, values in snapshot["arrays"].items():
            self.arrays[name][:] = values
        self.elapsed[:] = snapshot["elapsed"]
        self.cumulative[:] = snapshot["cumulative"]
        self.step_output[:] = snapshot["step_output"]
        self.published_output[:] = snapshot["published_output"]
        self.resident_revision = snapshot["resident_revision"]

    def native_digest(self):
        digest = hashlib.sha256()
        for name in sorted(self.arrays):
            digest.update(name.encode("utf-8"))
            digest.update(self.arrays[name].tobytes())
        digest.update(self.elapsed.tobytes())
        digest.update(self.cumulative.tobytes())
        digest.update(self.step_output.tobytes())
        digest.update(self.published_output.tobytes())
        digest.update(str(self.resident_revision).encode("ascii"))
        return digest.hexdigest()

    def step(self, inject_failure_after_native=False):
        self._require_open()
        dirty, rebuild = self.boundary.classify()
        if dirty or rebuild:
            raise RuntimeError("Resident step refused unresolved dirty state")
        snapshot = self._native_snapshot()
        try:
            self.arrays["oxygen_factor"][:] = (
                scheduler.OXYGEN_FACTOR * self.arrays["surface_exposure"]
            )
            arrhenius._call_native(
                self.library,
                self.arrays,
                self.topology,
                self.conduction_scratch,
                self.heat_capacity_scratch,
                self.elapsed,
                self.cumulative,
                self.step_output,
                self.log_count,
                self.cells_per_log,
                self.parameters,
                self.models[0]._mass_epsilon_kg,
            )
            if inject_failure_after_native:
                raise RuntimeError("Injected post-native failure")
            publish._call_native(
                self.library,
                self.arrays,
                self.log_count,
                self.cells_per_log,
                self.cells_per_section,
                self.initial_mass,
                self.initial_section_mass,
                self.step_output,
                self.published_output,
                self.parameters.ambient_temperature_k,
            )
            self.resident_revision += 1
        except Exception:
            self._restore_native_snapshot(snapshot)
            raise

    def export_logs(self, indices):
        self._require_open()
        started = time.perf_counter()
        cumulative_matrix = self.cumulative.reshape(
            (self.log_count, piecewise.CUMULATIVE_OUTPUT_COUNT)
        )
        for log_index in indices:
            begin = log_index * self.cells_per_log
            end = begin + self.cells_per_log
            sliced = {name: values[begin:end] for name, values in self.arrays.items()}
            piecewise._write_complete_arrays(sliced, self.models[log_index].cells)
            self.models[log_index].elapsed_seconds = float(self.elapsed[log_index])
            for field_index, field in enumerate(piecewise.CUMULATIVE_FIELDS):
                setattr(
                    self.models[log_index],
                    field,
                    float(cumulative_matrix[log_index, field_index]),
                )
            self.exported_revisions[log_index] = self.resident_revision
        return (time.perf_counter() - started) * 1000.0

    def begin_edit(self, log_index):
        self.export_logs((log_index,))
        return EditSession(
            log_index=log_index,
            resident_revision=self.resident_revision,
            model_snapshot=copy.deepcopy(self.models[log_index].to_dict()),
        )

    def commit_state_edit(self, session, cell_index, field, value, inject_failure=False):
        self._require_open()
        if session.resident_revision != self.resident_revision:
            raise RevisionConflict(
                f"Edit revision {session.resident_revision} is stale; resident is {self.resident_revision}"
            )
        log_index = session.log_index
        native_snapshot = self._native_snapshot()
        model_snapshot = copy.deepcopy(self.models[log_index].to_dict())
        ledger_snapshot = dataclasses.replace(self.boundary._states[log_index])
        try:
            self.boundary.edit_cell(
                self.models, log_index, cell_index, field, value
            )
            if inject_failure:
                raise RuntimeError("Injected managed-edit failure")
            result = revision._sync_dirty(
                self.boundary,
                self.models,
                self.arrays,
                self.cells_per_log,
                self.parameters.wood_specific_heat_j_kg_k,
            )
            if result["rebuild_required"] or result["imported"] != (log_index,):
                raise RuntimeError(f"Unexpected state-edit classification: {result}")
            if not all(np.all(np.isfinite(values)) for values in self.arrays.values()):
                raise RuntimeError("Non-finite resident state after edit")
        except Exception:
            self._restore_native_snapshot(native_snapshot)
            self.models[log_index] = self.combustion.WoodThermalModel.from_dict(
                model_snapshot
            )
            self.cells = piecewise._combined_cells(self.models)
            self.boundary._states[log_index] = ledger_snapshot
            raise

    def commit_structural_edit(self, log_index, cell_index, field, value):
        self._require_open()
        self.export_logs(range(self.log_count))
        model_snapshots = [copy.deepcopy(model.to_dict()) for model in self.models]
        ledger_snapshots = [dataclasses.replace(state) for state in self.boundary._states]
        try:
            self.boundary.edit_cell(self.models, log_index, cell_index, field, value)
            state_dirty, rebuild = self.boundary.classify()
            if state_dirty or rebuild != [log_index]:
                raise RuntimeError("Structural edit was not isolated as rebuild-required")
            candidates = [
                self.combustion.WoodThermalModel.from_dict(model.to_dict())
                for model in self.models
            ]
            reference_pairs = candidates[0]._conduction_pairs
            if any(
                model._conduction_pairs != reference_pairs for model in candidates[1:]
            ):
                raise RuntimeError(
                    "Heterogeneous per-log topology is outside this backend candidate"
                )
            candidate_cells = piecewise._combined_cells(candidates)
            candidate_arrays = piecewise._extract_complete_arrays(
                candidate_cells, candidates[0].parameters.wood_specific_heat_j_kg_k
            )
            candidate_topology = piecewise.conduction._topology_arrays(
                candidates[0]._conduction_pairs,
                self.log_count,
                len(candidates[0].cells),
            )
            if len(candidate_cells) != len(self.cells):
                raise RuntimeError("Structural candidate changed cell count")
            self.models = candidates
            self.cells = candidate_cells
            self.arrays = candidate_arrays
            self.topology = candidate_topology
            self.elapsed, self.cumulative = piecewise._model_boundary_arrays(self.models)
            self.boundary.accept_rebuild(rebuild)
            self._allocate_scratch()
            self.exported_revisions = [self.resident_revision] * self.log_count
        except Exception:
            self.models = [
                self.combustion.WoodThermalModel.from_dict(data)
                for data in model_snapshots
            ]
            self.cells = piecewise._combined_cells(self.models)
            self.arrays = piecewise._extract_complete_arrays(
                self.cells, self.models[0].parameters.wood_specific_heat_j_kg_k
            )
            self.elapsed, self.cumulative = piecewise._model_boundary_arrays(self.models)
            self.topology = piecewise.conduction._topology_arrays(
                self.models[0]._conduction_pairs,
                self.log_count,
                self.cells_per_log,
            )
            self.boundary._states = ledger_snapshots
            self._allocate_scratch()
            raise

    def serialize_log(self, log_index):
        self.export_logs((log_index,))
        payload = json.dumps(
            self.models[log_index].to_dict(),
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
        restored = self.combustion.WoodThermalModel.from_dict(json.loads(payload))
        restored_payload = json.dumps(
            restored.to_dict(), separators=(",", ":"), sort_keys=True, allow_nan=False
        )
        if payload != restored_payload:
            raise RuntimeError("Serialized log did not round-trip exactly")
        return payload

    def shutdown(self):
        if self.closed:
            return {"already_closed": True, "payloads": ()}
        elapsed_ms = self.export_logs(range(self.log_count))
        payloads = tuple(
            json.dumps(
                model.to_dict(), separators=(",", ":"), sort_keys=True, allow_nan=False
            )
            for model in self.models
        )
        for payload in payloads:
            self.combustion.WoodThermalModel.from_dict(json.loads(payload))
        self.closed = True
        return {
            "already_closed": False,
            "export_ms": elapsed_ms,
            "payloads": payloads,
        }


def _run_once(dll_path, log_count, initial_steps):
    combustion = base._load_combustion_module()
    templates = scheduler._templates(combustion)
    library = base._load_native_kernel(dll_path)
    arrhenius._configure_arrhenius_kernel(library)
    publish._configure_publish_kernel(library)
    backend = ResidentBackendProbe(combustion, templates, library, log_count)

    for _ in range(initial_steps):
        backend.step()
    serialized = backend.serialize_log(7 % log_count)

    stale_session = backend.begin_edit(7 % log_count)
    backend.step()
    conflict_detected = False
    try:
        backend.commit_state_edit(
            stale_session,
            42,
            "temperature_k",
            backend.models[7 % log_count].cells[42].temperature_k + 1.0,
        )
    except RevisionConflict:
        conflict_detected = True

    state_session = backend.begin_edit(7 % log_count)
    edited_temperature = backend.models[7 % log_count].cells[42].temperature_k + 1.0
    backend.commit_state_edit(
        state_session, 42, "temperature_k", edited_temperature
    )
    state_begin = (7 % log_count) * backend.cells_per_log
    state_import_exact = (
        float(backend.arrays["temperature_k"][state_begin + 42])
        == edited_temperature
    )

    rollback_session = backend.begin_edit(5 % log_count)
    edit_digest_before = backend.native_digest()
    edit_model_before = copy.deepcopy(rollback_session.model_snapshot)
    edit_rollback_detected = False
    try:
        backend.commit_state_edit(
            rollback_session,
            17,
            "temperature_k",
            backend.models[5 % log_count].cells[17].temperature_k + 10.0,
            inject_failure=True,
        )
    except RuntimeError:
        edit_rollback_detected = (
            backend.native_digest() == edit_digest_before
            and backend.models[5 % log_count].to_dict() == edit_model_before
        )

    structural_log = 3 % log_count
    old_volume = backend.models[structural_log].cells[11].volume_m3
    old_topology_edges = int(backend.topology["first_cell"].size)
    backend.commit_structural_edit(
        structural_log, 11, "volume_m3", old_volume * 1.001
    )
    structural_rebuild_exact = (
        backend.models[structural_log].cells[11].volume_m3 == old_volume * 1.001
        and int(backend.topology["first_cell"].size) == old_topology_edges
    )

    step_digest_before = backend.native_digest()
    step_rollback_detected = False
    try:
        backend.step(inject_failure_after_native=True)
    except RuntimeError:
        step_rollback_detected = backend.native_digest() == step_digest_before

    single_export_samples = []
    for _ in range(25):
        single_export_samples.append(backend.export_logs((7 % log_count,)))
    shutdown = backend.shutdown()
    second_shutdown = backend.shutdown()
    use_after_close_rejected = False
    try:
        backend.step()
    except RuntimeError:
        use_after_close_rejected = True

    gates = {
        "serialization_round_trip_exact": bool(serialized),
        "stale_edit_conflict_detected": conflict_detected,
        "state_import_exact": state_import_exact,
        "managed_edit_failure_rolled_back": edit_rollback_detected,
        "structural_candidate_rebuilt": structural_rebuild_exact,
        "post_native_failure_rolled_back": step_rollback_detected,
        "shutdown_exported_all_logs": len(shutdown["payloads"]) == log_count,
        "shutdown_idempotent": second_shutdown["already_closed"],
        "use_after_close_rejected": use_after_close_rejected,
    }
    if not all(gates.values()):
        raise RuntimeError(f"Lifecycle gate failed: {gates}")
    return {
        "measurement": {
            "log_count": log_count,
            "cells_per_log": backend.cells_per_log,
            "initial_native_steps": initial_steps,
            "single_export_samples": 25,
        },
        "timing": {
            "single_log_export": _timing_summary(single_export_samples),
            "shutdown_all_log_export_ms": shutdown["export_ms"],
        },
        "gates": gates,
        "contract": {
            "edit_order": [
                "export_fresh_python_view",
                "capture_resident_revision",
                "reject_stale_revision",
                "validate_candidate",
                "commit_or_restore",
            ],
            "structural_order": [
                "export_all_logs",
                "build_candidate_backend",
                "require_homogeneous_log_topology",
                "validate_candidate",
                "atomic_reference_swap",
            ],
            "shutdown_order": ["export_all_logs", "serialize", "close"],
            "production_backend_changed": False,
        },
    }


def run_benchmark(dll_path, log_count, initial_steps, runs):
    outcomes = [_run_once(dll_path, log_count, initial_steps) for _ in range(runs)]
    gate_names = tuple(outcomes[0]["gates"])
    return {
        "schema_version": 1,
        "phase": "phase6bb",
        "status": "ok",
        "measurement": {
            **outcomes[0]["measurement"],
            "runs": runs,
        },
        "contract": outcomes[0]["contract"],
        "gates": {
            name: all(outcome["gates"][name] for outcome in outcomes)
            for name in gate_names
        },
        "runs": [
            {"run": index + 1, "timing": outcome["timing"], "gates": outcome["gates"]}
            for index, outcome in enumerate(outcomes)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dll", required=True, type=Path)
    parser.add_argument("--logs", type=int, default=20)
    parser.add_argument("--initial-steps", type=int, default=8)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    if not arguments.dll.is_file():
        parser.error(f"Native DLL does not exist: {arguments.dll}")
    if arguments.logs <= 0 or arguments.initial_steps <= 0 or arguments.runs < 3:
        parser.error("Require positive logs/steps and at least three runs")
    report = run_benchmark(
        arguments.dll, arguments.logs, arguments.initial_steps, arguments.runs
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
