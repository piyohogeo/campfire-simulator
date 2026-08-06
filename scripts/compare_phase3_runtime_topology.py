"""Compare dynamic and explicitly snapshotted Phase 3 runtime topology."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = ROOT / "docs/devlog/assets/phase6/phase3_runtime_topology_report.json"
DEFAULT_SVG = DEFAULT_JSON.with_suffix(".svg")


def _load(paths: list[Path]) -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def _at(run: dict, path: tuple[str, ...]):
    value = run
    for key in path:
        value = value[key]
    return value


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def _comparison(dynamic: list[dict], precomputed: list[dict], path: tuple[str, ...]) -> dict:
    baseline = statistics.median(float(_at(run, path)) for run in dynamic)
    optimized = statistics.median(float(_at(run, path)) for run in precomputed)
    return {
        "dynamic_median": baseline,
        "precomputed_median": optimized,
        "improvement_percent": (baseline - optimized) / baseline * 100.0,
    }


def _validate(run: dict, precomputed: bool) -> None:
    scenario = run["scenario"]
    if run.get("status") != "ok" or run.get("phase") != "phase3":
        raise ValueError("Input is not a successful Phase 3 run")
    required = (
        scenario.get("wood_array_backend") == "python"
        and scenario.get("python_surface_boundary_fast_path")
        and scenario.get("python_state_clamp_fast_path")
        and scenario.get("deferred_cell_phase_updates")
        and scenario.get("compact_runtime_metrics")
        and not scenario.get("wood_internal_timing_enabled")
        and not scenario.get("wood_state_diagnostics_enabled")
        and scenario.get("debugger_free")
    )
    if not required:
        raise ValueError("Input did not preserve the adopted debugger-free control path")
    if bool(scenario.get("precomputed_runtime_topology")) != precomputed:
        raise ValueError("Input used the wrong runtime-topology path")


def build_report(dynamic_paths: list[Path], precomputed_paths: list[Path]) -> dict:
    dynamic = _load(dynamic_paths)
    precomputed = _load(precomputed_paths)
    if len(dynamic) != len(precomputed) or len(dynamic) < 3:
        raise ValueError("At least three equal alternating pairs are required")
    for run in dynamic:
        _validate(run, False)
    for run in precomputed:
        _validate(run, True)
    reference = dynamic[0]
    invariants = (
        ("metrics_csv_sha256",),
        ("wood", "dry", "authoritative_state_sha256"),
        ("wood", "wet", "authoritative_state_sha256"),
        ("wood", "dry", "ignition_seconds"),
        ("wood", "wet", "ignition_seconds"),
        ("scenario", "steps"),
        ("scenario", "model_dt_seconds"),
        ("scenario", "external_heat_flux_w_m2"),
    )
    for run in dynamic + precomputed:
        for path in invariants:
            if _at(run, path) != _at(reference, path):
                raise ValueError(f"Authoritative invariant differs: {'.'.join(path)}")
    paths = {
        "metrics_mean_ms": ("timing", "segments", "wood_metrics", "mean_ms"),
        "visual_mean_ms": ("timing", "segments", "wood_visual_usd", "mean_ms"),
        "step_loop_mean_ms": ("timing", "segments", "step_loop", "mean_ms"),
        "step_loop_p95_ms": ("timing", "segments", "step_loop", "p95_ms"),
        "scenario_seconds": ("scenario", "simulation_wall_seconds"),
        "runner_seconds": ("runner_wall_seconds",),
    }
    timings = {name: _comparison(dynamic, precomputed, path) for name, path in paths.items()}
    pairs = []
    for index, (base, optimized) in enumerate(zip(dynamic, precomputed), start=1):
        pair = {"pair": index}
        for name, path in (("metrics", paths["metrics_mean_ms"]), ("visual", paths["visual_mean_ms"]), ("step_loop", paths["step_loop_mean_ms"]), ("scenario", paths["scenario_seconds"])):
            before = float(_at(base, path))
            after = float(_at(optimized, path))
            pair[f"{name}_improvement_percent"] = (before - after) / before * 100.0
        pairs.append(pair)
    improving = sum(
        pair["step_loop_improvement_percent"] > 0.0
        and pair["scenario_improvement_percent"] > 0.0
        for pair in pairs
    )
    required_pairs = len(pairs) // 2 + 1
    median_gate = all(
        timings[name]["improvement_percent"] > 0.0
        for name in ("metrics_mean_ms", "visual_mean_ms", "step_loop_mean_ms", "scenario_seconds")
    )
    adopt = median_gate and improving >= required_pairs
    return {
        "schema_version": 1,
        "phase": "phase6af",
        "status": "ok",
        "paired_run_count": len(dynamic),
        "environment": {"application": "campfire.simulator.benchmark.kit", "backend": "python", "alternating_order": True, "debugger_free_all_runs": True},
        "mutability_audit": {
            "cells_and_surface_metadata_are_publicly_mutable": True,
            "calibration_rewrites_surface_metadata_after_construction": True,
            "unconditional_constructor_cache_rejected": True,
            "explicit_snapshot_after_scenario_configuration": True,
            "legacy_dynamic_api_preserved": True,
            "snapshot_contents": ["ordered cell references", "ordered surface-cell references", "initial dry-mass display baseline"],
        },
        "timings": timings,
        "paired_results": pairs,
        "equivalence": {
            "exact_authoritative_outputs_all_runs": True,
            "dry_state_sha256": reference["wood"]["dry"]["authoritative_state_sha256"],
            "wet_state_sha256": reference["wood"]["wet"]["authoritative_state_sha256"],
            "metrics_csv_sha256": reference["metrics_csv_sha256"],
            "ignition_seconds": {"dry": reference["wood"]["dry"]["ignition_seconds"], "wet": reference["wood"]["wet"]["ignition_seconds"]},
        },
        "decision": {
            "adopt_precomputed_runtime_topology": adopt,
            "all_median_gates_improved": median_gate,
            "pairs_improving_loop_and_scenario": improving,
            "required_improving_pairs": required_pairs,
            "reason": "all targeted medians and a majority of paired end-to-end runs improved" if adopt else "formal end-to-end adoption gates were not met",
        },
        "runs": {"dynamic": [_relative(path) for path in dynamic_paths], "precomputed": [_relative(path) for path in precomputed_paths]},
    }


def render_svg(report: dict) -> str:
    timings = report["timings"]
    decision = report["decision"]
    adopted = decision["adopt_precomputed_runtime_topology"]
    color = "#86efac" if adopted else "#fca5a5"
    verdict = "ADOPTED - explicit topology snapshot" if adopted else "REJECTED - keep dynamic topology reads"
    cards = (
        ("METRICS AGGREGATION", timings["metrics_mean_ms"]),
        ("WOOD VISUAL UPDATE", timings["visual_mean_ms"]),
        ("SCENARIO WALL TIME", timings["scenario_seconds"]),
    )
    blocks = []
    for index, (label, item) in enumerate(cards):
        x = 64 + index * 368
        unit = "s" if index == 2 else "ms"
        change = item["improvement_percent"]
        direction = "faster" if change >= 0.0 else "slower"
        blocks.append(f'''<rect x="{x}" y="188" width="336" height="292" rx="22" fill="#172033" stroke="#2563eb"/><text x="{x + 28}" y="230" class="heading">{label}</text><text x="{x + 28}" y="280" class="value">{abs(change):.2f}% {direction}</text><text x="{x + 28}" y="316" class="sub">{item['dynamic_median']:.4f} to {item['precomputed_median']:.4f} {unit}</text>''')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc"><title id="title">Phase 6AF runtime topology decision</title><desc id="desc">Three alternating pairs compare dynamic topology reads with an explicit snapshot.</desc><defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#0f172a"/><stop offset="1" stop-color="#172554"/></linearGradient></defs><style>.title{{font:750 38px 'Segoe UI',sans-serif;fill:#f8fafc}}.kicker{{font:700 17px 'Segoe UI',sans-serif;fill:#60a5fa;letter-spacing:2px}}.sub{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.heading{{font:700 16px 'Segoe UI',sans-serif;fill:#f8fafc}}.value{{font:750 28px 'Segoe UI',sans-serif;fill:#93c5fd}}.small{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.decision{{font:750 24px 'Segoe UI',sans-serif;fill:{color}}}</style><rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="64" class="kicker">PHASE 6AF - STATIC TOPOLOGY AUDIT</text><text x="64" y="114" class="title">Snapshot only after topology configuration</text><text x="64" y="148" class="sub">Public mutability preserved - {report['paired_run_count']} alternating pairs - exact state and CSV equivalence</text>{''.join(blocks)}<text x="92" y="374" class="small">No per-cell surface predicate</text><text x="92" y="402" class="small">Ordered surface references retained</text><text x="460" y="374" class="small">Initial dry-mass baseline cached</text><text x="460" y="402" class="small">Default visual API remains dynamic</text><text x="828" y="374" class="small">Step loop: {timings['step_loop_mean_ms']['improvement_percent']:.2f}%</text><text x="828" y="402" class="small">{decision['pairs_improving_loop_and_scenario']} / {report['paired_run_count']} pairs improve loop + scenario</text><rect x="64" y="522" width="1072" height="94" rx="18" fill="#111c34" stroke="{color}" stroke-width="2"/><text x="92" y="566" class="decision">{verdict}</text><text x="92" y="594" class="sub">Constructor caching rejected: calibration legitimately edits surface metadata after model creation.</text><text x="64" y="654" class="small">Adoption requires metrics, visual, step-loop, scenario medians and paired repeatability to improve.</text></svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dynamic-summary", type=Path, nargs="+", required=True)
    parser.add_argument("--precomputed-summary", type=Path, nargs="+", required=True)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--report-svg", type=Path, default=DEFAULT_SVG)
    args = parser.parse_args()
    report = build_report(args.dynamic_summary, args.precomputed_summary)
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.report_svg.write_text(render_svg(report) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
