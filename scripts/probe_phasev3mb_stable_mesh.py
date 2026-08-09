"""Kit/RTX probe for the production-candidate 360-cell wood render Mesh."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from pathlib import Path

import carb
import campfire.app
import numpy as np
import omni.kit.app
import omni.kit.viewport.utility
import omni.ui as ui
import omni.usd
from omni.gpu_foundation_factory import TextureFormat
from PIL import Image
from pxr import Gf, PhysxSchema, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade


RESOLUTION = (1280, 720)
TEXTURE_NAME = "campfire_phasev3mb_surface_id_atlas"
TEXTURE_URI = f"dynamic://{TEXTURE_NAME}"


def _arguments():
    settings = carb.settings.get_settings()
    return {
        "output": Path(settings.get_as_string("/phasev3mb/output")),
        "capture_dir": Path(settings.get_as_string("/phasev3mb/captureDir")),
    }


def _surface_id_atlas():
    descriptor = campfire.app.WOOD_ATLAS_MAX_DESCRIPTOR
    height = descriptor.height_px
    width = descriptor.width_px
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[..., 3] = 255
    bases = np.array(
        ([235, 45, 30], [35, 95, 235], [35, 210, 80], [225, 45, 205]),
        dtype=np.uint8,
    )
    for log_slot in range(campfire.app.WOOD_RENDER_MAX_LOGS):
        tile_x = log_slot % descriptor.tile_columns
        tile_y = log_slot // descriptor.tile_columns
        for surface_index in range(campfire.app.WOOD_SURFACE_CELLS_PER_LOG):
            cell_x = surface_index % 24
            cell_y = surface_index // 24
            x = (tile_x * 24 + cell_x) * descriptor.cell_stride_px
            y = (tile_y * 15 + cell_y) * descriptor.cell_stride_px
            base = bases[log_slot % len(bases)].astype(np.int16)
            checker = 30 if (cell_x + cell_y) % 2 else -20
            identity = np.array(
                ((surface_index * 17) % 41, (surface_index * 29) % 37, 0),
                dtype=np.int16,
            )
            color = np.clip(base + checker + identity, 0, 255).astype(np.uint8)
            image[
                y : y + descriptor.cell_stride_px,
                x : x + descriptor.cell_stride_px,
                :3,
            ] = color
    return image


def _bind_material(stage):
    material = UsdShade.Material.Define(stage, "/World/Looks/WoodSurfaceIds")
    surface = UsdShade.Shader.Define(stage, "/World/Looks/WoodSurfaceIds/Surface")
    surface.CreateIdAttr("UsdPreviewSurface")
    surface.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.5)
    reader = UsdShade.Shader.Define(stage, "/World/Looks/WoodSurfaceIds/Reader")
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    texture = UsdShade.Shader.Define(stage, "/World/Looks/WoodSurfaceIds/Texture")
    texture.CreateIdAttr("UsdUVTexture")
    texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(TEXTURE_URI))
    texture.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("raw")
    texture.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("clamp")
    texture.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("clamp")
    texture.CreateInput("minFilter", Sdf.ValueTypeNames.Token).Set("nearest")
    texture.CreateInput("magFilter", Sdf.ValueTypeNames.Token).Set("nearest")
    texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
        reader.ConnectableAPI(), "result"
    )
    texture.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    surface.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
        texture.ConnectableAPI(), "rgb"
    )
    surface.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
        texture.ConnectableAPI(), "rgb"
    )
    material.CreateSurfaceOutput().ConnectToSource(surface.ConnectableAPI(), "surface")
    for log_id in campfire.app.list_log_ids(stage):
        target = campfire.app.get_log_render_surface(stage, log_id)
        UsdShade.MaterialBindingAPI.Apply(target).Bind(material)


def _topology_digest(stage, log_id):
    render = campfire.app.get_log_render_surface(stage, log_id)
    mesh = UsdGeom.Mesh(render)
    primvars = UsdGeom.PrimvarsAPI(render)
    payload = {
        "points": [[float(v) for v in value] for value in mesh.GetPointsAttr().Get()],
        "counts": list(mesh.GetFaceVertexCountsAttr().Get()),
        "indices": list(mesh.GetFaceVertexIndicesAttr().Get()),
        "st": [[float(v) for v in value] for value in primvars.GetPrimvar("st").Get()],
        "surface": list(primvars.GetPrimvar("surfaceIndex").Get()),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _build_stage(path):
    path.unlink(missing_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.Xform.Define(stage, "/World/Logs")
    specs = (
        campfire.app.LogSpec("Log_00", (-1.15, -0.55, 0.55), 0.0, 0.30, 2.0),
        campfire.app.LogSpec("Log_01", (1.15, -0.55, 0.55), 0.0, 0.30, 2.0),
        campfire.app.LogSpec("Log_02", (-1.15, 0.75, 0.55), 180.0, 0.30, 2.0),
        campfire.app.LogSpec("Log_03", (1.15, 0.75, 0.55), 180.0, 0.30, 2.0),
    )
    for slot, spec in enumerate(specs):
        campfire.app.create_log(
            stage, spec, render_hierarchy=True, render_log_slot=slot
        )
    _bind_material(stage)
    ground = UsdGeom.Cube.Define(stage, "/World/Ground")
    ground.CreateSizeAttr(1.0)
    ground.AddScaleOp().Set(Gf.Vec3f(5.0, 4.0, 0.1))
    ground.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, -0.1))
    ground.CreateDisplayColorAttr([Gf.Vec3f(0.04, 0.04, 0.055)])
    camera = UsdGeom.Camera.Define(stage, "/World/Camera")
    camera.CreateFocalLengthAttr(46.0)
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(
        Gf.Vec3d(5.9, -8.8, 5.3),
        Gf.Vec3d(0.0, 0.0, 0.55),
        Gf.Vec3d(0.0, 0.0, 1.0),
    )
    camera.AddTransformOp().Set(view.GetInverse())
    dome = UsdLux.DomeLight.Define(stage, "/World/Lights/Dome")
    dome.CreateIntensityAttr(650.0)
    key = UsdLux.SphereLight.Define(stage, "/World/Lights/Key")
    key.CreateIntensityAttr(18000.0)
    key.CreateRadiusAttr(0.5)
    key.AddTranslateOp().Set(Gf.Vec3d(-1.0, -2.5, 5.0))
    if not stage.GetRootLayer().Save():
        raise RuntimeError("Unable to save V3M-B checker stage")
    return {
        log_id: _topology_digest(stage, log_id)
        for log_id in campfire.app.list_log_ids(stage)
    }


def _matrix_values(matrix):
    return tuple(
        float(matrix[row][column]) for row in range(4) for column in range(4)
    )


def _physics_contract():
    stages = {
        "off": Usd.Stage.CreateInMemory(),
        "on": Usd.Stage.CreateInMemory(),
    }
    spec = campfire.app.LogSpec("ContractLog", (0.35, -0.2, 1.1), 90.0)
    campfire.app.create_log(stages["off"], spec)
    campfire.app.create_log(
        stages["on"], spec, render_hierarchy=True, render_log_slot=0
    )
    records = {}
    for mode, stage in stages.items():
        root = campfire.app.get_log_root(stage, spec.log_id)
        collider = campfire.app.get_log_collider(stage, spec.log_id)
        render = campfire.app.get_log_render_surface(stage, spec.log_id)
        material = stage.GetPrimAtPath("/World/PhysicsMaterials/Wood")
        records[mode] = {
            "transform": _matrix_values(
                campfire.app.get_log_physics_transform(stage, spec.log_id)
            ),
            "dimensions": campfire.app.get_log_dimensions(stage, spec.log_id),
            "mass_kg": float(root.GetAttribute("physics:mass").Get()),
            "density_kg_m3": float(root.GetAttribute("campfire:densityKgM3").Get()),
            "rigid_body_enabled": bool(
                root.GetAttribute("physics:rigidBodyEnabled").Get()
            ),
            "kinematic_enabled": bool(
                root.GetAttribute("physics:kinematicEnabled").Get()
            ),
            "linear_damping": float(
                root.GetAttribute("physxRigidBody:linearDamping").Get()
            ),
            "angular_damping": float(
                root.GetAttribute("physxRigidBody:angularDamping").Get()
            ),
            "static_friction": float(
                material.GetAttribute("physics:staticFriction").Get()
            ),
            "dynamic_friction": float(
                material.GetAttribute("physics:dynamicFriction").Get()
            ),
            "restitution": float(material.GetAttribute("physics:restitution").Get()),
            "collider_has_collision": collider.HasAPI(UsdPhysics.CollisionAPI),
            "render_has_physics": render.HasAPI(UsdPhysics.CollisionAPI)
            or render.HasAPI(UsdPhysics.RigidBodyAPI)
            or render.HasAPI(UsdPhysics.MassAPI)
            or render.HasAPI(PhysxSchema.PhysxRigidBodyAPI),
        }
    layouts = {
        mode: campfire.app.resident_point_layout_for_logs(stage, (spec.log_id,))
        for mode, stage in stages.items()
    }
    physical_fields = (
        "transform",
        "dimensions",
        "mass_kg",
        "density_kg_m3",
        "rigid_body_enabled",
        "kinematic_enabled",
        "linear_damping",
        "angular_damping",
        "static_friction",
        "dynamic_friction",
        "restitution",
        "collider_has_collision",
    )
    equal_fields = tuple(
        name
        for name in physical_fields
        if records["off"][name] == records["on"][name]
    )
    return {
        "records": records,
        "resident_point_layout": layouts,
        "equal_fields": equal_fields,
        "all_values_equal": len(equal_fields) == len(physical_fields),
        "render_role_separated": records["off"]["render_has_physics"]
        and not records["on"]["render_has_physics"],
        "point_layout_equal": layouts["off"] == layouts["on"],
    }


async def _viewport():
    app = omni.kit.app.get_app()
    for _ in range(120):
        viewport = omni.kit.viewport.utility.get_active_viewport()
        if viewport is not None:
            break
        await app.next_update_async()
    else:
        raise RuntimeError("V3M-B requires a viewport")
    viewport.camera_path = "/World/Camera"
    viewport.fill_frame = False
    viewport.resolution = RESOLUTION
    for _ in range(120):
        await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        if tuple(viewport.resolution) == RESOLUTION:
            return viewport
    raise RuntimeError("V3M-B viewport did not settle")


async def _capture(viewport, path):
    request = omni.kit.viewport.utility.capture_viewport_to_file(
        viewport, file_path=str(path)
    )
    if not await request.wait_for_result(completion_frames=2):
        raise RuntimeError(f"V3M-B capture failed: {path}")
    for _ in range(30):
        if path.is_file():
            pixels = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
            return {
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "quantized_colors": int(
                    np.unique((pixels[150:650, 120:1160] // 24).reshape(-1, 3), axis=0).shape[0]
                ),
            }
        await asyncio.sleep(0.05)
    raise RuntimeError(f"V3M-B capture missing: {path}")


async def _run(arguments):
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    output = arguments["output"].resolve()
    capture_dir = arguments["capture_dir"].resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    capture_dir.mkdir(parents=True, exist_ok=True)
    stage_path = output.with_suffix(".usda")
    provider = None
    report = None
    exit_code = 1
    try:
        provider = ui.DynamicTextureProvider(TEXTURE_NAME)
        atlas = _surface_id_atlas()
        provider.set_bytes_data(
            atlas.reshape(-1).tolist(),
            [atlas.shape[1], atlas.shape[0]],
            TextureFormat.RGBA8_UNORM,
            strict=True,
        )
        initial_digests = _build_stage(stage_path)
        await context.open_stage_async(str(stage_path))
        viewport = await _viewport()
        for _ in range(35):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        initial = await _capture(viewport, capture_dir / "surface_ids_four_logs.png")
        stage = context.get_stage()
        paths_before = tuple(str(prim.GetPath()) for prim in stage.Traverse())
        campfire.app.move_log(stage, "Log_03", (1.0, 0.8, 0.9), 90.0)
        for _ in range(10):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        transformed = await _capture(
            viewport, capture_dir / "surface_ids_transformed.png"
        )
        paths_after = tuple(str(prim.GetPath()) for prim in stage.Traverse())
        digests_after = {
            log_id: _topology_digest(stage, log_id)
            for log_id in campfire.app.list_log_ids(stage)
        }
        if not stage.GetRootLayer().Save():
            raise RuntimeError("Unable to save transformed V3M-B stage")
        await context.close_stage_async()
        await context.open_stage_async(str(stage_path))
        viewport = await _viewport()
        for _ in range(18):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        reloaded = await _capture(viewport, capture_dir / "surface_ids_reloaded.png")
        stage = context.get_stage()
        paths_reloaded = tuple(str(prim.GetPath()) for prim in stage.Traverse())
        digests_reloaded = {
            log_id: _topology_digest(stage, log_id)
            for log_id in campfire.app.list_log_ids(stage)
        }
        mesh = UsdGeom.Mesh(campfire.app.get_log_render_surface(stage, "Log_00"))
        physics_contract = _physics_contract()
        surface = tuple(
            UsdGeom.PrimvarsAPI(mesh.GetPrim()).GetPrimvar("surfaceIndex").Get()
        )
        all_uvs = {
            tuple(float(value) for value in campfire.app.atlas_uv(log_slot, index))
            for log_slot in range(20)
            for index in range(360)
        }
        gates = {
            "four_log_checker_visible": min(
                initial["quantized_colors"], transformed["quantized_colors"]
            ) >= 20,
            "final_face_layout_is_288_side_96_caps": len(
                mesh.GetFaceVertexCountsAttr().Get()
            ) == 384,
            "all_360_identities_referenced": set(surface) == set(range(360)),
            "corner_overlap_reuses_state": all(
                surface[c] == surface[324 + c]
                and surface[276 + c] == surface[372 + c]
                for c in range(12)
            ),
            "twenty_log_atlas_has_7200_unique_samples": len(all_uvs) == 7200,
            "no_live_structure_or_topology_change": paths_before
            == paths_after
            == paths_reloaded
            and initial_digests == digests_after == digests_reloaded,
            "reload_preserves_fixed_dynamic_uri": stage.GetPrimAtPath(
                "/World/Looks/WoodSurfaceIds/Texture"
            ).GetAttribute("inputs:file").Get().path
            == TEXTURE_URI,
            "authored_physics_values_equal": physics_contract["all_values_equal"],
            "render_role_separated": physics_contract["render_role_separated"],
            "resident_point_layout_equal": physics_contract["point_layout_equal"],
        }
        report = {
            "schema": "campfire.phasev3mb.stable_mesh_probe.v1",
            "status": "qualified" if all(gates.values()) else "not_qualified",
            "gates": gates,
            "mesh": {
                "points": len(mesh.GetPointsAttr().Get()),
                "faces": len(mesh.GetFaceVertexCountsAttr().Get()),
                "unique_surface_identities": len(set(surface)),
                "side_faces": 288,
                "cap_faces": 96,
                "overlapping_corner_faces": 24,
                "topology_sha256": digests_reloaded,
            },
            "atlas": {
                "size": [atlas.shape[1], atlas.shape[0]],
                "logs": 20,
                "surface_cells_per_log": 360,
                "unique_samples": len(all_uvs),
                "cell_stride_px": campfire.app.WOOD_ATLAS_MAX_DESCRIPTOR.cell_stride_px,
                "gutter_px": 0,
                "uri": TEXTURE_URI,
            },
            "physics_contract": physics_contract,
            "captures": {
                "initial": initial,
                "transformed": transformed,
                "reloaded": reloaded,
                "kind": "surface-ID checker diagnostic; not combustion",
            },
        }
        exit_code = 0 if all(gates.values()) else 1
    except Exception as error:
        report = {
            "schema": "campfire.phasev3mb.stable_mesh_probe.v1",
            "status": "error",
            "error": f"{type(error).__name__}: {error}",
        }
    finally:
        if provider is not None:
            provider.destroy()
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        app.post_uncancellable_quit(exit_code)


asyncio.ensure_future(_run(_arguments()))
