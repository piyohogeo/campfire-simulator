"""Supersede the renderer STOP baseline confounded by Kit's frame quit cap."""

from __future__ import annotations

import argparse
import hashlib
import html
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


def _summary(raw: dict) -> dict:
    return {
        "viewport_readiness_seconds": raw["viewport_readiness"]["wall_seconds"],
        "resolution": raw["viewport_readiness"]["resolution"],
        "after_plays": _plays(raw, "after_viewport_frame"),
        "retry_plays": _plays(raw, "after_viewport_frame_retry"),
        "after_stop_events": _case(raw, "after_viewport_frame")[
            "stop_event_count"
        ],
        "retry_stop_events": _case(raw, "after_viewport_frame_retry")[
            "stop_event_count"
        ],
        "stage_update_node_count": len(raw["stage_update_nodes"]),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--historical-baseline", type=Path, required=True)
    parser.add_argument("--legacy-log", type=Path, required=True)
    parser.add_argument("--legacy-report", type=Path, required=True)
    parser.add_argument("--safe-report", type=Path, required=True)
    parser.add_argument("--isolated-report", type=Path, required=True)
    parser.add_argument("--production-sha-before", required=True)
    parser.add_argument("--production-sha-after", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()

    historical = _load(args.historical_baseline)
    safe = _load(args.safe_report)
    isolated = _load(args.isolated_report)
    legacy_log = args.legacy_log.read_text(encoding="utf-8-sig", errors="replace")
    legacy_autoquit = (
        "Application auto-quits as it worked for the specified number of frames: 900"
        in legacy_log
    )
    legacy_report = _load(args.legacy_report) if args.legacy_report.is_file() else None
    historical_scene = Path(historical["scene"])
    safe_scene = Path(safe["scene"])
    isolated_scene = Path(isolated["scene"])
    historical_summary = _summary(historical)
    safe_summary = _summary(safe)
    isolated_summary = _summary(isolated)

    gates = {
        "historical_stop_recorded": _stops(
            historical, "after_viewport_frame"
        )
        and _stops(historical, "after_viewport_frame_retry"),
        "legacy_900_frame_autoquit_observed": legacy_autoquit,
        "legacy_900_result_rejected": legacy_report is None
        or _stops(legacy_report, "after_viewport_frame")
        or _stops(legacy_report, "after_viewport_frame_retry"),
        "safe_30000_completed": safe["status"] == "ok",
        "safe_30000_preserves_play": safe_summary["after_plays"]
        and safe_summary["retry_plays"],
        "safe_30000_fixed_1280x720": safe_summary["resolution"] == [1280, 720],
        "isolated_cache_completed": isolated["status"] == "ok",
        "isolated_cache_preserves_play": isolated_summary["after_plays"]
        and isolated_summary["retry_plays"],
        "isolated_cache_fixed_1280x720": isolated_summary["resolution"]
        == [1280, 720],
        "stage_update_graph_complete": safe_summary["stage_update_node_count"] == 5
        and isolated_summary["stage_update_node_count"] == 5,
        "scene_bytes_equal": _sha256(historical_scene)
        == _sha256(safe_scene)
        == _sha256(isolated_scene),
        "production_app_unchanged": args.production_sha_before
        == args.production_sha_after,
    }
    status = "ok" if all(gates.values()) else "failed"
    report = {
        "schema_version": 1,
        "phase": "phase6cx",
        "status": status,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "default_off": True,
            "production_changed": False,
            "flow_version": "110.0.0",
            "fixed_resolution": [1280, 720],
            "existing_cache_deleted": False,
            "isolated_application_shader_cache_only": True,
        },
        "frame_limits": {
            "legacy": 900,
            "qualified": 30000,
            "unit": "application update frames",
        },
        "historical_phase6ct": historical_summary,
        "legacy_900_recheck": {
            "autoquit_observed": legacy_autoquit,
            "report_completed": legacy_report is not None,
            "result_accepted": False,
        },
        "safe_30000": safe_summary,
        "isolated_application_shader_cache_30000": isolated_summary,
        "production_app_sha256_before": args.production_sha_before,
        "production_app_sha256_after": args.production_sha_after,
        "gates": gates,
        "decision": {
            "phase6ct_stop_baseline_qualified": False,
            "phase6ct_stop_baseline_superseded": True,
            "phase6cu_to_phase6cw_causal_conclusions_superseded": True,
            "safe_cap_plain_renderer_stop_reproduced": False,
            "isolated_application_shader_cache_reproduces_stop": False,
            "root_app_fix_required_by_this_probe": False,
            "remaining_boundary": (
                "The plain-stage STOP was a diagnostic frame-limit artifact. "
                "Resident/Flow visual continuity must be requalified independently "
                "with the safe cap."
            ),
            "timeline_continuity_qualified": False,
            "seamless_visual_continuity_qualified": False,
            "flow_solver_state_checkpointed": False,
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    legacy_state = "NO REPORT" if legacy_report is None else "CONFOUNDED"
    rows = (
        (
            "Historical Phase 6CT",
            "900 frames",
            f"{historical_summary['viewport_readiness_seconds']:.1f} s",
            "STOP / STOP",
            "bad",
        ),
        ("Legacy limit recheck", "900 frames", "auto-quit", legacy_state, "bad"),
        (
            "Safe production control",
            "30,000 frames",
            f"{safe_summary['viewport_readiness_seconds']:.1f} s",
            "PLAY / PLAY",
            "good",
        ),
        (
            "Isolated app shader cache",
            "30,000 frames",
            f"{isolated_summary['viewport_readiness_seconds']:.1f} s",
            "PLAY / PLAY",
            "good",
        ),
    )
    row_svg = []
    for index, (test, limit, readiness, result, css) in enumerate(rows):
        y = 246 + index * 68
        row_svg.append(
            f'<rect x="64" y="{y - 38}" width="1072" height="54" rx="10" class="row"/>'
            f'<text x="84" y="{y}" class="cell">{html.escape(test)}</text>'
            f'<text x="455" y="{y}" class="cell">{html.escape(limit)}</text>'
            f'<text x="700" y="{y}" class="cell">{html.escape(readiness)}</text>'
            f'<text x="925" y="{y}" class="{css}">{html.escape(result)}</text>'
        )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6CX renderer quit-limit boundary</title><desc id="desc">The historical renderer stop is superseded because the 900 update-frame safety cap auto-quits before the probe completes. A 30000-frame cap preserves play with both warm and isolated application shader caches.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#0f172a"/><stop offset="1" stop-color="#134e4a"/></linearGradient><style>.k{{font:700 18px system-ui;fill:#99f6e4;letter-spacing:2px}}.t{{font:700 35px system-ui;fill:#f8fafc}}.s{{font:18px system-ui;fill:#cbd5e1}}.h{{font:700 15px system-ui;fill:#ccfbf1}}.cell{{font:17px system-ui;fill:#e2e8f0}}.good{{font:700 20px system-ui;fill:#86efac}}.bad{{font:700 18px system-ui;fill:#fca5a5}}.row{{fill:#111827;stroke:#475569}}.note{{font:17px system-ui;fill:#ccfbf1}}</style></defs>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="58" class="k">PHASE 6CX · QUIT-LIMIT BOUNDARY</text><text x="64" y="108" class="t">900 was a frame cap, not a time cap</text><text x="64" y="145" class="s">Same production app · same scene bytes · Flow 110.0.0 · fixed 1280×720 · production unchanged</text>
<text x="84" y="188" class="h">RUN</text><text x="455" y="188" class="h">SAFETY CAP</text><text x="700" y="188" class="h">VIEWPORT READY</text><text x="925" y="188" class="h">AFTER / RETRY</text>{''.join(row_svg)}
<rect x="64" y="510" width="1072" height="116" rx="16" fill="#042f2e" stroke="#5eead4" stroke-width="2"/><text x="88" y="548" class="s">Phase 6CT STOP baseline and the Phase 6CU–6CW causal contrast are superseded.</text><text x="88" y="580" class="note">Safe cap: production PLAY / PLAY; isolated application shader cache PLAY / PLAY.</text><text x="88" y="608" class="note">Resident/Flow video continuity remains a separate, unqualified issue.</text></svg>'''
    args.svg.write_text(svg, encoding="utf-8")
    if status != "ok":
        raise SystemExit(f"Phase 6CX gates failed: {gates}")
    print(f"Phase 6CX: {sum(gates.values())}/{len(gates)} gates passed")


if __name__ == "__main__":
    main()
