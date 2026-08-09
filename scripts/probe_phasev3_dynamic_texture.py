"""Fixed Kit/RTX feasibility probe for dynamic texture and analytic Cylinder UV."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import carb
import numpy as np
import omni.kit.app
import omni.kit.viewport.utility
import omni.timeline
import omni.ui as ui
import omni.usd
from omni.gpu_foundation_factory import TextureFormat
from PIL import Image
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdShade


RESOLUTION = (1280, 720)
TEXTURE_NAME = "campfire_phasev3_surface_probe"
TEXTURE_URI = f"dynamic://{TEXTURE_NAME}"


def _arguments():
    settings = carb.settings.get_settings()
    return {
        "output": Path(settings.get_as_string("/phasev3/output")),
        "capture_dir": Path(settings.get_as_string("/phasev3/captureDir")),
    }


def _checker(width=12, height=24, alternate=False):
    y, x = np.indices((height, width))
    checks = ((x // 2 + y // 3) % 2).astype(np.uint8)
    image = np.empty((height, width, 4), dtype=np.uint8)
    if alternate:
        left, right = np.array([25, 245, 70], np.uint8), np.array([245, 30, 210], np.uint8)
    else:
        left, right = np.array([245, 35, 25], np.uint8), np.array([25, 75, 245], np.uint8)
    image[..., :3] = np.where(checks[..., None] == 0, left, right)
    image[0, :, :3] = np.array([255, 255, 255], np.uint8)
    image[-1, :, :3] = np.array([5, 5, 5], np.uint8)
    image[:, 0, :3] = np.array([255, 220, 20], np.uint8)
    image[:, -1, :3] = np.array([20, 240, 240], np.uint8)
    image[..., 3] = 255
    return image


def _build_stage(path):
    path.unlink(missing_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    ground = UsdGeom.Cube.Define(stage, "/World/Ground")
    ground.CreateSizeAttr(1.0)
    ground.AddScaleOp().Set(Gf.Vec3f(8.0, 8.0, 0.1))
    ground.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, -0.1))
    ground.CreateDisplayColorAttr([Gf.Vec3f(0.06, 0.06, 0.07)])
    cylinder = UsdGeom.Cylinder.Define(stage, "/World/ProbeCylinder")
    cylinder.CreateAxisAttr(UsdGeom.Tokens.x)
    cylinder.CreateRadiusAttr(0.42)
    cylinder.CreateHeightAttr(3.0)
    cylinder.AddTranslateOp().Set(Gf.Vec3d(-0.8, 0.0, 0.70))
    reference = UsdGeom.Mesh.Define(stage, "/World/TransportReferenceQuad")
    reference.CreatePointsAttr(
        [
            Gf.Vec3f(1.0, 0.2, 0.15),
            Gf.Vec3f(3.0, 0.2, 0.15),
            Gf.Vec3f(3.0, 0.2, 2.15),
            Gf.Vec3f(1.0, 0.2, 2.15),
        ]
    )
    reference.CreateFaceVertexCountsAttr([4])
    reference.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    UsdGeom.PrimvarsAPI(reference).CreatePrimvar(
        "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying
    ).Set(
        [
            Gf.Vec2f(0.0, 0.0),
            Gf.Vec2f(1.0, 0.0),
            Gf.Vec2f(1.0, 1.0),
            Gf.Vec2f(0.0, 1.0),
        ]
    )
    material = UsdShade.Material.Define(stage, "/World/Looks/DynamicChecker")
    surface = UsdShade.Shader.Define(stage, "/World/Looks/DynamicChecker/Surface")
    surface.CreateIdAttr("UsdPreviewSurface")
    surface.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.45)
    reader = UsdShade.Shader.Define(stage, "/World/Looks/DynamicChecker/PrimvarReader")
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    reader.CreateInput("fallback", Sdf.ValueTypeNames.Float2).Set(Gf.Vec2f(0.0, 0.0))
    reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    texture = UsdShade.Shader.Define(stage, "/World/Looks/DynamicChecker/Texture")
    texture.CreateIdAttr("UsdUVTexture")
    texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(TEXTURE_URI))
    texture.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("raw")
    texture.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
    texture.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
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
    UsdShade.MaterialBindingAPI.Apply(cylinder.GetPrim()).Bind(material)
    UsdShade.MaterialBindingAPI.Apply(reference.GetPrim()).Bind(material)
    camera = UsdGeom.Camera.Define(stage, "/World/Camera")
    camera.CreateFocalLengthAttr(42.0)
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(
        Gf.Vec3d(6.4, -10.2, 5.4),
        Gf.Vec3d(0.2, 0.0, 0.95),
        Gf.Vec3d(0.0, 0.0, 1.0),
    )
    camera.AddTransformOp().Set(view.GetInverse())
    dome = UsdLux.DomeLight.Define(stage, "/World/Lights/Dome")
    dome.CreateIntensityAttr(700.0)
    dome.CreateColorAttr(Gf.Vec3f(0.7, 0.75, 0.85))
    key = UsdLux.SphereLight.Define(stage, "/World/Lights/Key")
    key.CreateIntensityAttr(18000.0)
    key.CreateRadiusAttr(0.4)
    key.AddTranslateOp().Set(Gf.Vec3d(-1.5, -2.0, 4.0))
    if not stage.GetRootLayer().Save():
        raise RuntimeError("Unable to save Phase V3 probe stage")
    return {
        "prim_paths": tuple(str(prim.GetPath()) for prim in stage.Traverse()),
        "asset_path": str(texture.GetInput("file").Get()),
        "authored_primvars": [
            primvar.GetPrimvarName()
            for primvar in UsdGeom.PrimvarsAPI(cylinder).GetPrimvars()
        ],
    }


async def _viewport():
    app = omni.kit.app.get_app()
    for _ in range(120):
        viewport = omni.kit.viewport.utility.get_active_viewport()
        if viewport is not None:
            break
        await app.next_update_async()
    else:
        raise RuntimeError("Phase V3 probe requires an active viewport")
    viewport.camera_path = "/World/Camera"
    viewport.fill_frame = False
    viewport.resolution = RESOLUTION
    for _ in range(120):
        await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        if tuple(viewport.resolution) == RESOLUTION:
            return viewport
    raise RuntimeError("Phase V3 viewport did not settle")


def _image_record(path):
    payload = path.read_bytes()
    image = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
    roi = image[220:560, 280:1000]
    quantized = (roi // 32).reshape(-1, 3)
    return {
        "path": str(path),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "roi_quantized_unique_colors": int(np.unique(quantized, axis=0).shape[0]),
        "roi_rgb_mean": [float(value) for value in roi.mean(axis=(0, 1))],
    }


async def _capture(viewport, path):
    request = omni.kit.viewport.utility.capture_viewport_to_file(viewport, file_path=str(path))
    if not await request.wait_for_result(completion_frames=2):
        raise RuntimeError(f"Phase V3 capture failed: {path}")
    for _ in range(30):
        if path.is_file():
            return _image_record(path)
        await asyncio.sleep(0.05)
    raise RuntimeError("Phase V3 capture file is missing")


async def _run(arguments):
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    output = arguments["output"].resolve()
    capture_dir = arguments["capture_dir"].resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    capture_dir.mkdir(parents=True, exist_ok=True)
    for old in capture_dir.glob("*.png"):
        old.unlink()
    stage_path = output.with_suffix(".usda")
    report = None
    exit_code = 1
    provider = None
    half_provider = None
    try:
        provider = ui.DynamicTextureProvider(TEXTURE_NAME)
        first_pixels = _checker()
        provider.set_bytes_data(
            first_pixels.reshape(-1).tolist(),
            [first_pixels.shape[1], first_pixels.shape[0]],
            TextureFormat.RGBA8_UNORM,
            strict=True,
        )
        half_upload = {"available": hasattr(provider, "set_bytes_data"), "succeeded": False}
        try:
            half_provider = ui.DynamicTextureProvider(TEXTURE_NAME + "_half")
            half_pixels = (first_pixels.astype(np.float32) / 255.0).astype(np.float16)
            half_provider.set_bytes_data(
                half_pixels.reshape(-1).tolist(),
                [half_pixels.shape[1], half_pixels.shape[0]],
                TextureFormat.RGBA16_SFLOAT,
                strict=True,
            )
            half_upload["succeeded"] = True
        except Exception as error:
            half_upload["error"] = f"{type(error).__name__}: {error}"

        contract = _build_stage(stage_path)
        await context.open_stage_async(str(stage_path))
        viewport = await _viewport()
        for _ in range(35):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        initial = await _capture(viewport, capture_dir / "dynamic_checker_initial.png")
        stage = context.get_stage()
        prim_paths_before = tuple(str(prim.GetPath()) for prim in stage.Traverse())
        texture_attr = stage.GetPrimAtPath(
            "/World/Looks/DynamicChecker/Texture"
        ).GetAttribute("inputs:file")
        asset_before = texture_attr.Get().path

        second_pixels = _checker(alternate=True)
        provider.set_bytes_data(
            second_pixels.reshape(-1).tolist(),
            [second_pixels.shape[1], second_pixels.shape[0]],
            TextureFormat.RGBA8_UNORM,
            strict=True,
        )
        latency_captures = []
        for frame in range(1, 5):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
            latency_captures.append(
                await _capture(viewport, capture_dir / f"dynamic_checker_update_{frame}.png")
            )
        updated = latency_captures[-1]

        cylinder = stage.GetPrimAtPath("/World/ProbeCylinder")
        cylinder.GetAttribute("xformOp:translate").Set(Gf.Vec3d(0.35, 0.20, 0.85))
        UsdGeom.Xformable(cylinder).AddRotateZOp().Set(37.0)
        for _ in range(8):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        transformed = await _capture(viewport, capture_dir / "dynamic_checker_transformed.png")

        timeline.stop()
        await app.next_update_async()
        timeline.play()
        await app.next_update_async()
        timeline.stop()
        await context.close_stage_async()
        await context.open_stage_async(str(stage_path))
        viewport = await _viewport()
        for _ in range(12):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        reloaded = await _capture(viewport, capture_dir / "dynamic_checker_reloaded.png")
        stage = context.get_stage()
        prim_paths_after = tuple(str(prim.GetPath()) for prim in stage.Traverse())
        asset_after = (
            stage.GetPrimAtPath("/World/Looks/DynamicChecker/Texture")
            .GetAttribute("inputs:file")
            .Get()
            .path
        )

        first_changed_frame = next(
            (
                index + 1
                for index, capture in enumerate(latency_captures)
                if max(
                    abs(capture["roi_rgb_mean"][channel] - initial["roi_rgb_mean"][channel])
                    for channel in range(3)
                )
                > 4.0
            ),
            None,
        )
        update_visible = first_changed_frame is not None
        # Analytic Cylinder has no authored st and the capture is used to check
        # whether RTX synthesizes a stable side/cap mapping.  A uniform fallback
        # cannot map the 360 stable surface identities.
        uv_mapping_qualified = "st" in contract["authored_primvars"] and initial[
            "roi_quantized_unique_colors"
        ] >= 8
        gates = {
            "dynamic_provider_available": True,
            "fixed_dynamic_uri_preserved": asset_before == asset_after == TEXTURE_URI,
            "cpu_rgba8_upload_visible": update_visible,
            "rgba16f_upload_accepted": half_upload["succeeded"],
            "no_live_prim_topology_change": prim_paths_before == prim_paths_after,
            "stage_reload_reacquires_resource": reloaded["bytes"] > 0,
            "analytic_cylinder_uv_maps_360_cells": uv_mapping_qualified,
            "side_cap_seam_orientation_qualified": uv_mapping_qualified,
            "object_local_mapping_after_transform": uv_mapping_qualified,
        }
        report = {
            "schema": "campfire.phasev3.dynamic_texture_feasibility.v1",
            "status": "qualified" if all(gates.values()) else "not_qualified",
            "kit_flow_version": "Kit 110.2 / Flow 110.0.0",
            "transport": {
                "uri": TEXTURE_URI,
                "cpu_rgba8": "accepted_and_rendered" if update_visible else "not_observed",
                "cpu_rgba16f": half_upload,
                "gpu_upload_api_available": hasattr(provider, "set_bytes_data_from_gpu"),
                "gpu_upload_qualified": False,
                "gpu_upload_reason": "no owned public GPU pointer source in this visual payload probe",
                "first_observed_changed_frame": first_changed_frame,
            },
            "uv": {
                "analytic_prim": "UsdGeom.Cylinder",
                "authored_primvars": contract["authored_primvars"],
                "reader": "UsdPrimvarReader_float2(st)",
                "fallback": [0.0, 0.0],
                "maps_360_surface_cells": uv_mapping_qualified,
                "failure_boundary": (
                    None
                    if uv_mapping_qualified
                    else "analytic Cylinder exposes no authored controllable st primvar for stable side/end-cap surface-cell atlas mapping"
                ),
            },
            "gates": gates,
            "captures": {
                "initial": initial,
                "latency": latency_captures,
                "updated": updated,
                "transformed": transformed,
                "reloaded": reloaded,
                "resolution": list(RESOLUTION),
            },
            "decision": {
                "production_integration_attempted": all(gates.values()),
                "production_integration_implemented": False,
                "stop_reason": (
                    None
                    if all(gates.values())
                    else "required analytic Cylinder UV gate did not qualify; Mesh/shape/V4 expansion forbidden"
                ),
                "v0_retained": True,
                "v1_fallback_retained": True,
                "feature_default_changed": False,
            },
        }
        exit_code = 0
    except Exception as error:
        report = {
            "schema": "campfire.phasev3.dynamic_texture_feasibility.v1",
            "status": "error",
            "error": f"{type(error).__name__}: {error}",
        }
    finally:
        if half_provider is not None:
            half_provider.destroy()
        if provider is not None:
            provider.destroy()
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        carb.settings.get_settings().set("/phasev3/exitCode", exit_code)
        app.post_uncancellable_quit(exit_code)


asyncio.ensure_future(_run(_arguments()))
