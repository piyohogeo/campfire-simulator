"""Validate and visualize the Phase 6BI native snapshot connection."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = (
    ROOT / "docs" / "devlog" / "assets" / "phase6" / "native_snapshot_connection_report.json"
)
DEFAULT_SVG = (
    ROOT / "docs" / "devlog" / "assets" / "phase6" / "native_snapshot_connection_report.svg"
)


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


def analyze(raw):
    _require(raw.get("schema_version") == 1, "Unexpected raw schema")
    _require(raw.get("phase") == "phase6bi", "Unexpected phase")
    _require(raw.get("status") == "ok", "Benchmark did not finish")
    runs = raw.get("runs", [])
    _require(len(runs) >= 3, "At least three runs are required")
    contract = raw["contract"]
    _require(
        contract["source"] == "resident_native_contiguous_output"
        and contract["destination"] == "ResidentPublishedSnapshot",
        "Native source is not connected to the production snapshot schema",
    )
    _require(not contract["python_model_scan_per_snapshot"], "Python model scan returned")
    _require(contract["buffer_copy_at_immutable_boundary"], "Immutable copy missing")
    _require(not contract["producer_owns_revision_state"], "Producer captured revision state")
    _require(contract["resident_scheduler_owns_revision"], "Resident revision ownership changed")
    _require(contract["usd_adapter_remains_commit_authority"], "USD commit authority changed")
    _require(contract["lifecycle_and_rollback_unchanged"], "Lifecycle contract changed")
    _require(not contract["production_default_enabled"], "Candidate enabled globally")

    connection_keys = tuple(runs[0]["connection"])
    for run in runs:
        _require(run["equivalence"]["within_tolerance"], "Native equivalence failed")
        _require(
            run["connection"]["maximum_schema_copy_error"] == 0.0,
            "Snapshot copy changed a native output",
        )
        for key in connection_keys:
            if key != "maximum_schema_copy_error":
                _require(run["connection"][key], f"Connection gate failed: {key}")

    update_p95 = [
        run["timing"]["native_update_and_schema_freeze"]["p95_ms"] for run in runs
    ]
    freeze_p95 = [run["timing"]["schema_freeze"]["p95_ms"] for run in runs]
    native_p95 = [
        run["timing"]["native_step_and_aggregate"]["p95_ms"] for run in runs
    ]
    update_budget = raw["budget_ms"]["native_update_and_schema_freeze"]
    freeze_budget = raw["budget_ms"]["schema_freeze"]
    all_updates_qualified = all(value < update_budget for value in update_p95)
    all_freezes_qualified = all(value < freeze_budget for value in freeze_p95)
    equivalence = {
        "maximum_temperature_error_k": max(
            run["equivalence"]["maximum_temperature_error_k"] for run in runs
        ),
        "maximum_cell_mass_error_kg": max(
            run["equivalence"]["maximum_cell_mass_error_kg"] for run in runs
        ),
        "phase_mismatch_count": max(
            run["equivalence"]["phase_mismatch_count"] for run in runs
        ),
        "maximum_published_output_error": max(
            run["equivalence"]["maximum_published_output_error"] for run in runs
        ),
        "passed": all(run["equivalence"]["within_tolerance"] for run in runs),
    }
    qualified = all_updates_qualified and all_freezes_qualified and equivalence["passed"]
    return {
        "schema_version": 1,
        "phase": "phase6bi",
        "status": "qualified" if qualified else "not_qualified",
        "source_raw": raw.get("source_raw"),
        "runtime": raw["runtime"],
        "native_toolchain": raw["native_toolchain"],
        "measurement": raw["measurement"],
        "contract": contract,
        "budget_ms": raw["budget_ms"],
        "timing": {
            "native_update_and_schema_freeze_p95_ms": update_p95,
            "schema_freeze_p95_ms": freeze_p95,
            "native_step_and_aggregate_p95_ms": native_p95,
            "median_update_p95_ms": statistics.median(update_p95),
            "median_freeze_p95_ms": statistics.median(freeze_p95),
            "median_native_p95_ms": statistics.median(native_p95),
            "all_update_runs_below_budget": all_updates_qualified,
            "all_freeze_runs_below_budget": all_freezes_qualified,
        },
        "equivalence": equivalence,
        "connection": {
            "maximum_schema_copy_error": 0.0,
            "all_gates_passed": True,
            "gate_names": [
                key for key in connection_keys if key != "maximum_schema_copy_error"
            ],
        },
        "decision": {
            "native_snapshot_connection_qualified": qualified,
            "python_contract_bridge_replaced_in_production": False,
            "production_default_changed": False,
            "usd_publication_bottleneck_changed": False,
            "next_step": (
                "Integrate the qualified producer behind an opt-in resident backend "
                "lifecycle switch, then run the unchanged USD adapter and rollback gates."
            ),
        },
    }


def render_svg(report):
    timing = report["timing"]
    status = "QUALIFIED" if report["status"] == "qualified" else "NOT QUALIFIED"
    update_values = " / ".join(
        f"{value:.4f}" for value in timing["native_update_and_schema_freeze_p95_ms"]
    )
    freeze_values = " / ".join(
        f"{value:.4f}" for value in timing["schema_freeze_p95_ms"]
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6BI resident native snapshot connection</title>
  <desc id="desc">Native contiguous publication values are frozen directly into the existing immutable ResidentPublishedSnapshot schema.</desc>
  <rect width="1200" height="680" rx="32" fill="#111820"/>
  <text x="70" y="78" fill="#f4b860" font-family="Segoe UI, sans-serif" font-size="24" font-weight="700">PHASE 6BI · NATIVE SNAPSHOT CONNECTION</text>
  <text x="70" y="130" fill="#ffffff" font-family="Segoe UI, sans-serif" font-size="38" font-weight="700">Resident SoA output → immutable schema</text>
  <rect x="70" y="175" width="1060" height="118" rx="20" fill="#192734" stroke="#315269"/>
  <text x="105" y="218" fill="#8fbcd4" font-family="Consolas, monospace" font-size="19">C++ double[logs × 11]</text>
  <text x="405" y="218" fill="#f4b860" font-family="Segoe UI, sans-serif" font-size="26">→</text>
  <text x="460" y="218" fill="#8fbcd4" font-family="Consolas, monospace" font-size="19">ResidentNativeSnapshotProducer</text>
  <text x="825" y="218" fill="#f4b860" font-family="Segoe UI, sans-serif" font-size="26">→</text>
  <text x="875" y="218" fill="#8fbcd4" font-family="Consolas, monospace" font-size="19">Snapshot</text>
  <text x="105" y="262" fill="#d7e1e8" font-family="Segoe UI, sans-serif" font-size="18">No Python wood-object scan · one immutable copy · adapter remains commit authority</text>
  <rect x="70" y="330" width="510" height="184" rx="20" fill="#182128"/>
  <text x="105" y="375" fill="#ffffff" font-family="Segoe UI, sans-serif" font-size="24" font-weight="700">20-log update + freeze p95</text>
  <text x="105" y="420" fill="#f4b860" font-family="Consolas, monospace" font-size="23">{update_values} ms</text>
  <text x="105" y="462" fill="#a8beca" font-family="Segoe UI, sans-serif" font-size="18">median {timing['median_update_p95_ms']:.4f} ms · budget &lt; 4 ms</text>
  <rect x="620" y="330" width="510" height="184" rx="20" fill="#182128"/>
  <text x="655" y="375" fill="#ffffff" font-family="Segoe UI, sans-serif" font-size="24" font-weight="700">Schema freeze p95</text>
  <text x="655" y="420" fill="#f4b860" font-family="Consolas, monospace" font-size="23">{freeze_values} ms</text>
  <text x="655" y="462" fill="#a8beca" font-family="Segoe UI, sans-serif" font-size="18">median {timing['median_freeze_p95_ms']:.4f} ms · exact copy</text>
  <rect x="70" y="554" width="1060" height="72" rx="20" fill="#17382d" stroke="#42b883"/>
  <text x="105" y="600" fill="#8ff0bd" font-family="Segoe UI, sans-serif" font-size="27" font-weight="700">{status}</text>
  <text x="310" y="600" fill="#d7e1e8" font-family="Segoe UI, sans-serif" font-size="18">revision/lifecycle/rollback unchanged · production default OFF · USD cost unchanged</text>
</svg>
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    raw = json.loads(arguments.raw.read_text(encoding="utf-8"))
    raw["source_raw"] = str(arguments.raw.resolve())
    report = analyze(raw)
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    arguments.svg.write_text(render_svg(report), encoding="utf-8")
    if report["status"] != "qualified":
        raise RuntimeError("Phase 6BI native snapshot connection did not qualify")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
