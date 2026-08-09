"""Isolated Kit/RTX probe for an Xform + Cylinder + UV Mesh log hierarchy."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from pathlib import Path

import carb
import numpy as np
import omni.kit.app
import omni.kit.viewport.utility
import omni.ui as ui
import omni.usd
from omni.gpu_foundation_factory import TextureFormat
from PIL import Image
from pxr import Gf, PhysxSchema, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade


RESOLUTION = (1280, 720)
TEXTURE_NAME = "campfire_phasev3ma_mesh_checker"
TEXTURE_URI = f"dynamic://{TEXTURE_NAME}"
ROOT_PATH = Sdf.Path("/World/Logs/ProbeLog")
COLLIDER_PATH = ROOT_PATH.AppendChild("Collider")
RENDER_PATH = ROOT_PATH.AppendChild("RenderSurface")
AXIAL_SEGMENTS = 6
CIRCUMFERENTIAL_SEGMENTS = 12


def _arguments():
    settings = carb.settings.get_settings()
    return {
        "output": Path(settings.get_as_string("/phasev3ma/output")),
        "capture_dir": Path(settings.get_as_string("/phasev3ma/captureDir")),
    }


def _checker_atlas(width=384, height=128):
    image = np.empty((height, width, 4), dtype=np.uint8)
    image[..., 3] = 255
    side_end = width * 2 // 3
    left_end = width * 5 // 6
    y, x = np.indices((height, side_end))
    checks = ((x // 24 + y // 16) % 2)[..., None]
    image[:, :side_end, :3] = np.where(
        checks == 0,
        np.array([235, 55, 35], dtype=np.uint8),
        np.array([30, 90, 235], dtype=np.uint8),
    )
    image[0:4, :side_end, :3] = [255, 230, 20]
    image[-4:, :side_end, :3] = [20, 245, 245]
    image[:, 0:4, :3] = [255, 255, 255]
    image[:, side_end - 4 : side_end, :3] = [10, 10, 10]
    for start, end, first, second in (
        (side_end, left_end, (245, 160, 25), (80, 25, 150)),
        (left_end, width, (30, 210, 80), (230, 30, 210)),
    ):
        cap_width = end - start
        yy, xx = np.indices((height, cap_width))
        cx, cy = (cap_width - 1) * 0.5, (height - 1) * 0.5
        radius = np.sqrt(((xx - cx) / max(cx, 1.0)) ** 2 + ((yy - cy) / max(cy, 1.0)) ** 2)
        sector = ((np.arctan2(yy - cy, xx - cx) + math.pi) / (math.pi / 4)).astype(int)
        pattern = ((sector + (radius * 4).astype(int)) % 2)[..., None]
        image[:, start:end, :3] = np.where(
            pattern == 0, np.array(first, np.uint8), np.array(second, np.uint8)
        )
        image[height // 2 - 2 : height // 2 + 2, start:end, :3] = [255, 255, 255]
        image[: height // 2, start + cap_width // 2 - 2 : start + cap_width // 2 + 2, :3] = [255, 255, 255]
    return image


def _mesh_data(radius=0.42, length=3.0):
    points = []
    counts = []
    indices = []
    uvs = []
    face_classes = []
    # Side vertices duplicate the circumferential seam explicitly.
    for axial in range(AXIAL_SEGMENTS + 1):
        x = -0.5 * length + length * axial / AXIAL_SEGMENTS
        for circumferential in range(CIRCUMFERENTIAL_SEGMENTS + 1):
            angle = 2.0 * math.pi * circumferential / CIRCUMFERENTIAL_SEGMENTS
            points.append(Gf.Vec3f(x, radius * math.cos(angle), radius * math.sin(angle)))
    stride = CIRCUMFERENTIAL_SEGMENTS + 1
    for axial in range(AXIAL_SEGMENTS):
        for circumferential in range(CIRCUMFERENTIAL_SEGMENTS):
            a = axial * stride + circumferential
            b = (axial + 1) * stride + circumferential
            c = b + 1
            d = a + 1
            indices.extend((a, b, c, d))
            counts.append(4)
            u0 = (2.0 / 3.0) * axial / AXIAL_SEGMENTS
            u1 = (2.0 / 3.0) * (axial + 1) / AXIAL_SEGMENTS
            v0 = circumferential / CIRCUMFERENTIAL_SEGMENTS
            v1 = (circumferential + 1) / CIRCUMFERENTIAL_SEGMENTS
            uvs.extend((Gf.Vec2f(u0, v0), Gf.Vec2f(u1, v0), Gf.Vec2f(u1, v1), Gf.Vec2f(u0, v1)))
            face_classes.append("side")

    for side, x_value, u_center, reverse in (
        ("left_cap", -0.5 * length, 0.75, True),
        ("right_cap", 0.5 * length, 11.0 / 12.0, False),
    ):
        center = len(points)
        points.append(Gf.Vec3f(x_value, 0.0, 0.0))
        ring = len(points)
        for circumferential in range(CIRCUMFERENTIAL_SEGMENTS):
            angle = 2.0 * math.pi * circumferential / CIRCUMFERENTIAL_SEGMENTS
            points.append(Gf.Vec3f(x_value, radius * math.cos(angle), radius * math.sin(angle)))
        for circumferential in range(CIRCUMFERENTIAL_SEGMENTS):
            current = ring + circumferential
            following = ring + (circumferential + 1) % CIRCUMFERENTIAL_SEGMENTS
            triangle = (center, following, current) if reverse else (center, current, following)
            indices.extend(triangle)
            counts.append(3)
            face_classes.append(side)
            cap_half_u = 1.0 / 12.0
            cap_half_v = 0.46
            values = []
            for vertex in triangle:
                if vertex == center:
                    values.append(Gf.Vec2f(u_center, 0.5))
                else:
                    point = points[vertex]
                    direction = -1.0 if reverse else 1.0
                    values.append(
                        Gf.Vec2f(
                            u_center + direction * cap_half_u * float(point[1]) / radius,
                            0.5 + cap_half_v * float(point[2]) / radius,
                        )
                    )
            uvs.extend(values)
    return points, counts, indices, uvs, face_classes


def _topology_digest(mesh):
    primvar = UsdGeom.PrimvarsAPI(mesh).GetPrimvar("st")
    payload = {
        "points": [[float(v) for v in value] for value in mesh.GetPointsAttr().Get()],
        "counts": list(mesh.GetFaceVertexCountsAttr().Get()),
        "indices": list(mesh.GetFaceVertexIndicesAttr().Get()),
        "uv": [[float(v) for v in value] for value in primvar.Get()],
        "interpolation": str(primvar.GetInterpolation()),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _build_stage(path):
    path.unlink(missing_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    physics_scene = UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
    physics_scene.CreateGravityDirectionAttr(Gf.Vec3f(0.0, 0.0, -1.0))
    physics_scene.CreateGravityMagnitudeAttr(9.81)
    ground = UsdGeom.Cube.Define(stage, "/World/Ground")
    ground.CreateSizeAttr(1.0)
    ground.AddScaleOp().Set(Gf.Vec3f(8.0, 8.0, 0.1))
    ground.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, -0.1))
    ground.CreateDisplayColorAttr([Gf.Vec3f(0.055, 0.055, 0.065)])
    UsdPhysics.CollisionAPI.Apply(ground.GetPrim())

    root = UsdGeom.Xform.Define(stage, ROOT_PATH)
    root.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.72))
    root.AddOrientOp(UsdGeom.XformOp.PrecisionFloat).Set(Gf.Quatf(1.0, Gf.Vec3f(0.0)))
    root_prim = root.GetPrim()
    root_prim.CreateAttribute("campfire:logId", Sdf.ValueTypeNames.String).Set("ProbeLog")
    root_prim.CreateAttribute("campfire:radiusM", Sdf.ValueTypeNames.Double).Set(0.42)
    root_prim.CreateAttribute("campfire:lengthM", Sdf.ValueTypeNames.Double).Set(3.0)
    root_prim.CreateAttribute("campfire:densityKgM3", Sdf.ValueTypeNames.Double).Set(520.0)
    mass = math.pi * 0.42**2 * 3.0 * 520.0
    root_prim.CreateAttribute("campfire:initialMassKg", Sdf.ValueTypeNames.Double).Set(mass)
    rigid = UsdPhysics.RigidBodyAPI.Apply(root_prim)
    rigid.CreateRigidBodyEnabledAttr(True)
    rigid.CreateKinematicEnabledAttr(False)
    rigid.CreateVelocityAttr(Gf.Vec3f(0.0))
    rigid.CreateAngularVelocityAttr(Gf.Vec3f(0.0))
    UsdPhysics.MassAPI.Apply(root_prim).CreateMassAttr(mass)
    physx = PhysxSchema.PhysxRigidBodyAPI.Apply(root_prim)
    physx.CreateLinearDampingAttr(0.05)
    physx.CreateAngularDampingAttr(0.20)

    physics_material = UsdShade.Material.Define(stage, "/World/PhysicsMaterials/Wood")
    physics_api = UsdPhysics.MaterialAPI.Apply(physics_material.GetPrim())
    physics_api.CreateStaticFrictionAttr(0.70)
    physics_api.CreateDynamicFrictionAttr(0.55)
    physics_api.CreateRestitutionAttr(0.10)
    collider = UsdGeom.Cylinder.Define(stage, COLLIDER_PATH)
    collider.CreateAxisAttr(UsdGeom.Tokens.x)
    collider.CreateRadiusAttr(0.42)
    collider.CreateHeightAttr(3.0)
    collider.CreateVisibilityAttr(UsdGeom.Tokens.invisible)
    UsdPhysics.CollisionAPI.Apply(collider.GetPrim())
    UsdShade.MaterialBindingAPI.Apply(collider.GetPrim()).Bind(
        physics_material, UsdShade.Tokens.weakerThanDescendants, "physics"
    )

    points, counts, indices, uvs, face_classes = _mesh_data()
    mesh = UsdGeom.Mesh.Define(stage, RENDER_PATH)
    mesh.CreatePointsAttr(points)
    mesh.CreateFaceVertexCountsAttr(counts)
    mesh.CreateFaceVertexIndicesAttr(indices)
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    mesh.CreateDoubleSidedAttr(False)
    mesh.GetPrim().CreateAttribute("campfire:renderOnly", Sdf.ValueTypeNames.Bool).Set(True)
    st = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar(
        "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying
    )
    st.Set(uvs)

    material = UsdShade.Material.Define(stage, "/World/Looks/MeshChecker")
    surface = UsdShade.Shader.Define(stage, "/World/Looks/MeshChecker/Surface")
    surface.CreateIdAttr("UsdPreviewSurface")
    surface.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.38)
    reader = UsdShade.Shader.Define(stage, "/World/Looks/MeshChecker/PrimvarReader")
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    texture = UsdShade.Shader.Define(stage, "/World/Looks/MeshChecker/Texture")
    texture.CreateIdAttr("UsdUVTexture")
    texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(TEXTURE_URI))
    texture.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("raw")
    texture.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("clamp")
    texture.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("clamp")
    texture.CreateInput("minFilter", Sdf.ValueTypeNames.Token).Set("nearest")
    texture.CreateInput("magFilter", Sdf.ValueTypeNames.Token).Set("nearest")
    texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
    texture.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    surface.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(texture.ConnectableAPI(), "rgb")
    surface.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(texture.ConnectableAPI(), "rgb")
    material.CreateSurfaceOutput().ConnectToSource(surface.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)

    camera = UsdGeom.Camera.Define(stage, "/World/Camera")
    camera.CreateFocalLengthAttr(48.0)
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(Gf.Vec3d(5.3, -7.6, 3.8), Gf.Vec3d(0.0, 0.0, 0.72), Gf.Vec3d(0.0, 0.0, 1.0))
    camera.AddTransformOp().Set(view.GetInverse())
    dome = UsdLux.DomeLight.Define(stage, "/World/Lights/Dome")
    dome.CreateIntensityAttr(650.0)
    dome.CreateColorAttr(Gf.Vec3f(0.65, 0.72, 0.85))
    key = UsdLux.SphereLight.Define(stage, "/World/Lights/Key")
    key.CreateIntensityAttr(19000.0)
    key.CreateRadiusAttr(0.4)
    key.AddTranslateOp().Set(Gf.Vec3d(1.5, -2.5, 4.2))
    if not stage.GetRootLayer().Save():
        raise RuntimeError("Unable to save V3M-A isolated stage")
    return {
        "face_classes": face_classes,
        "topology_digest": _topology_digest(mesh),
        "prim_paths": tuple(str(prim.GetPath()) for prim in stage.Traverse()),
    }


def _matrix_values(matrix):
    return [float(matrix[row][column]) for row in range(4) for column in range(4)]


def _matrix_error(left, right):
    return max(abs(a - b) for a, b in zip(_matrix_values(left), _matrix_values(right)))


def _record(path):
    payload = path.read_bytes()
    image = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
    roi = image[150:620, 150:1130]
    return {
        "path": str(path),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "roi_unique_colors_32": int(np.unique((roi // 32).reshape(-1, 3), axis=0).shape[0]),
    }


async def _viewport():
    app = omni.kit.app.get_app()
    for _ in range(120):
        viewport = omni.kit.viewport.utility.get_active_viewport()
        if viewport is not None:
            break
        await app.next_update_async()
    else:
        raise RuntimeError("V3M-A requires an active viewport")
    viewport.camera_path = "/World/Camera"
    viewport.fill_frame = False
    viewport.resolution = RESOLUTION
    for _ in range(120):
        await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        if tuple(viewport.resolution) == RESOLUTION:
            return viewport
    raise RuntimeError("V3M-A viewport did not settle")


async def _capture(viewport, path):
    request = omni.kit.viewport.utility.capture_viewport_to_file(viewport, file_path=str(path))
    if not await request.wait_for_result(completion_frames=2):
        raise RuntimeError(f"V3M-A capture failed: {path}")
    for _ in range(30):
        if path.is_file():
            return _record(path)
        await asyncio.sleep(0.05)
    raise RuntimeError(f"V3M-A capture missing: {path}")


async def _settle(viewport, frames=12):
    for _ in range(frames):
        await omni.kit.viewport.utility.next_viewport_frame_async(viewport)


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
        for path in capture_dir.glob("*.png"):
            path.unlink()
        provider = ui.DynamicTextureProvider(TEXTURE_NAME)
        pixels = _checker_atlas()
        provider.set_bytes_data(
            pixels.reshape(-1).tolist(),
            [pixels.shape[1], pixels.shape[0]],
            TextureFormat.RGBA8_UNORM,
            strict=True,
        )
        authored = _build_stage(stage_path)
        await context.open_stage_async(str(stage_path))
        viewport = await _viewport()
        await _settle(viewport, 35)
        initial = await _capture(viewport, capture_dir / "mesh_checker_right_cap.png")
        stage = context.get_stage()
        root = stage.GetPrimAtPath(ROOT_PATH)
        collider = stage.GetPrimAtPath(COLLIDER_PATH)
        render = stage.GetPrimAtPath(RENDER_PATH)
        paths_before = tuple(str(prim.GetPath()) for prim in stage.Traverse())
        topology_before = _topology_digest(UsdGeom.Mesh(render))

        root.GetAttribute("xformOp:orient").Set(
            Gf.Quatf(0.0, Gf.Vec3f(0.0, 0.0, 1.0))
        )
        await _settle(viewport)
        left_cap = await _capture(viewport, capture_dir / "mesh_checker_left_cap.png")

        half = math.radians(32.0) * 0.5
        root.GetAttribute("xformOp:translate").Set(Gf.Vec3d(0.45, 0.22, 1.05))
        root.GetAttribute("xformOp:orient").Set(
            Gf.Quatf(math.cos(half), Gf.Vec3f(0.0, 0.0, math.sin(half)))
        )
        await _settle(viewport)
        transformed = await _capture(viewport, capture_dir / "mesh_checker_transformed.png")
        cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        root_world = cache.GetLocalToWorldTransform(root)
        collider_world = cache.GetLocalToWorldTransform(collider)
        render_world = cache.GetLocalToWorldTransform(render)
        world_error = max(
            _matrix_error(root_world, collider_world),
            _matrix_error(root_world, render_world),
        )
        paths_after_transform = tuple(str(prim.GetPath()) for prim in stage.Traverse())
        topology_after_transform = _topology_digest(UsdGeom.Mesh(render))
        if not stage.GetRootLayer().Save():
            raise RuntimeError("Unable to persist transformed V3M-A stage")

        await context.close_stage_async()
        await context.open_stage_async(str(stage_path))
        viewport = await _viewport()
        await _settle(viewport, 18)
        reloaded = await _capture(viewport, capture_dir / "mesh_checker_reloaded.png")
        stage = context.get_stage()
        root = stage.GetPrimAtPath(ROOT_PATH)
        collider = stage.GetPrimAtPath(COLLIDER_PATH)
        render = stage.GetPrimAtPath(RENDER_PATH)
        paths_reloaded = tuple(str(prim.GetPath()) for prim in stage.Traverse())
        topology_reloaded = _topology_digest(UsdGeom.Mesh(render))
        st = UsdGeom.PrimvarsAPI(render).GetPrimvar("st")
        uv_values = list(st.Get())
        uv_finite = all(math.isfinite(float(component)) for uv in uv_values for component in uv)
        face_counts = list(UsdGeom.Mesh(render).GetFaceVertexCountsAttr().Get())
        face_indices = list(UsdGeom.Mesh(render).GetFaceVertexIndicesAttr().Get())
        api_names = tuple(str(value) for value in render.GetAppliedSchemas())
        gates = {
            "root_is_xform": root.IsA(UsdGeom.Xform),
            "root_owns_rigidbody_mass_damping": root.HasAPI(UsdPhysics.RigidBodyAPI)
            and root.HasAPI(UsdPhysics.MassAPI)
            and root.HasAPI(PhysxSchema.PhysxRigidBodyAPI),
            "collider_is_analytic_x_cylinder": collider.IsA(UsdGeom.Cylinder)
            and UsdGeom.Cylinder(collider).GetAxisAttr().Get() == UsdGeom.Tokens.x,
            "collider_only_owns_collision": collider.HasAPI(UsdPhysics.CollisionAPI)
            and not collider.HasAPI(UsdPhysics.RigidBodyAPI)
            and not collider.HasAPI(UsdPhysics.MassAPI),
            "collider_hidden_from_rtx": UsdGeom.Imageable(collider).GetVisibilityAttr().Get()
            == UsdGeom.Tokens.invisible,
            "render_is_uv_mesh": render.IsA(UsdGeom.Mesh)
            and st
            and st.GetInterpolation() == UsdGeom.Tokens.faceVarying,
            "render_has_no_physics_api": not render.HasAPI(UsdPhysics.CollisionAPI)
            and not render.HasAPI(UsdPhysics.RigidBodyAPI)
            and not render.HasAPI(UsdPhysics.MassAPI)
            and not any("Physics" in name or "Physx" in name for name in api_names),
            "side_and_both_caps_authored": authored["face_classes"].count("side")
            == AXIAL_SEGMENTS * CIRCUMFERENTIAL_SEGMENTS
            and authored["face_classes"].count("left_cap") == CIRCUMFERENTIAL_SEGMENTS
            and authored["face_classes"].count("right_cap") == CIRCUMFERENTIAL_SEGMENTS,
            "uv_cardinality_and_range_valid": uv_finite
            and len(uv_values) == len(face_indices)
            and all(0.0 <= float(component) <= 1.0 for uv in uv_values for component in uv),
            "checker_visible_on_side_and_caps": min(
                initial["roi_unique_colors_32"], left_cap["roi_unique_colors_32"]
            ) >= 12,
            "children_follow_root_transform": world_error <= 1.0e-12,
            "no_live_prim_or_topology_change": paths_before
            == paths_after_transform
            == paths_reloaded
            and topology_before == topology_after_transform == topology_reloaded,
            "reload_preserves_hierarchy_and_uv": topology_reloaded
            == authored["topology_digest"]
            and len(face_counts) == len(authored["face_classes"]),
            "fixed_dynamic_uri_preserved": stage.GetPrimAtPath(
                "/World/Looks/MeshChecker/Texture"
            ).GetAttribute("inputs:file").Get().path
            == TEXTURE_URI,
        }
        report = {
            "schema": "campfire.phasev3ma.isolated_mesh_probe.v1",
            "status": "qualified" if all(gates.values()) else "not_qualified",
            "kit_flow_version": "Kit 110.2 / Flow 110.0.0",
            "scope": "isolated stage only; no production scene integration",
            "hierarchy": {
                "root": str(ROOT_PATH),
                "collider": str(COLLIDER_PATH),
                "render_surface": str(RENDER_PATH),
                "root_type": root.GetTypeName(),
                "collider_type": collider.GetTypeName(),
                "render_type": render.GetTypeName(),
                "world_transform_max_error": world_error,
            },
            "mesh": {
                "axial_segments": AXIAL_SEGMENTS,
                "circumferential_segments": CIRCUMFERENTIAL_SEGMENTS,
                "point_count": len(UsdGeom.Mesh(render).GetPointsAttr().Get()),
                "face_count": len(face_counts),
                "face_vertex_count": len(face_indices),
                "face_varying_uv_count": len(uv_values),
                "topology_sha256": topology_reloaded,
                "side_faces": authored["face_classes"].count("side"),
                "left_cap_faces": authored["face_classes"].count("left_cap"),
                "right_cap_faces": authored["face_classes"].count("right_cap"),
                "seam_vertices_duplicated": True,
            },
            "texture": {
                "uri": TEXTURE_URI,
                "format": "RGBA8_UNORM",
                "atlas_size": [pixels.shape[1], pixels.shape[0]],
                "regions": ["side", "left_cap", "right_cap"],
                "filter": "nearest",
            },
            "gates": gates,
            "captures": {
                "right_cap": initial,
                "left_cap": left_cap,
                "transformed": transformed,
                "reloaded": reloaded,
                "resolution": list(RESOLUTION),
                "kind": "fixed checker diagnostic; not a combustion trajectory",
            },
            "decision": {
                "isolated_mesh_qualified": all(gates.values()),
                "production_integration_allowed_next": all(gates.values()),
                "production_code_changed": False,
                "phase6dm_resumed": False,
            },
        }
        exit_code = 0
    except Exception as error:
        report = {
            "schema": "campfire.phasev3ma.isolated_mesh_probe.v1",
            "status": "error",
            "error": f"{type(error).__name__}: {error}",
        }
    finally:
        if provider is not None:
            provider.destroy()
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        carb.settings.get_settings().set("/phasev3ma/exitCode", exit_code)
        app.post_uncancellable_quit(exit_code)


asyncio.ensure_future(_run(_arguments()))
