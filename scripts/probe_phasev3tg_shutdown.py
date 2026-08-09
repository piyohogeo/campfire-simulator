"""Phase V3T-G independent DynamicTextureProvider shutdown probe.

The probe owns all CPU and Warp allocations.  It changes no production module
and records fsync'd lifecycle markers so a native process crash remains
classifiable even when Python never regains control.
"""

from __future__ import annotations

import asyncio
import ctypes
import json
import os
import time
from pathlib import Path

import carb
import numpy as np
import omni.kit.app
import omni.kit.viewport.utility
import omni.timeline
import omni.ui as ui
import omni.usd
from omni.gpu_foundation_factory import TextureFormat
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade


WIDTH, HEIGHT = 120, 60
RESOLUTION = (1280, 720)
GPU_MODES = {
    "warp_only",
    "gpu_single_sync",
    "gpu_ring3_normal",
    "gpu_ring3_keep_allocations",
    "gpu_ring3_keep_providers",
    "gpu_ring3_stage_first",
}
_RETAINED = []


def _args():
    settings = carb.settings.get_settings()
    return {
        "output": Path(settings.get_as_string("/phasev3tg/output")).resolve(),
        "markers": Path(settings.get_as_string("/phasev3tg/markers")).resolve(),
        "mode": settings.get_as_string("/phasev3tg/mode"),
        "sequence": settings.get_as_string("/phasev3tg/sequence"),
        "warmup": settings.get_as_int("/phasev3tg/warmup"),
        "updates": settings.get_as_int("/phasev3tg/updates"),
        "run": settings.get_as_int("/phasev3tg/run"),
    }


def _marker(arguments, name, **detail):
    record = {"name": name, "wall_ns": time.time_ns(), "perf_ns": time.perf_counter_ns(), "detail": detail}
    arguments["markers"].parent.mkdir(parents=True, exist_ok=True)
    with arguments["markers"].open("a", encoding="utf-8", buffering=1) as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _capsule(array):
    capsule_new = ctypes.pythonapi.PyCapsule_New
    capsule_new.restype = ctypes.py_object
    capsule_new.argtypes = (ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p)
    return capsule_new(ctypes.c_void_p(array.ctypes.data), None, None)


def _fill(array, revision, texture):
    y, x = np.indices(array.shape[:2], dtype=np.uint16)
    array[..., 0] = (x * 7 + revision * 13 + texture * 41) & 255
    array[..., 1] = (y * 11 + revision * 17 + texture * 67) & 255
    array[..., 2] = ((x + y) * 5 + revision * 19 + texture * 29) & 255
    array[..., 3] = 255


def _panel(stage, path, material_path, uri, x0, x1):
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr([Gf.Vec3f(x0, -5, -0.7), Gf.Vec3f(x1, -5, -0.7), Gf.Vec3f(x1, -5, 0.7), Gf.Vec3f(x0, -5, 0.7)])
    mesh.CreateFaceVertexCountsAttr([4])
    mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying).Set(
        [Gf.Vec2f(0, 0), Gf.Vec2f(1, 0), Gf.Vec2f(1, 1), Gf.Vec2f(0, 1)]
    )
    material = UsdShade.Material.Define(stage, material_path)
    surface = UsdShade.Shader.Define(stage, material_path + "/Surface")
    surface.CreateIdAttr("UsdPreviewSurface")
    reader = UsdShade.Shader.Define(stage, material_path + "/Reader")
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    texture = UsdShade.Shader.Define(stage, material_path + "/Texture")
    texture.CreateIdAttr("UsdUVTexture")
    texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(uri))
    texture.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("raw")
    texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
    texture.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    surface.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(texture.ConnectableAPI(), "rgb")
    material.CreateSurfaceOutput().ConnectToSource(surface.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)


def _build_stage(path, uris):
    path.unlink(missing_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    import campfire.app
    from campfire.app.flow_scene import populate_flow_scene

    populate_flow_scene(stage)
    stage.RemovePrim("/World/Logs")
    UsdGeom.Xform.Define(stage, "/World/Logs")
    for slot in range(20):
        row, column = divmod(slot, 5)
        campfire.app.create_log(stage, campfire.app.LogSpec(f"Log_{slot:02d}", ((column - 2) * 1.15, (row - 1.5) * 1.05, 0.42), 0.0 if row % 2 == 0 else 90.0, 0.22, 0.92))
    _panel(stage, "/World/V3TG/Base", "/World/Looks/V3TGBase", uris[0], -3.0, -0.1)
    _panel(stage, "/World/V3TG/Emission", "/World/Looks/V3TGEmission", uris[1], 0.1, 3.0)
    camera = UsdGeom.Camera.Define(stage, "/World/V3TGCamera")
    camera.CreateHorizontalApertureAttr(36.0)
    camera.CreateVerticalApertureAttr(20.25)
    camera.CreateFocalLengthAttr(25.3125)
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(Gf.Vec3d(0, -10, 0), Gf.Vec3d(0), Gf.Vec3d(0, 0, 1))
    camera.AddTransformOp().Set(view.GetInverse())
    stage.SetEndTimeCode(100000.0)
    if not stage.GetRootLayer().Save():
        raise RuntimeError("unable to save V3T-G stage")
    return [str(prim.GetPath()) for prim in stage.Traverse()]


class Resources:
    def __init__(self, arguments):
        self.arguments = arguments
        self.names = [f"phasev3tg_{arguments['mode']}_{arguments['run']}_{name}" for name in ("base", "emission")]
        self.uris = [f"dynamic://{name}" for name in self.names]
        self.providers = [ui.DynamicTextureProvider(name) for name in self.names]
        self.cpu = [np.empty((HEIGHT, WIDTH, 4), dtype=np.uint8) for _ in range(2)]
        self.capsules = [_capsule(array) for array in self.cpu]
        self.wp = None
        self.device = None
        self.slots = []

    def init_gpu(self, ring=3):
        import warp as wp
        wp.init()
        self.wp = wp
        self.device = wp.get_device("cuda:0")
        for _ in range(ring):
            host = [np.empty((HEIGHT, WIDTH, 4), dtype=np.uint8) for _ in range(2)]
            host_wp = [wp.array(array.reshape(-1), dtype=wp.uint8, device="cpu", copy=False) for array in host]
            device = [wp.empty(array.size, dtype=wp.uint8, device=self.device) for array in host]
            self.slots.append({"host": host, "host_wp": host_wp, "device": device, "stream": wp.Stream(self.device), "event": wp.Event(self.device)})

    def publish_cpu(self, revision):
        for texture, array in enumerate(self.cpu):
            _fill(array, revision, texture)
        for provider, capsule in zip(self.providers, self.capsules):
            provider.set_raw_bytes_data(capsule, [WIDTH, HEIGHT], TextureFormat.RGBA8_UNORM, strict=True)

    def publish_gpu(self, revision, single_sync=False):
        slot = self.slots[0 if single_sync else revision % len(self.slots)]
        for texture, array in enumerate(slot["host"]):
            _fill(array, revision, texture)
        with self.wp.ScopedStream(slot["stream"]):
            for destination, source in zip(slot["device"], slot["host_wp"]):
                self.wp.copy(destination, source)
            slot["stream"].record_event(slot["event"])
        if single_sync:
            self.wp.synchronize_device(self.device)
        else:
            self.wp.synchronize_event(slot["event"])
        for provider, array in zip(self.providers, slot["device"]):
            provider.set_bytes_data_from_gpu(int(array.ptr), [WIDTH, HEIGHT], TextureFormat.RGBA8_UNORM, strict=True)

    def sync(self):
        if self.wp is not None:
            self.wp.synchronize_device(self.device)

    def destroy_providers(self):
        for provider in self.providers:
            provider.destroy()
        self.providers.clear()

    def release_gpu(self):
        self.slots.clear()
        self.device = None
        self.wp = None


async def _updates(app, count):
    for _ in range(count):
        await app.next_update_async()


async def _frame(viewport):
    await omni.kit.viewport.utility.next_viewport_frame_async(viewport)


async def _close_stage(arguments, context, app, viewport, drains):
    _marker(arguments, "stage_close_begin")
    await context.close_stage_async()
    _marker(arguments, "stage_close_end", stage_present=context.get_stage() is not None)
    _marker(arguments, "viewport_hydra_detach_begin")
    await _updates(app, drains)
    _marker(arguments, "viewport_hydra_detach_end", stage_present=context.get_stage() is not None, viewport_present=viewport is not None)


async def _teardown(arguments, resources, context, app, timeline, viewport):
    sequence = arguments["sequence"]
    _marker(arguments, "shutdown_begin", timeline_playing=timeline.is_playing())
    timeline.stop()
    _marker(arguments, "timeline_stop", timeline_playing=timeline.is_playing())
    if sequence == "A":
        _marker(arguments, "provider_destroy_begin")
        resources.destroy_providers()
        _marker(arguments, "provider_destroy_end")
        _marker(arguments, "warp_sync_begin")
        resources.sync()
        _marker(arguments, "warp_sync_end")
        _marker(arguments, "gpu_release_begin")
        resources.release_gpu()
        _marker(arguments, "gpu_release_end")
    elif sequence == "B":
        await _updates(app, 4)
        await _close_stage(arguments, context, app, viewport, 4)
        _marker(arguments, "provider_destroy_begin"); resources.destroy_providers(); _marker(arguments, "provider_destroy_end")
        _marker(arguments, "warp_sync_begin"); resources.sync(); _marker(arguments, "warp_sync_end")
        _marker(arguments, "gpu_release_begin"); resources.release_gpu(); _marker(arguments, "gpu_release_end")
    elif sequence == "C":
        _marker(arguments, "warp_sync_begin"); resources.sync(); _marker(arguments, "warp_sync_end")
        _marker(arguments, "provider_destroy_begin"); resources.destroy_providers(); _marker(arguments, "provider_destroy_end")
        await _updates(app, 4)
        await _close_stage(arguments, context, app, viewport, 0)
        _marker(arguments, "gpu_release_begin"); resources.release_gpu(); _marker(arguments, "gpu_release_end")
    elif sequence == "D":
        await _close_stage(arguments, context, app, viewport, 8)
        _marker(arguments, "provider_destroy_begin"); resources.destroy_providers(); _marker(arguments, "provider_destroy_end")
        _marker(arguments, "warp_sync_begin"); resources.sync(); _marker(arguments, "warp_sync_end")
        _marker(arguments, "gpu_release_begin"); resources.release_gpu(); _marker(arguments, "gpu_release_end")
    elif sequence == "E":
        _marker(arguments, "warp_sync_begin"); resources.sync(); _marker(arguments, "warp_sync_end")
        if arguments["mode"] == "gpu_ring3_keep_providers":
            _marker(arguments, "provider_destroy_deferred_to_process_exit")
        else:
            _marker(arguments, "provider_destroy_begin"); resources.destroy_providers(); _marker(arguments, "provider_destroy_end")
        await _close_stage(arguments, context, app, viewport, 4)
        _marker(arguments, "gpu_release_deferred_to_process_exit")
    else:
        raise ValueError(f"unknown sequence: {sequence}")
    _marker(arguments, "shutdown_pre_quit_end")


async def _run(arguments):
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    resources = None
    report = {"schema": "campfire.phasev3tg.process.v1", "status": "error", **{k: str(v) if isinstance(v, Path) else v for k, v in arguments.items() if k not in ("output", "markers")}}
    try:
        arguments["markers"].unlink(missing_ok=True)
        _marker(arguments, "probe_begin")
        resources = Resources(arguments)
        mode = arguments["mode"]
        if mode in GPU_MODES:
            resources.init_gpu(1 if mode == "gpu_single_sync" else 3)
        resources.publish_cpu(0)
        stage_path = arguments["output"].with_suffix(".usda")
        prims = _build_stage(stage_path, resources.uris)
        _marker(arguments, "stage_open_begin")
        await context.open_stage_async(str(stage_path))
        _marker(arguments, "stage_open_end")
        viewport = None
        for _ in range(240):
            viewport = omni.kit.viewport.utility.get_active_viewport()
            if viewport is not None:
                break
            await app.next_update_async()
        if viewport is None:
            raise RuntimeError("active viewport unavailable")
        viewport.camera_path = "/World/V3TGCamera"
        viewport.fill_frame = False
        viewport.resolution = RESOLUTION
        timeline.play()
        for _ in range(arguments["warmup"]):
            await _frame(viewport)
        _marker(arguments, "warmup_end", timeline_playing=timeline.is_playing())
        for revision in range(1, arguments["updates"] + 1):
            if mode == "cpu_reference":
                resources.publish_cpu(revision)
            elif mode == "provider_only":
                pass
            elif mode == "warp_only":
                slot = resources.slots[revision % 3]
                for texture, array in enumerate(slot["host"]):
                    _fill(array, revision, texture)
                with resources.wp.ScopedStream(slot["stream"]):
                    for destination, source in zip(slot["device"], slot["host_wp"]):
                        resources.wp.copy(destination, source)
                    slot["stream"].record_event(slot["event"])
                resources.wp.synchronize_event(slot["event"])
            elif mode == "gpu_single_sync":
                resources.publish_gpu(revision, single_sync=True)
            else:
                resources.publish_gpu(revision)
            await app.next_update_async()
        await _frame(viewport)
        _marker(arguments, "publication_end", updates=arguments["updates"])
        await _teardown(arguments, resources, context, app, timeline, viewport)
        if mode in ("gpu_ring3_keep_allocations", "gpu_ring3_keep_providers") or arguments["sequence"] == "E":
            _RETAINED.append(resources)
            _marker(arguments, "resources_strongly_retained_to_process_exit")
        _marker(arguments, "extension_disable_begin")
        disabled = bool(app.get_extension_manager().set_extension_enabled_immediate("omni.campfire.phasev3tg_shutdown", False))
        _marker(arguments, "extension_disable_end", disabled=disabled)
        report.update(status="ok", prim_count=len(prims), log_count=20, bytes_per_publication=WIDTH * HEIGHT * 4 * 2, gpu_api_available=hasattr(resources.providers[0], "set_bytes_data_from_gpu") if resources.providers else True)
    except Exception as error:
        report.update(status="error", error=f"{type(error).__name__}: {error}")
        _marker(arguments, "python_error", error=report["error"])
    finally:
        arguments["output"].parent.mkdir(parents=True, exist_ok=True)
        arguments["output"].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _marker(arguments, "quit_posted", status=report["status"])
        app.post_uncancellable_quit(0 if report["status"] == "ok" else 1)


asyncio.ensure_future(_run(_args()))
