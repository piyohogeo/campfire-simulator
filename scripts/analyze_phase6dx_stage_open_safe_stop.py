"""Create the sanitized Phase 6DX safe-stop report from ignored artifacts."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "phase6dx-stage-open-safe-preflight-1"
ASSET = ROOT / "docs" / "devlog" / "assets" / "phase6"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    evidence = _load(ARTIFACT / "box_control" / "run-1" / "runner_evidence.json")
    stop = _load(ARTIFACT / "matrix_safe_stop.json")
    history = evidence.get("lifecycle_history", [])
    if isinstance(history, dict):
        history = [history]
    report = {
        "schema": "campfire.phase6dx.stage-open-safe-stop-report.v1",
        "phase": "phase6dx",
        "status": "safe_stop",
        "source_phase": "phase6dt",
        "source_stage_sha256": "2ED926A1EAF14356A44487D2426E712002A61FBD6937C5C5A797F74E68861862",
        "process_results": [
            {
                "condition": "box_control",
                "started": True,
                "duration_seconds": evidence["duration_seconds"],
                "exit_code": evidence["process_exit_code"],
                "timed_out": evidence["timed_out"],
                "last_marker": evidence["lifecycle_marker"],
                "stage_created": False,
                "usd_context_connected": False,
                "first_renderer_update": False,
                "first_viewport_frame": False,
                "fatal_count": len(evidence.get("fatal_lines", [])),
                "dump_count": len(evidence.get("dump_inventory", [])),
                "upload_attempt_count": len(evidence.get("automatic_upload_attempt_lines", [])),
                "production_changed": evidence["production_changed"],
            },
            {"condition": "box_hull", "started": False, "reason": "fail-fast after known-good control timeout"},
            {
                "condition": "cylinder_decomposition",
                "started": False,
                "reason": "fail-fast after known-good control timeout",
            },
        ],
        "lifecycle_history": history,
        "selected_render_device": "NVIDIA GeForce RTX 3090",
        "selected_cuda_index": 0,
        "matrix_completed": stop.get("completed", []),
        "automatic_retry": stop.get("automatic_retry", False),
        "production_app_sha256_before": evidence["production_app_sha256_before"],
        "production_app_sha256_after": evidence["production_app_sha256_after"],
        "classification": {
            "observed": [
                "The known-good Box process timed out after 420 seconds before offline stage preparation or stage connection.",
                "The last durable marker was renderer_readiness_warmup_started while waiting for pre-stage viewport frames.",
                "No fatal token, crash dump, upload attempt, or production app hash change was observed.",
                "Neither box_hull nor cylinder_decomposition was started; cylinder_hull was excluded from the runnable matrix.",
            ],
            "strong_inference": [
                "This result classifies the new no-window pre-stage viewport-frame wait as an invalid harness boundary; it does not classify Box or Cylinder stage content.",
                "Phase 6DW's qualified runner checked for an active viewport before stage connection and waited for a viewport frame only after connection, unlike this preflight.",
            ],
            "unconfirmed": [
                "No Box-to-Cylinder topology, approximation, schema, hierarchy, or material boundary was exercised.",
                "The historical Fabric crash cause remains unresolved and Phase 6DU runtime work is not resumed.",
            ],
        },
        "restart_condition": "Create a new independent harness that reproduces the Phase 6DW qualified readiness order, then obtain a known-good Box normal OS exit before any topology ablation.",
        "regression": {
            "release_build": {"status": "passed", "seconds": 6.79},
            "standard_suite": {"status": "passed", "processes": 8, "passed": 78, "total": 78, "seconds": 304.5},
            "static_devlog": {
                "status": "passed",
                "unique_local_references": 326,
                "missing_references": 0,
                "utf8_replacement_characters": 0,
                "browser_render": "unavailable; no browser connection was available in this session",
            },
            "phase0_rtx": "not rerun; production code and app composition unchanged and the runtime matrix stopped at its control",
        },
        "latest_demo_changed": False,
        "production_changed": False,
    }
    ASSET.mkdir(parents=True, exist_ok=True)
    json_path = ASSET / "stage_open_safe_preflight_report.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="560" viewBox="0 0 1200 560" role="img" aria-labelledby="title desc">
<title id="title">Phase 6DX stage-open safe preflight</title>
<desc id="desc">Known-good Box stopped at the pre-stage viewport-frame readiness wait; no stage ablation ran.</desc>
<rect width="1200" height="560" fill="#0e1118"/>
<text x="54" y="68" fill="#f4f7fb" font-family="Segoe UI, sans-serif" font-size="30" font-weight="700">Phase 6DX · stage-open safe preflight</text>
<text x="54" y="104" fill="#9eabc1" font-family="Segoe UI, sans-serif" font-size="18">known-good control stopped before stage preparation · no topology conclusion</text>
<rect x="54" y="145" width="1092" height="108" rx="12" fill="#1a2130" stroke="#39445a"/>
<text x="82" y="183" fill="#ffcc80" font-family="Segoe UI, sans-serif" font-size="18" font-weight="700">BOX CONTROL</text>
<text x="82" y="218" fill="#f4f7fb" font-family="Segoe UI, sans-serif" font-size="24">420.47 s timeout at renderer_readiness_warmup_started</text>
<text x="890" y="218" fill="#ff8a80" font-family="Segoe UI, sans-serif" font-size="22" font-weight="700">SAFE STOP</text>
<line x1="86" y1="317" x2="1114" y2="317" stroke="#3c485d" stroke-width="4"/>
<circle cx="125" cy="317" r="16" fill="#ffcc80"/><circle cx="450" cy="317" r="16" fill="#4b5568"/><circle cx="775" cy="317" r="16" fill="#4b5568"/><circle cx="1080" cy="317" r="16" fill="#4b5568"/>
<text x="74" y="363" fill="#f4f7fb" font-family="Segoe UI, sans-serif" font-size="17">app ready</text>
<text x="365" y="363" fill="#8995aa" font-family="Segoe UI, sans-serif" font-size="17">stage prepare</text>
<text x="682" y="363" fill="#8995aa" font-family="Segoe UI, sans-serif" font-size="17">USD / Hydra</text>
<text x="1002" y="363" fill="#8995aa" font-family="Segoe UI, sans-serif" font-size="17">OS exit</text>
<rect x="54" y="414" width="1092" height="92" rx="12" fill="#151b27"/>
<text x="82" y="451" fill="#a8e6cf" font-family="Segoe UI, sans-serif" font-size="18">fatal 0 · dump 0 · upload 0 · production hash unchanged</text>
<text x="82" y="484" fill="#9eabc1" font-family="Segoe UI, sans-serif" font-size="17">box_hull and cylinder_decomposition not started · failed cylinder_hull excluded</text>
</svg>'''
    (ASSET / "stage_open_safe_preflight_report.svg").write_text(svg, encoding="utf-8")
    print(json_path)


if __name__ == "__main__":
    main()
