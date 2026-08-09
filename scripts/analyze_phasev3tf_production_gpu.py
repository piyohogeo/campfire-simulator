"""Aggregate a complete pre-crash Phase V3T-F candidate run.

The safe baseline no longer contains that candidate.  Use
``finalize_phasev3tf_rejection.py`` to regenerate the committed rejection
report from retained samples and the shutdown crash log.
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "devlog" / "assets" / "phasev3tf"
METRICS = (
    "pattern_generation_ms",
    "gpu_staging_prepare_ms",
    "h2d_enqueue_ms",
    "source_ready_wait_ms",
    "provider_setter_ms",
    "publication_to_next_rtx_frame_ms",
    "kit_update_ms",
    "publication_total_ms",
)


def _percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def _summary(values):
    values = list(values)
    return {
        "samples": len(values),
        "p50_ms": _percentile(values, 0.50),
        "mean_ms": statistics.fmean(values),
        "p95_ms": _percentile(values, 0.95),
        "p99_ms": _percentile(values, 0.99),
        "max_ms": max(values),
        "over_5_ms": sum(value > 5.0 for value in values),
        "over_16_67_ms": sum(value > 16.67 for value in values),
        "over_33_33_ms": sum(value > 33.33 for value in values),
        "over_50_ms": sum(value > 50.0 for value in values),
    }


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _readback_counts(records):
    counts = {
        "latest_complete": 0,
        "latest_previous_mixed": 0,
        "previous_complete": 0,
        "base_emission_one_revision_apart": 0,
        "two_or_more_generations_stale": 0,
        "invalid_or_uninitialized": 0,
    }
    for record in records:
        classification = record["classification"]
        categories = [value["category"] for value in classification["textures"].values()]
        if all(value == "latest_complete" for value in categories):
            counts["latest_complete"] += 1
        if any(value == "latest_previous_mixed" for value in categories):
            counts["latest_previous_mixed"] += 1
        if any(value == "previous_complete" for value in categories):
            counts["previous_complete"] += 1
        if classification["base_emission_within_one_revision"] and len(set(categories)) > 1:
            counts["base_emission_one_revision_apart"] += 1
        if any(value == "two_or_more_generations_stale" for value in categories):
            counts["two_or_more_generations_stale"] += 1
        if any(value == "invalid_or_uninitialized" for value in categories):
            counts["invalid_or_uninitialized"] += 1
    return counts


def _svg(report):
    perf = report["performance"]
    cpu = perf["cpu_reference"]["provider_setter_ms"]["p95_ms"]
    gpu = perf["gpu_ring3"]["provider_setter_ms"]["p95_ms"]
    wait = perf["gpu_ring3"]["source_ready_wait_ms"]["p95_ms"]
    cpu_frame = perf["cpu_reference"]["publication_to_next_rtx_frame_ms"]["p95_ms"]
    gpu_frame = perf["gpu_ring3"]["publication_to_next_rtx_frame_ms"]["p95_ms"]
    scale = 16.0
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1240" height="650" viewBox="0 0 1240 650" role="img">
<rect width="1240" height="650" fill="#07111f"/><g font-family="Segoe UI, sans-serif">
<text x="70" y="58" fill="#93c5fd" font-size="17" font-weight="700" letter-spacing="3">PHASE V3T-F · PRODUCTION GPU RING3</text>
<text x="70" y="106" fill="#f8fafc" font-size="36" font-weight="800">The owner-thread tail moves off the Provider setter.</text>
<text x="70" y="142" fill="#a7b2c2" font-size="17">20 logs · 120×60 RGBA8 · base + emission · Flow + RTX · three independent runs</text>
<text x="70" y="205" fill="#dbeafe" font-size="18" font-weight="700">Median-of-run p95 (ms)</text>
<text x="70" y="258" fill="#cbd5e1" font-size="15">CPU Provider setter</text><rect x="260" y="238" width="{cpu*scale:.1f}" height="26" rx="6" fill="#f59e0b"/><text x="{275+cpu*scale:.1f}" y="258" fill="#fef3c7" font-size="15">{cpu:.3f}</text>
<text x="70" y="310" fill="#cbd5e1" font-size="15">GPU Provider setter</text><rect x="260" y="290" width="{max(3,gpu*scale):.1f}" height="26" rx="6" fill="#22c55e"/><text x="{275+max(3,gpu*scale):.1f}" y="310" fill="#dcfce7" font-size="15">{gpu:.3f}</text>
<text x="70" y="362" fill="#cbd5e1" font-size="15">GPU source-ready wait</text><rect x="260" y="342" width="{max(3,wait*scale):.1f}" height="26" rx="6" fill="#38bdf8"/><text x="{275+max(3,wait*scale):.1f}" y="362" fill="#dbeafe" font-size="15">{wait:.3f}</text>
<rect x="70" y="418" width="1100" height="94" rx="18" fill="#0f2537" stroke="#28445d"/>
<text x="96" y="454" fill="#dbeafe" font-size="17" font-weight="700">Next requested RTX frame remains a separate boundary</text>
<text x="96" y="487" fill="#cbd5e1" font-size="15">CPU {cpu_frame:.3f} ms · GPU ring3 {gpu_frame:.3f} ms p95 — GPU transport is not claimed to solve Flow + RTX frame latency.</text>
<text x="70" y="565" fill="#f8fafc" font-size="18" font-weight="700">Adoption boundary</text>
<text x="70" y="600" fill="#a7b2c2" font-size="15">Default OFF · eventually consistent display observer · no public Provider source-consumed fence · CPU fallback retained</text>
</g></svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    manifest = _read_json(args.manifest)
    entries = [(entry, _read_json(entry["raw"])) for entry in manifest["entries"]]
    runs = [run for entry, run in entries if entry["scenario"] == "performance"]
    lifecycle_runs = [run for entry, run in entries if entry["scenario"] == "lifecycle"]
    if len(lifecycle_runs) != 1:
        raise RuntimeError("Phase V3T-F requires one isolated lifecycle process")
    performance = {}
    all_samples = []
    for mode in ("cpu_reference", "gpu_ring3"):
        performance[mode] = {}
        for metric in METRICS:
            run_summaries = [_summary(run["performance"][mode]["samples"][index][metric]
                                      for index in range(len(run["performance"][mode]["samples"])))
                             for run in runs]
            performance[mode][metric] = {
                "runs": run_summaries,
                "p95_ms": statistics.median(value["p95_ms"] for value in run_summaries),
                "p99_ms": statistics.median(value["p99_ms"] for value in run_summaries),
                "max_ms": max(value["max_ms"] for value in run_summaries),
            }
        for run in runs:
            for sample in run["performance"][mode]["samples"]:
                all_samples.append({"run": run["run"] + 1, "mode": mode, **sample})

    lifecycle_run = lifecycle_runs[0]
    lifecycle = lifecycle_run["lifecycle"]
    cpu_records = lifecycle["cpu_readback"]["records"]
    gpu_records = lifecycle["gpu_readback"]["records"]
    cpu_counts = _readback_counts(cpu_records)
    gpu_counts = _readback_counts(gpu_records)
    long_checkpoints = lifecycle["long_run"]["checkpoints"]
    close_expected = [
        "warp_source_generation_synchronized",
        "providers_destroyed",
        "gpu_source_allocations_released",
    ]
    gates = {
        "gpu_setter_p95_below_1_ms": performance["gpu_ring3"]["provider_setter_ms"]["p95_ms"] < 1.0,
        "gpu_wait_plus_setter_below_cpu_setter": (
            performance["gpu_ring3"]["source_ready_wait_ms"]["p95_ms"]
            + performance["gpu_ring3"]["provider_setter_ms"]["p95_ms"]
            < performance["cpu_reference"]["provider_setter_ms"]["p95_ms"] * 0.5
        ),
        "gpu_setter_has_no_16_67ms_tail": all(
            sample["provider_setter_ms"] < 16.67 for sample in all_samples if sample["mode"] == "gpu_ring3"
        ),
        "no_invalid_readback": cpu_counts["invalid_or_uninitialized"] == 0 and gpu_counts["invalid_or_uninitialized"] == 0,
        "no_two_generation_stale": cpu_counts["two_or_more_generations_stale"] == 0 and gpu_counts["two_or_more_generations_stale"] == 0,
        "cpu_gpu_reference_pixels_equivalent": lifecycle["cpu_gpu_reference_distance"]["maximum_rgb_distance"] < 35.0,
        "cpu_converged_bounded": lifecycle["cpu_readback"]["convergence"] is not None,
        "gpu_converged_bounded": lifecycle["gpu_readback"]["convergence"] is not None,
        "initialization_failure_falls_back": lifecycle["initialization_fallback"]["profile_transport"] == "cpu_fallback",
        "mid_publication_fault_falls_back_next_pair": (
            lifecycle["mid_publication_fallback"]["raised"]
            and lifecycle["mid_publication_fallback"]["fallback_profile"]["transport"] == "cpu_fallback"
            and lifecycle["mid_publication_fallback"]["fallback_profile"]["upload_count"] == 2
        ),
        "timeline_restart_gpu": lifecycle["timeline"]["resumed_transport"] == "gpu_ring3",
        "stage_replacement_recreates_providers": lifecycle["stage_replacement"]["provider_recreation_count"] == 1,
        "long_run_1200_or_more": lifecycle["long_run"]["updates"] >= 1200,
        "long_run_checkpoints_allowed": all(
            value["classification"]["allowed_eventual_state"] for value in long_checkpoints
        ),
        "extension_close_order": lifecycle["extension_disable"]["close_sequence"] == close_expected,
    }
    qualified = all(gates.values())
    report = {
        "schema": "campfire.phasev3tf.production_gpu_ring.report.v1",
        "status": "qualified" if qualified else "not_qualified",
        "gates": gates,
        "performance": performance,
        "readback": {
            "cpu_reference": cpu_counts,
            "gpu_ring3": gpu_counts,
            "convergence_frame_limit": lifecycle_run["convergence_frame_limit"],
            "cpu_convergence_frames": lifecycle["cpu_readback"]["convergence"]["frames"] if lifecycle["cpu_readback"]["convergence"] else None,
            "gpu_convergence_frames": lifecycle["gpu_readback"]["convergence"]["frames"] if lifecycle["gpu_readback"]["convergence"] else None,
            "accepted_degradation": "latest/previous mixing within a texture and one-revision base/emission skew",
        },
        "lifecycle": lifecycle,
        "contract": {
            "transport": "production WoodVisualV3Consumer triple persistent Warp source ring",
            "default": False,
            "cpu_reference_and_fallback_retained": True,
            "atomic_or_tearing_free_claimed": False,
            "provider_source_consumed_fence_available": False,
            "lifetime": "best effort in fixed Kit 110.2; three slots retained until source sync, provider destruction, then allocation release",
            "observer": "eventually consistent and regenerable; never authority or Flow input",
        },
        "environment": runs[0]["environment"],
        "raw_run_count": len(runs),
        "isolated_lifecycle_process_count": len(lifecycle_runs),
        "sample_count": len(all_samples),
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "production_gpu_ring_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUTPUT / "production_gpu_ring_samples.json").write_text(
        json.dumps({"schema": "campfire.phasev3tf.samples.v1", "samples": all_samples}, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUTPUT / "production_gpu_ring_report.svg").write_text(_svg(report), encoding="utf-8")
    representative = Path(long_checkpoints[-1]["capture"]["path"])
    shutil.copy2(representative, OUTPUT / "production_gpu_ring_readback.png")
    print(f"Phase V3T-F: {report['status']}, gates={sum(gates.values())}/{len(gates)}")
    if not qualified:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
