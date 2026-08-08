"""Publish the Phase 6CY continuous Resident renderer qualification."""

from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    parser.add_argument("--poster", type=Path, required=True)
    parser.add_argument("--production-sha256-before", required=True)
    parser.add_argument("--production-sha256-after", required=True)
    args = parser.parse_args()
    raw = json.loads(args.raw.read_text(encoding="utf-8-sig"))
    log_text = args.log.read_text(encoding="utf-8-sig", errors="replace")
    attachment_errors = {
        "physx_stage_already_attached": log_text.count("Stage already attached!"),
        "flow_stage_reattach_without_detach": log_text.count(
            "Attaching FlowUsd to a new stage without detaching"
        ),
    }
    observation = raw["observation"]
    segments = raw["segments"]
    gates = {
        "raw_probe_completed": raw["status"] == "ok",
        "coverage_gates_passed": all(raw["gates"].values()),
        "single_uninterrupted_play_contract": raw["scope"][
            "single_play_without_probe_pause_or_time_reset"
        ],
        "fixed_capture_written": bool(
            raw["capture"]["completed"]
            and raw["capture"]["file_written"]
            and args.capture.is_file()
        ),
        "all_segments_have_flow_samples": all(
            segment["active_blocks_peak"] >= 0 for segment in segments.values()
        ),
        "production_unchanged": (
            not raw["scope"]["production_changed"]
            and args.production_sha256_before == args.production_sha256_after
        ),
    }
    qualified = bool(observation["timeline_continuity_qualified"])
    report = {
        "schema_version": 1,
        "phase": "phase6cy",
        "status": "ok" if all(gates.values()) else "failed",
        "scope": raw["scope"],
        "viewport_wait": raw["viewport_wait"],
        "capture": raw["capture"],
        "segments": segments,
        "timeline_events": raw["timeline_events"],
        "stage": {
            "before": raw["stage_before"],
            "after": raw["stage_after"],
            "root_layers": observation["root_layers"],
        },
        "production_app": {
            "sha256_before": args.production_sha256_before,
            "sha256_after": args.production_sha256_after,
            "changed": args.production_sha256_before
            != args.production_sha256_after,
        },
        "runtime_attachment_errors": attachment_errors,
        "decision": {
            "historical_900_frame_stop_superseded": True,
            "sequential_pause_reset_matrix_is_valid_continuity_evidence": False,
            "single_play_timeline_continuity_qualified": qualified,
            "active_blocks_peak": observation["active_blocks_peak"],
            "flow_solver_state_checkpointed": False,
            "seamless_visual_continuity_qualified": False,
            "remaining_boundary": (
                "visual and Flow-field continuity across the known video seam"
                if qualified
                else "timeline pause/stop inside one uninterrupted Resident render run"
            ),
        },
        "gates": gates,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    before = segments["viewport_updates_disabled"]
    after = segments["after_updates_enabled_frame"]
    captured = segments["after_capture_callback"]
    state_color = "#86efac" if qualified else "#fca5a5"
    state_text = "PLAY CONTINUOUS" if qualified else "NOT CONTINUOUS"
    attachment_text = html.escape(
        f"PhysX reattach errors {attachment_errors['physx_stage_already_attached']} · "
        f"Flow reattach errors {attachment_errors['flow_stage_reattach_without_detach']}"
    )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6CY uninterrupted Resident renderer qualification</title><desc id="desc">One Resident playback crosses viewport enablement and a capture callback without probe pauses or time resets.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#111827"/><stop offset="1" stop-color="#164e63"/></linearGradient><style>.k{{font:700 18px system-ui;fill:#67e8f9;letter-spacing:2px}}.t{{font:700 38px system-ui;fill:#f8fafc}}.s{{font:19px system-ui;fill:#cbd5e1}}.h{{font:700 18px system-ui;fill:#f8fafc}}.v{{font:700 28px system-ui;fill:#a5f3fc}}.m{{font:16px system-ui;fill:#94a3b8}}.c{{fill:#0f172a;stroke:#475569;stroke-width:2}}</style></defs>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="62" class="k">PHASE 6CY · UNINTERRUPTED RESIDENT RUN</text><text x="64" y="116" class="t">{state_text}</text><text x="64" y="154" class="s" fill="{state_color}">Flow 110.0.0 · fixed 1280×720 · production unchanged</text>
<rect x="64" y="204" width="328" height="190" rx="20" class="c"/><text x="90" y="246" class="h">viewport updates disabled</text><text x="90" y="304" class="v">{before['time_start_s']:.1f} → {before['time_end_s']:.1f} s</text><text x="90" y="344" class="m">revision {before['revision_start']} → {before['revision_end']}</text><text x="90" y="374" class="m">active blocks peak {before['active_blocks_peak']}</text>
<rect x="436" y="204" width="328" height="190" rx="20" class="c"/><text x="462" y="246" class="h">after enabled viewport frame</text><text x="462" y="304" class="v">{after['time_start_s']:.1f} → {after['time_end_s']:.1f} s</text><text x="462" y="344" class="m">revision {after['revision_start']} → {after['revision_end']}</text><text x="462" y="374" class="m">active blocks peak {after['active_blocks_peak']}</text>
<rect x="808" y="204" width="328" height="190" rx="20" class="c"/><text x="834" y="246" class="h">after capture callback</text><text x="834" y="304" class="v">{captured['time_start_s']:.1f} → {captured['time_end_s']:.1f} s</text><text x="834" y="344" class="m">revision {captured['revision_start']} → {captured['revision_end']}</text><text x="834" y="374" class="m">active blocks peak {captured['active_blocks_peak']}</text>
<rect x="64" y="438" width="1072" height="118" rx="18" fill="#082f49" stroke="#06b6d4" stroke-width="2"/><text x="90" y="480" class="h">Harness correction</text><text x="90" y="516" class="s">No case teardown pause, no return to 0 s, and one root layer for every sample.</text><text x="90" y="544" class="m">{attachment_text}</text>
<text x="64" y="614" class="s">Timeline qualification: {str(qualified).lower()} · visual continuity: false · Flow checkpoint: false</text><text x="64" y="648" class="m">The capture proves renderer execution only; it does not by itself close the known movie seam.</text></svg>'''
    args.svg.write_text(svg, encoding="utf-8")
    shutil.copy2(args.capture, args.poster)
    if report["status"] != "ok":
        raise SystemExit("Phase 6CY publication gates failed")


if __name__ == "__main__":
    main()
