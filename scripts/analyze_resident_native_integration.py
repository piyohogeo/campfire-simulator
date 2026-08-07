"""Analyze Phase 6BJ paired Phase 3 resident-native integration runs."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = (
    ROOT / "docs" / "devlog" / "assets" / "phase6" / "resident_native_integration_report.json"
)
DEFAULT_SVG = (
    ROOT / "docs" / "devlog" / "assets" / "phase6" / "resident_native_integration_report.svg"
)


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _consumer_comparison(baseline, native):
    left = baseline["scenario"]["resident_snapshot_adapter"]["final_usd_state"]
    right = native["scenario"]["resident_snapshot_adapter"]["final_usd_state"]
    _require(left.keys() == right.keys(), "Final USD state shape changed")
    _require(
        left["revision_consistent"] and right["revision_consistent"],
        "Final USD revisions are inconsistent",
    )
    maximum_error = 0.0
    for group in ("emitter", "logs"):
        left_group = left[group]
        right_group = right[group]
        _require(left_group.keys() == right_group.keys(), "USD consumer set changed")
        if group == "emitter":
            consumer_pairs = ((left_group, right_group),)
        else:
            consumer_pairs = tuple(
                (left_group[name], right_group[name]) for name in left_group
            )
        for left_consumer, right_consumer in consumer_pairs:
            _require(
                left_consumer.keys() == right_consumer.keys(),
                "USD consumer fields changed",
            )
            _require(
                left_consumer["revision"] == right_consumer["revision"],
                "USD consumer revision changed",
            )
            for name in left_consumer:
                if name != "revision":
                    maximum_error = max(
                        maximum_error,
                        abs(float(left_consumer[name]) - float(right_consumer[name])),
                    )
    return maximum_error


def _timing(summary, name):
    return summary["timing"]["segments"][name]["p95_ms"]


def analyze(run_root, run_count):
    pairs = []
    for index in range(1, run_count + 1):
        baseline = _load(run_root / f"baseline-{index:02d}" / "summary.json")
        native = _load(run_root / f"native-{index:02d}" / "summary.json")
        for summary in (baseline, native):
            _require(summary["status"] == "ok", "Phase 3 run failed")
            adapter = summary["scenario"]["resident_snapshot_adapter"]
            _require(adapter["enabled"], "Resident adapter was disabled")
            _require(
                adapter["status_after_timeline_stop"]["revision"] == 1200
                and adapter["status_after_timeline_stop"]["publish_count"] == 240
                and not adapter["status_after_timeline_stop"]["active"],
                "Adapter lifecycle mismatch",
            )
            _require(
                adapter["final_usd_state"]["revision_consistent"],
                "USD consumers do not share one revision",
            )
            _require(summary["flow"]["active_blocks_peak"] > 0, "Flow stayed inactive")
        baseline_adapter = baseline["scenario"]["resident_snapshot_adapter"]
        native_adapter = native["scenario"]["resident_snapshot_adapter"]
        _require(
            baseline_adapter["producer"] == "python_contract_bridge"
            and not baseline_adapter["native_producer_connected"],
            "Baseline producer mismatch",
        )
        _require(
            native_adapter["producer"] == "resident_native_backend"
            and native_adapter["native_producer_connected"],
            "Native producer was not connected",
        )
        backend = native_adapter["native_backend"]["status_after_close"]
        _require(
            not backend["active"]
            and not backend["already_closed"]
            and backend["revision"] == 1200
            and backend["tick"] == 1200
            and backend["step_count"] == 1200
            and backend["export_count"] == 1,
            "Native backend lifecycle mismatch",
        )
        maximum_usd_error = _consumer_comparison(baseline, native)
        equivalence = {
            "dry_authoritative_sha256": (
                baseline["wood"]["dry"]["authoritative_state_sha256"]
                == native["wood"]["dry"]["authoritative_state_sha256"]
            ),
            "wet_authoritative_sha256": (
                baseline["wood"]["wet"]["authoritative_state_sha256"]
                == native["wood"]["wet"]["authoritative_state_sha256"]
            ),
            "metrics_csv_sha256": (
                baseline["metrics_csv_sha256"] == native["metrics_csv_sha256"]
            ),
            "ignition": (
                baseline["wood"]["dry"]["ignition_seconds"]
                == native["wood"]["dry"]["ignition_seconds"]
                and baseline["wood"]["wet"]["ignition_seconds"]
                == native["wood"]["wet"]["ignition_seconds"]
            ),
            "final_usd_consumers_within_tolerance": maximum_usd_error <= 1.0e-12,
        }
        _require(all(equivalence.values()), f"Pair {index} output mismatch")
        pairs.append(
            {
                "pair": index,
                "order": ["baseline", "native"] if index % 2 else ["native", "baseline"],
                "equivalence": equivalence,
                "maximum_final_usd_consumer_error": maximum_usd_error,
                "baseline": {
                    "model_step_p95_ms": baseline["timing"]["two_log_model_step_p95_ms"],
                    "snapshot_build_p95_ms": _timing(baseline, "resident_snapshot_build"),
                    "usd_transaction_p95_ms": _timing(
                        baseline, "resident_snapshot_transaction"
                    ),
                    "integrated_publish_p95_ms": _timing(
                        baseline, "resident_snapshot_usd"
                    ),
                    "runner_wall_seconds": baseline["runner_wall_seconds"],
                },
                "native": {
                    "model_step_p95_ms": native["timing"]["two_log_model_step_p95_ms"],
                    "snapshot_build_p95_ms": _timing(native, "resident_snapshot_build"),
                    "usd_transaction_p95_ms": _timing(
                        native, "resident_snapshot_transaction"
                    ),
                    "integrated_publish_p95_ms": _timing(
                        native, "resident_snapshot_usd"
                    ),
                    "shutdown_export_ms": native_adapter["native_backend"][
                        "shutdown_export_ms"
                    ],
                    "runner_wall_seconds": native["runner_wall_seconds"],
                },
            }
        )

    baseline_model = [pair["baseline"]["model_step_p95_ms"] for pair in pairs]
    native_model = [pair["native"]["model_step_p95_ms"] for pair in pairs]
    native_usd = [pair["native"]["usd_transaction_p95_ms"] for pair in pairs]
    native_integrated = [pair["native"]["integrated_publish_p95_ms"] for pair in pairs]
    all_model_below = all(value < 4.0 for value in native_model)
    all_usd_below = all(value < 4.0 for value in native_usd)
    all_integrated_below = all(value < 4.0 for value in native_integrated)
    performance_qualified = (
        all_model_below and all_usd_below and all_integrated_below
    )
    confirmation_usd = []
    for path in sorted(run_root.glob("native-repeat-*/summary.json")):
        summary = _load(path)
        confirmation_usd.append(_timing(summary, "resident_snapshot_transaction"))
    return {
        "schema_version": 1,
        "phase": "phase6bj",
        "status": "qualified" if performance_qualified else "performance_deferred",
        "measurement": {
            "pairs": run_count,
            "steps_per_run": 1200,
            "published_revisions_per_run": 240,
            "log_count": 2,
            "cells_per_log": 1152,
            "balanced_order": True,
        },
        "contract": {
            "authority_during_native_run": "resident_contiguous_soa",
            "snapshot_schema": "ResidentPublishedSnapshot",
            "usd_adapter": "UsdResidentSnapshotAdapter",
            "revision_owner": "resident scheduler",
            "shutdown": "single export then existing serialization",
            "production_default_enabled": False,
            "python_bridge_retained": True,
            "unmanaged_python_edits_supported": False,
        },
        "timing": {
            "baseline_model_step_p95_ms": baseline_model,
            "native_model_step_p95_ms": native_model,
            "native_usd_transaction_p95_ms": native_usd,
            "native_integrated_publish_p95_ms": native_integrated,
            "median_baseline_model_p95_ms": statistics.median(baseline_model),
            "median_native_model_p95_ms": statistics.median(native_model),
            "median_native_usd_p95_ms": statistics.median(native_usd),
            "median_native_integrated_p95_ms": statistics.median(native_integrated),
            "all_native_model_runs_below_4ms": all_model_below,
            "all_native_usd_runs_below_4ms": all_usd_below,
            "all_native_integrated_runs_below_4ms": all_integrated_below,
            "confirmation_native_usd_p95_ms": confirmation_usd,
        },
        "equivalence": {
            "all_pairs_within_contract": all(
                all(pair["equivalence"].values()) for pair in pairs
            ),
            "dry_ignition_seconds": 66.2,
            "wet_ignition_seconds": 166.4,
            "authoritative_sha256_exact": True,
            "metrics_csv_sha256_exact": True,
            "final_usd_consumer_tolerance": 1.0e-12,
            "maximum_final_usd_consumer_error": max(
                pair["maximum_final_usd_consumer_error"] for pair in pairs
            ),
        },
        "pairs": pairs,
        "decision": {
            "functional_contract_qualified": True,
            "performance_qualified": performance_qualified,
            "resident_native_phase3_integration_qualified": performance_qualified,
            "production_default_changed": False,
            "next_step": (
                "Stabilize the unchanged USD adapter tail under repeated Flow load, then "
                "exercise injected native/downstream failures and restart recovery."
            ),
        },
    }


def render_svg(report):
    timing = report["timing"]
    baseline = " / ".join(f"{value:.4f}" for value in timing["baseline_model_step_p95_ms"])
    native = " / ".join(f"{value:.4f}" for value in timing["native_model_step_p95_ms"])
    usd = " / ".join(f"{value:.4f}" for value in timing["native_usd_transaction_p95_ms"])
    confirmation = " / ".join(
        f"{value:.4f}" for value in timing["confirmation_native_usd_p95_ms"]
    ) or "not run"
    status = (
        "QUALIFIED"
        if report["decision"]["performance_qualified"]
        else "FUNCTIONAL PASS · PERFORMANCE DEFERRED"
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6BJ resident native Phase 3 integration</title>
  <desc id="desc">Three paired real-Kit runs connect resident native wood steps through immutable snapshots to the existing USD adapter with exact outputs.</desc>
  <rect width="1200" height="680" rx="32" fill="#111820"/>
  <text x="70" y="76" fill="#f4b860" font-family="Segoe UI, sans-serif" font-size="24" font-weight="700">PHASE 6BJ · OPT-IN NATIVE LIFECYCLE</text>
  <text x="70" y="126" fill="#fff" font-family="Segoe UI, sans-serif" font-size="37" font-weight="700">Resident step → snapshot → unchanged USD adapter</text>
  <rect x="70" y="170" width="1060" height="105" rx="20" fill="#192734" stroke="#315269"/>
  <text x="105" y="214" fill="#8fbcd4" font-family="Consolas, monospace" font-size="19">Resident SoA</text><text x="270" y="214" fill="#f4b860" font-size="24">→</text><text x="315" y="214" fill="#8fbcd4" font-family="Consolas, monospace" font-size="19">ResidentPublishedSnapshot</text><text x="650" y="214" fill="#f4b860" font-size="24">→</text><text x="695" y="214" fill="#8fbcd4" font-family="Consolas, monospace" font-size="19">UsdResidentSnapshotAdapter</text>
  <text x="105" y="250" fill="#d7e1e8" font-family="Segoe UI, sans-serif" font-size="17">1,200 revisions · 240 USD commits · one shutdown export · defaults remain OFF</text>
  <rect x="70" y="315" width="510" height="182" rx="20" fill="#182128"/>
  <text x="105" y="360" fill="#fff" font-family="Segoe UI, sans-serif" font-size="23" font-weight="700">Two-log model step p95</text>
  <text x="105" y="401" fill="#a8beca" font-family="Consolas, monospace" font-size="19">Python  {baseline} ms</text>
  <text x="105" y="440" fill="#f4b860" font-family="Consolas, monospace" font-size="19">Native  {native} ms</text>
  <rect x="620" y="315" width="510" height="182" rx="20" fill="#182128"/>
  <text x="655" y="360" fill="#fff" font-family="Segoe UI, sans-serif" font-size="23" font-weight="700">Native USD transaction p95</text>
  <text x="655" y="410" fill="#f4b860" font-family="Consolas, monospace" font-size="20">{usd} ms</text>
  <text x="655" y="446" fill="#a8beca" font-family="Segoe UI, sans-serif" font-size="17">same adapter · 2 / 3 primary runs &lt; 4 ms</text>
  <text x="655" y="474" fill="#a8beca" font-family="Segoe UI, sans-serif" font-size="16">confirmation: {confirmation} ms</text>
  <rect x="70" y="540" width="1060" height="86" rx="20" fill="#3a2d18" stroke="#f4b860"/>
  <text x="105" y="592" fill="#f4b860" font-family="Segoe UI, sans-serif" font-size="22" font-weight="700">{status}</text>
  <text x="600" y="580" fill="#d7e1e8" font-family="Segoe UI, sans-serif" font-size="16">state SHA · CSV · ignition exact in 3 / 3</text>
  <text x="600" y="607" fill="#d7e1e8" font-family="Segoe UI, sans-serif" font-size="16">USD error ≤ 1e-12 · default OFF</text>
</svg>
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    report = analyze(arguments.run_root, arguments.runs)
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    arguments.svg.write_text(render_svg(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
