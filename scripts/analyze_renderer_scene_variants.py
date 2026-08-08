"""Publish Phase 6CS offline-scene and application-boundary evidence."""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path


def _load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _raw(root, directory, filename):
    path = root / directory / filename
    if not path.is_file():
        raise FileNotFoundError(path)
    return _load(path)


def _case(raw, name="after_viewport_frame"):
    return next(case for case in raw["cases"] if case["name"] == name)


def _result(raw, name="after_viewport_frame"):
    case = _case(raw, name)
    return {
        "remained_playing": case["remained_playing"],
        "advanced_from_zero": case["advanced_from_zero"],
        "stop_event_count": case["stop_event_count"],
        "resolution": raw["viewport_readiness"]["resolution"],
        "viewport_ready_seconds": raw["viewport_readiness"]["wall_seconds"],
    }


def _stopped(result):
    return (
        not result["remained_playing"]
        and not result["advanced_from_zero"]
        and result["stop_event_count"] == 1
    )


def _playing(result):
    return (
        result["remained_playing"]
        and result["advanced_from_zero"]
        and result["stop_event_count"] == 0
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()
    root = args.artifacts_root

    variants = {}
    for name, directory in (
        ("no_flow", "phase6cs-no-flow"),
        ("no_physics", "phase6cs-no-physics"),
        ("render_only", "phase6cs-render-only"),
        ("phase0", "phase6cs-phase0-unchanged"),
        ("minimal_headless", "phase6cs-minimal-camera"),
    ):
        raw = _raw(root, directory, "plain_renderer_timeline.json")
        manifest = _raw(root, directory, "variant_manifest.json")
        variants[name] = {
            **_result(raw),
            "flow_present": manifest["flow_root_present"],
            "physics_scene_present": manifest.get("physics_scene_present"),
            "physics_schema_count": manifest.get("physics_schema_count"),
            "live_prim_edits": manifest["live_prim_edits"],
            "production_changed": manifest["production_changed"],
        }

    campfire_windowed_raw = _raw(
        root,
        "phase6cs-minimal-camera-windowed-retry",
        "plain_renderer_timeline_windowed.json",
    )
    campfire_windowed = _result(campfire_windowed_raw)
    campfire_retry = _result(
        campfire_windowed_raw, "after_viewport_frame_retry"
    )
    editor_base = _result(
        _raw(
            root,
            "phase6cs-minimal-camera-editor-base",
            "plain_renderer_timeline_windowed_editor_base.json",
        )
    )
    editor_flow = _result(
        _raw(
            root,
            "phase6cs-minimal-camera-editor-base-flow",
            "plain_renderer_timeline_windowed_editor_base_flow.json",
        )
    )
    editor_campfire = _result(
        _raw(
            root,
            "phase6cs-minimal-camera-editor-campfire",
            "plain_renderer_timeline_windowed_editor_base_campfire.json",
        )
    )
    editor_async = _result(
        _raw(
            root,
            "phase6cs-minimal-camera-editor-async",
            "plain_renderer_timeline_windowed_editor_base_flow.json",
        )
    )
    editor_fixed = _result(
        _raw(
            root,
            "phase6cs-minimal-camera-editor-fixed-viewport",
            "plain_renderer_timeline_windowed_editor_base_flow.json",
        )
    )
    campfire_fill = _result(
        _raw(
            root,
            "phase6cs-minimal-camera-campfire-fill",
            "plain_renderer_timeline_windowed_campfire.json",
        )
    )
    campfire_present = _result(
        _raw(
            root,
            "phase6cs-minimal-camera-campfire-present",
            "plain_renderer_timeline_windowed_campfire.json",
        )
    )

    gates = {
        "flow_not_required": _stopped(variants["no_flow"]),
        "physics_not_required": _stopped(variants["no_physics"]),
        "flow_and_physics_not_required": _stopped(variants["render_only"]),
        "phase3_content_not_required": _stopped(variants["phase0"]),
        "minimal_camera_cube_reproduces_stop": _stopped(
            variants["minimal_headless"]
        ),
        "window_system_not_required": _stopped(campfire_windowed),
        "stop_repeats_on_retry": _stopped(campfire_retry),
        "editor_base_preserves_play": _playing(editor_base),
        "flowusd_alone_preserves_play": _playing(editor_flow),
        "campfire_extension_alone_preserves_play": _playing(editor_campfire),
        "async_renderer_init_alone_preserves_play": _playing(editor_async),
        "fixed_viewport_alone_preserves_play": _playing(editor_fixed),
        "campfire_fill_viewport_workaround_preserves_play": _playing(
            campfire_fill
        ),
        "present_timing_does_not_remove_stop": _stopped(campfire_present),
        "offline_variants_have_no_live_prim_edits": all(
            item["live_prim_edits"] == 0 for item in variants.values()
        ),
        "production_unchanged": all(
            not item["production_changed"] for item in variants.values()
        ),
    }
    report = {
        "schema_version": 1,
        "phase": "phase6cs",
        "status": "ok" if all(gates.values()) else "failed",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "offline_scene_variants": variants,
        "application_matrix": {
            "campfire_windowed_fixed": campfire_windowed,
            "campfire_windowed_fixed_retry": campfire_retry,
            "editor_base": editor_base,
            "editor_base_plus_flowusd": editor_flow,
            "editor_base_plus_flowusd_plus_campfire_app": editor_campfire,
            "editor_base_plus_flowusd_async_renderer": editor_async,
            "editor_base_plus_flowusd_fixed_viewport": editor_fixed,
            "campfire_fill_viewport_true": campfire_fill,
            "campfire_fixed_plus_editor_present_timing": campfire_present,
        },
        "conclusion": {
            "scene_content_is_required_for_stop": False,
            "resident_is_required_for_stop": False,
            "headless_mode_is_required_for_stop": False,
            "flowusd_alone_is_sufficient_for_stop": False,
            "campfire_extension_alone_is_sufficient_for_stop": False,
            "async_renderer_init_alone_is_sufficient_for_stop": False,
            "fixed_viewport_alone_is_sufficient_for_stop": False,
            "fill_viewport_true_is_a_measured_workaround": True,
            "workaround_adopted": False,
            "workaround_rejection_reason": (
                "Changing the application default to fill the UI viewport would "
                "break the deterministic fixed-resolution capture contract."
            ),
            "remaining_boundary": (
                "A compound interaction between the Campfire application "
                "configuration and its fixed viewport mode; isolate the minimal "
                "application dependency/settings delta before changing production."
            ),
            "timeline_continuity_qualified": False,
            "seamless_visual_continuity_qualified": False,
        },
        "gates": gates,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    rows = (
        ("No Flow + no PhysX", "Campfire", "1280x720", "STOP", "bad"),
        ("Camera + Cube only", "Campfire headless", "1280x720", "STOP", "bad"),
        ("Camera + Cube only", "Campfire windowed", "1280x720", "STOP x2", "bad"),
        ("Camera + Cube only", "Editor + Flow + app", "1280x720", "PLAY", "good"),
        ("Camera + Cube only", "Campfire fill=true", "UI size", "PLAY", "good"),
    )
    row_svg = []
    for index, (scene, app, resolution, outcome, css) in enumerate(rows):
        y = 262 + index * 58
        row_svg.append(
            f'<rect x="64" y="{y - 32}" width="1072" height="48" rx="10" '
            f'class="row"/><text x="86" y="{y}" class="cell">{html.escape(scene)}</text>'
            f'<text x="390" y="{y}" class="cell">{html.escape(app)}</text>'
            f'<text x="756" y="{y}" class="cell">{resolution}</text>'
            f'<text x="964" y="{y}" class="{css}">{outcome}</text>'
        )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6CS renderer scene and application matrix</title><desc id="desc">Flow, PhysX, Resident, Phase 3 content, and headless mode are not required for the timeline stop. The editor base preserves play, and fill viewport is a workaround that is not adopted.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#111827"/><stop offset="1" stop-color="#164e63"/></linearGradient><style>.k{{font:700 18px system-ui;fill:#67e8f9;letter-spacing:2px}}.t{{font:700 36px system-ui;fill:#f8fafc}}.s{{font:19px system-ui;fill:#cbd5e1}}.h{{font:700 16px system-ui;fill:#a5f3fc}}.cell{{font:17px system-ui;fill:#e2e8f0}}.good{{font:700 20px system-ui;fill:#86efac}}.bad{{font:700 20px system-ui;fill:#fca5a5}}.row{{fill:#0f172a;stroke:#334155;stroke-width:1}}.note{{font:17px system-ui;fill:#cffafe}}</style></defs>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="58" class="k">PHASE 6CS · OFFLINE SCENE / APP MATRIX</text><text x="64" y="110" class="t">The STOP is a compound Campfire app boundary</text><text x="64" y="148" class="s">Flow, PhysX, Resident, Phase 3 content, headless mode: not required</text>
<text x="86" y="204" class="h">SCENE</text><text x="390" y="204" class="h">APPLICATION</text><text x="756" y="204" class="h">VIEWPORT</text><text x="964" y="204" class="h">AFTER FRAME</text>{''.join(row_svg)}
<rect x="64" y="548" width="1072" height="84" rx="16" fill="#083344" stroke="#22d3ee" stroke-width="2"/><text x="88" y="582" class="s">Measured workaround: Campfire fillViewport=true → PLAY</text><text x="88" y="610" class="note">Not adopted: it replaces deterministic 1280×720 capture with UI-sized rendering. Production remains unchanged.</text></svg>'''
    args.svg.write_text(svg, encoding="utf-8")
    if report["status"] != "ok":
        raise SystemExit("Phase 6CS gates failed")


if __name__ == "__main__":
    main()
