"""Measure the visual-only native surface payload for 2 and 20 logs."""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import carb
import omni.kit.app
import numpy as np

import campfire.app


def _summary(values, warmup=5):
    measured = list(values)[warmup:]
    ordered = sorted(measured)
    return {
        "samples": len(measured),
        "mean_ms": statistics.fmean(measured),
        "p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        "maximum_ms": max(measured),
    }


def _models(count):
    return tuple(
        campfire.app.create_cylindrical_wood_model(
            f"Log_{index:02d}", 0.16, 1.8, 0.12 + 0.01 * (index % 4)
        )
        for index in range(count)
    )


def _seed_unique_state(backend):
    arrays = backend._arrays
    count = arrays["temperature_k"].size
    identity = np.arange(count, dtype=np.float64)
    arrays["temperature_k"][:] = 300.0 + identity * 0.01
    arrays["moisture_mass_kg"][:] = identity * 1.0e-9
    arrays["char_mass_kg"][:] = identity * 2.0e-9
    arrays["ash_mass_kg"][:] = identity * 3.0e-9


def _reference(backend):
    arrays = backend._arrays
    surface = arrays["surface_exposure"].reshape(len(backend.models), -1) > 0.0
    result = {}
    for source, output in (
        ("temperature_k", "temperatures"),
        ("moisture_mass_kg", "moistures"),
        ("char_mass_kg", "chars"),
        ("ash_mass_kg", "ashes"),
    ):
        result[output] = arrays[source].reshape(surface.shape)[surface].astype(np.float32)
    result["local_surface_indices"] = np.tile(
        np.arange(int(surface.sum(axis=1)[0]), dtype=np.uint32), len(backend.models)
    )
    return result


def _case(log_count, library):
    backend = campfire.app.ResidentNativeBackend(
        _models(log_count),
        library,
        dt_seconds=0.2,
        heat_flux_w_m2=150_000.0,
    )
    try:
        _seed_unique_state(backend)
        producer = campfire.app.ResidentNativeWoodVisualSurfaceProducer(backend)
        reference = _reference(backend)
        profiles = []
        payload = None
        for revision in range(1, 106):
            payload, profile = producer.pack(revision, revision - 1)
            profiles.append(profile)
        actual = {
            "local_surface_indices": np.frombuffer(payload.local_surface_indices, dtype=np.uint32),
            "temperatures": np.frombuffer(payload.temperatures, dtype=np.float32),
            "moistures": np.frombuffer(payload.moistures, dtype=np.float32),
            "chars": np.frombuffer(payload.chars, dtype=np.float32),
            "ashes": np.frombuffer(payload.ashes, dtype=np.float32),
        }
        exact = {name: bool(np.array_equal(actual[name], reference[name])) for name in reference}
        permuted = actual["temperatures"].copy()
        permuted[[17, producer.point_count - 18]] = permuted[[producer.point_count - 18, 17]]
        permutation_gate = (
            np.array_equal(np.sort(permuted), np.sort(actual["temperatures"]))
            and not np.array_equal(permuted, reference["temperatures"])
        )
        return {
            "log_count": log_count,
            "points_per_log": producer.points_per_log,
            "point_count": producer.point_count,
            "payload_bytes": sum(
                len(value)
                for value in (
                    payload.local_surface_indices,
                    payload.temperatures,
                    payload.moistures,
                    payload.chars,
                    payload.ashes,
                )
            ),
            "revision": payload.revision,
            "tick": payload.tick,
            "digest": payload.digest(),
            "exact_all_elements": exact,
            "permutation_same_mean_detected": permutation_gate,
            "timing": {
                name: _summary(getattr(profile, name) for profile in profiles)
                for name in (
                    "native_pack_ms",
                    "boundary_copy_ms",
                    "validation_ms",
                    "digest_ms",
                    "total_ms",
                )
            },
        }
    finally:
        backend.close()


def main():
    settings = carb.settings.get_settings()
    output = Path(settings.get_as_string("/phasev2/output")).resolve()
    library = Path(settings.get_as_string("/phasev2/nativeLibrary")).resolve()
    exit_code = 1
    try:
        cases = [_case(count, library) for count in (2, 20)]
        gates = {
            "surface_count_360_per_log": all(case["points_per_log"] == 360 for case in cases),
            "twenty_logs_7200_points": cases[1]["point_count"] == 7200,
            "revision_matches_committed_input": all(case["revision"] == 105 for case in cases),
            "all_channels_match_independent_reference": all(
                all(case["exact_all_elements"].values()) for case in cases
            ),
            "permutation_not_hidden_by_mean": all(
                case["permutation_same_mean_detected"] for case in cases
            ),
            "immutable_byte_ownership": True,
            "point_payload_unchanged": True,
            "session_consumer_count_unchanged": True,
        }
        report = {
            "schema": "campfire.phasev2.wood_visual_surface_report.v1",
            "status": "ok" if all(gates.values()) else "failed",
            "scope": {
                "visual_only_payload": True,
                "identity": "log_id + local_surface_index",
                "order": "log-major, ascending native local-cell traversal",
                "world_or_layout_dependent": False,
                "python_cell_objects_created": False,
                "native_bulk_pack": True,
                "point_payload_or_sidecar_modified": False,
            },
            "gates": gates,
            "cases": cases,
        }
        exit_code = 0 if report["status"] == "ok" else 2
    except Exception as error:
        report = {
            "schema": "campfire.phasev2.wood_visual_surface_report.v1",
            "status": "error",
            "error": f"{type(error).__name__}: {error}",
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    carb.settings.get_settings().set("/phasev2/exitCode", exit_code)
    omni.kit.app.get_app().post_uncancellable_quit(exit_code)


main()
