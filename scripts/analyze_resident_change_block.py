"""Analyze the Phase 6BM real-Flow Sdf.ChangeBlock candidate."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "devlog" / "assets" / "phase6"
DEFAULT_REPORT = ASSETS / "resident_change_block_report.json"
DEFAULT_SVG = ASSETS / "resident_change_block_report.svg"


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _p95(summary):
    return float(
        summary["timing"]["segments"]["resident_snapshot_transaction"]["p95_ms"]
    )


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
        "metrics_csv_sha256": (
            control["metrics_csv_sha256"] == candidate["metrics_csv_sha256"]
        ),
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
    _require(all(checks.values()), "ChangeBlock candidate changed authoritative output")
    return checks


def _notice_status(summary):
    return summary["scenario"]["resident_snapshot_adapter"][
        "status_after_timeline_stop"
    ]


def analyze(run_root, run_count):
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
            status = _notice_status(summary)
            _require(adapter["native_producer_connected"], "Native producer missing")
            _require(adapter["lightweight_notice_tracking_enabled"], "Notice tracking missing")
            _require(
                adapter["lightweight_notice_coalescing_enabled"] is coalescing,
                "Unexpected coalescing mode",
            )
            _require(status["revision"] == 1200, "Resident revision mismatch")
            _require(status["lightweight_notice_publication_count"] == 239, "Publication count mismatch")
            _require(status["lightweight_notice_accepted_revision_count"] == 239, "Accepted revision count mismatch")
            _require(
                status["lightweight_notice_count"]
                == status["lightweight_notice_accepted_revision_count"]
                + status["lightweight_notice_rejected_count"],
                "Notice disposition mismatch",
            )
            _require(
                adapter["final_usd_state"]["revision_consistent"],
                "Final USD revisions are inconsistent",
            )
            _require(summary["flow"]["active_blocks_peak"] > 0, "Flow was inactive")
        control_status = _notice_status(control)
        candidate_status = _notice_status(candidate)
        _require(
            control_status["lightweight_notice_count"]
            == control_status["lightweight_write_count"],
            "Control notice count did not match USD writes",
        )
        _require(
            control_status["lightweight_notice_rejected_count"] > 0,
            "Control exposed no precommit notices",
        )
        _require(
            candidate_status["lightweight_notice_count"] == 239
            and candidate_status["lightweight_notice_rejected_count"] == 0
            and candidate_status["lightweight_notices_per_publication_minimum"] == 1
            and candidate_status["lightweight_notices_per_publication_maximum"] == 1,
            "Candidate did not emit exactly one accepted notice per publication",
        )
        pairs.append(
            {
                "pair": index,
                "order": ["control", "change_block"] if index % 2 else ["change_block", "control"],
                "equivalence": _equivalence(control, candidate),
                "control": {
                    "usd_p95_ms": _p95(control),
                    "notice_count": control_status["lightweight_notice_count"],
                    "accepted_revision_count": control_status["lightweight_notice_accepted_revision_count"],
                    "rejected_notice_count": control_status["lightweight_notice_rejected_count"],
                    "write_count": control_status["lightweight_write_count"],
                    "flow_active_blocks_peak": control["flow"]["active_blocks_peak"],
                },
                "change_block": {
                    "usd_p95_ms": _p95(candidate),
                    "notice_count": candidate_status["lightweight_notice_count"],
                    "accepted_revision_count": candidate_status["lightweight_notice_accepted_revision_count"],
                    "rejected_notice_count": candidate_status["lightweight_notice_rejected_count"],
                    "write_count": candidate_status["lightweight_write_count"],
                    "flow_active_blocks_peak": candidate["flow"]["active_blocks_peak"],
                },
            }
        )

    control_p95 = [pair["control"]["usd_p95_ms"] for pair in pairs]
    candidate_p95 = [pair["change_block"]["usd_p95_ms"] for pair in pairs]
    report = {
        "schema_version": 1,
        "phase": "phase6bm",
        "status": "qualified" if all(value < 4.0 for value in candidate_p95) else "rejected",
        "measurement": {
            "pairs": run_count,
            "balanced_order": True,
            "steps_per_run": 1200,
            "published_revisions_per_run": 240,
            "tracked_lightweight_publications_per_run": 239,
            "revision_gated_notice_tracking": True,
            "production_default_enabled": False,
        },
        "equivalence": {
            "all_pairs_exact": all(all(pair["equivalence"].values()) for pair in pairs)
        },
        "performance": {
            "control_p95_ms": control_p95,
            "change_block_p95_ms": candidate_p95,
            "median_control_p95_ms": statistics.median(control_p95),
            "median_change_block_p95_ms": statistics.median(candidate_p95),
            "median_p95_reduction_ms": statistics.median(control_p95) - statistics.median(candidate_p95),
            "all_change_block_runs_below_4ms": all(value < 4.0 for value in candidate_p95),
        },
        "notice_contract": {
            "control_notice_count": [pair["control"]["notice_count"] for pair in pairs],
            "change_block_notice_count": [pair["change_block"]["notice_count"] for pair in pairs],
            "change_block_accepted_revision_count": [pair["change_block"]["accepted_revision_count"] for pair in pairs],
            "change_block_rejected_notice_count": [pair["change_block"]["rejected_notice_count"] for pair in pairs],
            "exactly_one_notice_per_publication": all(pair["change_block"]["notice_count"] == 239 for pair in pairs),
        },
        "flow": {
            "control_active_blocks_peak": [pair["control"]["flow_active_blocks_peak"] for pair in pairs],
            "change_block_active_blocks_peak": [pair["change_block"]["flow_active_blocks_peak"] for pair in pairs],
            "active_in_all_runs": all(pair[mode]["flow_active_blocks_peak"] > 0 for pair in pairs for mode in ("control", "change_block")),
        },
        "failure_contract": {
            "revision_last_failure_replayed_inside_same_block": True,
            "one_old_revision_notice": True,
            "verified_by": "Kit test_scene revision-last failure injection",
        },
        "pairs": pairs,
        "decision": {
            "candidate_qualified": all(value < 4.0 for value in candidate_p95),
            "production_default_enabled": False,
            "contracts_preserved": [
                "immutable previous snapshot replay",
                "revision-last publication",
                "monotonic lifecycle revision",
                "fault-on-recovery-failure",
                "resident snapshot schema",
            ],
        },
    }
    return report


def render_svg(report):
    performance = report["performance"]
    notices = report["notice_contract"]
    control = " / ".join(str(value) for value in notices["control_notice_count"])
    candidate = " / ".join(str(value) for value in notices["change_block_notice_count"])
    control_p95 = " / ".join(f"{value:.4f}" for value in performance["control_p95_ms"])
    candidate_p95 = " / ".join(f"{value:.4f}" for value in performance["change_block_p95_ms"])
    decision = "QUALIFIED" if report["decision"]["candidate_qualified"] else "REJECTED"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6BM real-Flow resident ChangeBlock candidate</title>
  <desc id="desc">Balanced real-Kit runs compare plain lightweight USD notices with Sdf ChangeBlock notice coalescing.</desc>
  <rect width="1200" height="680" rx="32" fill="#111820"/>
  <text x="70" y="76" fill="#f4b860" font-family="Segoe UI, sans-serif" font-size="24" font-weight="700">PHASE 6BM · REAL FLOW CHANGE BLOCK CANDIDATE</text>
  <text x="70" y="126" fill="#fff" font-family="Segoe UI, sans-serif" font-size="37" font-weight="700">One accepted notice per resident revision</text>
  <rect x="70" y="170" width="1060" height="112" rx="20" fill="#192734" stroke="#315269"/>
  <text x="105" y="214" fill="#8fbcd4" font-family="Consolas, monospace" font-size="18">control notices  {control}</text>
  <text x="105" y="250" fill="#65c18c" font-family="Consolas, monospace" font-size="18">ChangeBlock      {candidate} · 239 accepted · 0 rejected</text>
  <rect x="70" y="322" width="1060" height="172" rx="20" fill="#182128"/>
  <text x="105" y="367" fill="#fff" font-family="Segoe UI, sans-serif" font-size="23" font-weight="700">Resident USD publication p95 · revision-gated listener enabled</text>
  <text x="105" y="412" fill="#a8beca" font-family="Consolas, monospace" font-size="18">control     {control_p95} ms</text>
  <text x="105" y="452" fill="#f4b860" font-family="Consolas, monospace" font-size="18">ChangeBlock {candidate_p95} ms</text>
  <rect x="70" y="535" width="1060" height="90" rx="20" fill="#173526" stroke="#65c18c"/>
  <text x="105" y="580" fill="#65c18c" font-family="Segoe UI, sans-serif" font-size="23" font-weight="700">{decision} · exact state / CSV / ignition / final USD · Flow active</text>
  <text x="105" y="607" fill="#d7e1e8" font-family="Segoe UI, sans-serif" font-size="16">default OFF · same-block immutable replay · revision-last and fault lifecycle retained</text>
</svg>
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    report = analyze(arguments.run_root, arguments.runs)
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    arguments.svg.write_text(render_svg(report), encoding="utf-8")
    if report["status"] != "qualified":
        raise RuntimeError("Phase 6BM candidate missed the 4 ms gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
