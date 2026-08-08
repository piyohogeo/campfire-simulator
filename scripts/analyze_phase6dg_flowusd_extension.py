"""Analyze the isolated Phase 6DG Flow USD extension boundary probe."""

from __future__ import annotations

import argparse
import json
import tomllib
from datetime import datetime, timezone
from pathlib import Path


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _load_toml(path: Path) -> dict:
    with path.open("rb") as stream:
        return tomllib.load(stream)


def _kit_dependencies(path: Path) -> set[str]:
    """Read only the first dependency table from Kit's generated TOML dialect."""
    text = path.read_text(encoding="utf-8")
    dependency_body = text.split("[dependencies]", 1)[1].split("\n[", 1)[0]
    return {
        line.split("=", 1)[0].strip().strip('"')
        for line in dependency_body.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_svg(path: Path, report: dict) -> None:
    conclusions = report["runtime"]["conclusions"]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6DG Flow USD extension lifecycle boundary</title><desc id="desc">The public disable request removes Flow USD and its StageUpdate node, but also cascades to the required campfire.app dependent. The Flow schema remains loaded and the original state is restored.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#101923"/><stop offset="1" stop-color="#1b2935"/></linearGradient><style>.k{{font:700 18px system-ui;fill:#72d6ba;letter-spacing:2px}}.title{{font:700 34px system-ui;fill:#f2f6f8}}.sub{{font:18px system-ui;fill:#b9c9d3}}.h{{font:700 21px system-ui;fill:#f2f6f8}}.v{{font:700 24px system-ui;fill:#72d6ba}}.bad{{font:700 24px system-ui;fill:#ffb36b}}.m{{font:16px system-ui;fill:#b9c9d3}}.box{{fill:#213340;stroke:#395363;stroke-width:2}}</style></defs>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="61" class="k">PHASE 6DG · EXTENSION LIFECYCLE</text><text x="64" y="111" class="title">FlowUsdだけの登録解除にはならない</text><text x="64" y="150" class="sub">stage未接続 · public immediate API · Flow 110.0.0 · production設定不変</text>
<rect x="64" y="195" width="330" height="150" rx="18" class="box"/><text x="88" y="232" class="h">解除要求</text><text x="88" y="278" class="v">成功</text><text x="88" y="310" class="m">omni.flowusd enabled → disabled</text>
<rect x="435" y="195" width="330" height="150" rx="18" class="box"/><text x="459" y="232" class="h">FlowUsd node</text><text x="459" y="278" class="v">1 → 0</text><text x="459" y="310" class="m">登録解除を公開surfaceで確認</text>
<rect x="806" y="195" width="330" height="150" rx="18" class="box"/><text x="830" y="232" class="h">必須dependent</text><text x="830" y="278" class="bad">campfire.appも停止</text><text x="830" y="310" class="m">Resident producerを保持できない</text>
<rect x="64" y="382" width="516" height="126" rx="18" class="box"/><text x="88" y="421" class="h">Flow schema</text><text x="88" y="464" class="v">loadedのまま</text><text x="88" y="491" class="m">omni.usd.schema.flowは依存解除されない</text>
<rect x="620" y="382" width="516" height="126" rx="18" class="box"/><text x="644" y="421" class="h">可逆性</text><text x="644" y="464" class="v">元の3 extension / nodeを復元</text><text x="644" y="491" class="m">production app SHA-256も前後一致</text>
<text x="64" y="561" class="h">判定</text><text x="64" y="598" class="bad">性能対照として不採用</text><text x="64" y="630" class="m">subscriberだけでなくproducer lifecycleまで変えるため、ChangeBlock残差をFlow ingestへ帰属できない。</text><text x="64" y="656" class="m">{report['gate_summary']['passed']} / {report['gate_summary']['total']} gates · production Sphere / Point既定OFF / rollback / revision / snapshot契約は不変</text>
</svg>'''
    assert conclusions["flowusd_disabled"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--app-config", type=Path, required=True)
    parser.add_argument("--extension-config", type=Path, required=True)
    parser.add_argument("--flow-config", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()

    runtime = _load_json(args.runtime)
    manifest = _load_json(args.manifest)
    app_dependencies = _kit_dependencies(args.app_config)
    extension_config = _load_toml(args.extension_config)
    flow_config = _load_toml(args.flow_config)
    before = runtime["before"]
    disabled = runtime["after_disable"]
    restored = runtime["after_restore"]
    conclusions = runtime["conclusions"]

    checks = {
        "runtime_status_ok": runtime["status"] == "ok",
        "manifest_status_ok": manifest["status"] == "ok",
        "no_stage_opened": runtime["scope"]["stage_opened"] is False,
        "disable_request_succeeded": runtime["disable_request"]["result"] is True,
        "flowusd_disabled": conclusions["flowusd_disabled"] is True,
        "flowusd_module_unloaded": disabled["flowusd_module_loaded"] is False,
        "flow_stageupdate_node_removed": conclusions[
            "flow_stageupdate_node_removed"
        ]
        is True,
        "campfire_app_cascaded_off": conclusions[
            "campfire_app_remained_enabled"
        ]
        is False,
        "flow_schema_remained_enabled": conclusions["schema_remained_enabled"]
        is True,
        "extension_state_restored": conclusions["restored_exactly"] is True,
        "flow_node_restored": restored["stage_update"]["flow_node_count"]
        == before["stage_update"]["flow_node_count"]
        == 1,
        "production_app_unchanged": manifest["production_changed"] is False,
        "root_declares_flowusd": "omni.flowusd" in app_dependencies,
        "campfire_declares_flowusd": "omni.flowusd"
        in extension_config.get("dependencies", {}),
        "flowusd_declares_schema": "omni.usd.schema.flow"
        in flow_config.get("dependencies", {}),
        "fixed_flow_version": str(flow_config["package"]["version"]) == "110.0.0",
    }
    report = {
        "schema_version": 1,
        "phase": "phase6dg",
        "status": "pass" if all(checks.values()) else "fail",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "public FlowUsd extension disable/restore boundary before stage connection",
        "gate_summary": {
            "passed": sum(checks.values()),
            "total": len(checks),
            "checks": checks,
        },
        "dependency_chain": [
            "campfire.simulator root -> omni.flowusd",
            "campfire.simulator root -> campfire.app -> omni.flowusd",
            "omni.flowusd -> omni.usd.schema.flow",
        ],
        "runtime": runtime,
        "decision": {
            "adopt_as_performance_control": False,
            "reason": (
                "Disabling omni.flowusd removes the FlowUsd StageUpdate node, but "
                "also disables campfire.app and therefore the Resident producer. "
                "It is not a subscriber-only contrast."
            ),
            "flow_ingest_timer_obtained": False,
            "phase6dd_residual_attributed_to_flowusd": False,
        },
        "contracts": {
            "production_sphere_default": True,
            "point_emitter_default_off": True,
            "flow_version": "110.0.0",
            "physics_changed": False,
            "json_schema_changed": False,
            "rollback_changed": False,
            "revision_changed": False,
            "immutable_snapshot_changed": False,
        },
        "next": (
            "Audit whether the FlowUsd native plugin exposes an independently "
            "controllable USD-notice attachment boundary. If not, stop subtractive "
            "consumer isolation and return to value-preserving publication work."
        ),
    }
    _write_json(args.report, report)
    _write_svg(args.svg, report)
    if report["status"] != "pass":
        failed = [name for name, passed in checks.items() if not passed]
        raise SystemExit(f"Phase 6DG gates failed: {failed}")
    print(f"Phase 6DG gates: {sum(checks.values())}/{len(checks)}")


if __name__ == "__main__":
    main()
