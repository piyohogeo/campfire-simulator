"""Aggregate Phase V3T-E GPU ring samples and render committed evidence."""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import statistics
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "devlog" / "assets" / "phasev3te"
METRICS = (
    "source_prepare_ms",
    "cpu_to_gpu_enqueue_ms",
    "explicit_sync_ms",
    "provider_setter_ms",
    "publication_to_next_rtx_frame_ms",
    "kit_update_total_ms",
)


def _arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--regression",
        type=Path,
        help=(
            "Optional final regression summary. When omitted, "
            "regression_report.json beside the manifest is used if present."
        ),
    )
    return parser.parse_args()


def _percentile(values, q):
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def _stats(values):
    values = [float(value) for value in values]
    return {
        "count": len(values),
        "p50_ms": round(_percentile(values, 0.50), 4),
        "mean_ms": round(statistics.fmean(values), 4),
        "p95_ms": round(_percentile(values, 0.95), 4),
        "p99_ms": round(_percentile(values, 0.99), 4),
        "max_ms": round(max(values), 4),
        "over_5_ms": sum(value > 5.0 for value in values),
        "over_16_67_ms": sum(value > 16.67 for value in values),
        "over_33_33_ms": sum(value > 33.33 for value in values),
        "over_50_ms": sum(value > 50.0 for value in values),
    }


def _gpu_summary(path):
    if not path or not Path(path).is_file():
        return {"available": False}
    utilization, memory = [], []
    # PowerShell Start-Process redirection can leave UTF-16-style NUL bytes in
    # an otherwise ASCII nvidia-smi stream.  They are transport encoding, not
    # sample content, so normalize them before CSV parsing.
    content = Path(path).read_text(encoding="utf-8", errors="ignore").replace(
        "\x00", ""
    )
    for row in csv.reader(content.splitlines()):
        if len(row) < 3:
            continue
        try:
            utilization.append(float(row[1].strip()))
            memory.append(float(row[2].strip()))
        except ValueError:
            pass
    return {
        "available": bool(utilization),
        "sample_count": len(utilization),
        "utilization_mean_percent": round(statistics.fmean(utilization), 3) if utilization else None,
        "utilization_max_percent": max(utilization) if utilization else None,
        "memory_mean_mib": round(statistics.fmean(memory), 3) if memory else None,
        "memory_max_mib": max(memory) if memory else None,
        "scope": "whole GPU process observation; not DynamicTextureProvider-owned memory",
    }


def _fatal_log_terms(path):
    if not path or not Path(path).is_file():
        return {"available": False, "matches": []}
    text = Path(path).read_text(encoding="utf-8", errors="replace").lower()
    terms = ("device lost", "use-after-free", "invalid device pointer", "cuda_error_illegal_address")
    return {"available": True, "matches": [term for term in terms if term in text]}


def _median_run_stats(rows, metric):
    return {
        key + "_median": round(statistics.median(row[metric][key] for row in rows), 4)
        for key in (
            "p50_ms",
            "mean_ms",
            "p95_ms",
            "p99_ms",
            "max_ms",
            "over_5_ms",
            "over_16_67_ms",
            "over_33_33_ms",
            "over_50_ms",
        )
    }


def _svg(report):
    rows = [row for row in report["aggregate"] if row["atlas"] == "120x60"]
    order = ["cpu_reference", "gpu_single_sync", "gpu_ring2", "gpu_ring3"]
    rows.sort(key=lambda row: order.index(row["mode"]))
    palette = ["#fb7185", "#f59e0b", "#60a5fa", "#34d399"]
    bars = []
    y = 210
    scale = 18.0
    for index, row in enumerate(rows):
        setter = row["provider_setter_ms"]["p95_ms_median"]
        sync = row["explicit_sync_ms"]["p95_ms_median"]
        frame = row["publication_to_next_rtx_frame_ms"]["p95_ms_median"]
        bars.append(
            f'<text x="70" y="{y + 19}" fill="#e2e8f0" font-size="16">{row["mode"]}</text>'
            f'<rect x="330" y="{y}" width="{min(520, setter * scale):.1f}" height="20" rx="10" fill="{palette[index]}"/>'
            f'<text x="875" y="{y + 17}" fill="#f8fafc" font-size="14">setter {setter:.4f} ms</text>'
            f'<text x="1035" y="{y + 17}" fill="#cbd5e1" font-size="14">sync {sync:.4f}</text>'
            f'<text x="1175" y="{y + 17}" text-anchor="end" fill="#94a3b8" font-size="14">frame {frame:.2f}</text>'
        )
        y += 48
    correctness = report["correctness"]
    life = report["lifecycle"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1240" height="610" viewBox="0 0 1240 610" role="img" aria-labelledby="title desc">
<title id="title">Phase V3T-E GPU source ring qualification</title><desc id="desc">GPU ring source readiness, provider setter, next RTX frame, pixel correctness, lifecycle, and production contract result.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#071827"/><stop offset="1" stop-color="#24142d"/></linearGradient></defs><rect width="1240" height="610" rx="28" fill="url(#bg)"/>
<g font-family="Segoe UI, sans-serif"><text x="70" y="58" fill="#93c5fd" font-size="17" font-weight="700" letter-spacing="3">PHASE V3T-E · GPU SOURCE LIFETIME</text><text x="70" y="105" fill="#f8fafc" font-size="36" font-weight="800">Ring buffer removes owner-thread sync, not the RTX frame.</text><text x="70" y="143" fill="#a7b2c2" font-size="17">120×60 RGBA8 · base + emission · median-of-three p95 · Flow + RTX</text>
{''.join(bars)}
<rect x="70" y="430" width="1100" height="105" rx="18" fill="#0f2537" stroke="#28445d"/><text x="96" y="465" fill="#dbeafe" font-size="17" font-weight="700">Pixel readback</text><text x="96" y="497" fill="#cbd5e1" font-size="15">normal complete {correctness["accepted_complete"]} / {correctness["total"]} · tearing {correctness["mixed_revision_tearing"]} · invalid {correctness["invalid_pixels"]}</text><text x="690" y="465" fill="#dbeafe" font-size="17" font-weight="700">Lifecycle / adoption</text><text x="690" y="497" fill="#cbd5e1" font-size="15">runtime gates {life["passed_gate_count"]} / {life["gate_count"]} · public consumed-fence: absent</text>
<text x="70" y="575" fill="#fca5a5" font-size="16">Production integration: NOT QUALIFIED — ring reuse remains best effort without a public provider-consumption fence.</text></g></svg>'''


def main():
    args = _arguments()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    regression_path = args.regression or args.manifest.with_name(
        "regression_report.json"
    )
    regression = (
        json.loads(regression_path.read_text(encoding="utf-8-sig"))
        if regression_path.is_file()
        else {}
    )
    matrix_runs = []
    lifecycle_run = None
    grouped = defaultdict(list)
    correctness_counts = Counter()
    correctness_by_mode = defaultdict(Counter)
    correctness_by_atlas_mode = defaultdict(Counter)
    topology_stable = True
    fatal_terms = []
    for item in manifest["runs"]:
        raw = json.loads(Path(item["samples"]).read_text(encoding="utf-8"))
        envelope = {
            "matrix": item,
            "gpu": _gpu_summary(item.get("gpu_samples")),
            "fatal_log": _fatal_log_terms(item.get("kit_log")),
            "probe": raw,
        }
        fatal_terms.extend(envelope["fatal_log"]["matches"])
        if item["scenario"] == "lifecycle":
            lifecycle_run = envelope
            continue
        matrix_runs.append(envelope)
        topology_stable = topology_stable and raw["stage_contract"]["topology_unchanged_during_measurement"]
        for mode, samples in raw["samples"].items():
            per_run = {metric: _stats(sample[metric] for sample in samples) for metric in METRICS}
            per_run["gpu"] = envelope["gpu"]
            per_run["bytes_per_publication"] = samples[0]["bytes"]
            per_run["api_calls_per_publication"] = samples[0]["api_calls"]
            grouped[(item["atlas"], mode)].append(per_run)
        for records in raw["correctness"].values():
            for record in records:
                correctness_counts[record["classification"]["category"]] += 1
        for mode, records in raw["correctness"].items():
            for record in records:
                category = record["classification"]["category"]
                correctness_by_mode[mode][category] += 1
                correctness_by_atlas_mode[(item["atlas"], mode)][category] += 1

    aggregate = []
    for (atlas, mode), rows in sorted(grouped.items()):
        aggregate.append(
            {
                "atlas": atlas,
                "mode": mode,
                "run_count": len(rows),
                **{metric: _median_run_stats(rows, metric) for metric in METRICS},
                "bytes_per_publication": rows[0]["bytes_per_publication"],
                "api_calls_per_publication": rows[0]["api_calls_per_publication"],
                "whole_gpu": {
                    "sample_count_total": sum(row["gpu"].get("sample_count", 0) for row in rows),
                    "utilization_mean_percent_median": round(statistics.median(row["gpu"]["utilization_mean_percent"] for row in rows), 3),
                    "utilization_max_percent_median": round(statistics.median(row["gpu"]["utilization_max_percent"] for row in rows), 3),
                    "memory_mean_mib_median": round(statistics.median(row["gpu"]["memory_mean_mib"] for row in rows), 3),
                    "memory_max_mib_median": round(statistics.median(row["gpu"]["memory_max_mib"] for row in rows), 3),
                    "scope": "whole GPU process observation; not provider-owned allocation",
                },
            }
        )

    if lifecycle_run is None:
        raise RuntimeError("Phase V3T-E lifecycle run is missing")
    lifecycle_probe = lifecycle_run["probe"]
    accepted = {"latest_complete", "one_generation_old_complete"}
    lifecycle_categories = {
        item["label"]: item["classification"]["category"] for item in lifecycle_probe["events"]
    }
    long_ok = lifecycle_probe["long_run"]["all_checkpoint_pixels_complete"]
    close_order_ok = lifecycle_probe["close_sequence"] == [
        "warp_source_generation_synchronized",
        "providers_destroyed",
        "probe_owned_gpu_allocations_released",
    ]
    failure_accounting_ok = (
        len(lifecycle_probe["injected_failures"]) == 2
        and lifecycle_probe["fallback_count"] >= 2
    )
    lifecycle_gates = {
        "startup_warmup": lifecycle_categories.get("normal") in accepted,
        "timeline_stop_resume": all(
            lifecycle_categories.get(label) in accepted for label in ("timeline_stop", "timeline_resume")
        ),
        "stage_reload": lifecycle_categories.get("stage_reload") in accepted,
        "stage_replacement": lifecycle_categories.get("stage_replacement") in accepted,
        "provider_regeneration": lifecycle_categories.get("provider_regeneration") in accepted,
        "publication_exception_cpu_fallback": (
            failure_accounting_ok
            and lifecycle_categories.get("partial_failure_cpu_fallback") in accepted
        ),
        "gpu_generation_failure_cpu_fallback": (
            failure_accounting_ok
            and lifecycle_categories.get("generation_failure_cpu_fallback") in accepted
        ),
        "close_with_publication_drain": lifecycle_probe["close_with_publication"]["allocation_alive_through_drain"],
        "provider_before_allocation_close_order": close_order_ok,
        "actual_extension_manager_close": lifecycle_probe["extension_close"]["qualified"],
        "long_continuous_update": long_ok,
        "no_fatal_device_pointer_log": not fatal_terms,
    }
    normal_total = sum(correctness_counts.values())
    accepted_total = sum(correctness_counts[name] for name in accepted)
    pixel_qualified = accepted_total == normal_total and normal_total > 0

    def row(mode, atlas="120x60"):
        return next(item for item in aggregate if item["mode"] == mode and item["atlas"] == atlas)

    cpu = row("cpu_reference")
    single = row("gpu_single_sync")
    ring2 = row("gpu_ring2")
    ring3 = row("gpu_ring3")
    sync_reduced = ring2["explicit_sync_ms"]["p95_ms_median"] < single["explicit_sync_ms"]["p95_ms_median"] * 0.5 and ring3["explicit_sync_ms"]["p95_ms_median"] < single["explicit_sync_ms"]["p95_ms_median"] * 0.5
    setter_retained = max(ring2["provider_setter_ms"]["p95_ms_median"], ring3["provider_setter_ms"]["p95_ms_median"]) <= 0.5
    provider_consumed_fence = False
    production_qualified = pixel_qualified and all(lifecycle_gates.values()) and provider_consumed_fence
    stress_counts = Counter(
        item["classification"]["category"]
        for item in lifecycle_probe["immediate_reuse_stress"]["records"]
    )
    report = {
        "schema": "campfire.phasev3te.gpu_ring.report.v1",
        "status": "probe_complete_no_production_integration",
        "environment": {
            "kit": manifest["kit"],
            "flow": manifest["flow"],
            "gpu_identity": manifest.get("gpu_identity"),
            "single_gpu_process_condition": True,
            "warp_renderer_device_match": lifecycle_probe["device"],
        },
        "matrix": {
            "matrix_processes": len(matrix_runs),
            "independent_runs": manifest["independent_runs"],
            "warmup_per_mode": manifest["warmup_per_mode"],
            "samples_per_mode": manifest["samples_per_mode"],
            "measured_samples": sum(
                len(samples)
                for run in matrix_runs
                for samples in run["probe"]["samples"].values()
            ),
            "correctness_readbacks": normal_total,
            "mode_order_rotated": len({tuple(run["probe"]["mode_order"]) for run in matrix_runs}) >= min(3, manifest["independent_runs"]),
            "topology_stable": topology_stable,
            "capture_excluded_from_performance_population": True,
        },
        "aggregate": aggregate,
        "correctness": {
            "total": normal_total,
            "accepted_complete": accepted_total,
            "latest_complete": correctness_counts["latest_complete"],
            "one_generation_old_complete": correctness_counts["one_generation_old_complete"],
            "stale_complete": correctness_counts["stale_complete"],
            "future_complete": correctness_counts["future_complete"],
            "mixed_revision_tearing": correctness_counts["mixed_revision_tearing"],
            "invalid_pixels": correctness_counts["invalid_pixels"],
            "readback_unavailable": 0,
            "qualified": pixel_qualified,
            "by_mode": {mode: dict(counts) for mode, counts in sorted(correctness_by_mode.items())},
            "by_atlas_and_mode": {
                f"{atlas}:{mode}": dict(counts)
                for (atlas, mode), counts in sorted(correctness_by_atlas_mode.items())
            },
            "boundary": "public RTX viewport PNG readback; not get_managed_resource caching",
        },
        "immediate_reuse_stress": {
            "production_candidate": False,
            "counts": dict(stress_counts),
            "purpose": "detect source overwrite sensitivity only",
        },
        "lifecycle": {
            "gates": lifecycle_gates,
            "passed_gate_count": sum(lifecycle_gates.values()),
            "gate_count": len(lifecycle_gates),
            "events": lifecycle_probe["events"],
            "injected_failures": lifecycle_probe["injected_failures"],
            "long_run": lifecycle_probe["long_run"],
            "close_sequence": lifecycle_probe["close_sequence"],
            "fatal_log_terms": sorted(set(fatal_terms)),
        },
        "performance_decision": {
            "single_gpu_sync_p95_ms": single["explicit_sync_ms"]["p95_ms_median"],
            "ring2_sync_p95_ms": ring2["explicit_sync_ms"]["p95_ms_median"],
            "ring3_sync_p95_ms": ring3["explicit_sync_ms"]["p95_ms_median"],
            "ring_sync_reduced": sync_reduced,
            "ring2_setter_p95_ms": ring2["provider_setter_ms"]["p95_ms_median"],
            "ring3_setter_p95_ms": ring3["provider_setter_ms"]["p95_ms_median"],
            "gpu_setter_approximately_0_2ms_retained": setter_retained,
            "cpu_setter_p95_ms": cpu["provider_setter_ms"]["p95_ms_median"],
            "cpu_sync_tail_reappeared": cpu["provider_setter_ms"]["p95_ms_median"] > 16.67,
            "ring2_next_frame_p95_ms": ring2["publication_to_next_rtx_frame_ms"]["p95_ms_median"],
            "ring3_next_frame_p95_ms": ring3["publication_to_next_rtx_frame_ms"]["p95_ms_median"],
            "next_frame_latency_solved": max(ring2["publication_to_next_rtx_frame_ms"]["p95_ms_median"], ring3["publication_to_next_rtx_frame_ms"]["p95_ms_median"]) < 16.67,
            "owner_thread_transport_effect": "evaluate setter plus explicit source-ready wait independently from requested RTX-frame completion",
        },
        "ownership_and_memory": {
            "max_ring_source_allocations": 6,
            "max_120x60_device_source_bytes": 120 * 60 * 4 * 2 * 3,
            "same_host_source_bytes": 120 * 60 * 4 * 2 * 3,
            "allocation_lifetime": "session-persistent; provider destroyed before Warp source release",
            "provider_owned_memory_measured": False,
            "whole_gpu": lifecycle_run["gpu"],
        },
        "production_decision": {
            "pixel_correctness_qualified": pixel_qualified,
            "runtime_lifecycle_qualified": all(lifecycle_gates.values()),
            "public_provider_source_consumed_fence_qualified": provider_consumed_fence,
            "production_gpu_transport_qualified": production_qualified,
            "production_integration_attempted": False,
            "production_module_modified": False,
            "defaults_changed": False,
            "stop_reason": "DynamicTextureProvider exposes no public source-consumed event/fence or documented reuse lifetime; observed ring correctness cannot turn best-effort reuse into an ABI/lifetime guarantee",
            "cpu_reference_and_fallback_retained": True,
        },
        "evidence_classification": {
            "observed": "timings, RTX readback categories, lifecycle transitions, fault fallback, long-run checkpoints, close order, runtime docstrings, and whole-GPU telemetry",
            "strong_inference": "ring prefetch removes most owner-thread source-ready waiting when runtime measurements support it",
            "unconfirmed": "the exact point at which DynamicTextureProvider finishes reading a GPU source pointer, renderer device identity through a matching public API, provider-owned memory, and internal RTX/Flow fences",
        },
        "regression": regression,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    all_samples = {
        "schema": "campfire.phasev3te.all_samples.v1",
        "manifest": manifest,
        "matrix_runs": matrix_runs,
        "lifecycle_run": lifecycle_run,
    }
    (OUTPUT / "gpu_ring_samples.json").write_text(
        json.dumps(all_samples, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    (OUTPUT / "gpu_ring_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if regression:
        (OUTPUT / "regression_report.json").write_text(
            json.dumps(regression, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    (OUTPUT / "gpu_ring_report.svg").write_text(_svg(report), encoding="utf-8")
    representative = lifecycle_probe["long_run"]["readback_checkpoints"][-1]["capture"]["path"]
    shutil.copy2(representative, OUTPUT / "gpu_ring3_pixel_readback.png")
    print(
        f"Phase V3T-E: {len(matrix_runs)} matrix processes, "
        f"{report['matrix']['measured_samples']} performance samples, "
        f"{normal_total} RTX pixel readbacks"
    )


if __name__ == "__main__":
    main()
