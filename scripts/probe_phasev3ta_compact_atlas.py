"""Kit/RTX qualification probe for the one-texel wood visual atlas."""

from __future__ import annotations

import asyncio
import hashlib
import json
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
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdShade


RESOLUTION = (1280, 720)


def _arguments():
    settings = carb.settings.get_settings()
    return {
        "output": Path(settings.get_as_string("/phasev3ta/output")),
        "capture_dir": Path(settings.get_as_string("/phasev3ta/captureDir")),
    }


def _encoded_color(log_slot, surface_index):
    code = log_slot * campfire.app.WOOD_SURFACE_CELLS_PER_LOG + surface_index + 1
    return np.array(
        (40 + (code * 37) % 200, 40 + (code * 73) % 200, 40 + (code * 109) % 200),
        dtype=np.uint8,
    )


def _checker_atlas(descriptor):
    image = np.zeros((descriptor.height_px, descriptor.width_px, 4), dtype=np.uint8)
    image[..., 3] = 255
    for log_slot in range(descriptor.render_log_count):
        tile_x = log_slot % descriptor.tile_columns
        tile_y = log_slot // descriptor.tile_columns
        for surface_index in range(campfire.app.WOOD_SURFACE_CELLS_PER_LOG):
            cell_x = surface_index % 24
            cell_y = surface_index // 24
            x = (tile_x * 24 + cell_x) * descriptor.cell_stride_px
            y = (tile_y * 15 + cell_y) * descriptor.cell_stride_px
            image[
                y : y + descriptor.cell_stride_px,
                x : x + descriptor.cell_stride_px,
                :3,
            ] = _encoded_color(log_slot, surface_index)
    return image


def _bind_checker_material(stage, texture_uri):
    material = UsdShade.Material.Define(stage, "/World/Looks/CompactChecker")
    surface = UsdShade.Shader.Define(stage, "/World/Looks/CompactChecker/Surface")
    surface.CreateIdAttr("UsdPreviewSurface")
    surface.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.6)
    reader = UsdShade.Shader.Define(stage, "/World/Looks/CompactChecker/Reader")
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    texture = UsdShade.Shader.Define(stage, "/World/Looks/CompactChecker/Texture")
    texture.CreateIdAttr("UsdUVTexture")
    texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(texture_uri))
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
        UsdShade.MaterialBindingAPI.Apply(
            campfire.app.get_log_render_surface(stage, log_id)
        ).Bind(material)


def _managed_digest(stage):
    records = {}
    for log_id in campfire.app.list_log_ids(stage):
        mesh = UsdGeom.Mesh(campfire.app.get_log_render_surface(stage, log_id))
        primvars = UsdGeom.PrimvarsAPI(mesh.GetPrim())
        value = {
            "points": [[float(v) for v in p] for p in mesh.GetPointsAttr().Get()],
            "counts": list(mesh.GetFaceVertexCountsAttr().Get()),
            "indices": list(mesh.GetFaceVertexIndicesAttr().Get()),
            "surface": list(primvars.GetPrimvar("surfaceIndex").Get()),
            "st": [[float(v) for v in uv] for uv in primvars.GetPrimvar("st").Get()],
        }
        records[log_id] = hashlib.sha256(
            json.dumps(value, sort_keys=True).encode("utf-8")
        ).hexdigest()
    return records


def _build_stage(path, descriptor, texture_uri):
    path.unlink(missing_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.Xform.Define(stage, "/World/Logs")
    columns = min(5, descriptor.render_log_count)
    rows = int(np.ceil(descriptor.render_log_count / columns))
    for slot in range(descriptor.render_log_count):
        column = slot % columns
        row = slot // columns
        if descriptor.render_log_count == 4:
            x = (column - 1.5) * 1.35
            y = -0.55 if slot < 2 else 0.75
            rotation = 0.0 if slot < 2 else 180.0
            radius = 0.28
            length = 1.15
        else:
            x = (column - 2.0) * 1.18
            y = (row - (rows - 1) * 0.5) * 0.88
            rotation = 12.0 * (slot % 3)
            radius = 0.20
            length = 0.92
        campfire.app.create_log(
            stage,
            campfire.app.LogSpec(
                f"Log_{slot:02d}", (x, y, 0.36), rotation, radius, length
            ),
            render_hierarchy=True,
            render_log_slot=slot,
            render_atlas_descriptor=descriptor,
        )
    _bind_checker_material(stage, texture_uri)
    ground = UsdGeom.Cube.Define(stage, "/World/Ground")
    ground.CreateSizeAttr(1.0)
    ground.AddScaleOp().Set(Gf.Vec3f(6.5, 4.5, 0.08))
    ground.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, -0.08))
    ground.CreateDisplayColorAttr([Gf.Vec3f(0.025, 0.025, 0.035)])
    camera = UsdGeom.Camera.Define(stage, "/World/Camera")
    camera.CreateFocalLengthAttr(48.0 if descriptor.render_log_count == 4 else 42.0)
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(
        Gf.Vec3d(6.4, -9.4, 6.3) if descriptor.render_log_count == 4 else Gf.Vec3d(7.8, -11.5, 8.8),
        Gf.Vec3d(0.0, 0.15, 0.38),
        Gf.Vec3d(0.0, 0.0, 1.0),
    )
    camera.AddTransformOp().Set(view.GetInverse())
    dome = UsdLux.DomeLight.Define(stage, "/World/Lights/Dome")
    dome.CreateIntensityAttr(500.0)
    if not stage.GetRootLayer().Save():
        raise RuntimeError("Unable to save compact-atlas probe stage")
    return _managed_digest(stage)


def _descriptor_contract(descriptor, atlas):
    samples = {}
    centres = True
    for slot in range(descriptor.render_log_count):
        for surface_index in range(campfire.app.WOOD_SURFACE_CELLS_PER_LOG):
            uv = campfire.app.atlas_uv(slot, surface_index, descriptor)
            x = float(uv[0]) * descriptor.width_px
            y = float(uv[1]) * descriptor.height_px
            centres = centres and abs((x / descriptor.cell_stride_px) % 1.0 - 0.5) < 1.0e-5
            centres = centres and abs((y / descriptor.cell_stride_px) % 1.0 - 0.5) < 1.0e-5
            pixel_x = min(descriptor.width_px - 1, int(x))
            pixel_y = min(descriptor.height_px - 1, int(y))
            samples[(slot, surface_index)] = tuple(int(v) for v in atlas[pixel_y, pixel_x, :3])
    encoded_exact = all(
        samples[(slot, surface_index)] == tuple(int(v) for v in _encoded_color(slot, surface_index))
        for slot in range(descriptor.render_log_count)
        for surface_index in range(campfire.app.WOOD_SURFACE_CELLS_PER_LOG)
    )
    return {
        "descriptor": {
            "render_log_count": descriptor.render_log_count,
            "tile_columns": descriptor.tile_columns,
            "tile_rows": descriptor.tile_rows,
            "cell_stride_px": descriptor.cell_stride_px,
            "width_px": descriptor.width_px,
            "height_px": descriptor.height_px,
            "bytes_two_rgba8": 2 * descriptor.bytes_per_rgba8_atlas,
        },
        "unique_uv_samples": len(samples),
        "all_uvs_are_texel_centres": centres,
        "encoded_samples_exact": encoded_exact,
        "log_tile_first_samples": [list(samples[(slot, 0)]) for slot in range(descriptor.render_log_count)],
    }


async def _viewport():
    app = omni.kit.app.get_app()
    for _ in range(120):
        viewport = omni.kit.viewport.utility.get_active_viewport()
        if viewport is not None:
            break
        await app.next_update_async()
    else:
        raise RuntimeError("V3T-A requires a viewport")
    viewport.camera_path = "/World/Camera"
    viewport.fill_frame = False
    viewport.resolution = RESOLUTION
    for _ in range(120):
        await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        if tuple(viewport.resolution) == RESOLUTION:
            return viewport
    raise RuntimeError("V3T-A viewport did not settle")


async def _capture(viewport, path):
    for _ in range(24):
        await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
    request = omni.kit.viewport.utility.capture_viewport_to_file(viewport, file_path=str(path))
    if not await request.wait_for_result(completion_frames=2):
        raise RuntimeError(f"V3T-A capture failed: {path}")
    for _ in range(30):
        if path.is_file():
            pixels = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
            return {
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "quantized_colors": int(
                    np.unique((pixels[100:680, 80:1200] // 20).reshape(-1, 3), axis=0).shape[0]
                ),
            }
        await asyncio.sleep(0.05)
    raise RuntimeError(f"V3T-A capture missing: {path}")


def _capture_difference(left_path, right_path):
    left = np.asarray(Image.open(left_path).convert("RGB"), dtype=np.int16)
    right = np.asarray(Image.open(right_path).convert("RGB"), dtype=np.int16)
    difference = np.abs(left - right)
    return {
        "mean_absolute": float(np.mean(difference)),
        "p95_absolute": float(np.percentile(difference, 95)),
        "maximum_absolute": int(np.max(difference)),
    }


async def _run(arguments):
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    output = arguments["output"].resolve()
    capture_dir = arguments["capture_dir"].resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    capture_dir.mkdir(parents=True, exist_ok=True)
    providers = []
    report = None
    exit_code = 1
    try:
        variants = {}
        initial_digest = None
        final_digest = None
        managed_paths = None
        for stride in (1, 2, 4):
            descriptor = campfire.app.compact_atlas_descriptor(4, cell_stride_px=stride)
            atlas = _checker_atlas(descriptor)
            texture_name = f"campfire_phasev3ta_stride_{stride}"
            provider = ui.DynamicTextureProvider(texture_name)
            providers.append(provider)
            provider.set_bytes_data(
                atlas.reshape(-1).tolist(),
                [descriptor.width_px, descriptor.height_px],
                TextureFormat.RGBA8_UNORM,
                strict=True,
            )
            stage_path = output.parent / f"compact_stride_{stride}.usda"
            digest = _build_stage(stage_path, descriptor, f"dynamic://{texture_name}")
            await context.open_stage_async(str(stage_path))
            viewport = await _viewport()
            capture = await _capture(viewport, capture_dir / f"compact_stride_{stride}_four_logs.png")
            contract = _descriptor_contract(descriptor, atlas)
            stage = context.get_stage()
            if stride == 1:
                initial_digest = digest
                managed_paths = tuple(
                    str(prim.GetPath())
                    for root_path in ("/World/Logs", "/World/Looks")
                    for prim in Usd.PrimRange(stage.GetPrimAtPath(root_path))
                )
                campfire.app.move_log(stage, "Log_03", (1.7, 0.85, 0.82), 90.0)
                transformed = await _capture(
                    viewport, capture_dir / "compact_stride_1_transformed.png"
                )
                if not stage.GetRootLayer().Save():
                    raise RuntimeError("Unable to save transformed compact stage")
                await context.close_stage_async()
                await context.open_stage_async(str(stage_path))
                viewport = await _viewport()
                reloaded = await _capture(
                    viewport, capture_dir / "compact_stride_1_reloaded.png"
                )
                stage = context.get_stage()
                final_digest = _managed_digest(stage)
                reloaded_paths = tuple(
                    str(prim.GetPath())
                    for root_path in ("/World/Logs", "/World/Looks")
                    for prim in Usd.PrimRange(stage.GetPrimAtPath(root_path))
                )
                contract["transformed_capture"] = transformed
                contract["reloaded_capture"] = reloaded
                contract["managed_paths_stable"] = managed_paths == reloaded_paths
            variants[stride] = {**contract, "capture": capture}
            await context.close_stage_async()
            provider.destroy()
            providers.remove(provider)

        descriptor20 = campfire.app.compact_atlas_descriptor(20)
        atlas20 = _checker_atlas(descriptor20)
        provider20 = ui.DynamicTextureProvider("campfire_phasev3ta_twenty")
        providers.append(provider20)
        provider20.set_bytes_data(
            atlas20.reshape(-1).tolist(),
            [descriptor20.width_px, descriptor20.height_px],
            TextureFormat.RGBA8_UNORM,
            strict=True,
        )
        stage20_path = output.parent / "compact_twenty_logs.usda"
        _build_stage(stage20_path, descriptor20, "dynamic://campfire_phasev3ta_twenty")
        await context.open_stage_async(str(stage20_path))
        viewport = await _viewport()
        capture20 = await _capture(viewport, capture_dir / "compact_stride_1_twenty_logs.png")
        contract20 = _descriptor_contract(descriptor20, atlas20)
        await context.close_stage_async()

        diff12 = _capture_difference(
            capture_dir / "compact_stride_1_four_logs.png",
            capture_dir / "compact_stride_2_four_logs.png",
        )
        gates = {
            "one_texel_four_log_descriptor_is_minimal": variants[1]["descriptor"]["width_px"] == 96
            and variants[1]["descriptor"]["height_px"] == 15,
            "one_texel_twenty_log_descriptor_is_120x60": contract20["descriptor"]["width_px"] == 120
            and contract20["descriptor"]["height_px"] == 60,
            "twenty_log_two_atlas_transfer_is_57600_bytes": contract20["descriptor"]["bytes_two_rgba8"] == 57_600,
            "all_four_log_uvs_are_unique_centres": variants[1]["unique_uv_samples"] == 1_440
            and variants[1]["all_uvs_are_texel_centres"],
            "all_twenty_log_uvs_are_unique_centres": contract20["unique_uv_samples"] == 7_200
            and contract20["all_uvs_are_texel_centres"],
            "encoded_surface_samples_are_exact": variants[1]["encoded_samples_exact"]
            and contract20["encoded_samples_exact"],
            "one_texel_and_two_texel_rtx_are_equivalent": diff12["mean_absolute"] <= 8.0
            and diff12["p95_absolute"] <= 24.0,
            "four_log_checker_is_visible": variants[1]["capture"]["quantized_colors"] >= 20,
            "twenty_log_checker_is_visible": capture20["quantized_colors"] >= 20,
            "transform_and_reload_preserve_topology_uv": initial_digest == final_digest,
            "managed_paths_are_stable": variants[1]["managed_paths_stable"],
            "one_texel_reduces_twenty_log_bytes_by_16x": variants[4]["descriptor"]["bytes_two_rgba8"]
            == 16 * variants[1]["descriptor"]["bytes_two_rgba8"]
            and contract20["descriptor"]["bytes_two_rgba8"] == 57_600,
        }
        report = {
            "schema": "campfire.phasev3ta.compact_atlas_probe.v1",
            "status": "qualified" if all(gates.values()) else "not_qualified",
            "gates": gates,
            "variants_four_logs": {str(key): value for key, value in variants.items()},
            "twenty_logs": {**contract20, "capture": capture20},
            "rtx_stride_1_vs_2": diff12,
            "sampler": {
                "min_filter": "nearest",
                "mag_filter": "nearest",
                "face_uv_rule": "all face vertices use one texel centre",
                "runtime_uv_changes": 0,
                "runtime_topology_changes": 0,
            },
            "decision": "adopt one texel per surface cell" if all(gates.values()) else "stop before V3T-B",
        }
        exit_code = 0 if all(gates.values()) else 1
    except Exception as error:
        report = {
            "schema": "campfire.phasev3ta.compact_atlas_probe.v1",
            "status": "error",
            "error": f"{type(error).__name__}: {error}",
        }
    finally:
        for provider in reversed(providers):
            provider.destroy()
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        app.post_uncancellable_quit(exit_code)


asyncio.ensure_future(_run(_arguments()))
