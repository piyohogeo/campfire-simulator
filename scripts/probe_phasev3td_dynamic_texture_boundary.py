"""Phase V3T-D isolated DynamicTextureProvider publication boundary probe.

This script intentionally does not import or modify the production V3 observer.
All USD topology, material bindings, dynamic URIs, and providers are created
before the measured interval.
"""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
import json
import math
import time
from pathlib import Path

import carb
import numpy as np
import omni.kit.app
import omni.timeline
import omni.ui as ui
import omni.usd
from omni.gpu_foundation_factory import TextureFormat
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdShade


RESOLUTION = (640, 360)
CASE_NAMES = (
    "base_fixed",
    "emission_fixed",
    "both_fixed",
    "base_changing",
    "emission_changing",
    "both_changing",
)


def _settings_arguments():
    settings = carb.settings.get_settings()
    return {
        "output": Path(settings.get_as_string("/phasev3td/output")).resolve(),
        "mode": settings.get_as_string("/phasev3td/mode"),
        "width": settings.get_as_int("/phasev3td/width"),
        "height": settings.get_as_int("/phasev3td/height"),
        "run": settings.get_as_int("/phasev3td/run"),
        "warmup": settings.get_as_int("/phasev3td/warmup"),
        "samples": settings.get_as_int("/phasev3td/samples"),
    }


def _pointer_capsule(array):
    capsule_new = ctypes.pythonapi.PyCapsule_New
    capsule_new.restype = ctypes.py_object
    capsule_new.argtypes = (ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p)
    return capsule_new(ctypes.c_void_p(array.ctypes.data), None, None)


def _pixels(width, height, seed):
    y, x = np.indices((height, width), dtype=np.uint16)
    image = np.empty((height, width, 4), dtype=np.uint8)
    image[..., 0] = (x * 13 + seed * 17) % 256
    image[..., 1] = (y * 19 + seed * 29) % 256
    image[..., 2] = ((x + y) * 7 + seed * 37) % 256
    image[..., 3] = 255
    return np.ascontiguousarray(image)


def _set_shader_texture(shader, texture, output_name):
    shader.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("raw")
    shader.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
    shader.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
    shader.CreateOutput(output_name, Sdf.ValueTypeNames.Float3)
    return shader


def _build_stage(path, *, connected, base_uri, emission_uri, flow_enabled):
    path.unlink(missing_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    if flow_enabled:
        from campfire.app.flow_scene import populate_flow_scene

        populate_flow_scene(stage)
    else:
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        world = UsdGeom.Xform.Define(stage, "/World")
        stage.SetDefaultPrim(world.GetPrim())

    mesh = UsdGeom.Mesh.Define(stage, "/World/V3TDBoundaryMesh")
    mesh.CreatePointsAttr(
        [
            Gf.Vec3f(-1.8, 0.0, 0.0),
            Gf.Vec3f(1.8, 0.0, 0.0),
            Gf.Vec3f(1.8, 0.0, 2.0),
            Gf.Vec3f(-1.8, 0.0, 2.0),
        ]
    )
    mesh.CreateFaceVertexCountsAttr([4])
    mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    UsdGeom.PrimvarsAPI(mesh).CreatePrimvar(
        "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying
    ).Set([Gf.Vec2f(0, 0), Gf.Vec2f(1, 0), Gf.Vec2f(1, 1), Gf.Vec2f(0, 1)])
    mesh.CreateDisplayColorAttr([Gf.Vec3f(0.22, 0.11, 0.04)])

    if connected:
        material = UsdShade.Material.Define(stage, "/World/Looks/V3TDBoundary")
        surface = UsdShade.Shader.Define(stage, "/World/Looks/V3TDBoundary/Surface")
        surface.CreateIdAttr("UsdPreviewSurface")
        surface.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.6)
        reader = UsdShade.Shader.Define(stage, "/World/Looks/V3TDBoundary/Reader")
        reader.CreateIdAttr("UsdPrimvarReader_float2")
        reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
        base = UsdShade.Shader.Define(stage, "/World/Looks/V3TDBoundary/Base")
        base.CreateIdAttr("UsdUVTexture")
        base.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(base_uri))
        base.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
            reader.ConnectableAPI(), "result"
        )
        _set_shader_texture(base, base_uri, "rgb")
        emission = UsdShade.Shader.Define(stage, "/World/Looks/V3TDBoundary/Emission")
        emission.CreateIdAttr("UsdUVTexture")
        emission.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(emission_uri))
        emission.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
            reader.ConnectableAPI(), "result"
        )
        _set_shader_texture(emission, emission_uri, "rgb")
        surface.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
            base.ConnectableAPI(), "rgb"
        )
        surface.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
            emission.ConnectableAPI(), "rgb"
        )
        material.CreateSurfaceOutput().ConnectToSource(surface.ConnectableAPI(), "surface")
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)

    camera = stage.GetPrimAtPath("/World/Camera")
    if not camera:
        camera = UsdGeom.Camera.Define(stage, "/World/Camera").GetPrim()
    camera_schema = UsdGeom.Camera(camera)
    camera_schema.CreateFocalLengthAttr(42.0)
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(Gf.Vec3d(0.0, -7.0, 2.3), Gf.Vec3d(0.0, 0.0, 1.0), Gf.Vec3d(0, 0, 1))
    xform = UsdGeom.Xformable(camera)
    existing = xform.GetOrderedXformOps()
    if existing:
        existing[0].Set(view.GetInverse())
    else:
        xform.AddTransformOp().Set(view.GetInverse())
    if not stage.GetPrimAtPath("/World/Lights/Dome"):
        dome = UsdLux.DomeLight.Define(stage, "/World/Lights/Dome")
        dome.CreateIntensityAttr(850.0)
    if not stage.GetRootLayer().Save():
        raise RuntimeError("Unable to save Phase V3T-D stage")
    return {
        "prim_paths": [str(prim.GetPath()) for prim in stage.Traverse()],
        "base_uri": base_uri if connected else None,
        "emission_uri": emission_uri if connected else None,
    }


async def _viewport():
    from omni.kit.viewport import utility as viewport_utility

    app = omni.kit.app.get_app()
    for _ in range(240):
        viewport = viewport_utility.get_active_viewport()
        if viewport is not None:
            viewport.camera_path = "/World/Camera"
            viewport.fill_frame = False
            viewport.resolution = RESOLUTION
            return viewport
        await app.next_update_async()
    raise RuntimeError("Active viewport unavailable")


async def _advance(viewport, rtx):
    start = time.perf_counter_ns()
    if rtx:
        from omni.kit.viewport import utility as viewport_utility

        await viewport_utility.next_viewport_frame_async(viewport)
    else:
        await omni.kit.app.get_app().next_update_async()
    return (time.perf_counter_ns() - start) / 1.0e6


def _api_contract(provider):
    gpu_method = getattr(provider, "set_bytes_data_from_gpu", None)
    managed = getattr(provider, "get_managed_resource", None)
    return {
        "dynamic_texture_provider_doc": getattr(ui.DynamicTextureProvider, "__doc__", None),
        "set_raw_bytes_data_doc": getattr(provider.set_raw_bytes_data, "__doc__", None),
        "set_bytes_data_from_gpu_available": gpu_method is not None,
        "set_bytes_data_from_gpu_doc": getattr(gpu_method, "__doc__", None),
        "get_managed_resource_available": managed is not None,
        "get_managed_resource_doc": getattr(managed, "__doc__", None),
        "managed_resource_inspection_attempted": False,
        "managed_resource_cached": False,
    }


def _case_parts(case_name):
    target, behavior = case_name.split("_", 1)
    return target, behavior


async def _run(arguments):
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    output = arguments["output"]
    mode = arguments["mode"]
    width, height = arguments["width"], arguments["height"]
    run_index = arguments["run"]
    warmup = arguments["warmup"]
    sample_count = arguments["samples"]
    is_gpu = mode.startswith("gpu_")
    connected = "unconnected" not in mode
    rtx = "_rtx_flow_" in mode
    flow = mode.endswith("flow_on")
    forced_behavior = "fixed" if mode == "cpu_unconnected_fixed" else (
        "changing" if mode == "cpu_unconnected_changing" else None
    )
    name_prefix = f"campfire_phasev3td_{mode}_{width}x{height}_r{run_index}"
    base_uri = f"dynamic://{name_prefix}_base"
    emission_uri = f"dynamic://{name_prefix}_emission"
    providers = []
    report = None
    exit_code = 1
    gpu_arrays = None
    try:
        if width <= 0 or height <= 0 or warmup < 1 or sample_count < 100:
            raise ValueError("Invalid Phase V3T-D dimensions/warmup/sample count")
        base = _pixels(width, height, 1)
        emission = _pixels(width, height, 2)
        providers = [ui.DynamicTextureProvider(name_prefix + "_base"), ui.DynamicTextureProvider(name_prefix + "_emission")]
        api = _api_contract(providers[0])
        capsules = [_pointer_capsule(base), _pointer_capsule(emission)]
        warp_contract = {
            "imported": False,
            "safe_owner_available": False,
            "source_sync": None,
            "device": None,
            "allocation_lifetime": "providers destroyed before probe-owned arrays are released",
        }
        if is_gpu:
            if not api["set_bytes_data_from_gpu_available"]:
                raise RuntimeError("GPU publication API unavailable")
            import warp as wp

            wp.init()
            device = wp.get_device("cuda:0")
            host_arrays = [wp.array(base.reshape(-1), dtype=wp.uint8, device="cpu", copy=False), wp.array(emission.reshape(-1), dtype=wp.uint8, device="cpu", copy=False)]
            device_arrays = [wp.empty(base.size, dtype=wp.uint8, device=device), wp.empty(emission.size, dtype=wp.uint8, device=device)]
            for destination, source in zip(device_arrays, host_arrays):
                wp.copy(destination, source)
            wp.synchronize_device(device)
            gpu_arrays = (wp, device, host_arrays, device_arrays)
            warp_contract.update(
                imported=True,
                safe_owner_available=True,
                source_sync="warp.synchronize_device after every host-to-device copy",
                device=str(device),
                device_ordinal=getattr(device, "ordinal", None),
                pointer_attribute_doc="warp.array public ptr attribute",
            )

        def publish(indices):
            start = time.perf_counter_ns()
            if is_gpu:
                device_arrays = gpu_arrays[3]
                for index in indices:
                    providers[index].set_bytes_data_from_gpu(
                        int(device_arrays[index].ptr), [width, height], TextureFormat.RGBA8_UNORM, strict=True
                    )
            else:
                for index in indices:
                    providers[index].set_raw_bytes_data(
                        capsules[index], [width, height], TextureFormat.RGBA8_UNORM, strict=True
                    )
            return (time.perf_counter_ns() - start) / 1.0e6

        publish((0, 1))
        contract = _build_stage(
            output.with_suffix(".usda"), connected=connected, base_uri=base_uri,
            emission_uri=emission_uri, flow_enabled=flow,
        )
        await context.open_stage_async(str(output.with_suffix(".usda")))
        viewport = await _viewport() if rtx else None
        if flow:
            timeline.play()
        for _ in range(60 if rtx else 20):
            await _advance(viewport, rtx)
        stage = context.get_stage()
        stable_updates = 0
        previous_paths = None
        stabilization_updates = 0
        for stabilization_updates in range(1, 2401):
            await _advance(viewport, rtx)
            if not rtx:
                # The editor root creates its camera helper after asynchronous
                # renderer initialization, based on wall time rather than only
                # update count. This delay is outside the measured population.
                await asyncio.sleep(0.01)
            current_paths = tuple(str(prim.GetPath()) for prim in stage.Traverse())
            stable_updates = stable_updates + 1 if current_paths == previous_paths else 0
            previous_paths = current_paths
            if stable_updates >= 30:
                break
        else:
            raise RuntimeError("Stage topology did not stabilize before measurement")
        prim_paths_before_measurement = [str(prim.GetPath()) for prim in stage.Traverse()]

        order = list(CASE_NAMES)
        order = order[run_index % len(order):] + order[:run_index % len(order)]
        if forced_behavior:
            order = [name for name in order if name.endswith(forced_behavior)]
        samples = []
        sequence = 0
        for case_name in order:
            target, behavior = _case_parts(case_name)
            indices = (0,) if target == "base" else ((1,) if target == "emission" else (0, 1))
            for iteration in range(warmup + sample_count):
                prep_start = time.perf_counter_ns()
                if behavior == "changing":
                    for index in indices:
                        np.bitwise_xor((base, emission)[index][..., :3], np.uint8(1), out=(base, emission)[index][..., :3])
                source_prepare_ms = (time.perf_counter_ns() - prep_start) / 1.0e6
                staging_ms = 0.0
                if is_gpu:
                    wp, device, host_arrays, device_arrays = gpu_arrays
                    staging_start = time.perf_counter_ns()
                    for index in indices:
                        wp.copy(device_arrays[index], host_arrays[index])
                    wp.synchronize_device(device)
                    staging_ms = (time.perf_counter_ns() - staging_start) / 1.0e6
                setter_ms = publish(indices)
                reflection_ms = await _advance(viewport, rtx)
                if iteration >= warmup:
                    sequence += 1
                    samples.append(
                        {
                            "sequence": sequence,
                            "case": case_name,
                            "iteration": iteration - warmup,
                            "source_prepare_ms": source_prepare_ms,
                            "cpu_to_gpu_staging_ms": staging_ms,
                            "provider_setter_ms": setter_ms,
                            "publication_to_next_render_ms": reflection_ms if rtx else None,
                            "render_update_count": 1 if rtx else 0,
                            "bytes": width * height * 4 * len(indices),
                            "api_calls": len(indices),
                        }
                    )

        flow_state = {"enabled": flow, "active_blocks": None}
        if flow:
            try:
                import omni.flowusd._flowusd as flowusd

                flow_state["active_blocks"] = int(flowusd.acquire_flowusd_interface().get_active_block_count())
            except Exception as error:
                flow_state["query_error"] = f"{type(error).__name__}: {error}"
        prim_paths_after_measurement = [str(prim.GetPath()) for prim in stage.Traverse()]
        report = {
            "schema": "campfire.phasev3td.dynamic_texture_boundary.samples.v1",
            "status": "ok",
            "mode": mode,
            "source": "gpu" if is_gpu else "cpu_raw_pointer",
            "atlas": {"width": width, "height": height, "bytes_per_texture": width * height * 4},
            "run": run_index,
            "warmup_per_case": warmup,
            "sample_count_per_case": sample_count,
            "case_order": order,
            "environment": {"connected": connected, "rtx": rtx, "flow": flow, "resolution": list(RESOLUTION)},
            "api": api,
            "gpu_owner": warp_contract,
            "stage_contract": {
                **contract,
                "stabilization_updates": stabilization_updates,
                "stable_updates_required": 30,
                "prim_paths_before_measurement": prim_paths_before_measurement,
                "prim_paths_after_measurement": prim_paths_after_measurement,
                "topology_unchanged_during_measurement": prim_paths_before_measurement == prim_paths_after_measurement,
                "usd_revision_sets_in_measurement": 0,
                "prim_or_binding_changes_in_measurement": 0,
            },
            "flow_state": flow_state,
            "samples": samples,
        }
        exit_code = 0
    except Exception as error:
        report = {
            "schema": "campfire.phasev3td.dynamic_texture_boundary.samples.v1",
            "status": "error",
            "mode": mode,
            "error": f"{type(error).__name__}: {error}",
        }
    finally:
        timeline.stop()
        for provider in providers:
            provider.destroy()
        gpu_arrays = None
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        app.post_uncancellable_quit(exit_code)


asyncio.ensure_future(_run(_settings_arguments()))
