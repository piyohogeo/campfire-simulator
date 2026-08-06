"""Compare dictionary-backed and slotted authoritative wood-cell storage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import compare_phase3_homogeneous_heat_capacity as phase6ak
import compare_phase3_inline_heat_capacity as phase6am


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = (
    ROOT
    / "docs"
    / "devlog"
    / "assets"
    / "phase6"
    / "phase3_slotted_cell_report.json"
)
DEFAULT_SVG = DEFAULT_JSON.with_suffix(".svg")


def _validate_run(run: dict, expected_slotted: bool) -> None:
    phase6am._validate_run(run, True)
    actual = run["scenario"].get("python_slotted_wood_cell_storage")
    if actual is not expected_slotted:
        raise ValueError(f"Evidence has unexpected slotted storage: {actual!r}")


def build_report(dictionary_paths: list[Path], slotted_paths: list[Path]) -> dict:
    dictionary = phase6ak._load(dictionary_paths)
    slotted = phase6ak._load(slotted_paths)
    if len(dictionary) != len(slotted) or len(dictionary) < 3:
        raise ValueError("At least three matched runs are required for each storage")
    for run in dictionary:
        _validate_run(run, False)
    for run in slotted:
        _validate_run(run, True)

    all_runs = dictionary + slotted
    reference = all_runs[0]
    invariant_paths = (
        ("metrics_csv_sha256",),
        ("wood", "dry", "authoritative_state_sha256"),
        ("wood", "wet", "authoritative_state_sha256"),
        ("wood", "dry", "ignition_seconds"),
        ("wood", "wet", "ignition_seconds"),
        ("scenario", "steps"),
        ("scenario", "model_dt_seconds"),
        ("scenario", "external_heat_flux_w_m2"),
    )
    for run in all_runs:
        for path in invariant_paths:
            if phase6ak._value_at(run, path) != phase6ak._value_at(reference, path):
                raise ValueError(f"Authoritative invariant differs: {'.'.join(path)}")

    timing_paths = {
        "two_log_step_mean_ms": ("timing", "two_log_model_step_mean_ms"),
        "two_log_step_p95_ms": ("timing", "two_log_model_step_p95_ms"),
        "scenario_seconds": ("scenario", "simulation_wall_seconds"),
    }
    timings = {
        name: phase6ak._comparison(dictionary, slotted, path)
        for name, path in timing_paths.items()
    }
    paired = []
    for index, (dictionary_run, slotted_run) in enumerate(
        zip(dictionary, slotted), start=1
    ):
        dictionary_step = float(
            dictionary_run["timing"]["two_log_model_step_mean_ms"]
        )
        slotted_step = float(slotted_run["timing"]["two_log_model_step_mean_ms"])
        dictionary_scenario = float(
            dictionary_run["scenario"]["simulation_wall_seconds"]
        )
        slotted_scenario = float(
            slotted_run["scenario"]["simulation_wall_seconds"]
        )
        paired.append(
            {
                "pair": index,
                "step_improvement_percent": (
                    (dictionary_step - slotted_step) / dictionary_step * 100.0
                ),
                "scenario_improvement_percent": (
                    (dictionary_scenario - slotted_scenario)
                    / dictionary_scenario
                    * 100.0
                ),
            }
        )
    improving_pairs = sum(
        item["step_improvement_percent"] > 0.0
        and item["scenario_improvement_percent"] > 0.0
        for item in paired
    )
    required_pairs = len(paired) // 2 + 1
    median_gate = (
        timings["two_log_step_mean_ms"]["improvement_percent"] > 0.0
        and timings["scenario_seconds"]["improvement_percent"] > 0.0
    )
    adopt = median_gate and improving_pairs >= required_pairs
    return {
        "schema_version": 1,
        "phase": "phase6ao",
        "status": "ok",
        "paired_run_count": len(dictionary),
        "environment": {
            "application": "campfire.simulator.benchmark.kit",
            "backend": "python",
            "debugger_free_all_runs": True,
            "alternating_order": True,
            "internal_timing_disabled": True,
            "runner_time_excluded_from_adoption": True,
        },
        "trial": {
            "dictionary": "ordinary dataclass instances with per-instance dictionaries",
            "slotted": "slotted dataclass instances with the same public fields",
            "scope": "authoritative cell storage only; equations and update order unchanged",
            "cross_step_cache": False,
            "mass_and_temperature_reads_remain_per_cell": True,
            "public_field_mutation_retained": True,
            "serialized_schema_unchanged": True,
        },
        "timings": timings,
        "paired_results": paired,
        "equivalence": {
            "exact_authoritative_outputs_all_runs": True,
            "dry_state_sha256": reference["wood"]["dry"]["authoritative_state_sha256"],
            "wet_state_sha256": reference["wood"]["wet"]["authoritative_state_sha256"],
            "metrics_csv_sha256": reference["metrics_csv_sha256"],
            "ignition_seconds": {
                "dry": reference["wood"]["dry"]["ignition_seconds"],
                "wet": reference["wood"]["wet"]["ignition_seconds"],
            },
            "flow_peak_dictionary": sorted(
                {run["flow"]["active_blocks_peak"] for run in dictionary}
            ),
            "flow_peak_slotted": sorted(
                {run["flow"]["active_blocks_peak"] for run in slotted}
            ),
            "flow_peak_is_not_authoritative": True,
        },
        "decision": {
            "adopt_slotted_storage": adopt,
            "median_step_and_scenario_improved": median_gate,
            "pairs_improving_step_and_scenario": improving_pairs,
            "required_improving_pairs": required_pairs,
            "reason": (
                "slotted storage met alternating end-to-end gates"
                if adopt
                else "formal end-to-end adoption gates were not met"
            ),
        },
        "runs": {
            "dictionary": [phase6ak._report_path(path) for path in dictionary_paths],
            "slotted": [phase6ak._report_path(path) for path in slotted_paths],
        },
    }


def render_svg(report: dict) -> str:
    step = report["timings"]["two_log_step_mean_ms"]
    scenario = report["timings"]["scenario_seconds"]
    decision = report["decision"]
    adopted = decision["adopt_slotted_storage"]
    color = "#86efac" if adopted else "#fca5a5"
    verdict = (
        "ADOPTED - slotted authoritative cell storage"
        if adopted
        else "REJECTED - retain dictionary-backed cell storage"
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6AO slotted wood-cell storage decision</title>
  <desc id="desc">Three alternating pairs compare dictionary-backed and slotted authoritative wood-cell storage.</desc>
  <style>.title{{font:750 37px 'Segoe UI',sans-serif;fill:#f8fafc}}.kicker{{font:700 17px 'Segoe UI',sans-serif;fill:#fda4af;letter-spacing:2px}}.sub{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.heading{{font:700 16px 'Segoe UI',sans-serif;fill:#f8fafc}}.value{{font:750 28px 'Segoe UI',sans-serif;fill:#fde68a}}.small{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.decision{{font:750 24px 'Segoe UI',sans-serif;fill:{color}}}</style>
  <rect width="1200" height="680" rx="30" fill="#0f172a"/>
  <text x="64" y="64" class="kicker">PHASE 6AO - SLOTTED WOOD-CELL STORAGE</text>
  <text x="64" y="114" class="title">Remove instance dictionaries, keep every public field</text>
  <text x="64" y="148" class="sub">{report['paired_run_count']} alternating pairs - no cache - exact state, CSV, and ignition</text>
  <rect x="64" y="188" width="520" height="292" rx="22" fill="#172033" stroke="#e11d48"/>
  <text x="92" y="230" class="heading">UNPROFILED WOOD STEP</text>
  <text x="92" y="280" class="value">{step['improvement_percent']:.2f}% faster</text>
  <text x="92" y="316" class="sub">{step['original_median']:.4f} to {step['homogeneous_median']:.4f} ms</text>
  <text x="92" y="374" class="small">Temperature and four masses still read per cell</text>
  <text x="92" y="402" class="small">Same equations, arithmetic order, and 1e-9 J/K floor</text>
  <text x="92" y="430" class="small">Public attributes remain mutable</text>
  <rect x="616" y="188" width="520" height="292" rx="22" fill="#172033" stroke="#e11d48"/>
  <text x="644" y="230" class="heading">SCENARIO WALL TIME</text>
  <text x="644" y="280" class="value">{scenario['improvement_percent']:.2f}% faster</text>
  <text x="644" y="316" class="sub">{scenario['original_median']:.4f} to {scenario['homogeneous_median']:.4f} s</text>
  <text x="644" y="374" class="small">Flow, CSV, USD, and two captures retained</text>
  <text x="644" y="402" class="small">{decision['pairs_improving_step_and_scenario']} / {report['paired_run_count']} pairs improve both</text>
  <text x="644" y="430" class="small">Internal timers disabled for adoption</text>
  <rect x="64" y="522" width="1072" height="94" rx="18" fill="#111827" stroke="{color}" stroke-width="2"/>
  <text x="92" y="566" class="decision">{verdict}</text>
  <text x="92" y="594" class="sub">Serialized schema and authoritative cell values remain unchanged.</text>
  <text x="64" y="654" class="small">Profile selected the storage audit; alternating unprofiled end-to-end measurements decide adoption.</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dictionary-summary", type=Path, nargs="+", required=True)
    parser.add_argument("--slotted-summary", type=Path, nargs="+", required=True)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--report-svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    report = build_report(arguments.dictionary_summary, arguments.slotted_summary)
    arguments.report_json.parent.mkdir(parents=True, exist_ok=True)
    arguments.report_json.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    arguments.report_svg.write_text(render_svg(report) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
