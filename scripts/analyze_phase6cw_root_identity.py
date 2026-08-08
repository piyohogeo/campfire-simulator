"""Summarize the Phase 6CW public root-identity boundary."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _case(raw: dict, name: str) -> dict:
    return next(item for item in raw["cases"] if item["name"] == name)


def _plays(raw: dict, name: str) -> bool:
    case = _case(raw, name)
    return (
        case["remained_playing"]
        and case["advanced_from_zero"]
        and case["stop_event_count"] == 0
    )


def _stops(raw: dict, name: str) -> bool:
    case = _case(raw, name)
    return (
        not case["remained_playing"]
        and not case["advanced_from_zero"]
        and case["stop_event_count"] == 1
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()

    production = _load(args.input_dir / "identity_production.json")
    distinct = _load(args.input_dir / "identity_derived.json")
    matching = _load(args.input_dir / "identity_matching_filename.json")
    timeline = _load(args.input_dir / "timeline_matching_filename.json")
    baseline = _load(args.baseline)
    manifest = _load(
        args.input_dir / "matching-filename" / "full_config_manifest.json"
    )

    compared_identity_keys = (
        "app_filename",
        "app_name",
        "app_environment",
        "app_version",
        "app_version_short",
        "build_version",
        "kernel_version",
        "kit_version",
        "platform",
        "is_app_external",
        "is_debug_build",
    )
    identity_matches = {
        key: production["identity"][key] == matching["identity"][key]
        for key in compared_identity_keys
    }
    gates = {
        "baseline_reproduces_stop": _stops(
            baseline, "after_viewport_frame"
        )
        and _stops(baseline, "after_viewport_frame_retry"),
        "three_identity_probes_completed": all(
            item["status"] == "ok" for item in (production, distinct, matching)
        ),
        "matching_filename_identity_equal": all(identity_matches.values()),
        "matching_settings_equal": production["settings"] == matching["settings"],
        "important_extensions_equal": production["enabled_extensions"]
        == matching["enabled_extensions"],
        "option_name_sets_equal": production["command_line"]["option_names"]
        == matching["command_line"]["option_names"],
        "matching_filename_preserves_play": _plays(
            timeline, "after_viewport_frame"
        )
        and _plays(timeline, "after_viewport_frame_retry"),
        "matching_filename_fixed_1280x720": timeline["viewport_readiness"][
            "resolution"
        ]
        == [1280, 720],
        "stage_update_graph_complete": len(timeline["stage_update_nodes"]) == 5,
        "production_app_unchanged": not manifest["production_changed"],
    }
    if not all(gates.values()):
        raise RuntimeError(f"Phase 6CW gate failed: {gates}")

    report = {
        "schema_version": 1,
        "phase": "phase6cw",
        "status": "ok",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "default_off": True,
            "production_changed": False,
            "flow_version": "110.0.0",
            "fixed_resolution": [1280, 720],
            "sensitive_argument_values_excluded": True,
        },
        "identity": {
            "production": production["identity"],
            "derived_distinct_filename": distinct["identity"],
            "derived_matching_filename": matching["identity"],
            "matching_fields": identity_matches,
        },
        "runtime_equivalence": {
            "settings_equal": gates["matching_settings_equal"],
            "important_extensions_equal": gates["important_extensions_equal"],
            "option_name_sets_equal": gates["option_name_sets_equal"],
        },
        "timeline": {
            "campfire_baseline_after_stops": _stops(
                baseline, "after_viewport_frame"
            ),
            "campfire_baseline_retry_stops": _stops(
                baseline, "after_viewport_frame_retry"
            ),
            "matching_filename_after_plays": _plays(
                timeline, "after_viewport_frame"
            ),
            "matching_filename_retry_plays": _plays(
                timeline, "after_viewport_frame_retry"
            ),
        },
        "gates": gates,
        "decision": {
            "app_filename_or_name_explains_stop": False,
            "public_app_identity_explains_stop": False,
            "remaining_boundary": (
                "root app load origin, config stack, or startup lifecycle not exposed "
                "by the matched public app identity and final enabled-extension set"
            ),
            "timeline_continuity_qualified": False,
            "seamless_visual_continuity_qualified": False,
            "flow_solver_state_checkpointed": False,
            "production_change_authorized": False,
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6CW public root application identity boundary</title><desc id="desc">A derived application named campfire.simulator matches the public production app identity and important extension set but remains playing after the viewport frame and retry, while the production root stops.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#0f172a"/><stop offset="1" stop-color="#3f1d5e"/></linearGradient><style>.k{font:700 18px system-ui;fill:#e9d5ff;letter-spacing:2px}.t{font:700 35px system-ui;fill:#f8fafc}.s{font:18px system-ui;fill:#cbd5e1}.h{font:700 15px system-ui;fill:#e9d5ff}.cell{font:17px system-ui;fill:#e2e8f0}.good{font:700 21px system-ui;fill:#86efac}.bad{font:700 21px system-ui;fill:#fca5a5}.row{fill:#111827;stroke:#64748b}.note{font:17px system-ui;fill:#f3e8ff}</style></defs>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="58" class="k">PHASE 6CW · PUBLIC ROOT IDENTITY</text><text x="64" y="108" class="t">Matching campfire.simulator identity still preserves PLAY</text><text x="64" y="145" class="s">Flow 110.0.0 · complete serialized config · same public identity · production unchanged</text>
<text x="84" y="194" class="h">ROOT</text><text x="500" y="194" class="h">PUBLIC IDENTITY</text><text x="905" y="194" class="h">AFTER / RETRY</text>
<rect x="64" y="215" width="1072" height="76" rx="12" class="row"/><text x="84" y="247" class="cell">Production campfire.simulator</text><text x="500" y="247" class="cell">filename/name/version match target</text><text x="905" y="247" class="bad">STOP / STOP</text><text x="84" y="275" class="s">release/apps origin</text>
<rect x="64" y="310" width="1072" height="76" rx="12" class="row"/><text x="84" y="342" class="cell">Derived campfire.simulator</text><text x="500" y="342" class="cell">11 / 11 identity fields equal</text><text x="905" y="342" class="good">PLAY / PLAY</text><text x="84" y="370" class="s">isolated artifact origin · fixed 1280x720 · 5 StageUpdate nodes</text>
<rect x="64" y="425" width="1072" height="88" rx="16" fill="#2e1065" stroke="#c084fc" stroke-width="2"/><text x="88" y="459" class="s">Also equal: selected settings, important extension IDs, non-sensitive option-name set</text><text x="88" y="489" class="note">App filename and public identity are not sufficient for STOP.</text>
<rect x="64" y="552" width="1072" height="70" rx="16" fill="#1e1b4b" stroke="#a78bfa" stroke-width="2"/><text x="88" y="582" class="s">Remaining: root load origin, config stack, or startup lifecycle outside public identity</text><text x="88" y="608" class="note">Continuity and Flow-state checkpoint qualifications remain false.</text></svg>'''
    args.svg.write_text(svg, encoding="utf-8")
    print(f"Phase 6CW: {sum(gates.values())}/{len(gates)} gates passed")


if __name__ == "__main__":
    main()
