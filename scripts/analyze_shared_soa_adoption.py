"""Re-evaluate the shared-SoA proxy after the resident path was qualified."""

from __future__ import annotations

import argparse
import html
import json
import statistics
from pathlib import Path


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _p95(report, name):
    return float(report["timing"][name]["p95_ms"])


def _svg(report):
    evidence = report["evidence"]
    proxy = evidence["shared_proxy"]
    current = evidence["current_resident"]
    rows = (
        ("Dataclass scalar write", proxy["dataclass_scalar_write_p95_ms"], "#64748b"),
        ("Proxy scalar write", proxy["proxy_scalar_write_p95_ms"], "#38bdf8"),
        ("Proxy 32-field edit", proxy["proxy_batch_edit_p95_ms"], "#2dd4bf"),
        ("Current shutdown export", current["shutdown_export_median_ms"], "#f59e0b"),
    )
    maximum = max(value for _, value, _ in rows)
    rendered = []
    for index, (label, value, color) in enumerate(rows):
        y = 221 + index * 58
        width = max(2.0, 326.0 * value / maximum)
        rendered.append(
            f'<text x="70" y="{y}" class="label">{html.escape(label)}</text>'
            f'<rect x="304" y="{y - 18}" width="{width:.2f}" height="23" rx="6" fill="{color}"/>'
            f'<text x="{316 + width:.2f}" y="{y}" class="value">{value:.4f} ms p95</text>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6BW shared SoA adoption re-evaluation</title>
<desc id="desc">The existing resident lifecycle already has no hot-path re-import, while a shared proxy adds compatibility and lifetime complexity. Adoption remains deferred.</desc>
<style>
.bg{{fill:#08121f}} .panel{{fill:#111f31;stroke:#29415f;stroke-width:1.5}} .title{{fill:#f7fafc;font:700 30px system-ui,sans-serif}} .subtitle{{fill:#9fb3c8;font:15px system-ui,sans-serif}} .head{{fill:#7dd3fc;font:700 16px system-ui,sans-serif}} .label{{fill:#dce7f2;font:14px system-ui,sans-serif}} .value{{fill:#f7fafc;font:700 13px ui-monospace,monospace}} .body{{fill:#b9c8d8;font:14px system-ui,sans-serif}} .ok{{fill:#86efac;font:700 17px system-ui,sans-serif}} .warn{{fill:#fbbf24;font:700 15px system-ui,sans-serif}}
</style>
<rect width="1200" height="680" class="bg"/>
<text x="64" y="58" class="title">Phase 6BW · Shared SoA adoption re-evaluation</text>
<text x="64" y="87" class="subtitle">Post-ChangeBlock evidence · production code and defaults unchanged</text>
<rect x="50" y="118" width="710" height="344" rx="16" class="panel"/>
<text x="70" y="154" class="head">Measured boundaries</text>
{''.join(rendered)}
<rect x="784" y="118" width="366" height="344" rx="16" class="panel"/>
<text x="808" y="154" class="head">Current 1,200-step lifecycle</text>
<text x="808" y="197" class="ok">0 hot-path re-imports</text>
<text x="808" y="237" class="body">1 initial object → SoA import</text>
<text x="808" y="267" class="body">1,200 native steps on resident SoA</text>
<text x="808" y="297" class="body">240 immutable snapshot publications</text>
<text x="808" y="327" class="body">1 shutdown export for serialization</text>
<text x="808" y="367" class="warn">Mid-run Python edits are unsupported</text>
<text x="808" y="397" class="body">Proxy value appears only if that feature is required.</text>
<rect x="50" y="486" width="1100" height="142" rx="16" class="panel"/>
<text x="70" y="522" class="head">Decision</text>
<text x="70" y="558" class="body">Keep the current private resident SoA + immutable snapshot lifecycle. It already avoids numeric re-import in the hot path.</text>
<text x="70" y="588" class="body">Reopen proxy adoption only for a concrete mid-run edit requirement, with a bulk serializer and revocable edit leases.</text>
<text x="70" y="614" class="warn">Deferred, not rejected: shared SoA does not reduce USD publication, Flow ingestion, or rasterization cost.</text>
</svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shared", required=True, type=Path)
    parser.add_argument("--native", required=True, type=Path)
    parser.add_argument("--change-block", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    args = parser.parse_args()

    shared = _load(args.shared)
    native = _load(args.native)
    change_block = _load(args.change_block)
    if shared["decision"]["technical_feasibility"] != "qualified":
        raise ValueError("Shared SoA feasibility is not qualified")
    if not all(shared["correctness"]["gates"].values()):
        raise ValueError("Shared SoA contract gate failed")
    if not native["decision"]["functional_contract_qualified"]:
        raise ValueError("Resident native lifecycle is not functionally qualified")
    if not change_block["decision"]["standardize_for_lightweight_path"]:
        raise ValueError("Resident ChangeBlock path is not qualified")

    shutdown_exports = [
        float(pair["native"]["shutdown_export_ms"]) for pair in native["pairs"]
    ]
    report = {
        "schema_version": 1,
        "phase": "phase6bw",
        "status": "adoption_deferred",
        "scope": {
            "production_code_changed": False,
            "production_defaults_changed": False,
            "physics_changed": False,
            "json_schema_changed": False,
            "usd_publication_changed": False,
        },
        "evidence": {
            "current_resident": {
                "authority_during_run": native["contract"]["authority_during_native_run"],
                "steps_per_run": native["measurement"]["steps_per_run"],
                "snapshot_publications_per_run": native["measurement"]["published_revisions_per_run"],
                "initial_imports_per_run": 1,
                "hot_path_reimports_per_run": 0,
                "shutdown_exports_per_run": 1,
                "shutdown_export_ms": shutdown_exports,
                "shutdown_export_median_ms": statistics.median(shutdown_exports),
                "native_step_p95_median_ms": native["timing"]["median_native_model_p95_ms"],
                "change_block_usd_p95_median_ms": change_block["performance"]["median_change_block_p95_ms"],
                "unmanaged_python_edits_supported": native["contract"]["unmanaged_python_edits_supported"],
            },
            "shared_proxy": {
                "cell_count": shared["measurement"]["cell_count"],
                "contract_gates_passed": sum(bool(value) for value in shared["correctness"]["gates"].values()),
                "contract_gate_count": len(shared["correctness"]["gates"]),
                "numeric_dirty_imports": shared["correctness"]["import_count"],
                "dataclass_scalar_read_p95_ms": _p95(shared, "dataclass_scalar_read"),
                "proxy_scalar_read_p95_ms": _p95(shared, "proxy_scalar_read"),
                "dataclass_scalar_write_p95_ms": _p95(shared, "dataclass_scalar_write"),
                "proxy_scalar_write_p95_ms": _p95(shared, "proxy_transactional_scalar_write"),
                "proxy_batch_edit_p95_ms": _p95(shared, "proxy_32_field_batch_edit"),
                "direct_soa_json_p95_ms": _p95(shared, "direct_soa_json_serialization"),
                "dataclass_json_p95_ms": _p95(shared, "dataclass_json_serialization"),
                "buffer_lifetime_revocable": False,
                "full_dataclass_compatibility": False,
            },
        },
        "decision": {
            "production_adoption": "deferred",
            "reason": (
                "The current resident lifecycle already performs zero numeric re-imports "
                "during its 1,200-step hot path. A proxy would primarily add a new mid-run "
                "editing feature, while increasing API, locking, stale-reference, buffer-lifetime, "
                "and serialization complexity."
            ),
            "usd_bottleneck_effect": "none",
            "reopen_when": [
                "a supported mid-run per-cell Python edit workflow is required",
                "measured edit/re-import cost is material in an application workload",
                "writable arrays remain private behind fail-fast edit leases",
                "a bulk serializer meets or beats the current canonical serializer",
                "full resident rollback, restart, snapshot, and consumer-revision gates pass",
            ],
            "next_work": (
                "Harden the existing default-off resident native lifecycle with native failure, "
                "downstream publication failure, shutdown, and restart recovery gates."
            ),
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.svg.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.svg.write_text(_svg(report), encoding="utf-8")
    print(f"Shared SoA adoption report: {args.report}")
    print(f"Shared SoA adoption SVG: {args.svg}")


if __name__ == "__main__":
    main()
