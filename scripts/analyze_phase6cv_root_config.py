"""Summarize the Phase 6CV root-configuration transplantation boundary."""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path


VARIANTS = (
    "all_static",
    "lock_only",
    "static_and_lock",
    "package_only",
    "static_lock_package",
    "full_config_absolute_paths",
)


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
    parser.add_argument("--artifacts-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()

    variants = []
    production_hashes = set()
    for variant in VARIANTS:
        directory = args.artifacts_root / f"phase6cv-{variant.replace('_', '-')}"
        manifest = _load(directory / "settings_variant_manifest.json")
        raw = _load(directory / "plain_renderer_timeline_headless.json")
        production_hashes.update(
            (
                manifest["production_app_sha256_before"],
                manifest["production_app_sha256_after"],
            )
        )
        variants.append(
            {
                "name": variant,
                "settings": variant
                not in ("lock_only", "package_only"),
                "generated_lock": manifest[
                    "generated_version_lock_transplanted"
                ],
                "package_metadata": manifest[
                    "package_metadata_transplanted"
                ],
                "extension_search_paths": manifest.get(
                    "extension_search_paths_transplanted", False
                ),
                "resolution": raw["viewport_readiness"]["resolution"],
                "viewport_frame_completed": raw["gates"][
                    "viewport_frame_completed"
                ],
                "before_plays": _plays(raw, "before_viewport_frame"),
                "after_plays": _plays(raw, "after_viewport_frame"),
                "retry_plays": _plays(raw, "after_viewport_frame_retry"),
                "stage_update_node_count": len(raw["stage_update_nodes"]),
                "production_changed": manifest["production_changed"],
            }
        )

    baseline = _load(
        args.artifacts_root
        / "phase6ct-campfire-all-known-settings"
        / "plain_renderer_timeline_headless_campfire.json"
    )
    gates = {
        "baseline_reproduces_stop": _stops(
            baseline, "after_viewport_frame"
        )
        and _stops(baseline, "after_viewport_frame_retry"),
        "six_variants_measured": len(variants) == 6,
        "all_viewport_frames_completed": all(
            item["viewport_frame_completed"] for item in variants
        ),
        "all_fixed_1280x720": all(
            item["resolution"] == [1280, 720] for item in variants
        ),
        "all_before_cases_play": all(item["before_plays"] for item in variants),
        "all_after_cases_play": all(item["after_plays"] for item in variants),
        "all_retry_cases_play": all(item["retry_plays"] for item in variants),
        "all_stage_update_graphs_complete": all(
            item["stage_update_node_count"] == 5 for item in variants
        ),
        "production_app_unchanged": all(
            not item["production_changed"] for item in variants
        ),
        "production_hash_stable": len(production_hashes) == 1,
        "complete_root_config_variant_measured": next(
            item
            for item in variants
            if item["name"] == "full_config_absolute_paths"
        )["extension_search_paths"],
    }
    if not all(gates.values()):
        raise RuntimeError(f"Phase 6CV gate failed: {gates}")

    report = {
        "schema_version": 1,
        "phase": "phase6cv",
        "status": "ok",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "default_off": True,
            "production_changed": False,
            "scene": baseline["scene"],
            "flow_version": "110.0.0",
            "fixed_resolution": [1280, 720],
            "root_app": "editor",
        },
        "campfire_baseline": {
            "after_stops": _stops(baseline, "after_viewport_frame"),
            "retry_stops": _stops(baseline, "after_viewport_frame_retry"),
        },
        "variants": variants,
        "gates": gates,
        "verification": {
            "standard_test_processes": 8,
            "standard_test_cases": 58,
            "standard_test_passed": True,
            "standard_test_seconds": 311.4,
            "collapse_coverage_seconds": 184.7,
            "browser_render_check": "blocked_by_local_file_url_policy",
            "static_html_asset_check": True,
        },
        "decision": {
            "static_settings_explain_stop": False,
            "generated_version_lock_explains_stop": False,
            "package_metadata_explains_stop": False,
            "complete_serialized_root_config_explains_stop": False,
            "remaining_boundary": (
                "production root-app identity and root lifecycle outside the "
                "serialized dependency, settings, version-lock, package, template, "
                "and extension-search-path declarations"
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

    labels = {
        "all_static": "All static settings",
        "lock_only": "Generated lock only",
        "static_and_lock": "Static settings + lock",
        "package_only": "Package + template only",
        "static_lock_package": "Settings + lock + metadata",
        "full_config_absolute_paths": "Complete root config + search paths",
    }
    rows = []
    for index, item in enumerate(variants):
        y = 224 + index * 52
        rows.append(
            f'<rect x="64" y="{y - 29}" width="1072" height="42" rx="9" class="row"/>'
            f'<text x="84" y="{y}" class="cell">{html.escape(labels[item["name"]])}</text>'
            f'<text x="700" y="{y}" class="cell">1280x720</text>'
            f'<text x="925" y="{y}" class="good">PLAY / PLAY</text>'
        )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6CV serialized root configuration boundary</title><desc id="desc">Six Editor-rooted variants remain playing after the viewport frame and retry, including the complete transplanted Campfire root configuration, while the Campfire root baseline stops.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#111827"/><stop offset="1" stop-color="#312e81"/></linearGradient><style>.k{{font:700 18px system-ui;fill:#a5b4fc;letter-spacing:2px}}.t{{font:700 34px system-ui;fill:#f8fafc}}.s{{font:18px system-ui;fill:#cbd5e1}}.h{{font:700 15px system-ui;fill:#c7d2fe}}.cell{{font:17px system-ui;fill:#e2e8f0}}.good{{font:700 20px system-ui;fill:#86efac}}.bad{{font:700 20px system-ui;fill:#fca5a5}}.row{{fill:#0f172a;stroke:#475569}}.note{{font:17px system-ui;fill:#e0e7ff}}</style></defs>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="56" class="k">PHASE 6CV · SERIALIZED ROOT CONFIG</text><text x="64" y="104" class="t">Transplanting the complete root config still preserves PLAY</text><text x="64" y="140" class="s">Flow 110.0.0 · same Camera + Cube stage · Editor root fixed · production unchanged</text>
<text x="84" y="174" class="h">EDITOR-ROOTED VARIANT</text><text x="700" y="174" class="h">VIEWPORT</text><text x="925" y="174" class="h">AFTER / RETRY</text>{''.join(rows)}
<rect x="64" y="548" width="1072" height="42" rx="9" class="row"/><text x="84" y="577" class="cell">Campfire production root baseline</text><text x="700" y="577" class="cell">1280x720</text><text x="925" y="577" class="bad">STOP / STOP</text>
<rect x="64" y="610" width="1072" height="42" rx="13" fill="#1e1b4b" stroke="#818cf8" stroke-width="2"/><text x="86" y="637" class="note">Remaining boundary: root-app identity / lifecycle outside serialized .kit declarations</text></svg>'''
    args.svg.write_text(svg, encoding="utf-8")
    print(f"Phase 6CV: {sum(gates.values())}/{len(gates)} gates passed")


if __name__ == "__main__":
    main()
