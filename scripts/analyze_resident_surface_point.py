"""Validate and publish the Phase 6CC Resident surface Point report."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def _load(path):
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("status") != "ok":
        raise ValueError(f"Phase 6CC raw report is not successful: {path}")
    failed = [name for name, value in report.get("gates", {}).items() if not value]
    if failed:
        raise ValueError(f"Phase 6CC failed gates: {failed}")
    if report["scope"]["point_count"] != 7200 or report["scope"]["emitter_count"] != 1:
        raise ValueError("Phase 6CC must retain one 7,200-point Emitter")
    return report


def _svg(report):
    timing = report["measurement"]
    legacy = timing["legacy_python_gf_source"]["p95_ms"]
    native = timing["native_dynamic_channels"]["p95_ms"]
    vt_copy = timing["numpy_to_vt_dynamic_copy"]["p95_ms"]
    usd_set = timing["usd_attribute_set"]["p95_ms"]
    exit_ms = timing["change_block_exit"]["p95_ms"]
    publication = timing["dynamic_publication_total"]["p95_ms"]
    speedup = legacy / native
    blocks = report["flow"]["active_blocks_peak"]
    gate_count = len(report["gates"])
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6CC Resident native surface arrays</title>
<desc id="desc">Resident SoA generates 7,200 Point Emitter channels natively, preserves immutable revision, and drives Flow 110 fire and smoke.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#071b2d"/><stop offset="1" stop-color="#2b160d"/></linearGradient></defs>
<style>.k{{font:700 17px 'Segoe UI',sans-serif;fill:#67e8f9;letter-spacing:2px}}.t{{font:750 38px 'Segoe UI',sans-serif;fill:#f8fafc}}.s{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.h{{font:700 17px 'Segoe UI',sans-serif;fill:#f8fafc}}.v{{font:750 30px 'Segoe UI',sans-serif;fill:#fdba74}}.m{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}.ok{{font:750 22px 'Segoe UI',sans-serif;fill:#86efac}}</style>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="61" class="k">PHASE 6CC · RESIDENT SURFACE → POINT EMITTER</text><text x="64" y="112" class="t">7,200 dynamic channels without Python object rebuilds</text><text x="64" y="149" class="s">20 logs × 360 surface cells · one Emitter · Flow 110.0.0 · additive default-off C ABI</text>
<rect x="64" y="188" width="1072" height="116" rx="20" fill="#0b2537" stroke="#155e75"/><text x="90" y="224" class="h">Source generation p95</text><text x="90" y="270" class="v">{legacy:.4f} ms → {native:.4f} ms</text><text x="650" y="253" class="v">{speedup:.1f}×</text><text x="650" y="280" class="m">legacy Python/Gf reference ÷ native dynamic channels</text>
<rect x="64" y="328" width="248" height="150" rx="18" fill="#12202e"/><text x="86" y="364" class="h">NumPy → Vt copy</text><text x="86" y="410" class="v">{vt_copy:.4f} ms</text><text x="86" y="448" class="m">explicit owned boundary</text>
<rect x="328" y="328" width="248" height="150" rx="18" fill="#12202e"/><text x="350" y="364" class="h">UsdAttribute.Set</text><text x="350" y="410" class="v">{usd_set:.4f} ms</text><text x="350" y="448" class="m">3 arrays + revision</text>
<rect x="592" y="328" width="248" height="150" rx="18" fill="#12202e"/><text x="614" y="364" class="h">ChangeBlock exit</text><text x="614" y="410" class="v">{exit_ms:.4f} ms</text><text x="614" y="448" class="m">one notice / revision</text>
<rect x="856" y="328" width="280" height="150" rx="18" fill="#12202e"/><text x="878" y="364" class="h">Dynamic publication</text><text x="878" y="410" class="v">{publication:.4f} ms</text><text x="878" y="448" class="m">86,408 B · positions static</text>
<rect x="64" y="512" width="1072" height="104" rx="20" fill="#10271d" stroke="#15803d"/><text x="90" y="552" class="ok">{gate_count}/{gate_count} gates · {blocks} active blocks · exact layout/channels/revision · live resync 0</text><text x="90" y="588" class="s">Decision: retain one Emitter; next isolate scheduler ownership and moving-log layout invalidation before production adoption.</text>
<text x="64" y="651" class="m">Production Sphere, physics, JSON schema, rollback, dependency lock, and defaults remain unchanged.</text></svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    parser.add_argument("--capture", required=True, type=Path)
    arguments = parser.parse_args()
    report = _load(arguments.raw)
    timing = report["measurement"]
    report["decision"] = {
        "native_dynamic_source_speedup_p95": (
            timing["legacy_python_gf_source"]["p95_ms"]
            / timing["native_dynamic_channels"]["p95_ms"]
        ),
        "single_emitter_retained": True,
        "production_adoption": "deferred",
        "next_boundary": "default-off scheduler ownership and moving-log layout invalidation",
    }
    for path in (arguments.report, arguments.svg, arguments.capture):
        path.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    arguments.svg.write_text(_svg(report), encoding="utf-8")
    final_capture = Path(report["flow"]["final"]["path"])
    if not final_capture.is_file():
        raise ValueError(f"Final capture is missing: {final_capture}")
    shutil.copy2(final_capture, arguments.capture)
    print(
        "Phase 6CC report written: "
        f"speedup={report['decision']['native_dynamic_source_speedup_p95']:.1f}x, "
        f"publication_p95={timing['dynamic_publication_total']['p95_ms']:.4f} ms"
    )


if __name__ == "__main__":
    main()
