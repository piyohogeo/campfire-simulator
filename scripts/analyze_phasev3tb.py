"""Publish the Phase V3T-B native beauty and change-aware report."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "devlog" / "assets" / "phasev3tb"


def _arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--probe",
        type=Path,
        default=ROOT / "artifacts" / "phasev3tb" / "native_beauty_probe.json",
    )
    parser.add_argument(
        "--v3mc-regression",
        type=Path,
        default=ROOT
        / "artifacts"
        / "phasev3tb"
        / "v3mc-regression"
        / "dynamic_mesh_probe.json",
    )
    return parser.parse_args()


def _svg(report):
    baseline = report["comparison"]["v3ta_compact_p95_ms"]
    current = report["performance"]["changing_publication_p95_ms"]
    native = report["performance"]["native_pack_p95_ms"]
    skipped = report["change_aware"]["unchanged_uploads"]
    scale = 120.0
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase V3T-B native beauty transport</title><desc id="desc">Native packing reuses fixed buffers and exact RGBA8 output. Unchanged quantized frames perform no upload or USD Set, while changing publication remains above one millisecond.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#0c1715"/><stop offset="1" stop-color="#172033"/></linearGradient></defs>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><g font-family="Segoe UI, sans-serif">
<text x="70" y="68" fill="#6ee7b7" font-size="18" font-weight="700" letter-spacing="3">PHASE V3T-B · NATIVE BEAUTY + CHANGE-AWARE</text>
<text x="70" y="118" fill="#f8fafc" font-size="38" font-weight="800">Stable buffers; unchanged frames write nothing</text>
<text x="70" y="154" fill="#a7b2c2" font-size="18">20 logs · 7,200 surface cells · compact 120×60 atlas · Kit/RTX measured</text>
<rect x="70" y="194" width="1060" height="120" rx="18" fill="#10261f" stroke="#34d399"/>
<text x="96" y="230" fill="#d1fae5" font-size="17">Native pack · all RGBA8 texels exact · three session allocations</text>
<rect x="96" y="253" width="{native * scale:.1f}" height="24" rx="12" fill="#34d399"/><text x="1095" y="276" text-anchor="end" fill="#f8fafc" font-size="25" font-weight="800">{native:.4f} ms p95</text>
<rect x="70" y="336" width="1060" height="116" rx="18" fill="#172554"/>
<text x="96" y="372" fill="#bfdbfe" font-size="17">Changing frame publication · compact baseline {baseline:.4f} ms</text>
<rect x="96" y="394" width="{current * scale:.1f}" height="24" rx="12" fill="#818cf8"/><text x="1095" y="417" text-anchor="end" fill="#f8fafc" font-size="25" font-weight="800">{current:.4f} ms p95</text>
<rect x="70" y="474" width="510" height="112" rx="18" fill="#10261f" stroke="#34d399"/><text x="96" y="512" fill="#d1fae5" font-size="17">105 unchanged revisions</text><text x="96" y="558" fill="#6ee7b7" font-size="30" font-weight="800">{skipped} uploads · 0 Sets</text>
<rect x="600" y="474" width="530" height="112" rx="18" fill="#312e1b" stroke="#fbbf24"/><text x="626" y="512" fill="#fef3c7" font-size="17">Adaptive normal path</text><text x="626" y="558" fill="#fbbf24" font-size="30" font-weight="800">2.5 Hz · max 0.4 s</text>
<text x="70" y="628" fill="#fbbf24" font-size="22" font-weight="750">Functional transport qualified; 1 ms target still missed. Continue to integrated V3T-C.</text>
</g></svg>'''


def main():
    args = _arguments()
    probe = json.loads(args.probe.read_text(encoding="utf-8"))
    regression = json.loads(args.v3mc_regression.read_text(encoding="utf-8"))
    if probe.get("status") != "qualified" or not all(probe["gates"].values()):
        raise RuntimeError("Phase V3T-B probe is not qualified")
    if regression.get("status") != "qualified" or not all(
        regression["gates"].values()
    ):
        raise RuntimeError("Phase V3M-C regression is not qualified")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    twenty = probe["reference_comparison"]["twenty_logs"]
    changing = probe["change_aware"]["changing_timing"]
    report = {
        "schema": "campfire.phasev3tb.report.v1",
        "status": "qualified_functionally_performance_target_missed",
        "gates_passed": sum(probe["gates"].values()),
        "gate_count": len(probe["gates"]),
        "v3mc_regression": {
            "gates_passed": sum(regression["gates"].values()),
            "gate_count": len(regression["gates"]),
            "consumer_revision": regression["consumer"]["revision"],
        },
        "mapping": {
            "rgba8_all_texels_exact": twenty["all_texels_exact"],
            "surface_permutation_visible": twenty["permutation_visible"],
            "buffer_pointer_stable": twenty["native_buffer_pointer_stable"],
            "session_allocation_count": twenty["native_session_allocation_count"],
        },
        "performance": {
            "native_pack_p95_ms": twenty["native_pack"]["p95_ms"],
            "numpy_reference_pack_p95_ms": twenty["python_pack"]["p95_ms"],
            "changing_publication_p95_ms": changing["total_ms"]["p95_ms"],
            "cpu_upload_p95_ms": changing["cpu_upload_ms"]["p95_ms"],
            "revision_commit_p95_ms": changing["revision_commit_ms"]["p95_ms"],
            "target_ms": 1.0,
            "target_met": changing["total_ms"]["p95_ms"] <= 1.0,
        },
        "change_aware": {
            "unchanged_samples": probe["change_aware"]["unchanged_samples"],
            "unchanged_uploads": probe["change_aware"]["unchanged_uploads"],
            "unchanged_usd_sets": probe["change_aware"]["unchanged_usd_sets"],
            "base_and_emission_independent": probe["gates"][
                "base_and_emission_skip_independently"
            ],
            "processed_and_displayed_revision_separate": probe["gates"][
                "processed_and_displayed_revision_are_observable"
            ],
        },
        "adaptive_schedule": probe["adaptive_schedule"],
        "comparison": {
            "v3mc_guttered_p95_ms": 5.4135,
            "v3ta_compact_p95_ms": 4.8254,
            "note": "Single probes are not an adoption claim; integrated alternating runs are reserved for V3T-C.",
        },
        "decision": {
            "v3_default": False,
            "continue_to_v3tc": True,
            "production_scope_changed": False,
        },
    }
    (OUTPUT / "native_beauty_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUTPUT / "native_beauty_report.svg").write_text(
        _svg(report) + "\n", encoding="utf-8"
    )
    shutil.copy2(args.probe, OUTPUT / "native_beauty_probe.json")
    shutil.copy2(args.v3mc_regression, OUTPUT / "native_v3mc_regression.json")
    source = args.probe.parent / "captures" / "native_beauty.png"
    shutil.copy2(source, OUTPUT / "native_beauty.png")
    print(
        f"Phase V3T-B: {report['gates_passed']}/{report['gate_count']} gates; "
        f"publication p95={report['performance']['changing_publication_p95_ms']:.4f} ms"
    )


if __name__ == "__main__":
    main()
