"""Create a pre-connection renderer scene variant inside Kit's USD runtime."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.kit.app
from pxr import PhysxSchema, Sdf, Usd, UsdGeom, UsdPhysics


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _physics_inventory(stage):
    schemas = []
    properties = []
    for prim in stage.Traverse():
        schemas.extend(
            f"{prim.GetPath()}:{schema}"
            for schema in prim.GetAppliedSchemas()
            if schema.startswith("Physics") or schema.startswith("Physx")
        )
        properties.extend(
            f"{prim.GetPath()}.{prop.GetName()}"
            for prop in prim.GetProperties()
            if prop.GetName().startswith("physics:")
            or prop.GetName().startswith("physx")
            or prop.GetName() == "material:binding:physics"
        )
    return schemas, properties


def _remove_physics(stage):
    removed_prims = []
    for path_text in ("/World/PhysicsScene", "/World/PhysicsMaterials"):
        path = Sdf.Path(path_text)
        if stage.GetPrimAtPath(path):
            if not stage.RemovePrim(path):
                raise RuntimeError(f"Unable to remove offline physics Prim: {path}")
            removed_prims.append(str(path))
    api_types = (
        UsdPhysics.CollisionAPI,
        UsdPhysics.RigidBodyAPI,
        UsdPhysics.MassAPI,
        UsdPhysics.MaterialAPI,
        PhysxSchema.PhysxRigidBodyAPI,
    )
    for prim in tuple(stage.Traverse()):
        for api_type in api_types:
            if prim.HasAPI(api_type) and not prim.RemoveAPI(api_type):
                raise RuntimeError(
                    f"Unable to remove {api_type.__name__} from {prim.GetPath()}"
                )
        for prop in tuple(prim.GetProperties()):
            name = prop.GetName()
            if (
                name.startswith("physics:")
                or name.startswith("physx")
                or name == "material:binding:physics"
            ) and not prim.RemoveProperty(name):
                raise RuntimeError(
                    f"Unable to remove physics property {prim.GetPath()}.{name}"
                )
    return removed_prims


async def _run():
    settings = carb.settings.get_settings()
    source = Path(settings.get_as_string("/phase6cs/source")).resolve()
    output = Path(settings.get_as_string("/phase6cs/variantScene")).resolve()
    manifest_path = Path(settings.get_as_string("/phase6cs/manifest")).resolve()
    variant = settings.get_as_string("/phase6cs/variant")
    if variant not in (
        "unchanged",
        "no_flow",
        "no_physics",
        "render_only",
        "minimal_camera",
    ):
        raise RuntimeError(f"Unsupported Phase 6CS variant: {variant}")
    if not source.is_file():
        raise RuntimeError(f"Source scene is missing: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if variant == "minimal_camera":
        output.unlink(missing_ok=True)
        stage = Usd.Stage.CreateNew(str(output))
        world = UsdGeom.Xform.Define(stage, "/World").GetPrim()
        stage.SetDefaultPrim(world)
        UsdGeom.Camera.Define(stage, "/World/Camera")
        cube = UsdGeom.Cube.Define(stage, "/World/ReferenceCube")
        cube.CreateSizeAttr(1.0)
        stage.SetStartTimeCode(0.0)
        stage.SetEndTimeCode(100.0)
        stage.SetTimeCodesPerSecond(60.0)
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    else:
        shutil.copyfile(source, output)
        stage = Usd.Stage.Open(str(output))
    if stage is None:
        raise RuntimeError(f"Variant stage did not open: {output}")
    stage.SetEditTarget(stage.GetRootLayer())
    removed_prims = []
    if variant in ("no_flow", "render_only"):
        path = Sdf.Path("/World/Flow")
        if not stage.GetPrimAtPath(path):
            raise RuntimeError(f"Expected Flow root is missing: {path}")
        if not stage.RemovePrim(path):
            raise RuntimeError(f"Unable to remove offline Flow root: {path}")
        removed_prims.append(str(path))
    if variant in ("no_physics", "render_only"):
        removed_prims.extend(_remove_physics(stage))
    metadata = dict(stage.GetRootLayer().customLayerData)
    metadata.update(
        {
            "campfire:diagnosticPhase": "phase6cs",
            "campfire:diagnosticVariant": variant,
            "campfire:mutatedBeforeStageConnection": True,
            "campfire:productionChanged": False,
        }
    )
    stage.GetRootLayer().customLayerData = metadata
    if not stage.GetRootLayer().Save():
        raise RuntimeError(f"Variant scene did not save: {output}")
    del stage
    verification = Usd.Stage.Open(str(output))
    if verification is None:
        raise RuntimeError(f"Saved variant did not reopen: {output}")
    flow_root_present = bool(verification.GetPrimAtPath("/World/Flow"))
    physics_scene_present = bool(verification.GetPrimAtPath("/World/PhysicsScene"))
    physics_schemas, physics_properties = _physics_inventory(verification)
    if variant in ("no_flow", "render_only", "minimal_camera") and flow_root_present:
        raise RuntimeError("Offline no_flow variant still contains /World/Flow")
    if variant in ("no_physics", "render_only", "minimal_camera") and (
        physics_scene_present or physics_schemas or physics_properties
    ):
        raise RuntimeError(
            "Offline physics-free variant retained physics content: "
            f"scene={physics_scene_present}, schemas={physics_schemas}, "
            f"properties={physics_properties}"
        )
    manifest = {
        "schema_version": 1,
        "phase": "phase6cs",
        "status": "ok",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "variant": variant,
        "source": str(source),
        "output": str(output),
        "source_sha256": _sha256(source),
        "output_sha256": _sha256(output),
        "removed_prims": removed_prims,
        "flow_root_present": flow_root_present,
        "physics_scene_present": physics_scene_present,
        "physics_schema_count": len(physics_schemas),
        "physics_property_count": len(physics_properties),
        "mutated_before_stage_connection": True,
        "live_prim_edits": 0,
        "production_changed": False,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    settings.set("/app/fastShutdown", True)
    omni.kit.app.get_app().post_uncancellable_quit(0)


asyncio.ensure_future(_run())
