"""Render the compact Phase 6ET devlog chart from its machine report."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


GIB = 1024 ** 3


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    rows = {row["condition"]: row for row in report["rows"]}
    a = rows["A_flow_only"]
    b = rows["B_minimal_fuel"]
    limit = 14.0
    values = [
        ("A · Flow only", a["kit_peak_gib"], "#4ade80"),
        ("B · public fuel readback", b["kit_peak_gib"], "#fb7185"),
        ("6ES root 1", report["baseline_read_only"]["phase6es_root1_failed_peak_gib"], "#f59e0b"),
        ("6ES root 2", report["baseline_read_only"]["phase6es_root2_failed_peak_gib"], "#f97316"),
    ]
    width, height = 1200, 680
    left, chart_top, chart_width, chart_height = 275, 185, 825, 270
    maximum = 16.0
    bars = []
    for index, (label, value, color) in enumerate(values):
        y = chart_top + index * 62
        bar_width = chart_width * value / maximum
        bars.append(
            f'<text x="{left - 18}" y="{y + 25}" text-anchor="end" class="label">{html.escape(label)}</text>'
            f'<rect x="{left}" y="{y}" width="{bar_width:.1f}" height="34" rx="8" fill="{color}"/>'
            f'<text x="{left + bar_width + 12:.1f}" y="{y + 24}" class="value">{value:.3f} GiB</text>'
        )
    limit_x = left + chart_width * limit / maximum
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<style>.title{{font:700 34px system-ui;fill:#f8fafc}}.sub{{font:18px system-ui;fill:#cbd5e1}}.label{{font:17px system-ui;fill:#e2e8f0}}.value{{font:700 17px ui-monospace,monospace;fill:#f8fafc}}.small{{font:16px system-ui;fill:#cbd5e1}}.strong{{font:700 18px system-ui;fill:#f8fafc}}</style>
<rect width="1200" height="680" rx="28" fill="#101827"/>
<text x="70" y="70" class="title">Phase 6ET · Four-log Kit memory boundary</text>
<text x="70" y="108" class="sub">Phase 6ES remains frozen · unchanged 14 GiB Kit guard · new artifact root</text>
<line x1="{limit_x:.1f}" y1="155" x2="{limit_x:.1f}" y2="465" stroke="#fda4af" stroke-width="3" stroke-dasharray="10 8"/>
<text x="{limit_x - 10:.1f}" y="150" text-anchor="end" class="small">fixed limit 14.000 GiB</text>
{''.join(bars)}
<rect x="70" y="500" width="1060" height="125" rx="18" fill="#1e293b"/>
<text x="95" y="536" class="strong">Safe stop at B · 1 / 21 normal-exit calibration processes</text>
<text x="95" y="569" class="small">A: no readback, peak at timeline sampling; active blocks 505 → 1329 → 1251.</text>
<text x="95" y="599" class="small">B: 32.86 MB selected fuel buffer at frame 90; Kit peak 14.271 GiB. Raw JSON 9.5 KB, NPZ 0.</text>
<text x="70" y="655" class="small">Conclusion: high four-log Flow baseline + first public readback boundary; transport aggregation and temperature/smoke collectors were not reached.</text>
</svg>'''
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
