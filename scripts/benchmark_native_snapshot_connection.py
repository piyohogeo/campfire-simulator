"""Measure direct native-output conversion to ResidentPublishedSnapshot."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import platform
import statistics
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE_BENCHMARK = ROOT / "scripts" / "benchmark_native_backend_lifecycle.py"
SNAPSHOT_MODULE = (
    ROOT
    / "source"
    / "extensions"
    / "campfire.app"
    / "campfire"
    / "app"
    / "resident_snapshot.py"
)
WOOD_BUDGET_MS = 4.0
FREEZE_BUDGET_MS = 1.0


def _load_module(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Unable to load module: {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


lifecycle = _load_module("campfire_phase6bi_lifecycle", LIFECYCLE_BENCHMARK)
snapshot_contract = _load_module(
    "campfire_phase6bi_snapshot_contract", SNAPSHOT_MODULE
)
scheduler = lifecycle.scheduler
publish = lifecycle.publish
arrhenius = lifecycle.arrhenius
base = lifecycle.base
np = lifecycle.np


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


def _run_once(combustion, templates, library, reference, log_count, cycles, warmup):
    backend = lifecycle.ResidentBackendProbe(
        combustion, templates, library, log_count
    )
    scheduler._apply_managed_edit(
        backend.boundary,
        backend.models,
        backend.arrays,
        7 % log_count,
        42,
    )
    log_ids = tuple(f"native_log_{index:02d}" for index in range(log_count))
    producer = snapshot_contract.ResidentNativeSnapshotProducer(log_ids)
    update_samples = []
    freeze_samples = []
    native_samples = []
    revisions = []
    ticks = []
    maximum_schema_error = 0.0
    committed_snapshot = None

    for tick in range(cycles):
        update_started = time.perf_counter_ns()
        native_started = time.perf_counter_ns()
        backend.step()
        native_ms = (time.perf_counter_ns() - native_started) / 1_000_000.0
        freeze_started = time.perf_counter_ns()
        candidate = producer.build(
            revision=backend.resident_revision,
            tick=tick,
            values=backend.published_output,
        )
        freeze_ms = (time.perf_counter_ns() - freeze_started) / 1_000_000.0
        matrix = backend.published_output.reshape(
            (log_count, len(snapshot_contract.RESIDENT_PUBLISHED_FIELD_NAMES))
        )
        for row_index, row in enumerate(candidate.rows):
            for field_index, field in enumerate(
                snapshot_contract.RESIDENT_PUBLISHED_FIELD_NAMES
            ):
                maximum_schema_error = max(
                    maximum_schema_error,
                    abs(getattr(row, field) - float(matrix[row_index, field_index])),
                )
        committed_snapshot = candidate
        revisions.append(candidate.revision)
        ticks.append(candidate.tick)
        if tick >= warmup:
            native_samples.append(native_ms)
            freeze_samples.append(freeze_ms)
            update_samples.append(
                (time.perf_counter_ns() - update_started) / 1_000_000.0
            )

    immutable_value = committed_snapshot.rows[0].surface_mean_temperature_k
    original_native_value = float(backend.published_output[0])
    backend.published_output[0] = original_native_value + 1.0
    immutable_after_native_mutation = (
        committed_snapshot.rows[0].surface_mean_temperature_k == immutable_value
    )
    backend.published_output[0] = original_native_value

    digest_before_failure = backend.native_digest()
    invalid_output = backend.published_output.copy()
    invalid_output[0] = np.nan
    failed_conversion_rejected = False
    try:
        producer.build(
            revision=backend.resident_revision + 1,
            tick=cycles,
            values=invalid_output,
        )
    except ValueError:
        failed_conversion_rejected = True
    failure_preserved_commit = (
        committed_snapshot.revision == backend.resident_revision
        and backend.native_digest() == digest_before_failure
    )

    comparison = scheduler._compare(
        reference,
        backend.arrays,
        backend.elapsed,
        backend.cumulative,
        backend.published_output,
        backend.models,
    )
    shutdown = backend.shutdown()
    expected_revisions = list(range(1, cycles + 1))
    expected_ticks = list(range(cycles))
    return {
        "timing": {
            "native_step_and_aggregate": _timing_summary(native_samples),
            "schema_freeze": _timing_summary(freeze_samples),
            "native_update_and_schema_freeze": _timing_summary(update_samples),
        },
        "equivalence": comparison,
        "connection": {
            "maximum_schema_copy_error": maximum_schema_error,
            "field_order_exact": tuple(publish.OUTPUT_FIELDS)
            == snapshot_contract.RESIDENT_PUBLISHED_FIELD_NAMES,
            "log_ids_exact": committed_snapshot.log_ids == log_ids,
            "row_type_exact": all(
                type(row) is snapshot_contract.ResidentPublishedRow
                for row in committed_snapshot.rows
            ),
            "snapshot_type_exact": type(committed_snapshot)
            is snapshot_contract.ResidentPublishedSnapshot,
            "strictly_monotonic_revisions": revisions == expected_revisions,
            "exact_ticks": ticks == expected_ticks,
            "immutable_after_native_mutation": immutable_after_native_mutation,
            "failed_conversion_rejected": failed_conversion_rejected,
            "failed_conversion_preserved_commit": failure_preserved_commit,
            "shutdown_exported_all_logs": len(shutdown["payloads"]) == log_count,
        },
    }


def run_benchmark(dll_path, log_count, cycles, warmup, runs):
    combustion = base._load_combustion_module()
    templates = scheduler._templates(combustion)
    library = base._load_native_kernel(dll_path)
    arrhenius._configure_arrhenius_kernel(library)
    publish._configure_publish_kernel(library)
    reference = scheduler._reference_run(combustion, templates, log_count, cycles)
    outcomes = [
        _run_once(
            combustion, templates, library, reference, log_count, cycles, warmup
        )
        for _ in range(runs)
    ]
    source_digest = hashlib.sha256()
    for source in (
        ROOT / "native" / "phase6au" / "wood_cell_kernel.cpp",
        ROOT / "native" / "phase6au" / "native_publish_outputs.inl",
        SNAPSHOT_MODULE,
        Path(__file__),
    ):
        source_digest.update(source.name.encode("utf-8"))
        source_digest.update(source.read_bytes())
    return {
        "schema_version": 1,
        "phase": "phase6bi",
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
            "source_sha256": source_digest.hexdigest(),
        },
        "measurement": {
            "log_count": log_count,
            "cells_per_log": len(reference["arrays"]["temperature_k"]) // log_count,
            "cycles_per_run": cycles,
            "warmup_cycles_excluded": warmup,
            "runs": runs,
            "published_fields_per_log": len(
                snapshot_contract.RESIDENT_PUBLISHED_FIELD_NAMES
            ),
        },
        "contract": {
            "source": "resident_native_contiguous_output",
            "destination": "ResidentPublishedSnapshot",
            "field_names": list(snapshot_contract.RESIDENT_PUBLISHED_FIELD_NAMES),
            "python_model_scan_per_snapshot": False,
            "buffer_copy_at_immutable_boundary": True,
            "producer_owns_revision_state": False,
            "resident_scheduler_owns_revision": True,
            "usd_adapter_remains_commit_authority": True,
            "lifecycle_and_rollback_unchanged": True,
            "production_default_enabled": False,
        },
        "budget_ms": {
            "native_update_and_schema_freeze": WOOD_BUDGET_MS,
            "schema_freeze": FREEZE_BUDGET_MS,
        },
        "runs": [
            {"run": index + 1, **outcome}
            for index, outcome in enumerate(outcomes)
        ],
    }


def main():
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
        or arguments.cycles <= 0
        or arguments.warmup_cycles >= arguments.cycles
        or arguments.runs < 3
    ):
        parser.error("Require positive logs/cycles, smaller warmup, and at least 3 runs")
    report = run_benchmark(
        arguments.dll,
        arguments.logs,
        arguments.cycles,
        arguments.warmup_cycles,
        arguments.runs,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
