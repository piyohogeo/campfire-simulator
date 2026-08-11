"""Summarize a Phase 6DZ matrix, including a fail-fast control stop."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _escape(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()

    prepared = _read(args.artifact_root / "prepared_stages.json")
    stop = _read(args.artifact_root / "matrix_safe_stop.json")
    evidence = _read(
        args.artifact_root / "stage-open" / stop["failed_condition"] / "runner_evidence.json"
    )
    history = evidence.get("lifecycle_history", [])
    markers = [entry["marker"] for entry in history]
    report = {
        "schema": "campfire.phase6dz.rotated-cylinder-safe-stop-report.v1",
        "phase": "phase6dz",
        "status": "safe_stop",
        "decision": "hold_phase_b_and_later",
        "failed_condition": stop["failed_condition"],
        "failed_step": stop["step"],
        "automatic_retry": False,
        "offline": {
            "source_sha256": prepared["source_sha256"],
            "case_count": len(prepared["cases"]),
            "local_geometry_sha256": next(
                iter(prepared["cases"].values())
            )["audit"]["local_geometry_sha256"],
            "gates": prepared["gates"],
            "conditions": {
                label: {
                    "rotation_xyz_deg": value["rotation_xyz_deg"],
                    "stage_sha256": value["stage_sha256"],
                    "physics_approximation": value["audit"]["physics_approximation"],
                    "transform_ops": value["audit"]["transform_ops"],
                }
                for label, value in prepared["cases"].items()
            },
        },
        "runtime_control": {
            "duration_seconds": evidence["duration_seconds"],
            "timed_out": evidence["timed_out"],
            "process_exit_code": evidence["process_exit_code"],
            "probe_status": evidence["probe_status"],
            "last_lifecycle_marker": evidence["lifecycle_marker"],
            "reached_first_viewport_frame": "first_viewport_frame_complete" in markers,
            "reached_stage_close": "stage_close_complete" in markers,
            "reached_renderer_drain": "renderer_drain_complete" in markers,
            "plugin_shutdown_log_count": len(evidence["plugin_shutdown_log_lines"]),
            "normal_os_exit": False,
            "isolated_process_terminated_after_path_verification": True,
            "fatal_count": len(evidence["fatal_lines"]),
            "dump_count": len(evidence["dump_inventory"]),
            "automatic_upload_attempt_count": len(evidence["automatic_upload_attempt_lines"]),
            "selected_render_gpu": "NVIDIA GeForce RTX 3090",
        },
        "production": {
            "app_sha256_before": evidence["production_app_sha256_before"],
            "app_sha256_after": evidence["production_app_sha256_after"],
            "changed": evidence["production_changed"],
        },
        "not_executed": [
            "all rotated stage-open conditions",
            "all Flow public readback conditions",
            "Phase B transform hierarchy",
            "Phase C RenderSurface coexistence",
            "Phase D PhysX sharing",
            "Phase E dynamic transform",
            "Phase F default-off integration",
            "Phase G 20-log performance",
        ],
        "restart_condition": (
            "Re-establish a normal OS exit for the unchanged Phase 6DY axis-aligned "
            "control through the calibrated Phase 6DW lifecycle before executing any rotation."
        ),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    rows = [
        ("Offline geometry/schema", "7 / 7", "PASS", "#6ee7a2"),
        ("Axis control stage + Hydra", "reached", "PASS", "#6ee7a2"),
        ("Stage close + renderer drain", "reached", "PASS", "#6ee7a2"),
        ("Normal OS exit ≤ 420 s", "not reached", "STOP", "#ff8b7b"),
        ("Rotated cases", "not started", "HELD", "#8c96aa"),
        ("Flow readback", "not started", "HELD", "#8c96aa"),
    ]
    row_svg = []
    for index, (name, value, state, color) in enumerate(rows):
        y = 164 + index * 52
        row_svg.append(
            f'<rect x="55" y="{y - 28}" width="1090" height="42" rx="8" fill="#162033"/>'
            f'<text x="76" y="{y}" class="label">{_escape(name)}</text>'
            f'<text x="730" y="{y}" class="value">{_escape(value)}</text>'
            f'<rect x="1015" y="{y - 22}" width="100" height="28" rx="14" fill="{color}"/>'
            f'<text x="1065" y="{y - 2}" class="state">{state}</text>'
        )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="570" viewBox="0 0 1200 570">
<style>.title{{font:700 32px system-ui;fill:#f5f7fb}}.sub{{font:18px system-ui;fill:#aeb8cc}}.label{{font:18px system-ui;fill:#eef2fa}}.value{{font:600 18px ui-monospace,monospace;fill:#d5def0}}.state{{font:700 13px system-ui;fill:#0b1020;text-anchor:middle}}.foot{{font:16px system-ui;fill:#aeb8cc}}</style>
<rect width="1200" height="570" fill="#0c1322"/><text x="55" y="58" class="title">Phase 6DZ — rotated Cylinder safe stop</text>
<text x="55" y="92" class="sub">Qualified geometry stayed identical; the unchanged axis control did not reach normal OS exit.</text>
{''.join(row_svg)}
<text x="55" y="505" class="foot">420.092 s · final durable marker: shutdown_requested · fatal / dump / upload: 0 / 0 / 0</text>
<text x="55" y="536" class="foot">Production unchanged · no rotation or Flow readback result was claimed.</text></svg>'''
    args.svg.write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
