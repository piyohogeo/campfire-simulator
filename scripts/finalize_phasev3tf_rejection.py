"""Finalize the Phase V3T-F probe as a rejected production candidate.

This script is intentionally analysis-only.  The candidate production transport was
removed after a Kit shutdown access violation, so this script consumes the retained
timing samples and crash log without importing or exercising that candidate again.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "devlog" / "assets" / "phasev3tf"
SAMPLES_PATH = ASSETS / "production_gpu_ring_samples.json"
REPORT_PATH = ASSETS / "production_gpu_ring_report.json"
PRECRASH_PATH = ASSETS / "production_gpu_ring_precrash_report.json"
SVG_PATH = ASSETS / "production_gpu_ring_report.svg"
CRASH_LOG = ROOT / "artifacts" / "phasev3tf" / "lifecycle" / "kit.log"
CRASH_EXCERPT_PATH = ASSETS / "shutdown_crash_excerpt.txt"

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


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def summary(values: list[float]) -> dict[str, object]:
    return {
        "samples": len(values),
        "p50_ms": round(percentile(values, 0.50), 4),
        "mean_ms": round(statistics.fmean(values), 4),
        "p95_ms": round(percentile(values, 0.95), 4),
        "p99_ms": round(percentile(values, 0.99), 4),
        "max_ms": round(max(values), 4),
        "over_5_ms": sum(value > 5.0 for value in values),
        "over_16_67_ms": sum(value > 16.67 for value in values),
        "over_33_33_ms": sum(value > 33.33 for value in values),
        "over_50_ms": sum(value > 50.0 for value in values),
    }


def performance(samples: list[dict[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for mode in ("cpu_reference", "gpu_ring3"):
        mode_samples = [sample for sample in samples if sample["mode"] == mode]
        by_run: dict[str, object] = {}
        for run in sorted({int(sample["run"]) for sample in mode_samples}):
            run_samples = [sample for sample in mode_samples if int(sample["run"]) == run]
            by_run[str(run)] = {
                metric: summary([float(sample[metric]) for sample in run_samples])
                for metric in METRICS
            }
        result[mode] = {
            "all_runs": {
                metric: summary([float(sample[metric]) for sample in mode_samples])
                for metric in METRICS
            },
            "runs": by_run,
        }
    return result


def crash_excerpt() -> tuple[list[str], str]:
    lines = CRASH_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    selected = [
        line
        for line in lines
        if any(
            marker in line
            for marker in (
                "Thread 19184 backtrace follows",
                "UsdGeomCylinder_1::ComputeExtent",
                "UsdContext::unregisterViewOverrideToHydraEngines",
                "carb.eventdispatcher.plugin.dll",
                "omni.timeline.plugin.dll",
                "omni.kit.loop-default.plugin.dll",
                "omni.kit.app.plugin.dll",
                "terminating this process with exit code",
            )
        )
    ]
    excerpt = "\n".join(selected) + "\n"
    return selected, excerpt


def svg(report: dict[str, object]) -> str:
    perf = report["performance"]
    cpu = perf["cpu_reference"]["all_runs"]
    gpu = perf["gpu_ring3"]["all_runs"]
    cpu_setter = cpu["provider_setter_ms"]["p95_ms"]
    gpu_setter = gpu["provider_setter_ms"]["p95_ms"]
    gpu_wait = gpu["source_ready_wait_ms"]["p95_ms"]
    cpu_frame = cpu["publication_to_next_rtx_frame_ms"]["p95_ms"]
    gpu_frame = gpu["publication_to_next_rtx_frame_ms"]["p95_ms"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1240" height="700" viewBox="0 0 1240 700" role="img" aria-labelledby="title desc">
<title id="title">Phase V3T-F GPU ring production candidate rejected</title>
<desc id="desc">GPU publication removed the CPU setter tail but a shutdown access violation caused the production integration to be reverted.</desc>
<rect width="1240" height="700" fill="#07111f"/>
<g font-family="Segoe UI, sans-serif">
<text x="70" y="56" fill="#93c5fd" font-size="17" font-weight="700" letter-spacing="3">PHASE V3T-F · PRODUCTION CANDIDATE</text>
<text x="70" y="105" fill="#f8fafc" font-size="37" font-weight="800">Fast setter, failed lifecycle gate.</text>
<text x="70" y="140" fill="#a7b2c2" font-size="17">20 logs · 120×60 RGBA8 · base + emission · Flow + RTX · 3 runs × 120 samples per transport</text>
<text x="70" y="200" fill="#dbeafe" font-size="18" font-weight="700">All-run p95 (ms)</text>
<text x="70" y="248" fill="#cbd5e1" font-size="15">CPU Provider setter</text><rect x="280" y="228" width="{cpu_setter * 14:.1f}" height="26" rx="6" fill="#f59e0b"/><text x="{295 + cpu_setter * 14:.1f}" y="248" fill="#fef3c7" font-size="15">{cpu_setter:.4f}</text>
<text x="70" y="296" fill="#cbd5e1" font-size="15">GPU Provider setter</text><rect x="280" y="276" width="6" height="26" rx="3" fill="#22c55e"/><text x="302" y="296" fill="#dcfce7" font-size="15">{gpu_setter:.4f}</text>
<text x="70" y="344" fill="#cbd5e1" font-size="15">GPU source-ready wait</text><rect x="280" y="324" width="{max(6, gpu_wait * 14):.1f}" height="26" rx="6" fill="#38bdf8"/><text x="{295 + max(6, gpu_wait * 14):.1f}" y="344" fill="#dbeafe" font-size="15">{gpu_wait:.4f}</text>
<rect x="70" y="392" width="1100" height="88" rx="16" fill="#0f2537" stroke="#28445d"/>
<text x="96" y="428" fill="#dbeafe" font-size="17" font-weight="700">End-to-end remains separate</text>
<text x="96" y="459" fill="#cbd5e1" font-size="15">Next RTX frame p95: CPU {cpu_frame:.4f} ms · GPU {gpu_frame:.4f} ms. GPU transport does not solve Flow + RTX latency.</text>
<rect x="70" y="512" width="1100" height="112" rx="18" fill="#3a1118" stroke="#fb7185" stroke-width="2"/>
<text x="98" y="550" fill="#fecdd3" font-size="19" font-weight="800">REJECTED · shutdown access violation 0xC0000005</text>
<text x="98" y="582" fill="#fda4af" font-size="15">Crash boundary: UsdGeom ComputeExtent → UsdContext unregisterViewOverride → timeline / Kit shutdown.</text>
<text x="98" y="607" fill="#fda4af" font-size="15">No public Provider source-consumed fence. Candidate integration reverted; CPU V3 and all defaults remain unchanged.</text>
<text x="70" y="670" fill="#94a3b8" font-size="14">Observed performance benefit is retained as probe evidence; it is not a safety, atomicity, or tearing-free claim.</text>
</g></svg>'''


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    previous = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    if not PRECRASH_PATH.exists():
        PRECRASH_PATH.write_text(
            json.dumps(previous, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    retained = json.loads(SAMPLES_PATH.read_text(encoding="utf-8"))
    samples = retained["samples"]
    selected_crash, excerpt = crash_excerpt()
    report = {
        "schema": "campfire.phasev3tf.production_gpu_ring.rejection.v1",
        "status": "not_qualified",
        "decision": "production_integration_reverted",
        "baseline": "c5cbb4a",
        "environment": {
            "kit": "110.2",
            "flow": "110.0.0",
            "gpu": "NVIDIA GeForce RTX 3090",
            "atlas": [120, 60],
            "textures": ["base", "emission"],
        },
        "population": {
            "runs": 3,
            "warmup_per_mode_per_run": 20,
            "samples_per_mode_per_run": 120,
            "retained_samples": len(samples),
            "bytes_per_publication": 57600,
            "api_calls_per_publication": 2,
        },
        "performance": performance(samples),
        "candidate_contract_tested": {
            "provider_count": 2,
            "source_slots_per_texture": 3,
            "persistent_probe_owned_warp_allocations": True,
            "source_ready_event_before_setter": True,
            "provider_source_consumed_fence_available": False,
            "lifetime_contract": "best effort only; not guaranteed by the public API",
            "eventual_consistency_only": True,
            "wood_or_flow_authority_changed": False,
        },
        "precrash_observations": {
            "performance_gate": "passed",
            "injected_initialization_failure_cpu_fallback": True,
            "injected_mid_publication_fault_next_complete_cpu_fallback": True,
            "timeline_stop_resume_exercised": True,
            "stage_replacement_and_provider_recreation_exercised": True,
            "continuous_updates": 1200,
            "long_run_checkpoints_latest_complete": True,
            "bounded_convergence_observed": True,
            "readback_classifier_qualified": False,
            "readback_note": "RTX exposure and temporal rendering made inverse revision classification unstable. The retained pre-crash report is exploratory evidence, not a production pixel-safety qualification.",
        },
        "stopping_failure": {
            "observed": True,
            "process_exit_decimal": 3221225477,
            "process_exit_hex": "0xC0000005",
            "phase": "isolated lifecycle process shutdown",
            "backtrace_excerpt": selected_crash,
            "cuda_illegal_address_logged": False,
            "device_lost_logged": False,
            "causal_attribution": "unconfirmed",
            "reason_for_rejection": "A shutdown crash is an explicit rejection condition, and the public API exposes no source-consumed fence with which to exclude GPU source lifetime from the cause.",
        },
        "observed_facts": [
            "GPU ring3 removed the approximately 30 ms CPU-source Provider setter tail in the retained timing population.",
            "Flow plus RTX next-frame latency remained tens of milliseconds and is a separate boundary.",
            "A later isolated lifecycle process terminated with 0xC0000005 during Kit shutdown.",
            "The candidate production changes were fully reverted before final regression.",
        ],
        "strong_inferences": [
            "GPU-source publication is promising for owner-thread latency but not adoptable in the fixed environment without a stable shutdown and a public consumption/lifetime boundary.",
        ],
        "unconfirmed": [
            "Whether DynamicTextureProvider source reuse contributed to the shutdown crash.",
            "Whether the low-confidence UsdGeom frames identify the root cause rather than shutdown fallout.",
            "The renderer-side GPU source-consumption completion point.",
            "Atomicity or tearing-free behavior across base and emission textures.",
        ],
        "final_production_state": {
            "gpu_transport_setting_added": False,
            "v3_demo_preset_changed": False,
            "production_modules_changed": False,
            "cpu_source_v3_retained": True,
            "v3_default_off": True,
            "point_and_rigid_default_off": True,
            "sphere_production_default": True,
        },
        "resume_conditions": [
            "A public source-consumed fence or documented GPU pointer reuse/lifetime contract becomes available.",
            "An isolated Kit/renderer update demonstrates repeated crash-free lifecycle closure and full regression.",
            "A real operational need justifies reopening this display-only optimization.",
        ],
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SVG_PATH.write_text(svg(report), encoding="utf-8")
    CRASH_EXCERPT_PATH.write_text(excerpt, encoding="utf-8")


if __name__ == "__main__":
    main()
