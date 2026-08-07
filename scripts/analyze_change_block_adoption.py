"""Analyze Phase 6BN ChangeBlock performance without notice telemetry."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "devlog" / "assets" / "phase6"
DEFAULT_NOTICE_REPORT = ASSETS / "resident_change_block_report.json"
DEFAULT_REPORT = ASSETS / "change_block_adoption_report.json"
DEFAULT_SVG = ASSETS / "change_block_adoption_report.svg"


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _timing(summary, name):
    return float(summary["timing"]["segments"][name]["p95_ms"])


def _equivalence(control, candidate):
    checks = {
        "dry_authoritative_sha256": (
            control["wood"]["dry"]["authoritative_state_sha256"]
            == candidate["wood"]["dry"]["authoritative_state_sha256"]
        ),
        "wet_authoritative_sha256": (
            control["wood"]["wet"]["authoritative_state_sha256"]
            == candidate["wood"]["wet"]["authoritative_state_sha256"]
        ),
        "metrics_csv_sha256": control["metrics_csv_sha256"] == candidate["metrics_csv_sha256"],
        "ignition": (
            control["wood"]["dry"]["ignition_seconds"]
            == candidate["wood"]["dry"]["ignition_seconds"]
            and control["wood"]["wet"]["ignition_seconds"]
            == candidate["wood"]["wet"]["ignition_seconds"]
        ),
        "final_usd_state": (
            control["scenario"]["resident_snapshot_adapter"]["final_usd_state"]
            == candidate["scenario"]["resident_snapshot_adapter"]["final_usd_state"]
        ),
    }
    _require(all(checks.values()), "Trackless ChangeBlock candidate changed output")
    return checks


def analyze(run_root, run_count, notice_report_path):
    notice_report = _load(notice_report_path)
    _require(notice_report["status"] == "qualified", "Phase 6BM notice contract is not qualified")
    _require(
        notice_report["notice_contract"]["exactly_one_notice_per_publication"],
        "Phase 6BM did not prove one notice per revision",
    )
    _require(
        notice_report["failure_contract"]["one_old_revision_notice"],
        "Phase 6BM failure contract is incomplete",
    )

    pairs = []
    for index in range(1, run_count + 1):
        control = _load(run_root / f"control-{index:02d}" / "summary.json")
        candidate = _load(run_root / f"change-block-{index:02d}" / "summary.json")
        for label, summary, coalescing in (
            ("control", control, False),
            ("candidate", candidate, True),
        ):
            _require(summary["status"] == "ok", f"{label} Phase 3 run failed")
            adapter = summary["scenario"]["resident_snapshot_adapter"]
            status = adapter["status_after_timeline_stop"]
            _require(adapter["native_producer_connected"], "Native producer missing")
            _require(not adapter["lightweight_notice_tracking_enabled"], "Notice telemetry was enabled")
            _require(
                adapter["lightweight_notice_coalescing_enabled"] is coalescing,
                "Unexpected coalescing mode",
            )
            _require(status["revision"] == 1200, "Resident revision mismatch")
            _require(status["lightweight_notice_count"] == 0, "Trackless run recorded notices")
            _require(adapter["final_usd_state"]["revision_consistent"], "Final USD revisions differ")
            _require(summary["flow"]["active_blocks_peak"] > 0, "Flow was inactive")
        equivalence = _equivalence(control, candidate)
        pairs.append(
            {
                "pair": index,
                "order": ["control", "change_block"] if index % 2 else ["change_block", "control"],
                "equivalence": equivalence,
                "control": {
                    "usd_p95_ms": _timing(control, "resident_snapshot_transaction"),
                    "flow_render_p95_ms": _timing(control, "kit_flow_render_update"),
                    "flow_active_blocks_peak": control["flow"]["active_blocks_peak"],
                },
                "change_block": {
                    "usd_p95_ms": _timing(candidate, "resident_snapshot_transaction"),
                    "flow_render_p95_ms": _timing(candidate, "kit_flow_render_update"),
                    "flow_active_blocks_peak": candidate["flow"]["active_blocks_peak"],
                },
            }
        )

    control_p95 = [pair["control"]["usd_p95_ms"] for pair in pairs]
    candidate_p95 = [pair["change_block"]["usd_p95_ms"] for pair in pairs]
    pair_improvements = [
        control_value - candidate_value
        for control_value, candidate_value in zip(control_p95, candidate_p95)
    ]
    exact = all(all(pair["equivalence"].values()) for pair in pairs)
    all_improved = all(value > 0.0 for value in pair_improvements)
    below_gate = all(value < 4.0 for value in candidate_p95)
    adoption_qualified = exact and all_improved and below_gate
    return {
        "schema_version": 1,
        "phase": "phase6bn",
        "status": "adoption_qualified" if adoption_qualified else "adoption_deferred",
        "measurement": {
            "pairs": run_count,
            "balanced_order": True,
            "steps_per_run": 1200,
            "published_revisions_per_run": 240,
            "notice_tracking_enabled": False,
            "resident_native_producer": True,
            "production_default_enabled": False,
        },
        "prior_contract": {
            "phase6bm_status": notice_report["status"],
            "one_notice_per_publication": True,
            "revision_last_failure_replay": True,
        },
        "equivalence": {"all_pairs_exact": exact},
        "performance": {
            "control_p95_ms": control_p95,
            "change_block_p95_ms": candidate_p95,
            "pair_reduction_ms": pair_improvements,
            "median_control_p95_ms": statistics.median(control_p95),
            "median_change_block_p95_ms": statistics.median(candidate_p95),
            "median_p95_reduction_ms": statistics.median(control_p95) - statistics.median(candidate_p95),
            "all_pairs_improved": all_improved,
            "all_change_block_runs_below_4ms": below_gate,
        },
        "flow": {
            "active_in_all_runs": all(
                pair[mode]["flow_active_blocks_peak"] > 0
                for pair in pairs
                for mode in ("control", "change_block")
            ),
            "control_active_blocks_peak": [pair["control"]["flow_active_blocks_peak"] for pair in pairs],
            "change_block_active_blocks_peak": [pair["change_block"]["flow_active_blocks_peak"] for pair in pairs],
        },
        "pairs": pairs,
        "decision": {
            "standardize_for_lightweight_path": adoption_qualified,
            "keep_global_production_default_off": True,
            "retain_explicit_disable_escape_hatch": True,
            "reason": (
                "Notice and failure contracts are qualified by Phase 6BM; trackless real-Flow runs must improve every pair and remain below 4 ms."
            ),
        },
    }


def render_svg(report):
    performance = report["performance"]
    control = " / ".join(f"{value:.4f}" for value in performance["control_p95_ms"])
    candidate = " / ".join(f"{value:.4f}" for value in performance["change_block_p95_ms"])
    reductions = " / ".join(f"{value:.4f}" for value in performance["pair_reduction_ms"])
    decision = "ADOPTION QUALIFIED" if report["decision"]["standardize_for_lightweight_path"] else "ADOPTION DEFERRED"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6BN trackless ChangeBlock adoption audit</title>
  <desc id="desc">Real Flow and resident native producer compare ChangeBlock with control after notice telemetry is removed.</desc>
  <rect width="1200" height="680" rx="32" fill="#111820"/>
  <text x="70" y="76" fill="#f4b860" font-family="Segoe UI, sans-serif" font-size="24" font-weight="700">PHASE 6BN · TRACKLESS ADOPTION AUDIT</text>
  <text x="70" y="126" fill="#fff" font-family="Segoe UI, sans-serif" font-size="37" font-weight="700">Measure the boundary without the measuring listener</text>
  <rect x="70" y="170" width="1060" height="112" rx="20" fill="#192734" stroke="#315269"/>
  <text x="105" y="214" fill="#a8beca" font-family="Consolas, monospace" font-size="18">control p95     {control} ms</text>
  <text x="105" y="250" fill="#f4b860" font-family="Consolas, monospace" font-size="18">ChangeBlock p95 {candidate} ms</text>
  <rect x="70" y="322" width="1060" height="172" rx="20" fill="#182128"/>
  <text x="105" y="367" fill="#fff" font-family="Segoe UI, sans-serif" font-size="23" font-weight="700">Paired reduction · exact authoritative outputs</text>
  <text x="105" y="412" fill="#65c18c" font-family="Consolas, monospace" font-size="19">Δ p95  {reductions} ms</text>
  <text x="105" y="452" fill="#d7e1e8" font-family="Segoe UI, sans-serif" font-size="17">Phase 6BM: one notice / revision · revision-last failure replays one old revision</text>
  <rect x="70" y="535" width="1060" height="90" rx="20" fill="#173526" stroke="#65c18c"/>
  <text x="105" y="580" fill="#65c18c" font-family="Segoe UI, sans-serif" font-size="23" font-weight="700">{decision} · every pair faster · all p95 below 4 ms</text>
  <text x="105" y="607" fill="#d7e1e8" font-family="Segoe UI, sans-serif" font-size="16">global default stays OFF · retain explicit disable escape hatch</text>
</svg>
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--notice-report", type=Path, default=DEFAULT_NOTICE_REPORT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    report = analyze(arguments.run_root, arguments.runs, arguments.notice_report)
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    arguments.svg.write_text(render_svg(report), encoding="utf-8")
    if report["status"] != "adoption_qualified":
        raise RuntimeError("Phase 6BN did not qualify ChangeBlock adoption")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
