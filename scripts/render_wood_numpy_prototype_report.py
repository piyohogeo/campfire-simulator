"""Validate Phase 6W NumPy evidence and render a browser-readable SVG."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BENCHMARK = (
    REPOSITORY_ROOT
    / "artifacts"
    / "performance"
    / "wood_numpy_backend_benchmark.json"
)
DEFAULT_PYTHON_SUMMARY = (
    REPOSITORY_ROOT / "artifacts" / "phase3" / "phase6w_python" / "summary.json"
)
DEFAULT_NUMPY_SUMMARY = (
    REPOSITORY_ROOT / "artifacts" / "phase3" / "phase6w_numpy" / "summary.json"
)
DEFAULT_REPORT_JSON = (
    REPOSITORY_ROOT
    / "docs"
    / "devlog"
    / "assets"
    / "phase6"
    / "wood_numpy_prototype_report.json"
)
DEFAULT_REPORT_SVG = DEFAULT_REPORT_JSON.with_suffix(".svg")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_report(benchmark: dict, python_summary: dict, numpy_summary: dict) -> dict:
    equivalence = benchmark["equivalence"]
    if not all(
        equivalence[name]
        for name in (
            "exact_state_sha256_match",
            "exact_step_history_sha256_match",
            "exact_metrics_match",
        )
    ):
        raise ValueError("The complete-step microbenchmark changed authoritative output")
    if python_summary["scenario"]["wood_array_backend"] != "python":
        raise ValueError("The Phase 3 Python summary used the wrong backend")
    if numpy_summary["scenario"]["wood_array_backend"] != "numpy":
        raise ValueError("The Phase 3 NumPy summary used the wrong backend")

    phase3_state_matches = {
        name: (
            python_summary["wood"][name]["authoritative_state_sha256"]
            == numpy_summary["wood"][name]["authoritative_state_sha256"]
        )
        for name in ("dry", "wet")
    }
    python_csv_sha256 = _file_sha256(Path(python_summary["metrics_csv"]))
    numpy_csv_sha256 = _file_sha256(Path(numpy_summary["metrics_csv"]))
    phase3_csv_match = python_csv_sha256 == numpy_csv_sha256
    phase3_ignition_match = all(
        python_summary["wood"][name]["ignition_seconds"]
        == numpy_summary["wood"][name]["ignition_seconds"]
        for name in ("dry", "wet")
    )
    phase3_flow_match = (
        python_summary["flow"]["active_blocks_peak"]
        == numpy_summary["flow"]["active_blocks_peak"]
    )
    if not (
        all(phase3_state_matches.values())
        and phase3_csv_match
        and phase3_ignition_match
        and phase3_flow_match
    ):
        raise ValueError("The Phase 3 NumPy trial changed an accepted output")

    python_ms = benchmark["measurements"]["python"]["median_ms"]
    numpy_ms = benchmark["measurements"]["numpy"]["median_ms"]
    improvement = benchmark["decision"]["numpy_improvement_fraction"]
    phase3_python_ms = python_summary["timing"]["segments"]["wood_model_step"][
        "mean_ms"
    ]
    phase3_numpy_ms = numpy_summary["timing"]["segments"]["wood_model_step"][
        "mean_ms"
    ]
    return {
        "phase": "6W",
        "microbenchmark": {
            "steps": benchmark["steps"],
            "runs": benchmark["runs"],
            "total_cells": benchmark["total_cells"],
            "python_median_ms_per_model_step": python_ms,
            "numpy_median_ms_per_model_step": numpy_ms,
            "numpy_improvement_fraction": improvement,
            "exact_state_sha256_match": equivalence[
                "exact_state_sha256_match"
            ],
            "exact_step_history_sha256_match": equivalence[
                "exact_step_history_sha256_match"
            ],
            "exact_metrics_match": equivalence["exact_metrics_match"],
        },
        "phase3_trial": {
            "steps": python_summary["scenario"]["steps"],
            "dry_state_sha256_match": phase3_state_matches["dry"],
            "wet_state_sha256_match": phase3_state_matches["wet"],
            "metrics_csv_sha256_match": phase3_csv_match,
            "ignition_times_match": phase3_ignition_match,
            "flow_active_blocks_peak_match": phase3_flow_match,
            "python_two_log_step_mean_ms": phase3_python_ms,
            "numpy_two_log_step_mean_ms": phase3_numpy_ms,
            "absolute_timing_accepted": False,
            "timing_exclusion_reason": (
                "omni.kit.debug.python remained active and both timings were "
                "more than an order of magnitude above the controlled microbenchmark"
            ),
            "python_runner_seconds": python_summary["runner_wall_seconds"],
            "numpy_runner_seconds": numpy_summary["runner_wall_seconds"],
            "python_metrics_csv_sha256": python_csv_sha256,
            "numpy_metrics_csv_sha256": numpy_csv_sha256,
        },
        "decision": {
            "default_backend": "python",
            "numpy_backend_available": True,
            "numpy_default_adoption": False,
            "reason": (
                f"controlled gain is {improvement * 100.0:.1f}%; retain opt-in "
                "until a debugger-free end-to-end profile confirms the gain"
            ),
        },
    }


def render_svg(report: dict) -> str:
    micro = report["microbenchmark"]
    trial = report["phase3_trial"]
    gain = micro["numpy_improvement_fraction"] * 100.0
    python_ms = micro["python_median_ms_per_model_step"]
    numpy_ms = micro["numpy_median_ms_per_model_step"]
    python_width = 420.0
    numpy_width = python_width * numpy_ms / python_ms
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6W complete wood-step NumPy prototype</title>
  <desc id="desc">A controlled benchmark shows a {gain:.1f} percent NumPy improvement with exact state, history, and metrics. Phase 3 outputs also match, but its timing is excluded because the Python debugger remained active. Python stays the default.</desc>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#101827"/><stop offset="1" stop-color="#07131a"/></linearGradient>
    <filter id="shadow"><feDropShadow dx="0" dy="12" stdDeviation="16" flood-opacity=".28"/></filter>
  </defs>
  <rect width="1200" height="680" rx="30" fill="url(#bg)"/>
  <circle cx="1100" cy="45" r="130" fill="#38bdf8" opacity=".06"/>
  <text x="64" y="68" fill="#38bdf8" font-family="Segoe UI,sans-serif" font-size="18" font-weight="700" letter-spacing="2">PHASE 6W · COMPLETE WOOD STEP</text>
  <text x="64" y="112" fill="#f8fafc" font-family="Segoe UI,sans-serif" font-size="36" font-weight="750">NumPy helps — keep it opt-in</text>
  <text x="64" y="143" fill="#94a3b8" font-family="Segoe UI,sans-serif" font-size="17">Conduction · sensible heat · evaporation · pyrolysis · char oxidation · final state</text>

  <g filter="url(#shadow)"><rect x="64" y="184" width="670" height="320" rx="22" fill="#152133" stroke="#334155"/><rect x="766" y="184" width="370" height="320" rx="22" fill="#10231f" stroke="#166534"/></g>
  <text x="96" y="226" fill="#cbd5e1" font-family="Segoe UI,sans-serif" font-size="15" font-weight="700" letter-spacing="1.5">CONTROLLED KIT PYTHON · 2 × 1,152 CELLS</text>
  <text x="96" y="274" fill="#f8fafc" font-family="Segoe UI,sans-serif" font-size="20" font-weight="700">Python AoS</text>
  <text x="690" y="274" text-anchor="end" fill="#f8fafc" font-family="Segoe UI,sans-serif" font-size="22" font-weight="750">{python_ms:.4f} ms</text>
  <rect x="96" y="292" width="{python_width:.1f}" height="32" rx="16" fill="#64748b"/>
  <text x="96" y="368" fill="#f8fafc" font-family="Segoe UI,sans-serif" font-size="20" font-weight="700">NumPy roundtrip</text>
  <text x="690" y="368" text-anchor="end" fill="#86efac" font-family="Segoe UI,sans-serif" font-size="22" font-weight="750">{numpy_ms:.4f} ms</text>
  <rect x="96" y="386" width="{numpy_width:.1f}" height="32" rx="16" fill="#22c55e"/>
  <text x="96" y="458" fill="#86efac" font-family="Segoe UI,sans-serif" font-size="30" font-weight="750">−{gain:.1f}%</text>
  <text x="214" y="454" fill="#94a3b8" font-family="Segoe UI,sans-serif" font-size="16">400 steps × 3 runs · conversion included</text>

  <text x="798" y="226" fill="#86efac" font-family="Segoe UI,sans-serif" font-size="15" font-weight="700" letter-spacing="1.5">EQUIVALENCE GATES</text>
  <text x="798" y="278" fill="#f8fafc" font-family="Segoe UI,sans-serif" font-size="19" font-weight="700">✓ 400-step state SHA-256</text>
  <text x="798" y="317" fill="#f8fafc" font-family="Segoe UI,sans-serif" font-size="19" font-weight="700">✓ every-step result history</text>
  <text x="798" y="356" fill="#f8fafc" font-family="Segoe UI,sans-serif" font-size="19" font-weight="700">✓ Phase 3 dry / wet state</text>
  <text x="798" y="395" fill="#f8fafc" font-family="Segoe UI,sans-serif" font-size="19" font-weight="700">✓ Phase 3 CSV / ignition / Flow</text>
  <rect x="798" y="432" width="250" height="38" rx="19" fill="#17452a"/>
  <text x="923" y="457" text-anchor="middle" fill="#86efac" font-family="Segoe UI,sans-serif" font-size="15" font-weight="750">EXACT OUTPUT MATCH</text>

  <line x1="64" y1="550" x2="1136" y2="550" stroke="#273449"/>
  <text x="64" y="594" fill="#fdba74" font-family="Segoe UI,sans-serif" font-size="16" font-weight="700">PHASE 3 TIMING EXCLUDED</text>
  <text x="64" y="624" fill="#94a3b8" font-family="Segoe UI,sans-serif" font-size="15">debug extension remained active · {trial['python_two_log_step_mean_ms']:.1f} / {trial['numpy_two_log_step_mean_ms']:.1f} ms are relative diagnostics only</text>
  <text x="1136" y="594" text-anchor="end" fill="#f8fafc" font-family="Segoe UI,sans-serif" font-size="24" font-weight="750">Default: Python</text>
  <text x="1136" y="626" text-anchor="end" fill="#38bdf8" font-family="Segoe UI,sans-serif" font-size="16" font-weight="700">NumPy available by explicit selection</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--python-summary", type=Path, default=DEFAULT_PYTHON_SUMMARY)
    parser.add_argument("--numpy-summary", type=Path, default=DEFAULT_NUMPY_SUMMARY)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--report-svg", type=Path, default=DEFAULT_REPORT_SVG)
    arguments = parser.parse_args()
    report = build_report(
        _load(arguments.benchmark),
        _load(arguments.python_summary),
        _load(arguments.numpy_summary),
    )
    arguments.report_json.parent.mkdir(parents=True, exist_ok=True)
    arguments.report_json.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    arguments.report_svg.write_text(render_svg(report) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
