"""Phase V3T-E GPU-source ring/lifecycle qualification probe.

This script is intentionally independent from the production V3 consumer.  It
owns every CPU and CUDA source allocation, fixes providers and USD topology
before each measured population, and uses public RTX viewport capture as the
pixel-readback boundary.
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
import omni.kit.viewport.utility
import omni.timeline
import omni.ui as ui
import omni.usd
from omni.gpu_foundation_factory import TextureFormat
from PIL import Image
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade


RESOLUTION = (1280, 720)
MODE_NAMES = ("cpu_reference", "gpu_single_sync", "gpu_ring2", "gpu_ring3")
PATTERN_PERIOD = 8
BLOCK_COLUMNS = 8
BLOCK_ROWS = 4


def _arguments():
    settings = carb.settings.get_settings()
    return {
        "output": Path(settings.get_as_string("/phasev3te/output")).resolve(),
        "capture_dir": Path(settings.get_as_string("/phasev3te/captureDir")).resolve(),
        "scenario": settings.get_as_string("/phasev3te/scenario"),
        "width": settings.get_as_int("/phasev3te/width"),
        "height": settings.get_as_int("/phasev3te/height"),
        "run": settings.get_as_int("/phasev3te/run"),
        "warmup": settings.get_as_int("/phasev3te/warmup"),
        "samples": settings.get_as_int("/phasev3te/samples"),
        "correctness": settings.get_as_int("/phasev3te/correctness"),
        "long_updates": settings.get_as_int("/phasev3te/longUpdates"),
    }


def _capsule(array):
    capsule_new = ctypes.pythonapi.PyCapsule_New
    capsule_new.restype = ctypes.py_object
    capsule_new.argtypes = (ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p)
    return capsule_new(ctypes.c_void_p(array.ctypes.data), None, None)


def _fill_revision(image, revision, texture_index):
    """Fill a stable macroblock signature without reallocating the array."""

    pattern = int(revision) % PATTERN_PERIOD
    height, width = image.shape[:2]
    palette = np.array(
        [
            [235, 30, 30],
            [30, 225, 45],
            [35, 65, 235],
            [235, 215, 25],
            [225, 35, 215],
            [25, 215, 225],
            [240, 120, 20],
            [125, 40, 230],
        ],
        dtype=np.int16,
    )
    base_color = palette[(pattern + texture_index * 3) % PATTERN_PERIOD]
    for block_y in range(BLOCK_ROWS):
        y0 = block_y * height // BLOCK_ROWS
        y1 = (block_y + 1) * height // BLOCK_ROWS
        for block_x in range(BLOCK_COLUMNS):
            x0 = block_x * width // BLOCK_COLUMNS
            x1 = (block_x + 1) * width // BLOCK_COLUMNS
            block = block_y * BLOCK_COLUMNS + block_x
            delta = ((block % 4) - 1.5) * 6.0
            color = np.empty(4, dtype=np.uint8)
            color[:3] = np.clip(base_color + np.array([delta, -delta, delta * 0.5]), 8, 247).astype(np.uint8)
            color[3] = 255
            image[y0:y1, x0:x1] = color
    # Orientation and cross-texture sentinels are included in every revision.
    image[0, :, :3] = np.array([250, 250, 250], dtype=np.uint8)
    image[-1, :, :3] = np.array([8, 8, 8], dtype=np.uint8)
    image[:, 0, :3] = np.array([250, 205, 20], dtype=np.uint8)
    image[:, -1, :3] = np.array([20, 225, 245], dtype=np.uint8)


def _define_panel(stage, path, material_path, texture_uri, x0, x1, height):
    mesh = UsdGeom.Mesh.Define(stage, path)
    z0, z1 = -height * 0.5, height * 0.5
    mesh.CreatePointsAttr(
        [
            Gf.Vec3f(x0, -5.0, z0),
            Gf.Vec3f(x1, -5.0, z0),
            Gf.Vec3f(x1, -5.0, z1),
            Gf.Vec3f(x0, -5.0, z1),
        ]
    )
    mesh.CreateFaceVertexCountsAttr([4])
    mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    mesh.CreateDoubleSidedAttr(True)
    UsdGeom.PrimvarsAPI(mesh).CreatePrimvar(
        "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying
    ).Set([Gf.Vec2f(0, 0), Gf.Vec2f(1, 0), Gf.Vec2f(1, 1), Gf.Vec2f(0, 1)])
    material = UsdShade.Material.Define(stage, material_path)
    surface = UsdShade.Shader.Define(stage, material_path + "/Surface")
    surface.CreateIdAttr("UsdPreviewSurface")
    surface.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
    reader = UsdShade.Shader.Define(stage, material_path + "/Reader")
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    texture = UsdShade.Shader.Define(stage, material_path + "/Texture")
    texture.CreateIdAttr("UsdUVTexture")
    texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(texture_uri))
    texture.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("raw")
    texture.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("clamp")
    texture.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("clamp")
    texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
    texture.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    surface.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
        texture.ConnectableAPI(), "rgb"
    )
    # Both provider URIs are visualized through the same diffuse-only probe
    # material.  This validates base and emission bytes independently without
    # RTX emissive temporal bloom being mistaken for source-buffer tearing.
    surface.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.0, 0.0, 0.0))
    surface.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    material.CreateSurfaceOutput().ConnectToSource(surface.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)


def _build_stage(path, width, height, base_uri, emission_uri):
    path.unlink(missing_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    from campfire.app.flow_scene import populate_flow_scene

    populate_flow_scene(stage)
    aspect = width / height
    # Panels sit halfway between the camera and Flow scene.  Their half-size
    # preserves the same screen ROI while ensuring Flow/log geometry cannot
    # occlude the readback samples.
    panel_width = 2.9
    panel_height = panel_width / aspect
    _define_panel(
        stage,
        "/World/V3TERingReadback/Base",
        "/World/Looks/V3TERingBase",
        base_uri,
        -3.0,
        -0.1,
        panel_height,
    )
    _define_panel(
        stage,
        "/World/V3TERingReadback/Emission",
        "/World/Looks/V3TERingEmission",
        emission_uri,
        0.1,
        3.0,
        panel_height,
    )
    camera = UsdGeom.Camera.Define(stage, "/World/V3TERingCamera")
    camera.CreateProjectionAttr(UsdGeom.Tokens.perspective)
    # At the fixed 10 m camera distance, these apertures/focal length project
    # exactly eight world units onto the 720-pixel vertical frame.
    camera.CreateHorizontalApertureAttr(36.0)
    camera.CreateVerticalApertureAttr(20.25)
    camera.CreateFocalLengthAttr(25.3125)
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(Gf.Vec3d(0.0, -10.0, 0.0), Gf.Vec3d(0.0, 0.0, 0.0), Gf.Vec3d(0, 0, 1))
    camera.AddTransformOp().Set(view.GetInverse())
    if not stage.GetRootLayer().Save():
        raise RuntimeError("Unable to save Phase V3T-E stage")
    return {
        "prim_paths": [str(prim.GetPath()) for prim in stage.Traverse()],
        "panel_height": panel_height,
        "base_uri": base_uri,
        "emission_uri": emission_uri,
    }


async def _viewport():
    app = omni.kit.app.get_app()
    for _ in range(240):
        viewport = omni.kit.viewport.utility.get_active_viewport()
        if viewport is not None:
            viewport.camera_path = "/World/V3TERingCamera"
            viewport.fill_frame = False
            viewport.resolution = RESOLUTION
            return viewport
        await app.next_update_async()
    raise RuntimeError("Phase V3T-E requires an active viewport")


async def _next_frame(viewport):
    start = time.perf_counter_ns()
    await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
    return (time.perf_counter_ns() - start) / 1.0e6


def _panel_bounds(width, height, texture_width, texture_height):
    pixels_per_world = height / 4.0
    panel_height = 2.9 / (texture_width / texture_height)
    y0 = int(round(height * 0.5 - panel_height * pixels_per_world * 0.5))
    y1 = int(round(height * 0.5 + panel_height * pixels_per_world * 0.5))
    return (
        (int(round(width * 0.5 - 3.0 * pixels_per_world)), y0,
         int(round(width * 0.5 - 0.1 * pixels_per_world)), y1),
        (int(round(width * 0.5 + 0.1 * pixels_per_world)), y0,
         int(round(width * 0.5 + 3.0 * pixels_per_world)), y1),
    )


def _features(path, texture_width, texture_height):
    payload = path.read_bytes()
    image = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
    panels = []
    for x0, y0, x1, y1 in _panel_bounds(image.shape[1], image.shape[0], texture_width, texture_height):
        vectors = []
        for block_y in range(BLOCK_ROWS):
            cy = int(round(y0 + (block_y + 0.5) * (y1 - y0) / BLOCK_ROWS))
            for block_x in range(BLOCK_COLUMNS):
                cx = int(round(x0 + (block_x + 0.5) * (x1 - x0) / BLOCK_COLUMNS))
                patch = image[max(0, cy - 2):cy + 3, max(0, cx - 2):cx + 3]
                vectors.append([float(value) for value in patch.mean(axis=(0, 1))])
        panels.append(vectors)
    return {
        "path": str(path),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "panel_features": panels,
    }


async def _capture(viewport, path, texture_width, texture_height):
    for _ in range(24):
        await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
    request = omni.kit.viewport.utility.capture_viewport_to_file(viewport, file_path=str(path))
    # RTX temporal accumulation otherwise blends the prior revision into the
    # diagnostic macroblocks.  Eight completed frames are outside the timing
    # population and make this a pixel-identity check rather than a TAA check.
    if not await request.wait_for_result(completion_frames=2):
        raise RuntimeError(f"Phase V3T-E capture failed: {path}")
    for _ in range(40):
        if path.is_file():
            return _features(path, texture_width, texture_height)
        await asyncio.sleep(0.05)
    raise RuntimeError(f"Phase V3T-E capture missing: {path}")


def _classify(features, references, expected_revision):
    expected = expected_revision % PATTERN_PERIOD
    labels = []
    distances = []
    for texture_index, panel in enumerate(features["panel_features"]):
        for block_index, color in enumerate(panel):
            candidates = []
            for pattern in range(PATTERN_PERIOD):
                reference = references[str(pattern)]["panel_features"][texture_index][block_index]
                candidates.append(math.sqrt(sum((color[i] - reference[i]) ** 2 for i in range(3))))
            label = int(np.argmin(candidates))
            labels.append(label)
            distances.append(candidates[label])
    unique = sorted(set(labels))
    invalid = max(distances, default=999.0) > 70.0
    if invalid:
        category = "invalid_pixels"
        age = None
    elif len(unique) > 1:
        category = "mixed_revision_tearing"
        age = None
    else:
        observed = unique[0]
        age = next((value for value in range(PATTERN_PERIOD) if (expected - value) % PATTERN_PERIOD == observed), None)
        if observed == (expected + 1) % PATTERN_PERIOD:
            category = "future_complete"
            age = -1
        elif age == 0:
            category = "latest_complete"
        elif age == 1:
            category = "one_generation_old_complete"
        else:
            category = "stale_complete"
    return {
        "expected_pattern": expected,
        "observed_patterns": unique,
        "category": category,
        "generation_age_modulo": age,
        "max_reference_distance": round(max(distances, default=0.0), 4),
        "mixed_fraction": round(1.0 - max((labels.count(label) for label in unique), default=0) / max(1, len(labels)), 6),
    }


class GpuSlot:
    def __init__(self, wp, device, width, height, slot_index):
        self.wp = wp
        self.device = device
        self.slot_index = slot_index
        self.host = [np.empty((height, width, 4), dtype=np.uint8) for _ in range(2)]
        self.host_warp = [
            wp.array(array.reshape(-1), dtype=wp.uint8, device="cpu", copy=False)
            for array in self.host
        ]
        self.device_arrays = [wp.empty(array.size, dtype=wp.uint8, device=device) for array in self.host]
        self.stream = wp.Stream(device)
        self.event = wp.Event(device)
        self.revision = None
        self.source_prepare_ms = 0.0
        self.h2d_enqueue_ms = 0.0

    def queue(self, revision):
        start = time.perf_counter_ns()
        for texture_index, array in enumerate(self.host):
            _fill_revision(array, revision, texture_index)
        self.source_prepare_ms = (time.perf_counter_ns() - start) / 1.0e6
        start = time.perf_counter_ns()
        with self.wp.ScopedStream(self.stream):
            for destination, source in zip(self.device_arrays, self.host_warp):
                self.wp.copy(destination, source)
            self.stream.record_event(self.event)
        self.h2d_enqueue_ms = (time.perf_counter_ns() - start) / 1.0e6
        self.revision = revision

    def wait_ready(self):
        start = time.perf_counter_ns()
        self.wp.synchronize_event(self.event)
        return (time.perf_counter_ns() - start) / 1.0e6


class Transport:
    def __init__(self, name_prefix, width, height):
        self.name_prefix = name_prefix
        self.width = width
        self.height = height
        self.provider_names = [name_prefix + "_base", name_prefix + "_emission"]
        self.uris = [f"dynamic://{name}" for name in self.provider_names]
        self.providers = [ui.DynamicTextureProvider(name) for name in self.provider_names]
        self.cpu = [np.empty((height, width, 4), dtype=np.uint8) for _ in range(2)]
        self.capsules = [_capsule(array) for array in self.cpu]
        self.faulted = False
        self.closed = False
        self.fallback_count = 0
        self.close_sequence = []
        self.wp = None
        self.device = None
        self.slots = []

    def initialize_gpu(self):
        import warp as wp

        wp.init()
        self.wp = wp
        self.device = wp.get_device("cuda:0")
        self.slots = [GpuSlot(wp, self.device, self.width, self.height, index) for index in range(3)]

    def api_contract(self):
        provider = self.providers[0]
        gpu_method = getattr(provider, "set_bytes_data_from_gpu", None)
        return {
            "dynamic_texture_provider_doc": getattr(ui.DynamicTextureProvider, "__doc__", None),
            "set_raw_bytes_data_doc": getattr(provider.set_raw_bytes_data, "__doc__", None),
            "set_bytes_data_from_gpu_available": gpu_method is not None,
            "set_bytes_data_from_gpu_doc": getattr(gpu_method, "__doc__", None),
            "warp_event_doc": getattr(self.wp.Event, "__doc__", None),
            "warp_event_is_complete_doc": getattr(type(self.slots[0].event).is_complete, "__doc__", None),
            "warp_synchronize_event_doc": getattr(self.wp.synchronize_event, "__doc__", None),
            "provider_source_consumed_fence_available": False,
            "provider_source_consumed_fence_search": "no return token, event, stream, or completion method in runtime method/docstring",
        }

    def _set_cpu(self, revision):
        start = time.perf_counter_ns()
        for texture_index, array in enumerate(self.cpu):
            _fill_revision(array, revision, texture_index)
        prepare_ms = (time.perf_counter_ns() - start) / 1.0e6
        start = time.perf_counter_ns()
        for provider, capsule in zip(self.providers, self.capsules):
            provider.set_raw_bytes_data(capsule, [self.width, self.height], TextureFormat.RGBA8_UNORM, strict=True)
        setter_ms = (time.perf_counter_ns() - start) / 1.0e6
        return {
            "source_prepare_ms": prepare_ms,
            "cpu_to_gpu_enqueue_ms": 0.0,
            "explicit_sync_ms": 0.0,
            "provider_setter_ms": setter_ms,
            "slot": None,
            "slot_reuse_publications": None,
        }

    def _set_gpu_slot(self, slot, reuse_publications):
        sync_ms = slot.wait_ready()
        start = time.perf_counter_ns()
        for provider, device_array in zip(self.providers, slot.device_arrays):
            provider.set_bytes_data_from_gpu(
                int(device_array.ptr), [self.width, self.height], TextureFormat.RGBA8_UNORM, strict=True
            )
        setter_ms = (time.perf_counter_ns() - start) / 1.0e6
        return {
            "source_prepare_ms": slot.source_prepare_ms,
            "cpu_to_gpu_enqueue_ms": slot.h2d_enqueue_ms,
            "explicit_sync_ms": sync_ms,
            "provider_setter_ms": setter_ms,
            "slot": slot.slot_index,
            "slot_reuse_publications": reuse_publications,
        }

    def begin_mode(self, mode, start_revision):
        if mode == "cpu_reference":
            return
        ring_size = {"gpu_single_sync": 1, "gpu_ring2": 2, "gpu_ring3": 3, "gpu_immediate_stress": 1}[mode]
        for revision in range(start_revision, start_revision + ring_size):
            self.slots[revision % ring_size].queue(revision)
        for index in range(ring_size):
            self.slots[index].wait_ready()

    def publish(self, mode, revision):
        if self.faulted:
            self.fallback_count += 1
            result = self._set_cpu(revision)
            result["fallback"] = True
            return result
        if mode == "cpu_reference":
            result = self._set_cpu(revision)
            result["fallback"] = False
            return result
        if mode == "gpu_single_sync":
            slot = self.slots[0]
            slot.queue(revision)
            start = time.perf_counter_ns()
            self.wp.synchronize_device(self.device)
            sync_ms = (time.perf_counter_ns() - start) / 1.0e6
            start = time.perf_counter_ns()
            for provider, device_array in zip(self.providers, slot.device_arrays):
                provider.set_bytes_data_from_gpu(
                    int(device_array.ptr), [self.width, self.height], TextureFormat.RGBA8_UNORM, strict=True
                )
            result = {
                "source_prepare_ms": slot.source_prepare_ms,
                "cpu_to_gpu_enqueue_ms": slot.h2d_enqueue_ms,
                "explicit_sync_ms": sync_ms,
                "provider_setter_ms": (time.perf_counter_ns() - start) / 1.0e6,
                "slot": 0,
                "slot_reuse_publications": 1,
                "fallback": False,
            }
            return result
        ring_size = {"gpu_ring2": 2, "gpu_ring3": 3, "gpu_immediate_stress": 1}[mode]
        slot = self.slots[revision % ring_size]
        if slot.revision != revision:
            raise RuntimeError(f"GPU slot {slot.slot_index} holds {slot.revision}, expected {revision}")
        result = self._set_gpu_slot(slot, ring_size)
        next_revision = revision + 1
        next_slot = self.slots[next_revision % ring_size]
        if next_slot.revision != next_revision:
            next_slot.queue(next_revision)
        result["fallback"] = False
        return result

    def inject_partial_failure(self, revision):
        slot = self.slots[revision % 3]
        slot.queue(revision)
        slot.wait_ready()
        self.providers[0].set_bytes_data_from_gpu(
            int(slot.device_arrays[0].ptr), [self.width, self.height], TextureFormat.RGBA8_UNORM, strict=True
        )
        self.faulted = True
        raise RuntimeError("injected after base GPU publication")

    def inject_generation_failure(self):
        self.faulted = True
        raise RuntimeError("injected before GPU source generation")

    def regenerate_providers(self):
        for provider in self.providers:
            provider.destroy()
        self.providers = [ui.DynamicTextureProvider(name) for name in self.provider_names]

    def close(self):
        if self.closed:
            return
        if self.wp is not None and self.device is not None:
            self.wp.synchronize_device(self.device)
            self.close_sequence.append("warp_source_generation_synchronized")
        for provider in self.providers:
            provider.destroy()
        self.close_sequence.append("providers_destroyed")
        self.providers = []
        self.slots = []
        self.close_sequence.append("probe_owned_gpu_allocations_released")
        self.closed = True


async def _settle(viewport, context):
    for _ in range(60):
        await _next_frame(viewport)
    stage = context.get_stage()
    previous = None
    stable = 0
    for update in range(1, 2401):
        await _next_frame(viewport)
        current = tuple(str(prim.GetPath()) for prim in stage.Traverse())
        stable = stable + 1 if current == previous else 0
        previous = current
        if stable >= 30:
            return update, list(current)
    raise RuntimeError("Phase V3T-E stage topology did not stabilize")


async def _reference_signatures(transport, viewport, capture_dir):
    references = {}
    for pattern in range(PATTERN_PERIOD):
        transport._set_cpu(pattern)
        capture = await _capture(
            viewport,
            capture_dir / f"reference_pattern_{pattern}.png",
            transport.width,
            transport.height,
        )
        references[str(pattern)] = capture
    return references


async def _correctness_sequence(transport, viewport, capture_dir, references, mode, count, start_revision):
    transport.begin_mode(mode, start_revision)
    records = []
    for offset in range(count):
        revision = start_revision + offset
        timing = transport.publish(mode, revision)
        capture = await _capture(
            viewport,
            capture_dir / f"{mode}_revision_{revision}.png",
            transport.width,
            transport.height,
        )
        records.append(
            {
                "revision": revision,
                "timing": timing,
                "capture": capture,
                "classification": _classify(capture, references, revision),
            }
        )
    return records


async def _performance_sequence(transport, viewport, mode, warmup, samples, start_revision):
    transport.begin_mode(mode, start_revision)
    records = []
    for offset in range(warmup + samples):
        revision = start_revision + offset
        iteration_start = time.perf_counter_ns()
        timing = transport.publish(mode, revision)
        next_frame_ms = await _next_frame(viewport)
        total_ms = (time.perf_counter_ns() - iteration_start) / 1.0e6
        if offset >= warmup:
            records.append(
                {
                    "revision": revision,
                    **timing,
                    "publication_to_next_rtx_frame_ms": next_frame_ms,
                    "kit_update_total_ms": total_ms,
                    "bytes": transport.width * transport.height * 4 * 2,
                    "api_calls": 2,
                }
            )
    return records


def _flow_state():
    result = {"active_blocks": None}
    try:
        import omni.flowusd._flowusd as flowusd

        result["active_blocks"] = int(flowusd.acquire_flowusd_interface().get_active_block_count())
    except Exception as error:
        result["query_error"] = f"{type(error).__name__}: {error}"
    return result


def _device_contract(transport):
    device = transport.device
    return {
        "warp_device": str(device),
        "warp_device_ordinal": getattr(device, "ordinal", None),
        "warp_device_name": getattr(device, "name", None),
        "warp_arch": getattr(device, "arch", None),
        "renderer_device_public_identity_available": False,
        "device_match": "unconfirmed",
        "reason": "fixed Kit exposes the Warp CUDA ordinal but no public DynamicTextureProvider/RTX device identity contract",
    }


async def _run_matrix(arguments, transport, viewport, context, stage_contract):
    references = await _reference_signatures(transport, viewport, arguments["capture_dir"])
    order = list(MODE_NAMES)
    shift = arguments["run"] % len(order)
    order = order[shift:] + order[:shift]
    correctness = {}
    performance = {}
    for mode_index, mode in enumerate(order):
        correctness_start = 10000 + arguments["run"] * 1000 + mode_index * 100
        correctness[mode] = await _correctness_sequence(
            transport,
            viewport,
            arguments["capture_dir"],
            references,
            mode,
            arguments["correctness"],
            correctness_start,
        )
        performance_start = 50000 + arguments["run"] * 10000 + mode_index * 1000
        performance[mode] = await _performance_sequence(
            transport,
            viewport,
            mode,
            arguments["warmup"],
            arguments["samples"],
            performance_start,
        )
    stage = context.get_stage()
    return {
        "schema": "campfire.phasev3te.gpu_ring.matrix.v1",
        "status": "ok",
        "scenario": "matrix",
        "run": arguments["run"],
        "atlas": {"width": transport.width, "height": transport.height, "bytes_per_texture": transport.width * transport.height * 4},
        "mode_order": order,
        "warmup_per_mode": arguments["warmup"],
        "samples_per_mode": arguments["samples"],
        "correctness_samples_per_mode": arguments["correctness"],
        "references": references,
        "correctness": correctness,
        "samples": performance,
        "api": transport.api_contract(),
        "gpu_owner": {
            "owner": "probe-owned persistent Warp arrays",
            "allocation_count": len(transport.slots) * 2,
            "allocation_lifetime": "created before measured modes and retained until provider destruction at session close",
            "source_ready_boundary": "public Warp event recorded after both H2D copies and synchronized before setter",
            "provider_source_consumed_boundary": "not exposed by public API; ring spacing is best effort",
        },
        "device": _device_contract(transport),
        "flow": _flow_state(),
        "stage_contract": {
            **stage_contract,
            "prim_paths_after": [str(prim.GetPath()) for prim in stage.Traverse()],
            "topology_unchanged_during_measurement": stage_contract["prim_paths_before"] == [str(prim.GetPath()) for prim in stage.Traverse()],
            "provider_count_during_measurement": 2,
            "usd_revision_sets_in_measurement": 0,
            "prim_material_uri_changes_in_measurement": 0,
        },
    }


async def _lifecycle_capture(transport, viewport, capture_dir, references, label, revision):
    timing = transport.publish("gpu_ring3", revision)
    capture = await _capture(viewport, capture_dir / f"lifecycle_{label}.png", transport.width, transport.height)
    return {
        "label": label,
        "revision": revision,
        "timing": timing,
        "classification": _classify(capture, references, revision),
        "capture": capture,
    }


async def _run_lifecycle(arguments, transport, viewport, context, timeline, stage_path, stage_contract):
    app = omni.kit.app.get_app()
    references = await _reference_signatures(transport, viewport, arguments["capture_dir"])
    transport.begin_mode("gpu_ring3", 69999)
    transport.publish("gpu_ring3", 69999)
    for _ in range(24):
        await _next_frame(viewport)
    events = []
    events.append(await _lifecycle_capture(transport, viewport, arguments["capture_dir"], references, "normal", 70000))

    timeline.stop()
    await app.next_update_async()
    events.append(await _lifecycle_capture(transport, viewport, arguments["capture_dir"], references, "timeline_stop", 70001))
    timeline.play()
    await app.next_update_async()
    events.append(await _lifecycle_capture(transport, viewport, arguments["capture_dir"], references, "timeline_resume", 70002))

    await context.close_stage_async()
    await context.open_stage_async(str(stage_path))
    viewport = await _viewport()
    for _ in range(12):
        await _next_frame(viewport)
    events.append(await _lifecycle_capture(transport, viewport, arguments["capture_dir"], references, "stage_reload", 70003))

    replacement_path = arguments["output"].with_name("phasev3te_replacement.usda")
    _build_stage(replacement_path, transport.width, transport.height, *transport.uris)
    await context.close_stage_async()
    await context.open_stage_async(str(replacement_path))
    viewport = await _viewport()
    for _ in range(12):
        await _next_frame(viewport)
    events.append(await _lifecycle_capture(transport, viewport, arguments["capture_dir"], references, "stage_replacement", 70004))

    await _next_frame(viewport)
    transport.regenerate_providers()
    transport._set_cpu(70005)
    for _ in range(24):
        await _next_frame(viewport)
    transport.begin_mode("gpu_ring3", 70006)
    transport.publish("gpu_ring3", 70006)
    for _ in range(24):
        await _next_frame(viewport)
    events.append(await _lifecycle_capture(transport, viewport, arguments["capture_dir"], references, "provider_regeneration", 70007))

    injected = []
    try:
        transport.inject_partial_failure(70008)
    except Exception as error:
        injected.append({"kind": "publication_mid_exception", "caught": f"{type(error).__name__}: {error}"})
    events.append(await _lifecycle_capture(transport, viewport, arguments["capture_dir"], references, "partial_failure_cpu_fallback", 70009))
    transport.faulted = False
    try:
        transport.inject_generation_failure()
    except Exception as error:
        injected.append({"kind": "gpu_generation_failure", "caught": f"{type(error).__name__}: {error}"})
    events.append(await _lifecycle_capture(transport, viewport, arguments["capture_dir"], references, "generation_failure_cpu_fallback", 70010))

    transport.faulted = False
    stress_start = 75000
    transport.begin_mode("gpu_immediate_stress", stress_start)
    stress_records = []
    for offset in range(12):
        revision = stress_start + offset
        timing = transport.publish("gpu_immediate_stress", revision)
        capture = await _capture(
            viewport,
            arguments["capture_dir"] / f"stress_revision_{revision}.png",
            transport.width,
            transport.height,
        )
        stress_records.append(
            {
                "revision": revision,
                "timing": timing,
                "classification": _classify(capture, references, revision),
                "capture": capture,
            }
        )

    long_start = 80000
    transport.begin_mode("gpu_ring3", long_start)
    long_records = []
    for offset in range(arguments["long_updates"]):
        revision = long_start + offset
        timing = transport.publish("gpu_ring3", revision)
        frame_ms = await _next_frame(viewport)
        if offset % max(1, arguments["long_updates"] // 6) == 0 or offset == arguments["long_updates"] - 1:
            capture = await _capture(
                viewport,
                arguments["capture_dir"] / f"long_revision_{revision}.png",
                transport.width,
                transport.height,
            )
            long_records.append(
                {
                    "offset": offset,
                    "revision": revision,
                    "provider_setter_ms": timing["provider_setter_ms"],
                    "next_frame_ms": frame_ms,
                    "classification": _classify(capture, references, revision),
                    "capture": capture,
                }
            )

    # A publication immediately precedes the explicit close preparation.  The
    # source allocations remain alive through a completed requested RTX frame.
    close_revision = 90000
    transport.begin_mode("gpu_ring3", close_revision)
    close_timing = transport.publish("gpu_ring3", close_revision)
    close_drain_ms = await _next_frame(viewport)
    prim_paths_after = [str(prim.GetPath()) for prim in context.get_stage().Traverse()]
    api_contract = transport.api_contract()
    device_contract = _device_contract(transport)
    flow_state = _flow_state()
    extension_close = {"attempted": False, "qualified": False}
    try:
        import omni.campfire.phasev3te_lifecycle as lifecycle_extension

        lifecycle_extension.register_transport(transport)
        extension_close["attempted"] = True
        manager = app.get_extension_manager()
        disabled = bool(
            manager.set_extension_enabled_immediate("omni.campfire.phasev3te_lifecycle", False)
        )
        extension_record = lifecycle_extension.get_record()
        extension_close.update(
            disabled=disabled,
            shutdown_called=bool(extension_record.get("shutdown_called")),
            close_sequence=list(extension_record.get("close_sequence", [])),
        )
        extension_close["qualified"] = bool(
            extension_close["shutdown_called"]
            and extension_close["close_sequence"]
            == [
                "warp_source_generation_synchronized",
                "providers_destroyed",
                "probe_owned_gpu_allocations_released",
            ]
        )
    except Exception as error:
        extension_close["error"] = f"{type(error).__name__}: {error}"
    return {
        "schema": "campfire.phasev3te.gpu_ring.lifecycle.v1",
        "status": "ok",
        "scenario": "lifecycle",
        "atlas": {"width": transport.width, "height": transport.height},
        "events": events,
        "injected_failures": injected,
        "fallback_count": transport.fallback_count,
        "immediate_reuse_stress": {
            "production_candidate": False,
            "records": stress_records,
        },
        "long_run": {
            "updates": arguments["long_updates"],
            "readback_checkpoints": long_records,
            "all_checkpoint_pixels_complete": all(
                item["classification"]["category"] in ("latest_complete", "one_generation_old_complete")
                for item in long_records
            ),
        },
        "close_with_publication": {
            "revision": close_revision,
            "timing": close_timing,
            "requested_rtx_drain_ms": close_drain_ms,
            "allocation_alive_through_drain": True,
        },
        "extension_close": extension_close,
        "api": api_contract,
        "device": device_contract,
        "flow": flow_state,
        "stage_contract": {
            **stage_contract,
            "prim_paths_after_replacement": prim_paths_after,
            "measurement_stage_topology_changed": False,
            "lifecycle_stage_reload_and_replacement_outside_performance_population": True,
        },
    }


async def _run(arguments):
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    output = arguments["output"]
    output.parent.mkdir(parents=True, exist_ok=True)
    arguments["capture_dir"].mkdir(parents=True, exist_ok=True)
    for old in arguments["capture_dir"].glob("*.png"):
        old.unlink()
    report = None
    transport = None
    exit_code = 1
    try:
        if arguments["scenario"] not in ("matrix", "lifecycle"):
            raise ValueError("scenario must be matrix or lifecycle")
        if arguments["width"] <= 0 or arguments["height"] <= 0:
            raise ValueError("invalid atlas dimensions")
        if arguments["scenario"] == "matrix" and (arguments["warmup"] < 1 or arguments["samples"] < 100):
            raise ValueError("matrix requires warmup and at least 100 samples")
        name_prefix = f"campfire_phasev3te_{arguments['scenario']}_{arguments['width']}x{arguments['height']}_r{arguments['run']}"
        transport = Transport(name_prefix, arguments["width"], arguments["height"])
        transport.initialize_gpu()
        transport._set_cpu(0)
        stage_path = output.with_suffix(".usda")
        authored = _build_stage(stage_path, transport.width, transport.height, *transport.uris)
        await context.open_stage_async(str(stage_path))
        viewport = await _viewport()
        timeline.play()
        stabilization_updates, prim_paths_before = await _settle(viewport, context)
        stage_contract = {
            **authored,
            "stabilization_updates": stabilization_updates,
            "prim_paths_before": prim_paths_before,
        }
        if arguments["scenario"] == "matrix":
            report = await _run_matrix(arguments, transport, viewport, context, stage_contract)
        else:
            report = await _run_lifecycle(
                arguments, transport, viewport, context, timeline, stage_path, stage_contract
            )
        exit_code = 0
    except Exception as error:
        report = {
            "schema": "campfire.phasev3te.error.v1",
            "status": "error",
            "scenario": arguments.get("scenario"),
            "error": f"{type(error).__name__}: {error}",
        }
    finally:
        timeline.stop()
        if transport is not None:
            transport.close()
            if report is not None:
                report["close_sequence"] = transport.close_sequence
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        app.post_uncancellable_quit(exit_code)


asyncio.ensure_future(_run(_arguments()))
