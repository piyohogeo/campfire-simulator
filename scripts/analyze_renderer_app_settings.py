"""Publish Phase 6CT extension and runtime-settings boundary evidence."""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path


def _load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _flatten(value, prefix=""):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            result.update(_flatten(item, f"{prefix}/{key}"))
        return result
    if isinstance(value, list):
        return {prefix: tuple(value)}
    return {prefix: value}


def _raw(root, directory, filename):
    path = root / directory / filename
    if not path.is_file():
        raise FileNotFoundError(path)
    return _load(path)


def _case(raw, name="after_viewport_frame"):
    return next(case for case in raw["cases"] if case["name"] == name)


def _stopped(raw, name="after_viewport_frame"):
    case = _case(raw, name)
    return (
        not case["remained_playing"]
        and not case["advanced_from_zero"]
        and case["stop_event_count"] == 1
    )


def _playing(raw, name="after_viewport_frame"):
    case = _case(raw, name)
    return (
        case["remained_playing"]
        and case["advanced_from_zero"]
        and case["stop_event_count"] == 0
    )


def _summary(raw):
    after = _case(raw)
    retry = _case(raw, "after_viewport_frame_retry")
    return {
        "resolution": raw["viewport_readiness"]["resolution"],
        "after_remained_playing": after["remained_playing"],
        "after_stop_event_count": after["stop_event_count"],
        "retry_remained_playing": retry["remained_playing"],
        "retry_stop_event_count": retry["stop_event_count"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()
    root = args.artifacts_root

    settings_root = root / "phase6ct-runtime-settings"
    campfire_settings = _load(settings_root / "campfire.json")
    editor_settings = _load(settings_root / "editor_matched_extensions.json")
    campfire_flat = _flatten(campfire_settings["settings"])
    editor_flat = _flatten(editor_settings["settings"])
    keys = sorted(set(campfire_flat) | set(editor_flat))
    differences = [
        {
            "path": key,
            "campfire": campfire_flat.get(key),
            "editor": editor_flat.get(key),
        }
        for key in keys
        if campfire_flat.get(key) != editor_flat.get(key)
    ]

    raws = {
        "editor_matched_extension_set": _raw(
            root,
            "phase6ct-editor-shell",
            "plain_renderer_timeline_windowed_editor_base_shell.json",
        ),
        "campfire_editor_run_loops": _raw(
            root,
            "phase6ct-campfire-runloops",
            "plain_renderer_timeline_headless_campfire.json",
        ),
        "campfire_without_first_open_auto_frame": _raw(
            root,
            "phase6ct-campfire-no-autoframe",
            "plain_renderer_timeline_headless_campfire.json",
        ),
        "campfire_editor_graphics_defaults": _raw(
            root,
            "phase6ct-campfire-graphics",
            "plain_renderer_timeline_headless_campfire.json",
        ),
        "campfire_editor_persistent_resolution": _raw(
            root,
            "phase6ct-campfire-persistent-resolution",
            "plain_renderer_timeline_headless_campfire.json",
        ),
        "campfire_all_known_settings": _raw(
            root,
            "phase6ct-campfire-all-known-settings",
            "plain_renderer_timeline_headless_campfire.json",
        ),
        "campfire_fill_viewport": _raw(
            root,
            "phase6cs-minimal-camera-campfire-fill",
            "plain_renderer_timeline_windowed_campfire.json",
        ),
    }
    summaries = {name: _summary(raw) for name, raw in raws.items()}
    gates = {
        "settings_probe_completed": (
            campfire_settings["status"] == editor_settings["status"] == "ok"
        ),
        "sensitive_settings_roots_excluded": (
            campfire_settings["scope"]["sensitive_roots_excluded"]
            and editor_settings["scope"]["sensitive_roots_excluded"]
        ),
        "runtime_settings_delta_is_bounded": len(differences) == 15,
        "matched_extension_set_preserves_play": (
            _playing(raws["editor_matched_extension_set"])
            and _playing(
                raws["editor_matched_extension_set"],
                "after_viewport_frame_retry",
            )
        ),
        "matched_extension_set_retains_1280x720": summaries[
            "editor_matched_extension_set"
        ]["resolution"]
        == [1280, 720],
        "editor_run_loops_do_not_remove_stop": _stopped(
            raws["campfire_editor_run_loops"]
        ),
        "auto_frame_does_not_remove_stop": _stopped(
            raws["campfire_without_first_open_auto_frame"]
        ),
        "graphics_defaults_do_not_remove_stop": _stopped(
            raws["campfire_editor_graphics_defaults"]
        ),
        "persistent_resolution_does_not_remove_stop": _stopped(
            raws["campfire_editor_persistent_resolution"]
        ),
        "all_known_settings_do_not_remove_stop": (
            _stopped(raws["campfire_all_known_settings"])
            and _stopped(
                raws["campfire_all_known_settings"],
                "after_viewport_frame_retry",
            )
        ),
        "all_known_settings_retain_1280x720": summaries[
            "campfire_all_known_settings"
        ]["resolution"]
        == [1280, 720],
        "fill_viewport_workaround_still_preserves_play": (
            _playing(raws["campfire_fill_viewport"])
            and _playing(
                raws["campfire_fill_viewport"],
                "after_viewport_frame_retry",
            )
        ),
        "production_unchanged": all(
            not raw["scope"]["production_changed"] for raw in raws.values()
        ),
    }
    report = {
        "schema_version": 1,
        "phase": "phase6ct",
        "status": "ok" if all(gates.values()) else "failed",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "settings_scalar_counts": {
            "campfire": len(campfire_flat),
            "editor_matched_extensions": len(editor_flat),
            "difference_count": len(differences),
        },
        "runtime_settings_differences": differences,
        "timeline_matrix": summaries,
        "conclusion": {
            "extension_set_is_sufficient_for_stop": False,
            "captured_scalar_settings_values_are_sufficient_for_stop": False,
            "fill_viewport_true_is_a_measured_workaround": True,
            "workaround_adopted": False,
            "remaining_boundary": (
                "Application configuration initialization order, viewport creation "
                "timing, or internal state outside the non-sensitive settings "
                "allowlist. Compare a derived diagnostic .kit app before changing "
                "the production app."
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
        ("Matched extension set", "Editor base", "1280x720", "PLAY", "good"),
        ("15 scalar deltas found", "Allowlisted settings", "225 / 229", "BOUNDED", "info"),
        ("Run-loop group aligned", "Campfire", "1280x720", "STOP", "bad"),
        ("Viewport groups aligned", "Campfire", "1280x720", "STOP", "bad"),
        ("All 15 deltas aligned", "Campfire", "1280x720", "STOP x2", "bad"),
        ("fillViewport=true", "Campfire", "UI size", "PLAY", "good"),
    )
    row_svg = []
    for index, (test, app, resolution, outcome, css) in enumerate(rows):
        y = 238 + index * 54
        row_svg.append(
            f'<rect x="64" y="{y - 31}" width="1072" height="44" rx="9" class="row"/>'
            f'<text x="84" y="{y}" class="cell">{html.escape(test)}</text>'
            f'<text x="430" y="{y}" class="cell">{html.escape(app)}</text>'
            f'<text x="760" y="{y}" class="cell">{resolution}</text>'
            f'<text x="970" y="{y}" class="{css}">{outcome}</text>'
        )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6CT application settings boundary</title><desc id="desc">Matching the extension set and all fifteen allowlisted scalar settings differences does not remove the Campfire timeline stop. Fill viewport remains an unadopted workaround.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#111827"/><stop offset="1" stop-color="#4c1d95"/></linearGradient><style>.k{{font:700 18px system-ui;fill:#c4b5fd;letter-spacing:2px}}.t{{font:700 35px system-ui;fill:#f8fafc}}.s{{font:19px system-ui;fill:#cbd5e1}}.h{{font:700 15px system-ui;fill:#ddd6fe}}.cell{{font:17px system-ui;fill:#e2e8f0}}.good{{font:700 20px system-ui;fill:#86efac}}.bad{{font:700 20px system-ui;fill:#fca5a5}}.info{{font:700 18px system-ui;fill:#93c5fd}}.row{{fill:#0f172a;stroke:#475569;stroke-width:1}}.note{{font:17px system-ui;fill:#ede9fe}}</style></defs>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="58" class="k">PHASE 6CT · APP SETTINGS BOUNDARY</text><text x="64" y="108" class="t">Matching extensions and 15 settings is not enough</text><text x="64" y="145" class="s">Flow 110 fixed · Camera + Cube · production unchanged · fixed capture retained</text>
<text x="84" y="184" class="h">TEST</text><text x="430" y="184" class="h">APPLICATION</text><text x="760" y="184" class="h">VIEWPORT</text><text x="970" y="184" class="h">RESULT</text>{''.join(row_svg)}
<rect x="64" y="554" width="1072" height="78" rx="16" fill="#2e1065" stroke="#a78bfa" stroke-width="2"/><text x="88" y="586" class="s">Remaining: app initialization order, viewport creation timing, or non-allowlisted internal state</text><text x="88" y="613" class="note">fillViewport=true remains unadopted because it breaks deterministic fixed-resolution capture.</text></svg>'''
    args.svg.write_text(svg, encoding="utf-8")
    if report["status"] != "ok":
        raise SystemExit("Phase 6CT gates failed")


if __name__ == "__main__":
    main()
