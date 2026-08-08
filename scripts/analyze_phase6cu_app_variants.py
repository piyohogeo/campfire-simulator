"""Summarize the Phase 6CU derived-app initialization boundary."""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path


VARIANTS = (
    "editor_declared_head",
    "editor_declared_tail",
    "campfire_editor_order",
    "campfire_editor_order_window_extensions",
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
        directory = args.artifacts_root / f"phase6cu-{variant.replace('_', '-')}"
        manifest = _load(directory / "app_variant_manifest.json")
        raw = _load(directory / "plain_renderer_timeline_headless.json")
        production_hashes.add(manifest["production_app_sha256_before"])
        production_hashes.add(manifest["production_app_sha256_after"])
        variants.append(
            {
                "name": variant,
                "base_app": manifest["base_app"],
                "base_sha256": manifest["base_sha256"],
                "derived_sha256": manifest["output_sha256"],
                "production_changed": manifest["production_changed"],
                "resolution": raw["viewport_readiness"]["resolution"],
                "viewport_frame_completed": raw["gates"]["viewport_frame_completed"],
                "before_plays": _plays(raw, "before_viewport_frame"),
                "after_plays": _plays(raw, "after_viewport_frame"),
                "retry_plays": _plays(raw, "after_viewport_frame_retry"),
                "stage_update_node_count": len(raw["stage_update_nodes"]),
            }
        )

    baseline_path = (
        args.artifacts_root
        / "phase6ct-campfire-all-known-settings"
        / "plain_renderer_timeline_headless_campfire.json"
    )
    baseline = _load(baseline_path)
    gates = {
        "baseline_reproduces_stop": _stops(baseline, "after_viewport_frame")
        and _stops(baseline, "after_viewport_frame_retry"),
        "four_variants_measured": len(variants) == 4,
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
    }
    if not all(gates.values()):
        raise RuntimeError(f"Phase 6CU gate failed: {gates}")

    report = {
        "schema_version": 1,
        "phase": "phase6cu",
        "status": "ok",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "default_off": True,
            "production_changed": False,
            "scene": baseline["scene"],
            "flow_version": "110.0.0",
            "fixed_resolution": [1280, 720],
        },
        "campfire_baseline": {
            "after_stops": _stops(baseline, "after_viewport_frame"),
            "retry_stops": _stops(baseline, "after_viewport_frame_retry"),
        },
        "variants": variants,
        "gates": gates,
        "decision": {
            "direct_dependency_set_explains_stop": False,
            "direct_dependency_declaration_position_explains_stop": False,
            "window_extensions_dependency_explains_stop": False,
            "remaining_boundary": (
                "production root-app initialization: static declaration order, "
                "generated version lock, package metadata, or root lifecycle"
            ),
            "production_change_authorized": False,
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    rows = []
    labels = {
        "editor_declared_head": "Editor + declarations at head",
        "editor_declared_tail": "Editor + declarations at tail",
        "campfire_editor_order": "Campfire deps in Editor order",
        "campfire_editor_order_window_extensions": "Above + Extensions Manager",
    }
    for index, item in enumerate(variants):
        y = 238 + index * 64
        rows.append(
            f'<rect x="64" y="{y - 31}" width="1072" height="50" rx="9" class="row"/>'
            f'<text x="84" y="{y}" class="cell">{html.escape(labels[item["name"]])}</text>'
            f'<text x="682" y="{y}" class="cell">1280x720</text>'
            f'<text x="900" y="{y}" class="good">PLAY / PLAY</text>'
        )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6CU derived application initialization boundary</title><desc id="desc">All four Editor-rooted dependency variants remain playing after the viewport frame and retry, while the Campfire baseline stops.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#111827"/><stop offset="1" stop-color="#164e63"/></linearGradient><style>.k{{font:700 18px system-ui;fill:#67e8f9;letter-spacing:2px}}.t{{font:700 35px system-ui;fill:#f8fafc}}.s{{font:19px system-ui;fill:#cbd5e1}}.h{{font:700 15px system-ui;fill:#a5f3fc}}.cell{{font:17px system-ui;fill:#e2e8f0}}.good{{font:700 20px system-ui;fill:#86efac}}.bad{{font:700 20px system-ui;fill:#fca5a5}}.row{{fill:#0f172a;stroke:#475569}}.note{{font:17px system-ui;fill:#cffafe}}</style></defs>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="58" class="k">PHASE 6CU · ROOT APP INITIALIZATION</text><text x="64" y="108" class="t">Direct dependency composition does not reproduce STOP</text><text x="64" y="145" class="s">Flow 110.0.0 · same saved stage · production unchanged · fixed 1280x720</text>
<text x="84" y="184" class="h">DERIVED EDITOR-ROOTED APP</text><text x="682" y="184" class="h">VIEWPORT</text><text x="900" y="184" class="h">AFTER / RETRY</text>{''.join(rows)}
<rect x="64" y="480" width="1072" height="50" rx="9" class="row"/><text x="84" y="512" class="cell">Campfire root baseline</text><text x="682" y="512" class="cell">1280x720</text><text x="900" y="512" class="bad">STOP / STOP</text>
<rect x="64" y="558" width="1072" height="78" rx="16" fill="#083344" stroke="#22d3ee" stroke-width="2"/><text x="88" y="590" class="s">Remaining boundary: production root-app initialization, generated lock, metadata, or lifecycle</text><text x="88" y="617" class="note">Next: bisect root declarations in isolated derived apps; do not change production yet.</text></svg>'''
    args.svg.parent.mkdir(parents=True, exist_ok=True)
    args.svg.write_text(svg, encoding="utf-8")
    print(f"Phase 6CU: {sum(gates.values())}/{len(gates)} gates passed")


if __name__ == "__main__":
    main()
