"""Validate and visualize the Phase 6BC opt-in Kit USD adapter run."""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "devlog" / "assets" / "phase6"
DEFAULT_JSON = ASSETS / "resident_snapshot_adapter_report.json"
DEFAULT_SVG = ASSETS / "resident_snapshot_adapter_report.svg"
LOCAL_BUDGET_MS = 4.0


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _timing(summary, name):
    timing = summary["timing"]["segments"][name]
    _require(timing is not None, f"Missing timing segment: {name}")
    for field in ("mean_ms", "p95_ms", "max_ms"):
        value = float(timing[field])
        _require(math.isfinite(value) and value >= 0.0, f"Invalid {name}.{field}")
    return timing


def analyze(baseline, adapter):
    for name, summary in (("baseline", baseline), ("adapter", adapter)):
        _require(
            summary.get("phase") == "phase3" and summary.get("status") == "ok",
            f"Expected a successful Phase 3 {name} summary",
        )
    baseline_contract = baseline["scenario"]["resident_snapshot_adapter"]
    adapter_contract = adapter["scenario"]["resident_snapshot_adapter"]
    _require(not baseline_contract["enabled"], "Baseline unexpectedly enabled adapter")
    _require(adapter_contract["enabled"], "Candidate did not enable adapter")
    _require(
        adapter_contract["producer"] == "python_contract_bridge"
        and not adapter_contract["native_producer_connected"],
        "Phase 6BC must use the explicit Python bridge without native producer",
    )

    status = adapter_contract["status_after_timeline_stop"]
    lifecycle = {
        "inactive_after_stop": not status["active"],
        "one_start_and_stop": status["start_count"] == status["stop_count"] == 1,
        "all_updates_published": (
            status["publish_count"] == 240 and status["revision"] == 1200
        ),
        "final_revision_consistent": adapter_contract["final_usd_state"][
            "revision_consistent"
        ],
    }
    _require(all(lifecycle.values()), f"Adapter lifecycle failed: {lifecycle}")
    final_revisions = [adapter_contract["final_usd_state"]["emitter"]["revision"]]
    final_revisions.extend(
        value["revision"]
        for value in adapter_contract["final_usd_state"]["logs"].values()
    )
    _require(final_revisions == [1200, 1200, 1200], "Unexpected final revisions")

    exact_outputs = {
        "dry_authoritative_state": (
            baseline["wood"]["dry"]["authoritative_state_sha256"]
            == adapter["wood"]["dry"]["authoritative_state_sha256"]
        ),
        "wet_authoritative_state": (
            baseline["wood"]["wet"]["authoritative_state_sha256"]
            == adapter["wood"]["wet"]["authoritative_state_sha256"]
        ),
        "metrics_csv": baseline["metrics_csv_sha256"] == adapter["metrics_csv_sha256"],
        "ignition_times": (
            baseline["wood"]["dry"]["ignition_seconds"]
            == adapter["wood"]["dry"]["ignition_seconds"]
            and baseline["wood"]["wet"]["ignition_seconds"]
            == adapter["wood"]["wet"]["ignition_seconds"]
        ),
    }
    _require(all(exact_outputs.values()), f"Output equivalence failed: {exact_outputs}")
    _require(
        baseline["flow"]["active_blocks_peak"] > 0
        and adapter["flow"]["active_blocks_peak"] > 0,
        "Flow was not active in both runs",
    )

    adapter_usd = _timing(adapter, "resident_snapshot_usd")
    baseline_emitter = _timing(baseline, "flow_emitter_usd")
    baseline_visual = _timing(baseline, "wood_visual_usd")
    baseline_render = _timing(baseline, "kit_flow_render_update")
    adapter_render = _timing(adapter, "kit_flow_render_update")
    within_local_budget = adapter_usd["p95_ms"] <= LOCAL_BUDGET_MS
    return {
        "schema_version": 1,
        "phase": "phase6bc",
        "status": "ok",
        "measurement": {
            "hardware": "NVIDIA GeForce RTX 3090 / D3D12",
            "scenario": "Phase 3 dry/wet logs, 1200 steps, 240 model seconds",
            "adapter_updates": status["publish_count"],
            "warmup_updates_excluded": adapter_usd["warmup_samples_excluded"],
            "default_enabled": False,
        },
        "lifecycle_gates": lifecycle,
        "exact_output_gates": exact_outputs,
        "final_usd_state": adapter_contract["final_usd_state"],
        "timing_ms": {
            "adapter_snapshot_usd": adapter_usd,
            "legacy_emitter_usd": baseline_emitter,
            "legacy_visual_usd": baseline_visual,
            "adapter_flow_render_update": adapter_render,
            "baseline_flow_render_update": baseline_render,
            "adapter_runner_wall_seconds": adapter["runner_wall_seconds"],
            "baseline_runner_wall_seconds": baseline["runner_wall_seconds"],
        },
        "scenario_results": {
            "dry_ignition_seconds": adapter["wood"]["dry"]["ignition_seconds"],
            "wet_ignition_seconds": adapter["wood"]["wet"]["ignition_seconds"],
            "wet_delay_seconds": adapter["comparison"]["wet_delay_seconds"],
            "adapter_active_blocks_peak": adapter["flow"]["active_blocks_peak"],
            "baseline_active_blocks_peak": baseline["flow"]["active_blocks_peak"],
        },
        "decision": {
            "functional_lifecycle_qualified": True,
            "within_4ms_local_budget": within_local_budget,
            "production_native_backend_qualified": False,
            "keep_default_disabled": True,
            "reason": (
                "Native producer is not connected and integrated USD publish p95 "
                + ("meets" if within_local_budget else "exceeds")
                + " the 4 ms local budget."
            ),
            "next_gate": (
                "reduce transactional USD publish cost below the local budget, then "
                "connect the resident native producer without changing authority schema"
            ),
        },
    }


def _svg(report):
    timing = report["timing_ms"]
    adapter_p95 = timing["adapter_snapshot_usd"]["p95_ms"]
    adapter_mean = timing["adapter_snapshot_usd"]["mean_ms"]
    legacy_emitter = timing["legacy_emitter_usd"]["p95_ms"]
    legacy_visual = timing["legacy_visual_usd"]["p95_ms"]
    scale = 105.0
    gate_x = 300 + LOCAL_BUDGET_MS * scale
    adapter_width = adapter_p95 * scale
    rows = [
        ("REVISION", "Emitter + dry log + wet log = 1200"),
        ("LIFECYCLE", "1 start / 240 publishes / 1 stop / inactive"),
        ("AUTHORITY", "dry SHA + wet SHA + metrics CSV are exact"),
        ("IGNITION", "66.2 s dry / 166.4 s wet / 100.2 s delay"),
    ]
    gate_rows = "".join(
        f'<g transform="translate(0 {index * 43})"><rect x="72" y="423" width="116" height="27" rx="13" class="pass"/><text x="130" y="442" text-anchor="middle" class="tag">{html.escape(tag)}</text><text x="212" y="442" class="small">{html.escape(text)}</text></g>'
        for index, (tag, text) in enumerate(rows)
    )
    budget_label = "PASS" if report["decision"]["within_4ms_local_budget"] else "HOLD"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680">
<style>
 .bg{{fill:#0d1222}} .panel{{fill:#171f34}} .title{{fill:#f5f7ff;font:700 30px system-ui,sans-serif}}
 .sub{{fill:#a9b4cc;font:16px system-ui,sans-serif}} .label{{fill:#edf1ff;font:600 17px system-ui,sans-serif}}
 .value{{fill:#fff;font:700 17px ui-monospace,monospace}} .small{{fill:#b8c2d9;font:14px system-ui,sans-serif}}
 .bar{{fill:#ff8a4c}} .legacy{{fill:#52617f}} .gate{{stroke:#ffd166;stroke-width:3;stroke-dasharray:8 7}}
 .gateText{{fill:#ffd166;font:700 14px ui-monospace,monospace}} .pass{{fill:#1f9d68}}
 .tag{{fill:#fff;font:700 11px system-ui,sans-serif}} .decision{{fill:#ffd166;font:700 19px system-ui,sans-serif}}
</style>
<rect width="1200" height="680" class="bg"/><text x="70" y="68" class="title">Phase 6BC - Opt-in Kit resident snapshot adapter</text>
<text x="70" y="98" class="sub">Real Flow/USD publish - one immutable revision for emitter, visuals, and support diagnostics - default OFF</text>
<rect x="55" y="126" width="1090" height="240" rx="18" class="panel"/>
<text x="80" y="167" class="label">Integrated transactional USD publish p95</text>
<rect x="300" y="188" width="{adapter_width:.2f}" height="40" rx="20" class="bar"/><text x="{320 + adapter_width:.2f}" y="214" class="value">{adapter_p95:.4f} ms</text>
<line x1="{gate_x:.2f}" y1="176" x2="{gate_x:.2f}" y2="244" class="gate"/><text x="{gate_x + 8:.2f}" y="185" class="gateText">4 ms local gate</text>
<text x="300" y="260" class="small">mean {adapter_mean:.4f} ms - 236 measured updates after 4 warmup updates</text>
<text x="80" y="301" class="label">Legacy segments (different cadence)</text><rect x="430" y="281" width="{legacy_emitter * scale:.2f}" height="18" rx="9" class="legacy"/><text x="{445 + legacy_emitter * scale:.2f}" y="295" class="small">emitter p95 {legacy_emitter:.4f} ms</text>
<rect x="430" y="314" width="{legacy_visual * scale:.2f}" height="18" rx="9" class="legacy"/><text x="{445 + legacy_visual * scale:.2f}" y="328" class="small">visual p95 {legacy_visual:.4f} ms</text>
{gate_rows}
<rect x="55" y="625" width="1090" height="1" fill="#35405b"/><text x="70" y="654" class="decision">FUNCTION PASS - PERFORMANCE {budget_label} - DEFAULT OFF</text>
<text x="610" y="654" class="small">next: reduce transactional publish cost, then connect native producer</text>
</svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--adapter", required=True, type=Path)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    baseline = json.loads(arguments.baseline.read_text(encoding="utf-8"))
    adapter = json.loads(arguments.adapter.read_text(encoding="utf-8"))
    report = analyze(baseline, adapter)
    arguments.json.parent.mkdir(parents=True, exist_ok=True)
    arguments.json.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    arguments.svg.write_text(_svg(report) + "\n", encoding="utf-8")
    print(f"Wrote {arguments.json}")
    print(f"Wrote {arguments.svg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
