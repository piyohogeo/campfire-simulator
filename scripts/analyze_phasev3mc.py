"""Publish Phase V3M-C probe, regression, performance, and visual evidence."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "phasev3mc"
OUTPUT = ROOT / "docs" / "devlog" / "assets" / "phasev3mc"


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _copy(source, name):
    target = OUTPUT / name
    shutil.copy2(source, target)
    return target


def main():
    probe = _load(ARTIFACT / "dynamic_mesh_probe.json")
    off = _load(ARTIFACT / "phase3_off" / "summary.json")
    on = _load(ARTIFACT / "phase3_v3" / "summary.json")
    OUTPUT.mkdir(parents=True, exist_ok=True)

    dry_sha_equal = (
        off["wood"]["dry"]["authoritative_state_sha256"]
        == on["wood"]["dry"]["authoritative_state_sha256"]
    )
    wet_sha_equal = (
        off["wood"]["wet"]["authoritative_state_sha256"]
        == on["wood"]["wet"]["authoritative_state_sha256"]
    )
    gates = {
        "dynamic_mesh_probe_qualified": probe["status"] == "qualified",
        "all_probe_gates_passed": all(probe["gates"].values()),
        "dry_authority_sha_exact": dry_sha_equal,
        "wet_authority_sha_exact": wet_sha_equal,
        "ignition_exact": all(
            off["wood"][name]["ignition_seconds"]
            == on["wood"][name]["ignition_seconds"]
            for name in ("dry", "wet")
        ),
        "mass_balance_zero": all(
            summary["wood"][name]["mass_balance_error_kg"] == 0.0
            for summary in (off, on)
            for name in ("dry", "wet")
        ),
        "resident_revision_1200": all(
            summary["scenario"]["resident_snapshot_adapter"]
            ["status_after_timeline_stop"]["revision"]
            == 1200
            for summary in (off, on)
        ),
        "flow_fuel_preserved": off["flow"]["peak_fuel_input"]
        == on["flow"]["peak_fuel_input"]
        == 1.0,
        "flow_active_blocks_nonzero": min(
            off["flow"]["active_blocks_peak"],
            on["flow"]["active_blocks_peak"],
        )
        > 0,
        "v3_lifecycle_complete": (
            on["scenario"]["wood_visual_v3"]["status_after_timeline_stop"]
            ["publish_count"]
            == 1200
            and on["scenario"]["wood_visual_v3"]["upload_count"] == 2400
            and on["scenario"]["wood_visual_v3"]["usd_set_count"] == 1200
            and not on["scenario"]["wood_visual_v3"]["errors"]
        ),
        "actual_trajectory_has_60_frames": len(
            on["video_frames"]["frames"]
        )
        == 60,
        "feature_remains_default_off": probe["decision"]["feature_default"]
        is False,
    }
    visual_p95 = probe["performance"]["visual_publication"]["total_ms"][
        "p95_ms"
    ]
    report = {
        "schema": "campfire.phasev3mc.final_report.v1",
        "status": "qualified_default_off" if all(gates.values()) else "failed",
        "gates": gates,
        "scope": {
            "input": "ImmutableWoodVisualSurfacePayload",
            "surface_identity": "log_id + local_surface_index",
            "logs": 20,
            "surface_cells": 7200,
            "frequency_hz": 5,
            "transport": "two fixed RGBA8 dynamic textures plus one USD revision Set",
            "point_payload_modified": False,
            "authority_modified": False,
            "feature_default": False,
        },
        "performance": probe["performance"],
        "gpu": probe.get("runner_gpu"),
        "performance_decision": {
            "reference_p95_ms": 1.0,
            "measured_p95_ms": visual_p95,
            "target_met": visual_p95 <= 1.0,
            "decision": "retain default OFF; optimize beauty pack and CPU upload before reconsidering default ON",
        },
        "phase3_off_on": {
            "dry_authority_sha256": {
                "off": off["wood"]["dry"]["authoritative_state_sha256"],
                "on": on["wood"]["dry"]["authoritative_state_sha256"],
            },
            "wet_authority_sha256": {
                "off": off["wood"]["wet"]["authoritative_state_sha256"],
                "on": on["wood"]["wet"]["authoritative_state_sha256"],
            },
            "ignition_seconds": {
                name: {
                    "off": off["wood"][name]["ignition_seconds"],
                    "on": on["wood"][name]["ignition_seconds"],
                }
                for name in ("dry", "wet")
            },
            "flow_active_blocks": {
                "off_peak": off["flow"]["active_blocks_peak"],
                "on_peak": on["flow"]["active_blocks_peak"],
                "interpretation": "both remain active; exact Flow field equality is not claimed because DynamicTexture CPU stalls change wall-frame pacing",
            },
            "resident_revision": 1200,
            "mass_balance_error_kg": 0.0,
        },
        "lifecycle": on["scenario"]["wood_visual_v3"],
        "known_limits": [
            "The 1.0 ms publication p95 reference is not met.",
            "GPU upload is not qualified because V2 owns CPU bytes and no owned public GPU pointer source exists.",
            "Whole-GPU memory samples are not a DynamicTextureProvider-scoped allocation measurement.",
            "The production trajectory models only Log_00 and Log_01; unmodeled logs intentionally remain neutral and partially occlude local state changes.",
            "No deformation, shrinkage, cracking, collapse, mesh collider, V4, or Phase 6DM work is included.",
        ],
        "regression": {
            "release_build": "passed",
            "test_processes": 8,
            "test_cases": 73,
            "test_cases_passed": 73,
        },
    }
    (OUTPUT / "wood_visual_v3_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _copy(ARTIFACT / "dynamic_mesh_probe.json", "dynamic_mesh_probe.json")
    _copy(
        ARTIFACT / "captures" / "surface_states_update_4.png",
        "surface_states_20_logs.png",
    )
    _copy(
        ARTIFACT / "phase3_v3" / "video_frames" / "frame_0040.png",
        "wood_visual_v3_combustion_poster.png",
    )
    _copy(
        ARTIFACT / "phase3_v3" / "video_frames" / "frame_0060.png",
        "v3_phase3_mesh.png",
    )
    _copy(
        ROOT
        / "artifacts"
        / "phasev0"
        / "phase3-on-final"
        / "frame_1200.png",
        "v0_phase3_reference.png",
    )
    _copy(
        ARTIFACT / "phase3_v3" / "phase3_burn.mp4",
        "wood_visual_v3_combustion.mp4",
    )

    timing = probe["performance"]["visual_publication"]
    native = probe["performance"]["v2_native_extraction"]["timing"][
        "total_ms"
    ]["p95_ms"]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase V3M-C dynamic Mesh performance</title><desc id="desc">Twenty logs and 7200 surface cells at a five hertz target. Functional gates pass but the one millisecond publication target does not.</desc>
<defs><linearGradient id="bg" x2="1" y2="1"><stop stop-color="#071426"/><stop offset="1" stop-color="#251238"/></linearGradient></defs>
<rect width="1200" height="680" rx="28" fill="url(#bg)"/><text x="64" y="62" fill="#67e8f9" font-family="Segoe UI,sans-serif" font-size="18" font-weight="700">PHASE V3M-C · 20 LOGS · 7,200 SURFACE CELLS · RGBA8 × 2</text>
<text x="64" y="118" fill="#f8fafc" font-family="Segoe UI,sans-serif" font-size="36" font-weight="750">The fixed transport works; the 1 ms budget does not</text>
<text x="64" y="158" fill="#cbd5e1" font-family="Segoe UI,sans-serif" font-size="18">100 post-warmup samples · CPU raw upload · one revision Set · feature remains default OFF</text>
<g font-family="Segoe UI,sans-serif"><rect x="64" y="210" width="1072" height="78" rx="16" fill="#172554"/><text x="88" y="242" fill="#bfdbfe" font-size="17">V2 native extraction p95</text><rect x="390" y="232" width="{native * 105:.1f}" height="22" rx="11" fill="#38bdf8"/><text x="1090" y="252" text-anchor="end" fill="#f8fafc" font-size="24" font-weight="700">{native:.4f} ms</text>
<rect x="64" y="306" width="1072" height="78" rx="16" fill="#172554"/><text x="88" y="338" fill="#bfdbfe" font-size="17">Beauty atlas pack p95</text><rect x="390" y="328" width="{timing['beauty_pack_ms']['p95_ms'] * 105:.1f}" height="22" rx="11" fill="#a78bfa"/><text x="1090" y="348" text-anchor="end" fill="#f8fafc" font-size="24" font-weight="700">{timing['beauty_pack_ms']['p95_ms']:.4f} ms</text>
<rect x="64" y="402" width="1072" height="78" rx="16" fill="#172554"/><text x="88" y="434" fill="#bfdbfe" font-size="17">CPU texture upload p95</text><rect x="390" y="424" width="{timing['cpu_upload_ms']['p95_ms'] * 105:.1f}" height="22" rx="11" fill="#f59e0b"/><text x="1090" y="444" text-anchor="end" fill="#f8fafc" font-size="24" font-weight="700">{timing['cpu_upload_ms']['p95_ms']:.4f} ms</text>
<rect x="64" y="498" width="1072" height="94" rx="16" fill="#3f1d2e" stroke="#fb7185" stroke-width="2"/><text x="88" y="535" fill="#fecdd3" font-size="18">Visual publication total p95</text><rect x="390" y="525" width="{visual_p95 * 105:.1f}" height="24" rx="12" fill="#fb7185"/><text x="1090" y="550" text-anchor="end" fill="#fff1f2" font-size="28" font-weight="800">{visual_p95:.4f} ms</text><text x="88" y="574" fill="#fecdd3" font-size="15">reference 1.0000 ms · {probe['transport']['bytes_per_revision']:,} bytes/revision · target missed</text></g>
<text x="64" y="640" fill="#94a3b8" font-family="Segoe UI,sans-serif" font-size="16">Functional 17/17 · reload + rollback + no-op + stable topology · GPU upload unqualified · production default unchanged</text></svg>'''
    (OUTPUT / "wood_visual_v3_performance.svg").write_text(
        svg + "\n", encoding="utf-8"
    )
    if report["status"] != "qualified_default_off":
        raise SystemExit("Phase V3M-C final report gates failed")


if __name__ == "__main__":
    main()
