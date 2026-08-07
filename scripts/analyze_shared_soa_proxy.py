"""Validate and visualize the isolated shared-SoA proxy research spike."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def _metric(report, name):
    return report["timing"][name]["p95_ms"]


def _svg(report):
    timing = report["timing"]
    proxy = _metric(report, "proxy_transactional_scalar_write")
    batch = _metric(report, "proxy_32_field_batch_edit")
    lifecycle = _metric(report, "legacy_one_log_export_edit_import")
    native = _metric(report, "transactional_native_step")
    soa_json = _metric(report, "direct_soa_json_serialization")
    object_json = _metric(report, "dataclass_json_serialization")
    cells = report["measurement"]["cell_count"]
    gates = report["correctness"]["gates"]
    passed = sum(bool(value) for value in gates.values())
    total = len(gates)
    bars = (
        ("Proxy scalar transaction", proxy, "#68d391"),
        ("Proxy 32-field edit lease", batch, "#4fd1c5"),
        ("Legacy export + edit + import", lifecycle, "#f6ad55"),
        ("Prototype step + rollback copy", native, "#63b3ed"),
    )
    maximum = max(value for _, value, _ in bars) or 1.0
    bar_rows = []
    for row, (label, value, color) in enumerate(bars):
        y = 218 + row * 58
        width = 350.0 * value / maximum
        bar_rows.append(
            f'<text x="72" y="{y}" class="label">{html.escape(label)}</text>'
            f'<rect x="330" y="{y - 19}" width="{width:.2f}" height="24" rx="7" fill="{color}"/>'
            f'<text x="{342 + width:.2f}" y="{y}" class="value">{value:.4f} ms p95</text>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Shared SoA and Python proxy research spike</title>
<desc id="desc">Zero-copy, lifecycle, rollback, serialization, and timing results for an isolated future candidate.</desc>
<style>
.bg{{fill:#08121f}} .panel{{fill:#111f31;stroke:#29415f;stroke-width:1.5}} .title{{fill:#f7fafc;font:700 30px system-ui,sans-serif}} .subtitle{{fill:#9fb3c8;font:15px system-ui,sans-serif}} .label{{fill:#dce7f2;font:14px system-ui,sans-serif}} .value{{fill:#f7fafc;font:700 14px ui-monospace,monospace}} .head{{fill:#7dd3fc;font:700 16px system-ui,sans-serif}} .body{{fill:#b9c8d8;font:14px system-ui,sans-serif}} .ok{{fill:#86efac;font:700 17px system-ui,sans-serif}} .warn{{fill:#fbbf24;font:700 15px system-ui,sans-serif}}
</style>
<rect width="1200" height="680" class="bg"/>
<text x="66" y="58" class="title">Future study · Shared SoA + Python proxy</text>
<text x="66" y="87" class="subtitle">Isolated headless spike · {cells:,} cells · production and USD paths unchanged</text>
<rect x="52" y="118" width="746" height="332" rx="16" class="panel"/>
<text x="72" y="154" class="head">Measured p95 boundary cost</text>
{''.join(bar_rows)}
<rect x="822" y="118" width="326" height="332" rx="16" class="panel"/>
<text x="846" y="154" class="head">Contract gates</text>
<text x="846" y="195" class="ok">{passed} / {total} passed</text>
<text x="846" y="237" class="body">✓ same NumPy pointer after C++</text>
<text x="846" y="267" class="body">✓ no numeric dirty import</text>
<text x="846" y="297" class="body">✓ busy write rejected</text>
<text x="846" y="327" class="body">✓ edit / step rollback exact</text>
<text x="846" y="357" class="body">✓ stale proxy rejected on swap</text>
<text x="846" y="397" class="warn">Read-only buffers are not revocable</text>
<rect x="52" y="474" width="1096" height="154" rx="16" class="panel"/>
<text x="72" y="510" class="head">Decision</text>
<text x="72" y="546" class="body">Technically feasible when writable arrays stay private and all writes use a proxy or edit lease.</text>
<text x="72" y="576" class="body">JSON p95: direct SoA {soa_json:.3f} ms · dataclass {object_json:.3f} ms. Scalar proxy access adds lifecycle overhead.</text>
<text x="72" y="606" class="warn">Defer adoption: this does not reduce transactional USD publication cost.</text>
</svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    args = parser.parse_args()
    raw = json.loads(args.raw.read_text(encoding="utf-8"))
    if raw.get("status") != "ok":
        raise ValueError("Shared SoA raw report did not succeed")
    if not all(raw["correctness"]["gates"].values()):
        raise ValueError("Shared SoA contract gate failed")
    if raw["scope"]["production_code_changed"]:
        raise ValueError("Research spike must not change production code")
    if raw["scope"]["usd_publish_path_changed"]:
        raise ValueError("Research spike must not change USD publication")
    report = dict(raw)
    report["decision"] = {
        "technical_feasibility": "qualified",
        "production_adoption": "deferred",
        "reason": (
            "The proxy removes numeric re-import only when raw writable buffers are "
            "private; it adds lifecycle and compatibility complexity and does not "
            "address the USD publication bottleneck."
        ),
        "priority_order": [
            "instrument transactional USD publication",
            "reduce USD publication p95 below 4 ms",
            "connect native producer to ResidentPublishedSnapshot",
            "then reconsider shared SoA authority",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.svg.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.svg.write_text(_svg(report), encoding="utf-8")
    print(f"Shared SoA report: {args.report}")
    print(f"Shared SoA SVG: {args.svg}")


if __name__ == "__main__":
    main()
