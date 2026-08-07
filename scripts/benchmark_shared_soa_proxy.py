"""Headless research spike for a shared NumPy/C++ SoA authority.

This is deliberately isolated from the production backend.  It exercises the
already-audited Phase 6AU C ABI with NumPy-owned buffers, generation-checked
Python proxies, transactional edits, and fail-fast lifecycle ownership.
"""

from __future__ import annotations

import argparse
import copy
import gc
import hashlib
import json
import math
import platform
import statistics
import sys
import threading
import time
import weakref
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_BENCHMARK = ROOT / "scripts" / "benchmark_native_wood_boundary.py"


def _load_base():
    import importlib.util

    specification = importlib.util.spec_from_file_location(
        "campfire_shared_soa_base", BASE_BENCHMARK
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Unable to load native boundary: {BASE_BENCHMARK}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


base = _load_base()
np = base.np

PHASE_TO_CODE = base.PHASE_TO_CODE
CODE_TO_PHASE = base.CODE_TO_PHASE
FLOAT_FIELDS = (
    "temperature_k",
    "moisture_mass_kg",
    "dry_wood_mass_kg",
    "volatile_potential_kg",
    "char_mass_kg",
    "ash_mass_kg",
    "oxygen_factor",
    "surface_exposure",
    "volume_m3",
    "external_area_m2",
    "dry_specific_heat_j_kg_k",
)
NATIVE_FLOAT_FIELDS = base.DOUBLE_FIELDS
PUBLIC_TO_ARRAY = {
    "temperature_k": "temperature_k",
    "moisture_mass_kg": "moisture_mass_kg",
    "dry_wood_mass_kg": "dry_wood_mass_kg",
    "volatile_potential_kg": "volatile_potential_kg",
    "char_mass_kg": "char_mass_kg",
    "ash_mass_kg": "ash_mass_kg",
    "oxygen_factor": "oxygen_factor",
    "surface_exposure": "surface_exposure",
    "volume_m3": "volume_m3",
    "external_area_m2": "external_area_m2",
}
MASS_FIELDS = {
    "moisture_mass_kg",
    "dry_wood_mass_kg",
    "volatile_potential_kg",
    "char_mass_kg",
    "ash_mass_kg",
}


class BackendBusy(RuntimeError):
    pass


class StaleProxy(RuntimeError):
    pass


class StructuralEditRequired(RuntimeError):
    pass


@dataclass(frozen=True)
class SharedSoASnapshot:
    revision: int
    tick: int
    structure_generation: int
    temperature_prefix_k: tuple[float, ...]
    state_sha256: str


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


def _canonical_json(payload):
    return json.dumps(
        payload, separators=(",", ":"), sort_keys=True, allow_nan=False
    )


class WoodCellProxy:
    __slots__ = ("_backend_ref", "_index", "_generation")

    def __init__(self, backend, index):
        self._backend_ref = weakref.ref(backend)
        self._index = index
        self._generation = backend.structure_generation

    def _backend(self):
        backend = self._backend_ref()
        if backend is None:
            raise StaleProxy("Shared SoA owner no longer exists")
        backend._require_proxy(self._generation)
        return backend

    def _get(self, field):
        return self._backend()._get_numeric(self._index, field)

    def _set(self, field, value):
        self._backend()._set_numeric(self._index, field, value)

    @property
    def current_mass_kg(self):
        return (
            self.moisture_mass_kg
            + self.dry_wood_mass_kg
            + self.char_mass_kg
            + self.ash_mass_kg
        )

    @property
    def phase(self):
        return self._backend()._get_phase(self._index)

    @phase.setter
    def phase(self, value):
        self._backend()._set_phase(self._index, value)

    @property
    def dry_wood_specific_heat_j_kg_k(self):
        return self._backend()._get_specific_heat(self._index)

    @dry_wood_specific_heat_j_kg_k.setter
    def dry_wood_specific_heat_j_kg_k(self, value):
        self._backend()._set_specific_heat(self._index, value)

    @property
    def dry_wood_specific_heat_model(self):
        backend = self._backend()
        return backend._specific_heat_models[self._index]

    @dry_wood_specific_heat_model.setter
    def dry_wood_specific_heat_model(self, _value):
        raise StructuralEditRequired(
            "dry_wood_specific_heat_model requires candidate rebuild"
        )


def _numeric_property(field):
    return property(
        lambda self: self._get(field),
        lambda self, value: self._set(field, value),
    )


for _field in PUBLIC_TO_ARRAY:
    setattr(WoodCellProxy, _field, _numeric_property(_field))


class CellProxySequence:
    __slots__ = ("_backend_ref", "_start", "_count", "_generation")

    def __init__(self, backend, start, count):
        self._backend_ref = weakref.ref(backend)
        self._start = start
        self._count = count
        self._generation = backend.structure_generation

    def __len__(self):
        return self._count

    def __getitem__(self, index):
        backend = self._backend_ref()
        if backend is None:
            raise StaleProxy("Shared SoA owner no longer exists")
        backend._require_proxy(self._generation)
        if isinstance(index, slice):
            return tuple(self[item] for item in range(*index.indices(self._count)))
        if index < 0:
            index += self._count
        if not 0 <= index < self._count:
            raise IndexError(index)
        return WoodCellProxy(backend, self._start + index)


class WoodModelProxy:
    __slots__ = ("cells", "log_index")

    def __init__(self, backend, log_index):
        self.log_index = log_index
        self.cells = CellProxySequence(
            backend, log_index * backend.cells_per_log, backend.cells_per_log
        )


class SharedSoABackend:
    """Prototype only: private NumPy authority borrowed synchronously by C++."""

    def __init__(self, combustion, models, library):
        self._combustion = combustion
        self._library = library
        self._model_payloads = [copy.deepcopy(model.to_dict()) for model in models]
        self.log_count = len(models)
        self.cells_per_log = len(models[0].cells)
        cells = [cell for model in models for cell in model.cells]
        self._default_specific_heat = models[0].parameters.wood_specific_heat_j_kg_k
        self._parameters = models[0].parameters
        self._mass_epsilon = models[0]._mass_epsilon_kg
        native_arrays = base._extract_arrays(cells, self._default_specific_heat)
        self._arrays = dict(native_arrays)
        self._arrays.update(
            {
                "volatile_potential_kg": np.fromiter(
                    (cell.volatile_potential_kg for cell in cells),
                    dtype=np.float64,
                    count=len(cells),
                ),
                "oxygen_factor": np.fromiter(
                    (cell.oxygen_factor for cell in cells),
                    dtype=np.float64,
                    count=len(cells),
                ),
                "volume_m3": np.fromiter(
                    (cell.volume_m3 for cell in cells),
                    dtype=np.float64,
                    count=len(cells),
                ),
                "specific_heat_overridden": np.fromiter(
                    (cell.dry_wood_specific_heat_j_kg_k is not None for cell in cells),
                    dtype=np.bool_,
                    count=len(cells),
                ),
            }
        )
        self._specific_heat_models = tuple(
            cell.dry_wood_specific_heat_model for cell in cells
        )
        self._lock = threading.RLock()
        self._state = "IDLE"
        self._edit_owner = None
        self._edit_journal = None
        self._closed = False
        self.revision = 0
        self.tick = 0
        self.structure_generation = 1
        self.import_count = 0
        self.native_call_count = 0
        self._validate_all_arrays()

    def _validate_array(self, name, array):
        expected_dtype = np.int32 if name == "phase_code" else (
            np.bool_ if name == "specific_heat_overridden" else np.float64
        )
        if array.dtype != expected_dtype:
            raise TypeError(f"{name} dtype {array.dtype} != {expected_dtype}")
        if array.ndim != 1:
            raise TypeError(f"{name} must be one-dimensional")
        if not array.flags.c_contiguous or not array.flags.aligned:
            raise TypeError(f"{name} must be C-contiguous and aligned")
        if not array.flags.writeable:
            raise TypeError(f"{name} must be writable")
        if array.size != self.log_count * self.cells_per_log:
            raise TypeError(f"{name} has an unexpected element count")

    def _validate_all_arrays(self):
        for name, array in self._arrays.items():
            self._validate_array(name, array)

    def validate_candidate_array(self, name, array):
        self._validate_array(name, array)

    def _require_open(self):
        if self._closed:
            raise StaleProxy("Shared SoA backend is closed")

    def _require_proxy(self, generation):
        with self._lock:
            self._require_open()
            if generation != self.structure_generation:
                raise StaleProxy(
                    f"Proxy generation {generation} != {self.structure_generation}"
                )
            if self._state in {"STEPPING", "SERIALIZING"}:
                raise BackendBusy(f"Cannot access cell while backend is {self._state}")

    def model(self, log_index):
        with self._lock:
            self._require_open()
            if not 0 <= log_index < self.log_count:
                raise IndexError(log_index)
            return WoodModelProxy(self, log_index)

    def _record(self, name, index):
        if self._edit_journal is not None:
            key = (name, index)
            if key not in self._edit_journal:
                self._edit_journal[key] = self._arrays[name][index].item()

    def _validate_value(self, field, value):
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError(f"{field} must be finite")
        if field in MASS_FIELDS and numeric < 0.0:
            raise ValueError(f"{field} must be non-negative")
        return numeric

    def _get_numeric(self, index, field):
        with self._lock:
            self._require_proxy(self.structure_generation)
            return float(self._arrays[PUBLIC_TO_ARRAY[field]][index])

    def _write_numeric_locked(self, index, field, value):
        if field == "volume_m3":
            raise StructuralEditRequired("volume_m3 requires candidate rebuild")
        name = PUBLIC_TO_ARRAY[field]
        self._record(name, index)
        self._arrays[name][index] = self._validate_value(field, value)

    def _set_numeric(self, index, field, value):
        with self._lock:
            self._require_open()
            current_thread = threading.get_ident()
            if self._state == "IDLE":
                self._write_numeric_locked(index, field, value)
                self.revision += 1
                return
            if self._state == "EDITING" and self._edit_owner == current_thread:
                self._write_numeric_locked(index, field, value)
                return
            raise BackendBusy(f"Cannot edit cell while backend is {self._state}")

    def _get_phase(self, index):
        with self._lock:
            self._require_proxy(self.structure_generation)
            return CODE_TO_PHASE[int(self._arrays["phase_code"][index])]

    def _set_phase(self, index, value):
        if value not in PHASE_TO_CODE:
            raise ValueError(f"Unknown phase {value}")
        with self._lock:
            self._require_open()
            current_thread = threading.get_ident()
            if self._state not in {"IDLE", "EDITING"} or (
                self._state == "EDITING" and self._edit_owner != current_thread
            ):
                raise BackendBusy(f"Cannot edit phase while backend is {self._state}")
            self._record("phase_code", index)
            self._arrays["phase_code"][index] = PHASE_TO_CODE[value]
            if self._state == "IDLE":
                self.revision += 1

    def _get_specific_heat(self, index):
        with self._lock:
            self._require_proxy(self.structure_generation)
            if not bool(self._arrays["specific_heat_overridden"][index]):
                return None
            return float(self._arrays["dry_specific_heat_j_kg_k"][index])

    def _set_specific_heat(self, index, value):
        with self._lock:
            self._require_open()
            current_thread = threading.get_ident()
            if self._state not in {"IDLE", "EDITING"} or (
                self._state == "EDITING" and self._edit_owner != current_thread
            ):
                raise BackendBusy(f"Cannot edit specific heat while {self._state}")
            self._record("dry_specific_heat_j_kg_k", index)
            self._record("specific_heat_overridden", index)
            if value is None:
                self._arrays["dry_specific_heat_j_kg_k"][index] = (
                    self._default_specific_heat
                )
                self._arrays["specific_heat_overridden"][index] = False
            else:
                numeric = self._validate_value(
                    "dry_wood_specific_heat_j_kg_k", value
                )
                if numeric <= 0.0:
                    raise ValueError("dry_wood_specific_heat_j_kg_k must be positive")
                self._arrays["dry_specific_heat_j_kg_k"][index] = numeric
                self._arrays["specific_heat_overridden"][index] = True
            if self._state == "IDLE":
                self.revision += 1

    @contextmanager
    def edit(self):
        with self._lock:
            self._require_open()
            if self._state != "IDLE":
                raise BackendBusy(f"Cannot begin edit while backend is {self._state}")
            self._state = "EDITING"
            self._edit_owner = threading.get_ident()
            self._edit_journal = {}
        try:
            yield self
        except Exception:
            with self._lock:
                for (name, index), old_value in reversed(
                    tuple(self._edit_journal.items())
                ):
                    self._arrays[name][index] = old_value
                self._state = "IDLE"
                self._edit_owner = None
                self._edit_journal = None
            raise
        else:
            with self._lock:
                self.revision += 1
                self._state = "IDLE"
                self._edit_owner = None
                self._edit_journal = None

    def _state_digest_locked(self):
        digest = hashlib.sha256()
        for name in sorted(self._arrays):
            digest.update(name.encode("ascii"))
            digest.update(self._arrays[name].tobytes())
        digest.update(str(self.revision).encode("ascii"))
        digest.update(str(self.tick).encode("ascii"))
        digest.update(str(self.structure_generation).encode("ascii"))
        return digest.hexdigest()

    def digest(self):
        with self._lock:
            return self._state_digest_locked()

    def _snapshot_locked(self):
        return SharedSoASnapshot(
            revision=self.revision,
            tick=self.tick,
            structure_generation=self.structure_generation,
            temperature_prefix_k=tuple(
                float(value) for value in self._arrays["temperature_k"][:8]
            ),
            state_sha256=self._state_digest_locked(),
        )

    def step(self, repetitions=1, entered_event=None, inject_failure=False):
        with self._lock:
            self._require_open()
            if self._state != "IDLE":
                raise BackendBusy(f"Cannot step while backend is {self._state}")
            self._state = "STEPPING"
            rollback = {
                name: self._arrays[name].copy()
                for name in (*NATIVE_FLOAT_FIELDS, "phase_code")
            }
            revision_before = self.revision
            tick_before = self.tick
        if entered_event is not None:
            entered_event.set()
        try:
            self._validate_all_arrays()
            for _ in range(repetitions):
                base._call_native(
                    self._library,
                    self._arrays,
                    self._model_parameters(),
                    self._mass_epsilon_kg(),
                )
                self.native_call_count += 1
            if inject_failure:
                raise RuntimeError("Injected post-native failure")
            with self._lock:
                self.tick += 1
                self.revision += 1
                snapshot = self._snapshot_locked()
                self._state = "IDLE"
                return snapshot
        except Exception:
            with self._lock:
                for name, values in rollback.items():
                    self._arrays[name][:] = values
                self.revision = revision_before
                self.tick = tick_before
                self._state = "IDLE"
            raise

    def _model_parameters(self):
        return self._parameters

    def _mass_epsilon_kg(self):
        return self._mass_epsilon

    def _cell_payload(self, index):
        specific_heat = (
            float(self._arrays["dry_specific_heat_j_kg_k"][index])
            if bool(self._arrays["specific_heat_overridden"][index])
            else None
        )
        return {
            "temperature_k": float(self._arrays["temperature_k"][index]),
            "moisture_mass_kg": float(self._arrays["moisture_mass_kg"][index]),
            "dry_wood_mass_kg": float(self._arrays["dry_wood_mass_kg"][index]),
            "volatile_potential_kg": float(
                self._arrays["volatile_potential_kg"][index]
            ),
            "char_mass_kg": float(self._arrays["char_mass_kg"][index]),
            "ash_mass_kg": float(self._arrays["ash_mass_kg"][index]),
            "oxygen_factor": float(self._arrays["oxygen_factor"][index]),
            "surface_exposure": float(self._arrays["surface_exposure"][index]),
            "phase": CODE_TO_PHASE[int(self._arrays["phase_code"][index])],
            "volume_m3": float(self._arrays["volume_m3"][index]),
            "external_area_m2": float(self._arrays["external_area_m2"][index]),
            "dry_wood_specific_heat_j_kg_k": specific_heat,
            "dry_wood_specific_heat_model": self._specific_heat_models[index],
        }

    def serialize_log(self, log_index, validate_round_trip=True):
        with self._lock:
            self._require_open()
            if self._state != "IDLE":
                raise BackendBusy(f"Cannot serialize while backend is {self._state}")
            self._state = "SERIALIZING"
            try:
                payload = copy.deepcopy(self._model_payloads[log_index])
                begin = log_index * self.cells_per_log
                payload["cells"] = [
                    self._cell_payload(index)
                    for index in range(begin, begin + self.cells_per_log)
                ]
                canonical = _canonical_json(payload)
                if validate_round_trip:
                    restored = self._combustion.WoodThermalModel.from_dict(
                        json.loads(canonical)
                    )
                    if _canonical_json(restored.to_dict()) != canonical:
                        raise RuntimeError("Shared SoA serialization did not round-trip")
                return canonical
            finally:
                self._state = "IDLE"

    def replace_structure(self, inject_failure=False):
        with self._lock:
            self._require_open()
            if self._state != "IDLE":
                raise BackendBusy(f"Cannot rebuild while backend is {self._state}")
            candidates = {name: values.copy() for name, values in self._arrays.items()}
            candidates["volume_m3"][0] *= 1.001
            for name, values in candidates.items():
                self._validate_array(name, values)
            if inject_failure:
                raise RuntimeError("Injected candidate rebuild failure")
            self._arrays = candidates
            self.structure_generation += 1
            self.revision += 1

    def readonly_buffer(self, field):
        with self._lock:
            self._require_open()
            view = memoryview(self._arrays[field]).toreadonly()
            return view

    def pointer(self, field):
        with self._lock:
            self._require_open()
            return int(self._arrays[field].ctypes.data)

    def close(self):
        with self._lock:
            if self._closed:
                return
            if self._state != "IDLE":
                raise BackendBusy(f"Cannot close while backend is {self._state}")
            self._closed = True
            self.structure_generation += 1


def _models(combustion, log_count):
    templates = {}
    for label, moisture in (("dry", 0.12), ("wet", 0.60)):
        model = combustion.create_cylindrical_wood_model(
            f"shared_soa_{label}", 0.16, 1.80, moisture
        )
        model.use_slotted_cell_storage()
        templates[label] = model.to_dict()
    models = []
    for index in range(log_count):
        label = "dry" if index % 2 == 0 else "wet"
        models.append(combustion.WoodThermalModel.from_dict(templates[label]))
    return models


def _measure(operation, samples):
    timings = []
    for _ in range(samples):
        started = time.perf_counter()
        operation()
        timings.append((time.perf_counter() - started) * 1000.0)
    return _timing_summary(timings)


def _run(dll_path, log_count, scalar_samples, boundary_samples):
    combustion = base._load_combustion_module()
    library = base._load_native_kernel(dll_path)
    models = _models(combustion, log_count)
    backend = SharedSoABackend(combustion, models, library)
    model_proxy = backend.model(0)
    proxy_cell = model_proxy.cells[42]
    dataclass_cell = models[0].cells[42]

    initial_serialization_exact = (
        backend.serialize_log(0) == _canonical_json(models[0].to_dict())
    )
    pointer_before = backend.pointer("temperature_k")
    reference_models = [
        combustion.WoodThermalModel.from_dict(model.to_dict()) for model in models
    ]
    snapshot = backend.step()
    for model in reference_models:
        base._python_step(model.cells, model.parameters, model._mass_epsilon_kg)
    pointer_after = backend.pointer("temperature_k")
    native_reference_max_temperature_error_k = max(
        abs(
            float(backend._arrays["temperature_k"][index])
            - reference_models[index // backend.cells_per_log]
            .cells[index % backend.cells_per_log]
            .temperature_k
        )
        for index in range(log_count * backend.cells_per_log)
    )
    post_step_serialization_exact = (
        backend.serialize_log(0) == _canonical_json(reference_models[0].to_dict())
    )
    immutable_prefix = snapshot.temperature_prefix_k
    old_import_count = backend.import_count
    proxy_cell.temperature_k += 0.125
    proxy_write_visible_without_import = (
        float(backend._arrays["temperature_k"][42]) == proxy_cell.temperature_k
        and backend.import_count == old_import_count
    )
    immutable_snapshot_unchanged = snapshot.temperature_prefix_k == immutable_prefix

    edit_digest = backend.digest()
    edit_rollback_exact = False
    try:
        with backend.edit():
            proxy_cell.temperature_k += 1.0
            proxy_cell.moisture_mass_kg += 0.01
            raise RuntimeError("Injected proxy edit failure")
    except RuntimeError:
        edit_rollback_exact = backend.digest() == edit_digest

    step_digest = backend.digest()
    step_rollback_exact = False
    try:
        backend.step(inject_failure=True)
    except RuntimeError:
        step_rollback_exact = backend.digest() == step_digest

    entered = threading.Event()
    thread_error = []

    def _contended_step():
        try:
            backend.step(repetitions=200, entered_event=entered)
        except Exception as error:  # pragma: no cover - recorded in report
            thread_error.append(repr(error))

    step_thread = threading.Thread(target=_contended_step, name="shared-soa-step")
    step_thread.start()
    if not entered.wait(timeout=5.0):
        raise RuntimeError("Contended native step did not enter")
    concurrent_write_rejected = False
    try:
        proxy_cell.temperature_k += 1.0
    except BackendBusy:
        concurrent_write_rejected = True
    step_thread.join(timeout=30.0)
    if step_thread.is_alive() or thread_error:
        raise RuntimeError(f"Contended native step failed: {thread_error}")

    wrong_dtype_rejected = False
    try:
        backend.validate_candidate_array(
            "temperature_k", np.zeros(backend._arrays["temperature_k"].size, dtype=np.float32)
        )
    except TypeError:
        wrong_dtype_rejected = True
    noncontiguous_rejected = False
    try:
        candidate = np.zeros(backend._arrays["temperature_k"].size * 2)[::2]
        backend.validate_candidate_array("temperature_k", candidate)
    except TypeError:
        noncontiguous_rejected = True

    failed_rebuild_digest = backend.digest()
    generation_before = backend.structure_generation
    proxy_before_rebuild = backend.model(0).cells[42]
    candidate_failure_rollback_exact = False
    try:
        backend.replace_structure(inject_failure=True)
    except RuntimeError:
        candidate_failure_rollback_exact = (
            backend.digest() == failed_rebuild_digest
            and backend.structure_generation == generation_before
            and math.isfinite(proxy_before_rebuild.temperature_k)
        )
    backend.replace_structure()
    stale_proxy_rejected = False
    try:
        _ = proxy_before_rebuild.temperature_k
    except StaleProxy:
        stale_proxy_rejected = True
    current_proxy = backend.model(0).cells[42]

    read_only_view = backend.readonly_buffer("temperature_k")
    readonly_write_rejected = False
    try:
        read_only_view[0] = 0.0
    except TypeError:
        readonly_write_rejected = True

    toggle = [0]

    def _proxy_read():
        return current_proxy.temperature_k

    def _dataclass_read():
        return dataclass_cell.temperature_k

    def _proxy_write():
        toggle[0] ^= 1
        current_proxy.temperature_k = 500.0 + toggle[0] * 0.001

    def _dataclass_write():
        toggle[0] ^= 1
        dataclass_cell.temperature_k = 500.0 + toggle[0] * 0.001

    proxy_write_timing = _measure(_proxy_write, scalar_samples)
    dataclass_write_timing = _measure(_dataclass_write, scalar_samples)
    proxy_read_timing = _measure(_proxy_read, scalar_samples)
    dataclass_read_timing = _measure(_dataclass_read, scalar_samples)

    def _proxy_batch_write():
        with backend.edit():
            for index in range(32):
                cell = backend.model(0).cells[index]
                cell.temperature_k = 500.0 + (index % 2) * 0.001

    proxy_batch_timing = _measure(_proxy_batch_write, boundary_samples)

    export_models = [
        combustion.WoodThermalModel.from_dict(model.to_dict()) for model in models
    ]
    export_begin = 0
    export_end = backend.cells_per_log

    def _export_edit_import():
        sliced = {
            name: values[export_begin:export_end]
            for name, values in backend._arrays.items()
            if name in (*NATIVE_FLOAT_FIELDS, "phase_code")
        }
        base._write_arrays(sliced, export_models[0].cells)
        export_models[0].cells[42].temperature_k += 0.001
        imported = base._extract_arrays(
            export_models[0].cells, backend._default_specific_heat
        )
        for name, values in imported.items():
            backend._arrays[name][export_begin:export_end] = values

    export_import_timing = _measure(_export_edit_import, boundary_samples)
    direct_serialization_timing = _measure(
        lambda: backend.serialize_log(0, validate_round_trip=False),
        max(3, boundary_samples // 5),
    )
    dataclass_serialization_timing = _measure(
        lambda: _canonical_json(export_models[0].to_dict()),
        max(3, boundary_samples // 5),
    )

    native_step_timing = _measure(lambda: backend.step(), boundary_samples)
    final_revision = backend.revision
    final_tick = backend.tick
    backend.close()
    close_invalidates_proxy = False
    try:
        _ = current_proxy.temperature_k
    except StaleProxy:
        close_invalidates_proxy = True
    buffer_view_survives_close = math.isfinite(float(read_only_view[0]))
    read_only_view.release()
    del backend
    gc.collect()

    gates = {
        "numpy_pointer_unchanged_across_cpp_step": pointer_before == pointer_after,
        "native_matches_python_reference": native_reference_max_temperature_error_k
        <= base.TEMPERATURE_TOLERANCE_K,
        "initial_serialization_exact": initial_serialization_exact,
        "post_step_serialization_exact": post_step_serialization_exact,
        "proxy_write_visible_without_import": proxy_write_visible_without_import,
        "immutable_snapshot_unchanged": immutable_snapshot_unchanged,
        "edit_rollback_exact": edit_rollback_exact,
        "step_rollback_exact": step_rollback_exact,
        "concurrent_write_rejected": concurrent_write_rejected,
        "wrong_dtype_rejected": wrong_dtype_rejected,
        "noncontiguous_rejected": noncontiguous_rejected,
        "candidate_failure_rollback_exact": candidate_failure_rollback_exact,
        "stale_proxy_rejected_after_swap": stale_proxy_rejected,
        "readonly_buffer_rejects_write": readonly_write_rejected,
        "close_invalidates_proxy": close_invalidates_proxy,
        "readonly_buffer_lifetime_is_not_revocable": buffer_view_survives_close,
    }
    if not all(gates.values()):
        raise RuntimeError(f"Shared SoA gate failed: {gates}")

    return {
        "status": "ok",
        "scope": {
            "kind": "future_research_spike",
            "production_code_changed": False,
            "usd_publish_path_changed": False,
            "native_producer_connected": False,
            "authority": "private_numpy_owned_contiguous_soa",
            "native_access": "synchronous_borrow_via_ctypes_cdll",
        },
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "platform": platform.platform(),
            "native_abi_version": int(library.campfire_native_abi_version()),
            "native_msvc_version": int(library.campfire_native_msvc_version()),
        },
        "measurement": {
            "log_count": log_count,
            "cells_per_log": len(models[0].cells),
            "cell_count": log_count * len(models[0].cells),
            "scalar_samples": scalar_samples,
            "boundary_samples": boundary_samples,
            "native_contention_repetitions": 200,
        },
        "correctness": {
            "gates": gates,
            "maximum_temperature_error_k": native_reference_max_temperature_error_k,
            "initial_snapshot_revision": snapshot.revision,
            "initial_snapshot_tick": snapshot.tick,
            "final_revision": final_revision,
            "final_tick": final_tick,
            "import_count": old_import_count,
        },
        "timing": {
            "dataclass_scalar_read": dataclass_read_timing,
            "proxy_scalar_read": proxy_read_timing,
            "dataclass_scalar_write": dataclass_write_timing,
            "proxy_transactional_scalar_write": proxy_write_timing,
            "proxy_32_field_batch_edit": proxy_batch_timing,
            "legacy_one_log_export_edit_import": export_import_timing,
            "direct_soa_json_serialization": direct_serialization_timing,
            "dataclass_json_serialization": dataclass_serialization_timing,
            "transactional_native_step": native_step_timing,
        },
        "evaluation": {
            "unmanaged_python_write_problem": (
                "solved only when raw writable arrays remain private and every write "
                "uses a proxy or edit lease"
            ),
            "dirty_import_for_numeric_fields": "not required",
            "revision_role": "tick_snapshot_consumer_consistency",
            "structure_role": "separate generation invalidates stale proxies",
            "buffer_protocol_limit": (
                "a handed-out read-only memoryview remains readable after backend close; "
                "lifetime cannot be revoked"
            ),
            "usd_publish_bottleneck": "unchanged and outside this spike",
            "source_compatibility_limit": (
                "cell.temperature_k syntax works, but the proxy is not a dataclass; "
                "asdict, replacement, identity, and structural direct writes differ"
            ),
            "recommendation": (
                "defer adoption until transactional USD p95 is below 4 ms and the "
                "resident native producer is connected to ResidentPublishedSnapshot"
            ),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dll", required=True, type=Path)
    parser.add_argument("--logs", type=int, default=20)
    parser.add_argument("--scalar-samples", type=int, default=2000)
    parser.add_argument("--boundary-samples", type=int, default=25)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    runs = [
        _run(args.dll.resolve(), args.logs, args.scalar_samples, args.boundary_samples)
        for _ in range(args.runs)
    ]
    report = copy.deepcopy(runs[0])
    report["measurement"]["run_count"] = args.runs
    report["correctness"]["gates"] = {
        name: all(run["correctness"]["gates"][name] for run in runs)
        for name in report["correctness"]["gates"]
    }
    report["correctness"]["maximum_temperature_error_k"] = max(
        run["correctness"]["maximum_temperature_error_k"] for run in runs
    )
    for boundary_name in report["timing"]:
        report["timing"][boundary_name] = {
            key: statistics.median(
                run["timing"][boundary_name][key] for run in runs
            )
            for key in ("mean_ms", "median_ms", "p95_ms", "maximum_ms")
        }
        report["timing"][boundary_name]["per_run_sample_count"] = runs[0][
            "timing"
        ][boundary_name]["sample_count"]
        report["timing"][boundary_name]["run_count"] = args.runs
    report["independent_runs"] = [
        {"correctness": run["correctness"], "timing": run["timing"]}
        for run in runs
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["correctness"], indent=2, sort_keys=True))
    print(json.dumps(report["timing"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
