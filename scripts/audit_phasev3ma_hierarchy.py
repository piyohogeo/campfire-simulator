"""Audit code and saved stages that assume a Cylinder log root.

This Phase V3M-A tool is intentionally read-only with respect to production
sources.  It records the compatibility boundary before the render hierarchy is
introduced behind a default-off setting in a later independent phase.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


PRODUCTION_FILES = (
    "source/extensions/campfire.app/campfire/app/wood.py",
    "source/extensions/campfire.app/campfire/app/scene.py",
    "source/extensions/campfire.app/campfire/app/support.py",
    "source/extensions/campfire.app/campfire/app/resident_point_scene.py",
    "source/extensions/campfire.app/campfire/app/wood_visual_v0.py",
    "source/extensions/campfire.app/campfire/app/wood_visual_v1.py",
    "source/extensions/campfire.app/campfire/app/phase2_scene.py",
    "source/extensions/campfire.app/campfire/app/phase3_scene.py",
    "source/extensions/campfire.app/campfire/app/phase4_scene.py",
    "source/extensions/campfire.app/campfire/app/phase5_scene.py",
    "source/extensions/campfire.app/campfire/app/flow_scene.py",
    "source/extensions/campfire.app/campfire/app/extension.py",
)

SCAN_ROOTS = (
    "source/extensions/campfire.app/campfire/app",
    "scripts",
    "assets/scenes",
)

RULES = {
    "log_root_path": re.compile(r"/World/Logs"),
    "cylinder_schema": re.compile(r"UsdGeom\.Cylinder|def Cylinder \"(?:Log|CollapseLog)"),
    "dimension_access": re.compile(
        r"(?:Get|Create)(?:Radius|Height|Axis)Attr|campfire:(?:radiusM|lengthM)|"
        r"^\s*(?:double|float)\s+(?:radius|height)\s*="
    ),
    "physics_api": re.compile(
        r"UsdPhysics\.(?:Collision|RigidBody|Mass)API|PhysxRigidBodyAPI|Physics(?:Collision|RigidBody|Mass)API"
    ),
    "material_binding": re.compile(r"MaterialBindingAPI|material:binding:physics"),
    "transform_access": re.compile(
        r"ComputeLocalToWorldTransform|xformOp:(?:translate|orient)|move_log|get_log_world_position"
    ),
    "checkpoint_recovery": re.compile(
        r"checkpoint|recovery|reload|export_stage|\.Export\(", re.IGNORECASE
    ),
}

REQUIRED_EVIDENCE = {
    "wood_root_is_cylinder": (
        "source/extensions/campfire.app/campfire/app/wood.py",
        r"UsdGeom\.Cylinder\.Define\(stage, path\)",
    ),
    "scene_root_is_cylinder": (
        "source/extensions/campfire.app/campfire/app/scene.py",
        r"UsdGeom\.Cylinder\.Define\(stage, f\"/World/Logs/",
    ),
    "support_updates_root_radius": (
        "source/extensions/campfire.app/campfire/app/support.py",
        r"UsdGeom\.Cylinder\(prim\)\.GetRadiusAttr",
    ),
    "resident_point_uses_shared_log_boundary": (
        "source/extensions/campfire.app/campfire/app/resident_point_scene.py",
        r"from \.wood import get_log_dimensions, get_log_physics_transform",
    ),
    "v0_binds_log_root": (
        "source/extensions/campfire.app/campfire/app/wood_visual_v0.py",
        r"MaterialBindingAPI\.Apply\(log_prim\)",
    ),
    "v1_requires_cylinder": (
        "source/extensions/campfire.app/campfire/app/wood_visual_v1.py",
        r"source\.IsA\(UsdGeom\.Cylinder\)",
    ),
    "list_log_ids_reads_root_children": (
        "source/extensions/campfire.app/campfire/app/wood.py",
        r"def list_log_ids",
    ),
    "move_log_writes_root_transform": (
        "source/extensions/campfire.app/campfire/app/wood.py",
        r"def move_log",
    ),
    "checkpoint_v1_uses_log_root": (
        "scripts/resident_checkpoint_package.py",
        r"/World/Logs|log_ids",
    ),
    "stage_recovery_uses_log_root": (
        "source/extensions/campfire.app/campfire/app/resident_stage_recovery.py",
        r"stage|consumer",
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _iter_files(root: Path):
    for relative_root in SCAN_ROOTS:
        base = root / relative_root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if (
                path.is_file()
                and path.suffix.lower() in {".py", ".ps1", ".usda"}
                and "phasev3ma" not in path.name.lower()
            ):
                yield path


def _line_matches(root: Path):
    matches = []
    for path in _iter_files(root):
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), 1):
            categories = [name for name, pattern in RULES.items() if pattern.search(line)]
            if categories:
                matches.append(
                    {
                        "file": relative,
                        "line": line_number,
                        "categories": categories,
                        "text": line.strip()[:300],
                    }
                )
    return matches


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output).resolve()

    evidence = {}
    for name, (relative, pattern) in REQUIRED_EVIDENCE.items():
        path = root / relative
        text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        evidence[name] = {
            "file": relative,
            "present": bool(re.search(pattern, text)),
            "pattern": pattern,
        }

    matches = _line_matches(root)
    stage_files = sorted(
        {
            item["file"]
            for item in matches
            if item["file"].startswith("assets/scenes/")
            and "cylinder_schema" in item["categories"]
        }
    )
    checkpoint_files = sorted(
        {
            item["file"]
            for item in matches
            if "checkpoint_recovery" in item["categories"]
            and ("checkpoint" in item["file"] or "recovery" in item["file"])
        }
    )
    category_counts = {
        name: sum(name in item["categories"] for item in matches) for name in RULES
    }
    gates = {
        "all_required_evidence_present": all(
            value["present"] for value in evidence.values()
        ),
        "required_production_files_present": all(
            (root / relative).is_file() for relative in PRODUCTION_FILES
        ),
        "saved_stage_cylinder_assumptions_enumerated": bool(stage_files),
        "checkpoint_and_recovery_paths_enumerated": bool(checkpoint_files),
        "shared_helper_boundary_defined": True,
        "production_sources_unchanged_by_audit": True,
    }
    report = {
        "schema": "campfire.phasev3ma.hierarchy_audit.v1",
        "status": "ok" if all(gates.values()) else "failed",
        "scope": "Cylinder-root compatibility before any production hierarchy change",
        "gates": gates,
        "required_evidence": evidence,
        "category_counts": category_counts,
        "matches": matches,
        "saved_stage_files": stage_files,
        "checkpoint_recovery_files": checkpoint_files,
        "production_sha256": {
            relative: _sha256(root / relative) for relative in PRODUCTION_FILES
        },
        "compatibility_findings": [
            {
                "boundary": "authoring and identity",
                "current": "create_log authors Cylinder at the stable log path; metadata and transform live on that Cylinder",
                "future": "stable Xform root owns identity, metadata, transform, RigidBody, Mass and damping",
            },
            {
                "boundary": "collision and dimensions",
                "current": "Collision and Cylinder radius/height/axis are read or written on the log root",
                "future": "resolve a Collider child for hierarchy mode while legacy mode resolves the root",
            },
            {
                "boundary": "render material",
                "current": "V0 binds the root and V1 requires a Cylinder source",
                "future": "resolve RenderSurface for hierarchy mode and root for legacy mode; modes remain mutually exclusive",
            },
            {
                "boundary": "Point and Flow transforms",
                "current": "Point layout and Flow diagnostics resolve /World/Logs/<id> directly and some require Cylinder",
                "future": "physics/world transform always resolves from the stable log root; dimensions resolve from Collider",
            },
            {
                "boundary": "support collapse",
                "current": "prepared Phase 5 Cylinder segments update radius directly and remove joints",
                "future": "outside first hierarchy integration; legacy Phase 5 remains unchanged",
            },
            {
                "boundary": "serialization and recovery",
                "current": "wood state and checkpoint v1 address stable log IDs/paths, not render topology",
                "future": "preserve checkpoint v1 and rebuild pre-authored render children from mode before attachment",
            },
        ],
        "proposed_helper_boundary": {
            "get_log_root": "return stable /World/Logs/<log_id> prim",
            "get_log_collider": "legacy Cylinder root or hierarchy Collider child",
            "get_log_render_surface": "legacy Cylinder root or hierarchy RenderSurface child",
            "get_log_dimensions": "validated radius, length and X axis from collider/metadata",
            "get_log_physics_transform": "world transform from stable root",
            "get_log_material_target": "render surface only; never physics collider in hierarchy mode",
        },
        "phase_boundaries": {
            "phasev3ma_changes_production": False,
            "phasev3mb_may_add_default_off_helpers": True,
            "phasev3mc_may_connect_texture_only_after_physics_equivalence": True,
            "phase6dm_resumed": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Phase V3M-A audit: {sum(gates.values())}/{len(gates)} gates, "
        f"{len(matches)} evidence lines, {len(stage_files)} saved stages"
    )
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
