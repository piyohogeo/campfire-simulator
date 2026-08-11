"""Collect the Phase 6DV stage-open classification safe stop."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "phase6dv-stage-open-classification-1"
ASSET = ROOT / "docs" / "devlog" / "assets" / "phase6"


def _load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8-sig"))


def _sha256(relative: str) -> str:
    digest = hashlib.sha256()
    with (ROOT / relative).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _process(label: str, relative: str, qualified: bool, note: str) -> dict:
    raw = _load(f"{relative}/raw.json")
    evidence_path = ROOT / relative / "runner_evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8-sig")) if evidence_path.is_file() else None
    return {
        "label": label,
        "artifact": relative.replace("\\", "/"),
        "qualified": qualified,
        "probe_status": raw.get("status"),
        "last_marker": raw.get("lifecycle_marker"),
        "process_exit_code": evidence.get("process_exit_code") if evidence else None,
        "fatal_count": len(evidence.get("fatal_lines", [])) if evidence else None,
        "dump_count": len(evidence.get("dump_inventory", [])) if evidence else None,
        "upload_attempt_count": len(evidence.get("automatic_upload_attempt_lines", [])) if evidence else None,
        "production_changed": evidence.get("production_changed") if evidence else None,
        "note": note,
    }


def _svg(report: dict) -> str:
    rows = report["process_results"]
    height = 310 + 54 * len(rows)
    colors = {True: "#54d39b", False: "#ffb45f"}
    row_svg = []
    for index, row in enumerate(rows):
        y = 220 + index * 54
        status = "qualified" if row["qualified"] else "excluded / safe stop"
        row_svg.append(
            f'<rect x="48" y="{y}" width="1184" height="42" rx="10" fill="#17243a"/>'
            f'<circle cx="72" cy="{y + 21}" r="7" fill="{colors[row["qualified"]]}"/>'
            f'<text x="92" y="{y + 18}" class="row">{row["label"]}</text>'
            f'<text x="92" y="{y + 34}" class="small">{status} · marker {row["last_marker"]} · exit {row["process_exit_code"]}</text>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="{height}" viewBox="0 0 1280 {height}">
<style>.title{{font:700 34px 'Segoe UI',sans-serif;fill:#f4f7ff}}.sub{{font:18px 'Segoe UI',sans-serif;fill:#aebbd2}}.row{{font:600 16px 'Segoe UI',sans-serif;fill:#eef3ff}}.small{{font:13px 'Segoe UI',sans-serif;fill:#9dacbf}}.metric{{font:700 25px 'Segoe UI',sans-serif;fill:#fff}}</style>
<rect width="1280" height="{height}" fill="#0b1220"/>
<text x="48" y="58" class="title">Phase 6DV — stage-open crash classification</text>
<text x="48" y="91" class="sub">Same native signature; known-good harness did not exit normally, so Hydra ablation stopped.</text>
<rect x="48" y="118" width="360" height="76" rx="14" fill="#17243a"/><text x="68" y="148" class="sub">Crash signature</text><text x="68" y="178" class="metric">fabric +0xD6960 · read 0x20</text>
<rect x="432" y="118" width="360" height="76" rx="14" fill="#17243a"/><text x="452" y="148" class="sub">6DT / 6DU dump match</text><text x="452" y="178" class="metric">exact · 0xC0000005</text>
<rect x="816" y="118" width="416" height="76" rx="14" fill="#17243a"/><text x="836" y="148" class="sub">Restart decision</text><text x="836" y="178" class="metric" fill="#ffb45f">HOLD — harness boundary first</text>
{''.join(row_svg)}
<text x="48" y="{height - 30}" class="small">Production app hash unchanged · no new dump/upload · Cylinder Flow measurement not resumed</text>
</svg>'''


def main() -> int:
    crash = _load("artifacts/phase6dv-stage-open-classification-1/crash_analysis.json")
    known = _load("artifacts/phase6dt-reference-audit-2/phase6ds_mesh_usd_mesh_collision/run-1/raw.json")
    failed = _load("artifacts/phase6du-static-cylinder-1/mesh_hull/run-1/raw.json")
    processes = [
        {
            "label": "6DT known-good Box / original harness",
            "artifact": "artifacts/phase6dt-reference-audit-2/phase6ds_mesh_usd_mesh_collision/run-1",
            "qualified": True,
            "probe_status": known["status"],
            "last_marker": known["lifecycle_marker"],
            "process_exit_code": 0,
            "fatal_count": 0,
            "dump_count": 0,
            "upload_attempt_count": 0,
            "production_changed": False,
            "note": "Historical positive control reached Flow readback and shutdown.",
        },
        {
            "label": "6DU Cylinder hull / original failed preflight",
            "artifact": "artifacts/phase6du-static-cylinder-1/mesh_hull/run-1",
            "qualified": False,
            "probe_status": failed["status"],
            "last_marker": failed["lifecycle_marker"],
            "process_exit_code": -1073741819,
            "fatal_count": 1,
            "dump_count": 1,
            "upload_attempt_count": 0,
            "production_changed": False,
            "note": "Preserved historical crash; not rerun.",
        },
        _process(
            "6DV Box OpenUSD-only / first cold attempt",
            "artifacts/phase6dv-stage-open-classification-1/box_offline/run-1",
            False,
            "Probe reached shutdown_complete, but the outer 330 s command ended before runner evidence was written.",
        ),
        _process(
            "6DV Box OpenUSD-only / no readiness prelude",
            "artifacts/phase6dv-stage-open-classification-1/box_offline/run-2",
            False,
            "Pure OpenUSD completed; isolated Kit was terminated after prolonged post-plugin-shutdown residue.",
        ),
        _process(
            "6DV Box OpenUSD-only / 8-frame renderer readiness",
            "artifacts/phase6dv-stage-open-classification-1/box_offline/run-3",
            False,
            "Pure OpenUSD completed; the same process residue remained for more than seven minutes.",
        ),
    ]
    crash_exception = crash["results"][0]["exception"]
    report = {
        "schema": "campfire.phase6dv.stage-open-classification-report.v1",
        "phase": "phase6dv",
        "status": "safe_stop_known_good_harness_anomaly",
        "production_code_changed": False,
        "production_app_sha256": _sha256("_build/windows-x86_64/release/apps/campfire.simulator.kit"),
        "versions": {
            "kit": "110.2.0+feature.342835.698af100.gl",
            "flow": "110.0.0",
            "physx": "110.1.1",
            "hydra_rtx": "1.0.4",
            "usdrt_scenegraph": "7.6.3",
            "driver": "591.86",
            "gpu": "NVIDIA GeForce RTX 3090",
        },
        "debugger": {
            "windbg_or_cdb_available": False,
            "method": crash["analysis_method"],
            "limitation": crash["symbol_limit"],
        },
        "crash_signature": {
            "same_between_phase6dt_and_phase6du": crash["same_fault_signature"],
            **crash_exception,
            "low_confidence_log_stack_prefix": [
                "omni.fabric.plugin.dll+0xCE5B0 (symbol-relative log label)",
                "usdrt.hydra.fabric_scene_delegate.plugin.dll+0xE5415",
                "usdrt.hydra.fabric_scene_delegate.plugin.dll+0x204AE",
                "omni.hydra.usdrt_delegate.plugin.dll+0x4FD3",
                "rtx.hydra.dll+0xF36",
            ],
            "preferred_instruction_location": "omni.fabric.plugin.dll+0xD6960 from MINIDUMP ExceptionStream",
        },
        "process_results": processes,
        "normalized_stage_difference": [
            {"boundary": "collision shape", "phase6dt_known_good": "Box Mesh; 8 vertices, 6 faces, 24 indices", "phase6du_failed": "closed 12-segment Cylinder Mesh; 26 vertices, 36 faces, 120 indices", "classification": "unresolved; not ablated after harness anomaly"},
            {"boundary": "extent", "phase6dt_known_good": "world-space [-1,-1,0.875] to [1,1,1.125]", "phase6du_failed": "local [-0.9,-0.16,-0.16] to [0.9,0.16,0.16]", "classification": "offline values valid"},
            {"boundary": "transform hierarchy", "phase6dt_known_good": "/World/ColliderReferenceMesh, no parent transform", "phase6du_failed": "/World/Log/FlowCollisionProxy under translate Z=1", "classification": "unresolved"},
            {"boundary": "collision schemas", "phase6dt_known_good": "PhysicsCollisionAPI + PhysicsMeshCollisionAPI", "phase6du_failed": "PhysicsCollisionAPI + PhysicsMeshCollisionAPI", "classification": "same required API pair"},
            {"boundary": "approximation", "phase6dt_known_good": "convexDecomposition", "phase6du_failed": "convexHull", "classification": "unresolved"},
            {"boundary": "render/material", "phase6dt_known_good": "invisible collision Mesh; disabled original Cube remains", "phase6du_failed": "invisible proxy plus visible material-bound RenderSurface", "classification": "unresolved"},
            {"boundary": "analytic sibling", "phase6dt_known_good": "disabled original Cube", "phase6du_failed": "non-collision analytic Cylinder sibling", "classification": "unresolved; no overlapping collision API"},
            {"boundary": "visibility/purpose", "phase6dt_known_good": "invisible / default", "phase6du_failed": "proxy invisible / default", "classification": "equivalent for collision proxy"},
            {"boundary": "authoring", "phase6dt_known_good": "flatten existing Phase 6DS stage, patch before connection", "phase6du_failed": "create complete fresh stage before connection", "classification": "both offline-before-connect; construction route differs"},
        ],
        "confirmed": [
            "Both preserved crashes are 0xC0000005 reads of 0x20 at omni.fabric.plugin.dll+0xD6960.",
            "Their low-confidence native stack prefixes and opening_prebuilt_stage markers match.",
            "The known-good Phase 6DT Box stage opens and audits through pure OpenUSD in the Phase 6DV process.",
            "No Phase 6DV stage was connected to Hydra after the known-good process failed the normal-exit boundary.",
            "No new dump or automatic upload attempt occurred, and the production app hash remained unchanged.",
        ],
        "strong_inference": [
            "The repeated signature across structurally different stages is more consistent with a shared Fabric/Hydra engine-add or initialization/lifetime boundary than a proven Cylinder-topology defect.",
            "The new post-shutdown residue is harness/renderer-lifecycle behavior, not evidence that the OpenUSD Box stage is invalid.",
        ],
        "unconfirmed": [
            "The native call stack below module+offset because WinDbg/CDB and matching private symbols are unavailable.",
            "Whether Box versus Cylinder topology, convexHull, hierarchy, render sibling, or analytic sibling is the first stage-content discriminator.",
            "Whether renderer readiness, context scheduling, process teardown, or a fixed-build Fabric race is the root cause.",
            "Cylinder Flow occlusion, rotation, decomposition, shared PhysX proxy, dynamic transform, and 20-log cost.",
        ],
        "restart_decision": {
            "phase6du_may_resume": False,
            "reason": "The same-launcher known-good process did not produce a normal OS exit; the user-requested safe-stop condition was met before Hydra ablation.",
            "minimum_next_information": [
                "A known-good Box stage-open runner that reaches normal process exit with durable pre/post-Hydra markers.",
                "WinDbg/CDB or NVIDIA/Kit symbols for omni.fabric.plugin.dll build 698af100, or an NVIDIA crash report using the two preserved dump hashes.",
                "Only after that control passes: Box hull, Cylinder decomposition, Cylinder hull, hierarchy, RenderSurface, and analytic-sibling ablations in separate processes.",
            ],
        },
        "regression": {
            "release_build": {"status": "passed", "seconds": 6.01},
            "targeted_flow_collider_test": {
                "status": "passed",
                "test": "campfire.app.tests.test_scene.TestScene.test_flow_scene_has_emitter_simulation_and_colliders",
                "passed": 1,
                "total": 1,
                "seconds": 0.073,
            },
            "static_devlog": {
                "status": "passed",
                "checks": ["UTF-8 HTML", "Phase order", "asset references", "JSON", "SVG XML"],
                "browser_render": "unavailable; no browser binding was connected in this session",
            },
            "phase0_rtx": "not rerun; no production code or app composition changed",
            "standard_suite": "not rerun; no shared production code changed",
        },
        "gates": {
            "preserved_dump_signature_parsed": True,
            "same_signature_classified": crash["same_fault_signature"],
            "pure_openusd_known_good_opened": True,
            "known_good_normal_process_exit": False,
            "hydra_stage_ablation_started": False,
            "failed_cylinder_condition_rerun": False,
            "new_crash_or_dump": False,
            "automatic_upload_attempt": False,
            "production_hash_unchanged": True,
            "phase6du_resume_qualified": False,
        },
    }
    ASSET.mkdir(parents=True, exist_ok=True)
    json_path = ASSET / "stage_open_crash_classification_report.json"
    svg_path = ASSET / "stage_open_crash_classification_report.svg"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    svg_path.write_text(_svg(report), encoding="utf-8")
    print(json.dumps({"report": str(json_path), "svg": str(svg_path), "status": report["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
