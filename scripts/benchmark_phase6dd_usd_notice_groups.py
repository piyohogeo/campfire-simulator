"""Benchmark Point attribute groups at the local USD notice boundary."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
_DLL_DIRECTORY_HANDLES = []


def _load_local_packages():
    ext_cache = ROOT / "_build" / "windows-x86_64" / "release" / "extscache"
    pip_archives = sorted(ext_cache.glob("omni.kit.pip_archive-*"))
    usd_packages = sorted(ext_cache.glob("omni.usd.libs-*"))
    if not pip_archives or not usd_packages:
        raise RuntimeError("Built Kit NumPy/USD packages were not found")
    sys.path.insert(0, str(pip_archives[-1] / "pip_prebundle"))
    usd_package = usd_packages[-1]
    _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(usd_package / "bin")))
    sys.path.insert(0, str(usd_package))
    import numpy
    from pxr import Sdf, Tf, Usd, Vt

    return numpy, Sdf, Tf, Usd, Vt, usd_package.name


np, Sdf, Tf, Usd, Vt, USD_PACKAGE = _load_local_packages()


CASES = {
    "revision_only": ("resident_revision",),
    "channels_revision": (
        "fuels",
        "temperatures",
        "smokes",
        "resident_revision",
    ),
    "layout_only": ("positions", "layout_revision"),
    "full_layout": (
        "positions",
        "fuels",
        "temperatures",
        "smokes",
        "layout_revision",
        "resident_revision",
    ),
}


def _summary(values):
    ordered = sorted(values)
    return {
        "sample_count": len(values),
        "mean_ms": round(statistics.fmean(values), 6),
        "p95_ms": round(
            ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 6
        ),
        "max_ms": round(max(values), 6),
    }


def _stage(point_count):
    stage = Usd.Stage.CreateInMemory()
    prim = stage.DefinePrim("/World/Flow/ResidentPointEmitter")
    attributes = {
        "positions": prim.CreateAttribute(
            "pointPositions", Sdf.ValueTypeNames.Float3Array
        ),
        "fuels": prim.CreateAttribute("pointFuels", Sdf.ValueTypeNames.FloatArray),
        "temperatures": prim.CreateAttribute(
            "pointTemperatures", Sdf.ValueTypeNames.FloatArray
        ),
        "smokes": prim.CreateAttribute("pointSmokes", Sdf.ValueTypeNames.FloatArray),
        "layout_revision": prim.CreateAttribute(
            "campfire:layoutRevision", Sdf.ValueTypeNames.Int64
        ),
        "resident_revision": prim.CreateAttribute(
            "campfire:residentRevision", Sdf.ValueTypeNames.Int64
        ),
    }
    index = np.arange(point_count, dtype=np.float32)
    values = []
    for parity in (0, 1):
        offset = np.float32(parity * 0.0005)
        positions = np.empty((point_count, 3), dtype=np.float32)
        positions[:, 0] = index * np.float32(0.001) + offset
        positions[:, 1] = offset
        positions[:, 2] = np.float32(0.2)
        values.append(
            {
                "positions": Vt.Vec3fArray.FromNumpy(positions),
                "fuels": Vt.FloatArray.FromNumpy(
                    np.full(point_count, 0.4 + parity * 0.01, dtype=np.float32)
                ),
                "temperatures": Vt.FloatArray.FromNumpy(
                    np.full(point_count, 850.0 + parity, dtype=np.float32)
                ),
                "smokes": Vt.FloatArray.FromNumpy(
                    np.full(point_count, 0.1 + parity * 0.01, dtype=np.float32)
                ),
            }
        )
    for name in ("positions", "fuels", "temperatures", "smokes"):
        if not attributes[name].Set(values[0][name]):
            raise RuntimeError(f"Unable to seed {name}")
    for name in ("layout_revision", "resident_revision"):
        if not attributes[name].Set(1):
            raise RuntimeError(f"Unable to seed {name}")
    return stage, attributes, tuple(values)


def _measure(case_name, listener_mode, point_count, iterations, warmup, run_index):
    stage, attributes, values = _stage(point_count)
    names = CASES[case_name]
    notice_count = 0
    callback_ms = []
    resync_count = 0
    changed_counts = []

    def observe(notice, _sender):
        nonlocal notice_count, resync_count
        started = time.perf_counter_ns()
        resynced = tuple(notice.GetResyncedPaths())
        changed = tuple(notice.GetChangedInfoOnlyPaths())
        resync_count += len(resynced)
        changed_counts.append(len(changed))
        notice_count += 1
        callback_ms.append((time.perf_counter_ns() - started) / 1_000_000.0)

    listener = None
    if listener_mode == "enumerating_listener":
        listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, observe, stage)
    set_ms = []
    exit_ms = []
    for offset in range(iterations + warmup):
        revision = offset + 2
        payload = values[revision % 2]
        block = Sdf.ChangeBlock()
        block.__enter__()
        set_started = time.perf_counter_ns()
        for name in names:
            value = revision if name.endswith("revision") else payload[name]
            if not attributes[name].Set(value):
                raise RuntimeError(f"{case_name} {name} Set failed")
        set_elapsed = (time.perf_counter_ns() - set_started) / 1_000_000.0
        exit_started = time.perf_counter_ns()
        block.__exit__(None, None, None)
        exit_elapsed = (time.perf_counter_ns() - exit_started) / 1_000_000.0
        if offset >= warmup:
            set_ms.append(set_elapsed)
            exit_ms.append(exit_elapsed)
    if listener is not None:
        listener.Revoke()
        expected = iterations + warmup
        if notice_count != expected:
            raise RuntimeError(f"{case_name} notices {notice_count} != {expected}")
        measured_changed_counts = changed_counts[warmup:]
        if resync_count != 0 or set(measured_changed_counts) != {len(names)}:
            raise RuntimeError(
                f"{case_name} notice paths invalid: resync={resync_count}, "
                f"changed={set(measured_changed_counts)}"
            )
    else:
        measured_changed_counts = []
    return {
        "run": run_index,
        "case": case_name,
        "listener_mode": listener_mode,
        "attribute_names": list(names),
        "attribute_count": len(names),
        "set_timing_ms": _summary(set_ms),
        "change_block_exit_ms": _summary(exit_ms),
        "notice_count_total": notice_count,
        "changed_path_count_per_notice": (
            sorted(set(measured_changed_counts))
        ),
        "resync_count_total": resync_count,
        "diagnostic_callback_ms": (
            _summary(callback_ms[warmup:]) if callback_ms else None
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--points", type=int, default=720)
    parser.add_argument("--iterations", type=int, default=300)
    parser.add_argument("--warmup", type=int, default=30)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    measurements = []
    case_names = tuple(CASES)
    listener_modes = ("no_listener", "enumerating_listener")
    for run_index in range(1, args.runs + 1):
        ordered_cases = case_names[run_index - 1 :] + case_names[: run_index - 1]
        ordered_listeners = (
            listener_modes if run_index % 2 else tuple(reversed(listener_modes))
        )
        for listener_mode in ordered_listeners:
            for case_name in ordered_cases:
                measurements.append(
                    _measure(
                        case_name,
                        listener_mode,
                        args.points,
                        args.iterations,
                        args.warmup,
                        run_index,
                    )
                )
    gates = {
        "all_sample_counts_exact": all(
            item["change_block_exit_ms"]["sample_count"] == args.iterations
            and item["set_timing_ms"]["sample_count"] == args.iterations
            for item in measurements
        ),
        "listener_one_notice_per_publication": all(
            item["notice_count_total"] == args.iterations + args.warmup
            for item in measurements
            if item["listener_mode"] == "enumerating_listener"
        ),
        "listener_changed_path_counts_exact": all(
            item["changed_path_count_per_notice"] == [item["attribute_count"]]
            for item in measurements
            if item["listener_mode"] == "enumerating_listener"
        ),
        "listener_no_resync": all(
            item["resync_count_total"] == 0 for item in measurements
        ),
        "no_listener_has_no_diagnostic_callback": all(
            item["diagnostic_callback_ms"] is None
            and item["notice_count_total"] == 0
            for item in measurements
            if item["listener_mode"] == "no_listener"
        ),
    }
    if not all(gates.values()):
        raise RuntimeError(f"Phase 6DD microbenchmark failed: {gates}")
    report = {
        "phase": "phase6dd",
        "status": "ok",
        "scope": "in-memory USD attribute-group and diagnostic-listener baseline",
        "point_count": args.points,
        "iterations_per_case_run": args.iterations,
        "warmup_iterations": args.warmup,
        "run_count": args.runs,
        "usd_package": USD_PACKAGE,
        "cases": {name: list(values) for name, values in CASES.items()},
        "measurements": measurements,
        "gates": gates,
        "interpretation": (
            "This isolated Stage has no Flow, Hydra, PhysX, or production-stage "
            "subscriber set. Live-minus-isolated timing is not a direct Flow-ingest timer."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Phase 6DD USD microbenchmark: {sum(gates.values())}/{len(gates)} gates")


if __name__ == "__main__":
    main()
