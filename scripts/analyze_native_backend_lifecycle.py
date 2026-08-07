"""Validate and visualize the Phase 6BB resident backend lifecycle trial."""

from __future__ import annotations

import argparse
import html
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = ROOT / "docs" / "devlog" / "assets" / "phase6" / "native_backend_lifecycle_report.json"
DEFAULT_SVG = ROOT / "docs" / "devlog" / "assets" / "phase6" / "native_backend_lifecycle_report.svg"
WOOD_BUDGET_MS = 4.0


def _median(raw, path):
    values = []
    for run in raw["runs"]:
        value = run
        for key in path:
            value = value[key]
        values.append(float(value))
    return statistics.median(values), values


def analyze(raw):
    if raw.get("phase") != "phase6bb" or raw.get("status") != "ok":
        raise ValueError("Expected a successful Phase 6BB raw report")
    if len(raw.get("runs", ())) < 3:
        raise ValueError("Phase 6BB requires at least three independent runs")
    if not raw.get("gates") or not all(raw["gates"].values()):
        raise ValueError(f"Lifecycle gates failed: {raw.get('gates')}")
    export_p95, export_p95_runs = _median(
        raw, ("timing", "single_log_export", "p95_ms")
    )
    export_mean, export_mean_runs = _median(
        raw, ("timing", "single_log_export", "mean_ms")
    )
    shutdown, shutdown_runs = _median(
        raw, ("timing", "shutdown_all_log_export_ms")
    )
    decision = {
        "headless_lifecycle_qualified": export_p95 <= WOOD_BUDGET_MS,
        "production_backend_qualified": False,
        "single_log_export_within_4ms": export_p95 <= WOOD_BUDGET_MS,
        "shutdown_export_is_frame_gated": False,
        "next_gate": "opt-in Kit adapter lifecycle and real Flow/USD publish",
    }
    if not decision["headless_lifecycle_qualified"]:
        raise ValueError(f"Single-log export p95 exceeds local budget: {export_p95}")
    return {
        "schema_version": 1,
        "phase": "phase6bb",
        "status": "ok",
        "measurement": raw["measurement"],
        "budget_ms": WOOD_BUDGET_MS,
        "median_of_runs": {
            "single_log_export_mean_ms": export_mean,
            "single_log_export_p95_ms": export_p95,
            "shutdown_all_log_export_ms": shutdown,
        },
        "per_run": {
            "single_log_export_mean_ms": export_mean_runs,
            "single_log_export_p95_ms": export_p95_runs,
            "shutdown_all_log_export_ms": shutdown_runs,
        },
        "gates": raw["gates"],
        "contract": raw["contract"],
        "decision": decision,
    }


def _svg(report):
    p95 = report["median_of_runs"]["single_log_export_p95_ms"]
    mean = report["median_of_runs"]["single_log_export_mean_ms"]
    shutdown = report["median_of_runs"]["shutdown_all_log_export_ms"]
    scale = 500.0 / max(WOOD_BUDGET_MS, p95)
    bar_width = max(3.0, p95 * scale)
    gate_x = 350 + WOOD_BUDGET_MS * scale
    gate_rows = [
        ("SERIALIZE", "exact WoodThermalModel round trip"),
        ("CONFLICT", "stale edit rejected before import"),
        ("ROLLBACK", "managed edit + post-native failure restored"),
        ("REBUILD", "structural candidate validated before swap"),
        ("SHUTDOWN", "20 logs exported; close idempotent"),
    ]
    rows = "".join(
        f'<g transform="translate(0 {index * 42})"><rect x="70" y="430" width="112" height="26" rx="13" class="pass"/><text x="126" y="448" text-anchor="middle" class="tag">{html.escape(tag)}</text><text x="205" y="448" class="small">{html.escape(text)}</text></g>'
        for index, (tag, text) in enumerate(gate_rows)
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680">
<style>
  .bg{{fill:#0d1222}} .panel{{fill:#171f34}} .title{{fill:#f5f7ff;font:700 30px system-ui,sans-serif}}
  .sub{{fill:#a9b4cc;font:16px system-ui,sans-serif}} .label{{fill:#edf1ff;font:600 17px system-ui,sans-serif}}
  .value{{fill:#fff;font:700 17px ui-monospace,monospace}} .small{{fill:#b8c2d9;font:14px system-ui,sans-serif}}
  .bar{{fill:#23c483}} .gate{{stroke:#ffd166;stroke-width:3;stroke-dasharray:8 7}} .gateText{{fill:#ffd166;font:700 14px ui-monospace,monospace}}
  .pass{{fill:#1f9d68}} .tag{{fill:white;font:700 11px system-ui,sans-serif}} .decision{{fill:#ffd166;font:700 19px system-ui,sans-serif}}
</style>
<rect width="1200" height="680" class="bg"/><text x="70" y="68" class="title">Phase 6BB · Resident backend lifecycle contract</text>
<text x="70" y="98" class="sub">20 logs · fresh export before edit/serialization · revision conflict · transactional rollback · rebuild · shutdown</text>
<rect x="55" y="126" width="1090" height="240" rx="18" class="panel"/>
<text x="80" y="169" class="label">Single-log resident → Python export</text>
<rect x="350" y="196" width="{bar_width:.2f}" height="42" rx="21" class="bar"/>
<text x="{370 + bar_width:.2f}" y="223" class="value">p95 {p95:.3f} ms</text>
<text x="350" y="263" class="small">median mean {mean:.3f} ms · 25 samples/run · three independent runs</text>
<line x1="{gate_x:.2f}" y1="180" x2="{gate_x:.2f}" y2="292" class="gate"/><text x="{gate_x + 8:.2f}" y="190" class="gateText">4 ms local gate</text>
<text x="80" y="326" class="label">Shutdown all-log export</text><text x="350" y="326" class="value">{shutdown:.3f} ms</text>
<text x="570" y="326" class="small">explicit shutdown boundary · not charged to a render frame</text>
{rows}
<rect x="55" y="638" width="1090" height="1" fill="#35405b"/><text x="70" y="664" class="decision">HEADLESS LIFECYCLE QUALIFIES; production gate remains closed</text>
<text x="770" y="664" class="small">next: opt-in Kit adapter + real Flow/USD publish</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    raw = json.loads(arguments.raw.read_text(encoding="utf-8"))
    report = analyze(raw)
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
