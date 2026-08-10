"""Production-neutral GPU transport lifecycle probe with durable markers."""

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
_CRASH_HANDLER = None


def _arguments():
    settings = carb.settings.get_settings()
    return {
        "output": Path(settings.get_as_string("/phasev3tj/output")).resolve(),
        "markers": Path(settings.get_as_string("/phasev3tj/markers")).resolve(),
        "transport": settings.get_as_string("/phasev3tj/transport"),
        "scenario": settings.get_as_string("/phasev3tj/scenario"),
        "warmup": settings.get_as_int("/phasev3tj/warmup"),
        "updates": settings.get_as_int("/phasev3tj/updates"),
        "run": settings.get_as_int("/phasev3tj/run"),
        "crash_handler": Path(settings.get_as_string("/phasev3tj/crashHandler")).resolve(),
        "dump_helper": Path(settings.get_as_string("/phasev3tj/dumpHelper")).resolve(),
        "crash_dump": Path(settings.get_as_string("/phasev3tj/crashDump")).resolve(),
        "crash_metadata": Path(settings.get_as_string("/phasev3tj/crashMetadata")).resolve(),
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


def _build_stage(path, uris, suffix):
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
    _panel(stage, "/World/V3TJ/Base", "/World/Looks/V3TJBase", uris[0], -3.0, -0.1)
    _panel(stage, "/World/V3TJ/Emission", "/World/Looks/V3TJEmission", uris[1], 0.1, 3.0)
    camera = UsdGeom.Camera.Define(stage, "/World/V3TJCamera")
    camera.CreateHorizontalApertureAttr(36.0)
    camera.CreateVerticalApertureAttr(20.25)
    camera.CreateFocalLengthAttr(25.3125)
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(Gf.Vec3d(0, -10, 0), Gf.Vec3d(0), Gf.Vec3d(0, 0, 1))
    camera.AddTransformOp().Set(view.GetInverse())
    stage.GetRootLayer().customLayerData = {"phasev3tjStage": suffix}
    stage.SetEndTimeCode(100000.0)
    if not stage.GetRootLayer().Save():
        raise RuntimeError("unable to save V3T-J stage")
    return [str(prim.GetPath()) for prim in stage.Traverse()]


class Resources:
    def __init__(self, arguments):
        stem = f"phasev3tj_{arguments['scenario']}_{arguments['run']}"
        self.names = [f"{stem}_{name}" for name in ("base", "emission")]
        self.uris = [f"dynamic://{name}" for name in self.names]
        self.providers = []
        self.cpu = [np.empty((HEIGHT, WIDTH, 4), dtype=np.uint8) for _ in range(2)]
        self.capsules = [_capsule(array) for array in self.cpu]
        self.wp = None
        self.device = None
        self.slots = []
        self.transport = arguments["transport"]
        self.faulted = False
        self.publication_allowed = True
        self.last_revision = 0
        self.last_slot = None

    def create_providers(self):
        self.providers = [ui.DynamicTextureProvider(name) for name in self.names]

    def init_gpu(self):
        import warp as wp
        wp.init()
        self.wp = wp
        self.device = wp.get_device("cuda:0")
        for _ in range(3):
            host = [np.empty((HEIGHT, WIDTH, 4), dtype=np.uint8) for _ in range(2)]
            host_wp = [wp.array(array.reshape(-1), dtype=wp.uint8, device="cpu", copy=False) for array in host]
            device = [wp.empty(array.size, dtype=wp.uint8, device=self.device) for array in host]
            self.slots.append({"host": host, "host_wp": host_wp, "device": device, "stream": wp.Stream(self.device), "event": wp.Event(self.device)})

    def publish(self, revision):
        if not self.publication_allowed:
            raise RuntimeError("publication is closed")
        if self.faulted or self.transport == "cpu":
            for texture, array in enumerate(self.cpu):
                _fill(array, revision, texture)
            for provider, capsule in zip(self.providers, self.capsules):
                provider.set_raw_bytes_data(capsule, [WIDTH, HEIGHT], TextureFormat.RGBA8_UNORM, strict=True)
            self.last_slot = None
        else:
            slot_index = revision % 3
            slot = self.slots[slot_index]
            for texture, array in enumerate(slot["host"]):
                _fill(array, revision, texture)
            with self.wp.ScopedStream(slot["stream"]):
                for destination, source in zip(slot["device"], slot["host_wp"]):
                    self.wp.copy(destination, source)
                slot["stream"].record_event(slot["event"])
            self.wp.synchronize_event(slot["event"])
            for provider, array in zip(self.providers, slot["device"]):
                provider.set_bytes_data_from_gpu(int(array.ptr), [WIDTH, HEIGHT], TextureFormat.RGBA8_UNORM, strict=True)
            self.last_slot = slot_index
        self.last_revision = revision

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


async def _open_stage(arguments, context, app, viewport, stage_path, marker_name):
    _marker(arguments, marker_name + "_begin")
    await context.open_stage_async(str(stage_path))
    viewport.camera_path = "/World/V3TJCamera"
    viewport.fill_frame = False
    viewport.resolution = RESOLUTION
    await _updates(app, 2)
    _marker(arguments, marker_name + "_end", stage=str(stage_path))


async def _run(arguments):
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    report = {"schema": "campfire.phasev3tj.gpu-lifecycle-process.v1", "status": "error"}
    resources = None
    try:
        arguments["markers"].unlink(missing_ok=True)
        global _CRASH_HANDLER
        _CRASH_HANDLER = ctypes.WinDLL(str(arguments["crash_handler"]))
        install = _CRASH_HANDLER.phasev3tj_install_crash_handler
        install.restype = ctypes.c_int
        install.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p)
        if not install(str(arguments["dump_helper"]), str(arguments["crash_dump"]), str(arguments["crash_metadata"])):
            raise RuntimeError("unable to install isolated crash handler")
        _marker(arguments, "crash_handler_installed", dump=str(arguments["crash_dump"]), metadata=str(arguments["crash_metadata"]))
        _marker(arguments, "probe_begin", transport=arguments["transport"], scenario=arguments["scenario"])
        if arguments["transport"] not in ("cpu", "gpu_ring3"):
            raise ValueError("invalid transport")
        allowed = {"normal_exit", "timeline_restart", "stage_replacement", "provider_regeneration", "extension_disable", "gpu_initialization_failure", "publication_failure"}
        if arguments["scenario"] not in allowed:
            raise ValueError("invalid scenario")
        resources = Resources(arguments)
        resources.create_providers()
        fallback_count = 0
        if arguments["transport"] == "gpu_ring3":
            try:
                if arguments["scenario"] == "gpu_initialization_failure":
                    raise RuntimeError("injected GPU initialization failure")
                resources.init_gpu()
            except Exception as error:
                resources.faulted = True
                fallback_count += 1
                _marker(arguments, "gpu_initialization_faulted_cpu_fallback", error=str(error))
        resources.publish(0)
        stage0 = arguments["output"].with_suffix(".stage0.usda")
        stage1 = arguments["output"].with_suffix(".stage1.usda")
        prims0 = _build_stage(stage0, resources.uris, "initial")
        prims1 = _build_stage(stage1, resources.uris, "replacement")
        viewport = None
        for _ in range(240):
            viewport = omni.kit.viewport.utility.get_active_viewport()
            if viewport is not None:
                break
            await app.next_update_async()
        if viewport is None:
            raise RuntimeError("active viewport unavailable")
        await _open_stage(arguments, context, app, viewport, stage0, "stage_open")
        timeline.play()
        for _ in range(arguments["warmup"]):
            await _frame(viewport)
        _marker(arguments, "warmup_end", timeline_playing=timeline.is_playing())
        midpoint = max(1, arguments["updates"] // 2)
        for revision in range(1, arguments["updates"] + 1):
            if arguments["scenario"] == "publication_failure" and revision == midpoint and not resources.faulted:
                resources.faulted = True
                resources.sync()
                fallback_count += 1
                _marker(arguments, "gpu_publication_faulted", revision=revision, slot=revision % 3, error="injected before Provider setter")
                continue
            resources.publish(revision)
            if revision == midpoint and arguments["scenario"] == "timeline_restart":
                timeline.stop(); _marker(arguments, "timeline_stop_midrun", revision=revision)
                await _updates(app, 4)
                timeline.play(); _marker(arguments, "timeline_restart", revision=revision)
            elif revision == midpoint and arguments["scenario"] == "stage_replacement":
                resources.publication_allowed = False
                _marker(arguments, "stage_replacement_publication_gate_closed", revision=revision)
                resources.sync(); _marker(arguments, "stage_replacement_source_sync")
                timeline.stop()
                await context.close_stage_async(); _marker(arguments, "stage_replacement_old_stage_closed")
                await _open_stage(arguments, context, app, viewport, stage1, "stage_replacement_new_stage_open")
                timeline.play()
                resources.publication_allowed = True
                _marker(arguments, "stage_replacement_publication_gate_open")
            elif revision == midpoint and arguments["scenario"] == "provider_regeneration":
                resources.publication_allowed = False
                resources.sync(); _marker(arguments, "provider_regeneration_source_sync")
                resources.destroy_providers(); _marker(arguments, "provider_regeneration_old_destroyed")
                resources.create_providers(); _marker(arguments, "provider_regeneration_new_created")
                resources.publication_allowed = True
                resources.publish(revision)
                _marker(arguments, "provider_regeneration_republished", revision=revision)
            await app.next_update_async()
        await _frame(viewport)
        _marker(arguments, "publication_end", revision=resources.last_revision, slot=resources.last_slot, fallback_count=fallback_count)

        _marker(arguments, "teardown_begin", revision=resources.last_revision, slot=resources.last_slot)
        resources.publication_allowed = False
        _marker(arguments, "teardown_publication_gate_closed")
        try:
            resources.publish(resources.last_revision + 1)
            raise AssertionError("teardown publication unexpectedly succeeded")
        except RuntimeError:
            _marker(arguments, "teardown_publication_rejected")
        timeline.stop(); _marker(arguments, "timeline_stop", timeline_playing=timeline.is_playing())
        _marker(arguments, "source_generation_sync_begin"); resources.sync(); _marker(arguments, "source_generation_sync_end")
        _marker(arguments, "stage_close_begin"); await context.close_stage_async(); _marker(arguments, "stage_close_end", stage_present=context.get_stage() is not None)
        await _updates(app, 4)
        _marker(arguments, "provider_destroy_begin"); resources.destroy_providers(); _marker(arguments, "provider_destroy_end")
        _marker(arguments, "gpu_allocation_release_begin"); resources.release_gpu(); _marker(arguments, "gpu_allocation_release_end")
        _marker(arguments, "extension_disable_begin")
        disabled = bool(app.get_extension_manager().set_extension_enabled_immediate("omni.campfire.phasev3tg_shutdown", False))
        _marker(arguments, "extension_disable_end", disabled=disabled)
        _marker(arguments, "normal_quit_posted", revision=resources.last_revision, fallback_count=fallback_count)
        report = {
            "schema": "campfire.phasev3tj.gpu-lifecycle-process.v1", "status": "ok",
            "transport": arguments["transport"], "scenario": arguments["scenario"], "run": arguments["run"] + 1,
            "kit": "110.2", "flow": "110.0.0", "rtx": "omni.hydra.rtx 1.0.4",
            "atlas": {"width": WIDTH, "height": HEIGHT, "textures": 2, "bytes": WIDTH * HEIGHT * 4 * 2},
            "log_count": 20, "prim_count": len(prims0), "replacement_prim_count": len(prims1),
            "last_revision": resources.last_revision, "last_slot": resources.last_slot,
            "fallback_count": fallback_count, "publication_gate_closed": True,
            "production_changed": False, "gpu_pointer_externally_exposed": False,
        }
    except Exception as error:
        report.update(status="error", error=f"{type(error).__name__}: {error}")
        _marker(arguments, "python_error", error=report["error"], revision=resources.last_revision if resources else None, slot=resources.last_slot if resources else None)
    finally:
        arguments["output"].parent.mkdir(parents=True, exist_ok=True)
        arguments["output"].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        app.post_uncancellable_quit(0 if report["status"] == "ok" else 1)


asyncio.ensure_future(_run(_arguments()))
