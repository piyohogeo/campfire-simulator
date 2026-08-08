"""Analyze paired profiler-off FlowUsd StageUpdate enablement runs."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


PAIR_COUNT = 3
METRICS = {
    "enclosing_update_mean_ms": ("update", "all_ms", "mean_ms"),
    "enclosing_update_p95_ms": ("update", "all_ms", "p95_ms"),
    "changed_update_p95_ms": ("update", "changed_ms", "p95_ms"),
    "unchanged_update_p95_ms": ("update", "unchanged_ms", "p95_ms"),
    "layout_exit_p95_ms": (
        "publication",
        "sidecar",
        "live_translation_timing_ms",
        "change_block_exit",
        "p95_ms",
    ),
    "channel_exit_p95_ms": (
        "publication",
        "sidecar",
        "live_translation_timing_ms",
        "channel_only_change_block_exit",
        "p95_ms",
    ),
    "layout_transaction_p95_ms": (
        "publication",
        "sidecar",
        "live_translation_timing_ms",
        "publish_transaction",
        "p95_ms",
    ),
    "channel_transaction_p95_ms": (
        "publication",
        "sidecar",
        "live_translation_timing_ms",
        "channel_only_publish_transaction",
        "p95_ms",
    ),
}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _value(data: dict, path: tuple[str, ...]) -> float:
    current = data
    for key in path:
        current = current[key]
    return float(current)


def _median(values) -> float:
    return round(float(statistics.median(values)), 6)


def _metric_summary(cases: list[dict], path: tuple[str, ...]) -> dict:
    enabled = [_value(case, path) for case in cases if case["flow_usd_enabled"]]
    disabled = [_value(case, path) for case in cases if not case["flow_usd_enabled"]]
    enabled_median = _median(enabled)
    disabled_median = _median(disabled)
    delta = enabled_median - disabled_median
    return {
        "enabled_runs": [round(value, 6) for value in enabled],
        "disabled_runs": [round(value, 6) for value in disabled],
        "enabled_median": enabled_median,
        "disabled_median": disabled_median,
        "enabled_minus_disabled_ms": round(delta, 6),
        "enabled_minus_disabled_percent": (
            round(delta / disabled_median * 100.0, 4)
            if disabled_median
            else None
        ),
    }


def _render_svg(report: dict) -> str:
    metrics = report["timing"]
    rows = (
        ("Enclosing update", metrics["enclosing_update_p95_ms"]),
        ("Layout ChangeBlock exit", metrics["layout_exit_p95_ms"]),
        ("Channel ChangeBlock exit", metrics["channel_exit_p95_ms"]),
    )
    maximum = max(
        max(values["enabled_median"], values["disabled_median"])
        for _, values in rows
    ) or 1.0
    row_svg = []
    for index, (label, values) in enumerate(rows):
        y = 253 + index * 108
        enabled_width = max(2.0, 500.0 * values["enabled_median"] / maximum)
        disabled_width = max(2.0, 500.0 * values["disabled_median"] / maximum)
        row_svg.append(
            f'<text x="80" y="{y}" class="label">{label}</text>'
            f'<rect x="360" y="{y - 29}" width="{enabled_width:.2f}" height="25" rx="6" fill="#fb923c"/>'
            f'<text x="875" y="{y - 9}" class="value">ON {values["enabled_median"]:.4f} ms</text>'
            f'<rect x="360" y="{y + 8}" width="{disabled_width:.2f}" height="25" rx="6" fill="#38bdf8"/>'
            f'<text x="875" y="{y + 28}" class="value">OFF {values["disabled_median"]:.4f} ms</text>'
        )
    update_delta = metrics["enclosing_update_p95_ms"][
        "enabled_minus_disabled_percent"
    ]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6DF FlowUsd StageUpdate enablement boundary</title><desc id="desc">Three paired profiler-off runs compare the enabled and disabled FlowUsd StageUpdate node. Authoritative and Point source outputs remain identical, but disabled Flow output is absent and cannot qualify production adoption.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#112b3d"/><stop offset="1" stop-color="#352037"/></linearGradient></defs><style>.k{{font:700 17px 'Segoe UI',sans-serif;fill:#93c5fd;letter-spacing:2px}}.title{{font:750 34px 'Segoe UI',sans-serif;fill:#f8fafc}}.sub{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.label{{font:650 17px 'Segoe UI',sans-serif;fill:#e2e8f0}}.value{{font:700 15px 'Segoe UI',sans-serif;fill:#f8fafc}}.good{{font:750 21px 'Segoe UI',sans-serif;fill:#86efac}}.warn{{font:650 16px 'Segoe UI',sans-serif;fill:#fbbf24}}.note{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}</style>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="61" class="k">PHASE 6DF · FLOWUSD STAGEUPDATE CONTROL</text><text x="64" y="111" class="title">StageUpdate OFF is a diagnostic contrast, not an optimization</text><text x="64" y="150" class="sub">3 paired runs · profiler OFF · 720 points · 500 revisions/run · fixed 1280×720 viewport</text>
<rect x="56" y="188" width="1088" height="365" rx="20" fill="#0b2032"/>{''.join(row_svg)}
<text x="64" y="592" class="good">{report['gates_passed']} / {report['gate_count']} gates · source hashes exact · revisions 500/500/500</text>
<text x="64" y="623" class="warn">Enclosing update p95 ON−OFF: {update_delta:+.2f}% — OFF also removes Flow blocks and NanoVDB output.</text>
<text x="64" y="652" class="note">ChangeBlock timing remains live in both modes; this toggle does not unregister synchronous USD notice subscribers or isolate direct ingest cost.</text></svg>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    parser.add_argument("--production-sha256-before", required=True)
    parser.add_argument("--production-sha256-after", required=True)
    args = parser.parse_args()

    case_paths = sorted(args.root.glob("pair*-*/case.json"))
    cases = [_read(path) for path in case_paths]
    manifests = [_read(path.parent / "manifest.json") for path in case_paths]
    enabled = [case for case in cases if case["flow_usd_enabled"]]
    disabled = [case for case in cases if not case["flow_usd_enabled"]]
    pairs = {
        pair: [case for case in cases if case["label"] == pair]
        for pair in (f"pair{index}" for index in range(PAIR_COUNT))
    }

    native_hashes = {case["outputs"]["native_state_sha256"] for case in cases}
    point_hashes = {
        field: {case["outputs"]["point"][field]["sha256"] for case in cases}
        for field in ("positions", "fuels", "temperatures", "smokes")
    }
    gates = {
        "six_cases_captured": len(cases) == PAIR_COUNT * 2,
        "three_enabled_and_disabled": len(enabled) == len(disabled) == PAIR_COUNT,
        "each_pair_has_both_modes": all(
            len(pair_cases) == 2
            and {case["flow_usd_enabled"] for case in pair_cases} == {True, False}
            for pair_cases in pairs.values()
        ),
        "all_case_gates_passed": all(
            case["status"] == "ok" and all(case["gates"].values())
            for case in cases
        ),
        "profiler_capture_disabled_all_runs": all(
            case["runtime"]["profiler_capture_mask"] == 0
            and case["runtime"]["profiler_capture_mask_after"] == 0
            and not case["update"]["profiler_capture_enabled"]
            for case in cases
        ),
        "flow_node_restored_all_runs": all(
            case["control"]["node_restored"] for case in cases
        ),
        "revisions_exact_all_runs": all(
            case["publication"]["revisions"] == [500, 500, 500]
            for case in cases
        ),
        "native_state_exact_across_modes": len(native_hashes) == 1,
        "point_source_arrays_exact_across_modes": all(
            len(hashes) == 1 for hashes in point_hashes.values()
        ),
        "enabled_flow_output_present": all(
            case["flow"]["active_blocks_max"] > 0
            and all(
                case["flow"]["readback"][name]["count"] > 0
                for name in ("temperature", "fuel", "burn", "smoke", "velocity")
            )
            for case in enabled
        ),
        "disabled_flow_output_absent": all(
            case["flow"]["active_blocks_max"] == 0
            and not any(
                value["count"] > 0
                for value in case["flow"]["readback"].values()
            )
            for case in disabled
        ),
        "publication_integrity_all_runs": all(
            case["publication"]["sidecar"]["prepare_count"] == 500
            and case["publication"]["sidecar"]["publish_count"] == 500
            and case["publication"]["sidecar"]["failure_count"] == 0
            and not case["publication"]["point_resyncs"]
            and not case["publication"]["unexpected_point_changes"]
            for case in cases
        ),
        "production_app_unchanged": (
            args.production_sha256_before == args.production_sha256_after
            and all(not manifest["production_changed"] for manifest in manifests)
        ),
    }
    if not all(gates.values()):
        raise RuntimeError(f"Phase 6DF gates failed: {gates}")

    timing = {
        name: _metric_summary(cases, path) for name, path in METRICS.items()
    }
    report = {
        "phase": "phase6df",
        "status": "ok",
        "scope": "profiler-off FlowUsd StageUpdate enablement boundary",
        "run_count": len(cases),
        "pair_count": PAIR_COUNT,
        "execution_order_design": [
            "pair0-enabled",
            "pair0-disabled",
            "pair1-disabled",
            "pair1-enabled",
            "pair2-enabled",
            "pair2-disabled",
        ],
        "case_paths_sorted": [path.parent.name for path in case_paths],
        "timing": timing,
        "output_equivalence": {
            "native_state_sha256": next(iter(native_hashes)),
            "point_array_sha256": {
                field: next(iter(hashes)) for field, hashes in point_hashes.items()
            },
            "resident_revisions": [500, 500, 500],
            "source_values_equal": True,
            "flow_output_equal": False,
            "flow_output_difference_expected": (
                "disabled FlowUsd StageUpdate produces zero active blocks/readback"
            ),
        },
        "flow_boundary": {
            "enabled_active_block_maxima": [
                case["flow"]["active_blocks_max"] for case in enabled
            ],
            "disabled_active_block_maxima": [
                case["flow"]["active_blocks_max"] for case in disabled
            ],
            "enabled_readback_counts": [
                {
                    name: value["count"]
                    for name, value in case["flow"]["readback"].items()
                }
                for case in enabled
            ],
            "disabled_readback_counts": [
                {
                    name: value["count"]
                    for name, value in case["flow"]["readback"].items()
                }
                for case in disabled
            ],
        },
        "interpretation": {
            "qualified": (
                "The StageUpdate node can be configured before the derived target "
                "stage connects and restored after the run. Authoritative wood state, "
                "Point source arrays, publication counts, and revisions remain exact."
            ),
            "not_qualified": (
                "The disabled contrast removes Flow simulation output, so its timing "
                "difference is not an output-equivalent optimization or direct ingest "
                "timer. StageUpdate disablement does not prove that synchronous USD "
                "notice subscribers were unregistered."
            ),
            "phase6dd_effect": (
                "ChangeBlock exit remains measurable in both modes; the Phase 6DD "
                "residual still cannot be assigned wholly to FlowUsd StageUpdate."
            ),
            "next": (
                "Inspect whether a derived extension-disable control can remove the "
                "FlowUsd notice subscriber before stage connection without changing "
                "USD schemas; do not adopt it before API and output consequences are proven."
            ),
        },
        "gates": gates,
        "gates_passed": sum(gates.values()),
        "gate_count": len(gates),
        "production_app": {
            "sha256_before": args.production_sha256_before,
            "sha256_after": args.production_sha256_after,
            "changed_during_run": False,
        },
        "contracts": {
            "production_default": "OFF",
            "production_sphere_emitter_changed": False,
            "point_production_adopted": False,
            "physics_changed": False,
            "json_schema_changed": False,
            "serialization_changed": False,
            "usd_save_changed": False,
            "rollback_changed": False,
            "revision_changed": False,
            "immutable_snapshot_changed": False,
            "flow_version": "110.0.0",
        },
        "video": {
            "reused": "resident_translation_breakdown.mp4",
            "reason": "same deterministic Resident translation source publication",
            "disabled_case_visual_success": False,
            "success_criterion": "not video-only",
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.svg.write_text(_render_svg(report), encoding="utf-8")
    print(f"Phase 6DF: {sum(gates.values())}/{len(gates)} gates passed")


if __name__ == "__main__":
    main()
