"""Combine the V3M-A compatibility audit and isolated Kit probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", required=True)
    parser.add_argument("--probe", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    audit = _read(args.audit)
    probe = _read(args.probe)
    gates = {
        "audit_passed": audit["status"] == "ok" and all(audit["gates"].values()),
        "isolated_probe_qualified": probe["status"] == "qualified"
        and all(probe["gates"].values()),
        "production_unchanged": not probe["decision"]["production_code_changed"],
        "phase6dm_still_held": not probe["decision"]["phase6dm_resumed"],
        "physics_render_roles_separated": all(
            probe["gates"][name]
            for name in (
                "root_owns_rigidbody_mass_damping",
                "collider_only_owns_collision",
                "collider_hidden_from_rtx",
                "render_has_no_physics_api",
            )
        ),
        "uv_side_caps_transform_reload_qualified": all(
            probe["gates"][name]
            for name in (
                "side_and_both_caps_authored",
                "uv_cardinality_and_range_valid",
                "checker_visible_on_side_and_caps",
                "children_follow_root_transform",
                "no_live_prim_or_topology_change",
                "reload_preserves_hierarchy_and_uv",
            )
        ),
    }
    report = {
        "schema": "campfire.phasev3ma.final_report.v1",
        "status": "ok" if all(gates.values()) else "failed",
        "gates": gates,
        "audit": audit,
        "isolated_probe": probe,
        "decision": {
            "phasev3ma_qualified": all(gates.values()),
            "phasev3mb_may_start": all(gates.values()),
            "production_integration_performed": False,
            "next_boundary": "default-off stable 360-cell mesh topology and OFF/ON physics equivalence",
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Phase V3M-A final: {sum(gates.values())}/{len(gates)} gates")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
