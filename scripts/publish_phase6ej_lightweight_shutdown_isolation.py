"""Publish a path-sanitized Phase 6EJ devlog report and SVG."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    p0 = source["p0_equivalent"]
    telemetry = source["telemetry_off_on"]
    isolated = source["fixtures"]["results"][0]
    timeout = source["fixtures"]["results"][1]
    report = {
        "schema": "campfire.phase6ej.public-report.v1",
        "phase": "phase6ej",
        "status": source["status"],
        "phase6eg_formal_restarted": False,
        "restart_recommendation": source["restart_recommendation"],
        "isolation_fixture": {
            "helper_peak_private_bytes": isolated["helper_guard"]["peak_private_bytes"],
            "helper_duration_seconds": isolated["helper_guard"]["duration_seconds"],
            "result_persisted": isolated["result_exists"],
            "diagnostic_capture_succeeded": isolated["diagnostic_capture_succeeded"],
            "cdb_available": source["fixture_diagnostic"]["cdb_available"],
            "timeout_fixture_peak_private_bytes": timeout["helper_guard"]["peak_private_bytes"],
            "timeout_fixture_process_absent": timeout["process_absent"],
        },
        "telemetry_off_on": telemetry,
        "p0_equivalent": p0,
        "gates": source["gates"],
        "cause_classification": source["cause_classification"],
        "limitations": [
            "P0 exited normally, so the Phase 6EI silent residual interval was not reproduced",
            "CDB was unavailable in the current WinDbg package lookup; a future residual fails closed rather than matching the known NGX signature",
            "the exact allocator behind the former parent-PowerShell growth remains unconfirmed",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    runner_limit = 512.0
    bars = [
        ("diagnostic child fixture", isolated["helper_guard"]["peak_private_bytes"] / 1048576.0, "#22c55e"),
        ("P0 parent runner", p0["runner_peak_private_bytes"] / 1048576.0, "#60a5fa"),
        ("Phase 6EI parent", 553889792 / 1048576.0, "#ef4444"),
    ]
    elements = []
    for index, (label, value, color) in enumerate(bars):
        y = 130 + index * 70
        width = min(620.0, value / runner_limit * 620.0)
        elements.append(f'<text x="35" y="{y}" fill="#e5e7eb" font-size="18">{label}</text>')
        elements.append(f'<rect x="240" y="{y-22}" width="620" height="27" rx="6" fill="#253044"/>')
        elements.append(f'<rect x="240" y="{y-22}" width="{width:.1f}" height="27" rx="6" fill="{color}"/>')
        elements.append(f'<text x="880" y="{y}" fill="#e5e7eb" font-size="16">{value:.1f} MiB</text>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="410" viewBox="0 0 1100 410">
<rect width="1100" height="410" fill="#101827"/><g font-family="Segoe UI, sans-serif">
<text x="35" y="46" fill="#f8fafc" font-size="28">Phase 6EJ — isolated shutdown diagnostic</text>
<text x="35" y="78" fill="#94a3b8" font-size="16">Whole diagnostic moved out of the parent PowerShell; P0 exited normally.</text>
{''.join(elements)}
<line x1="860" y1="92" x2="860" y2="335" stroke="#fbbf24" stroke-width="3" stroke-dasharray="8 6"/>
<text x="720" y="365" fill="#fbbf24" font-size="16">512 MiB parent limit</text>
<text x="35" y="392" fill="#94a3b8" font-size="15">telemetry delta {telemetry['duration_delta_seconds']:.3f} s · shutdown CPU mean {p0['cpu']['shutdown_interval']['mean_percent_of_logical_total']:.2f}% of all logical CPUs</text>
</g></svg>'''
    args.svg.write_text(svg, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
