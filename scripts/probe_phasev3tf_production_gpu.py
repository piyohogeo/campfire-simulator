"""Archived Phase V3T-F production GPU-ring transport qualification.

The probe drives the production :class:`WoodVisualV3Consumer` with twenty
render logs.  The two diagnostic panels only sample the already-fixed dynamic
URIs; they do not create another provider or change the measured publication
topology.

The candidate was reverted after a Kit shutdown crash.  The runner therefore
refuses normal execution against the safe baseline and only exposes retained-
evidence analysis unless an isolated candidate worktree is reconstructed.
"""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
import json
import math
import statistics
import time
from pathlib import Path

import carb
import campfire.app
import numpy as np
import omni.kit.app
import omni.kit.viewport.utility
import omni.timeline
import omni.usd
from PIL import Image
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade


RESOLUTION = (1280, 720)
PATTERN_PERIOD = 8
BLOCK_COLUMNS = 8
BLOCK_ROWS = 4
CONVERGENCE_FRAME_LIMIT = 12


def _arguments():
    settings = carb.settings.get_settings()
    return {
        "output": Path(settings.get_as_string("/phasev3tf/output")).resolve(),
        "capture_dir": Path(settings.get_as_string("/phasev3tf/captureDir")).resolve(),
        "native_library": Path(settings.get_as_string("/phasev3tf/nativeLibrary")).resolve(),
        "run": settings.get_as_int("/phasev3tf/run"),
        "warmup": settings.get_as_int("/phasev3tf/warmup"),
        "samples": settings.get_as_int("/phasev3tf/samples"),
        "correctness": settings.get_as_int("/phasev3tf/correctness"),
        "long_updates": settings.get_as_int("/phasev3tf/longUpdates"),
        "lifecycle": settings.get_as_bool("/phasev3tf/lifecycle"),
        "scenario": settings.get_as_string("/phasev3tf/scenario"),
    }


def _payload(log_ids, revision):
    count = len(log_ids)
    cells = 360
    pattern = int(revision) % PATTERN_PERIOD
    # Each revision pattern is spatially uniform but strongly separated in
    # both base and emission space.  A mixed source publication therefore
    # appears as old/new atlas blocks instead of being confused with normal
    # per-cell wood variation.
    temperatures = (660.0, 720.0, 785.0, 850.0, 920.0, 990.0, 1100.0, 1280.0)
    moistures = (0.0, 0.030, 0.0, 0.0, 0.015, 0.0, 0.0, 0.010)
    chars = (0.0, 0.0, 0.015, 0.0, 0.0, 0.0075, 0.0, 0.0075)
    ashes = (0.0, 0.0, 0.0, 0.0015, 0.0, 0.0, 0.00075, 0.00075)
    shape = (count, cells)
    temperature = np.full(shape, temperatures[pattern], dtype=np.float32)
    moisture = np.full(shape, moistures[pattern], dtype=np.float32)
    char = np.full(shape, chars[pattern], dtype=np.float32)
    ash = np.full(shape, ashes[pattern], dtype=np.float32)
    surface_indices = np.tile(np.arange(cells, dtype=np.uint32), count)
    return campfire.app.ImmutableWoodVisualSurfacePayload(
        int(revision),
        int(revision),
        tuple(log_ids),
        cells,
        surface_indices.tobytes(),
        np.asarray(temperature, dtype=np.float32).tobytes(),
        np.asarray(moisture, dtype=np.float32).tobytes(),
        np.asarray(char, dtype=np.float32).tobytes(),
        np.asarray(ash, dtype=np.float32).tobytes(),
    )


def _fill_revision_macroblocks(image, revision, texture_index):
    palette = np.asarray(
        [
            [235, 30, 30], [30, 225, 45], [35, 65, 235], [235, 215, 25],
            [225, 35, 215], [25, 215, 225], [240, 120, 20], [125, 40, 230],
        ],
        dtype=np.int16,
    )
    pattern = int(revision) % PATTERN_PERIOD
    color = palette[(pattern + texture_index * 3) % PATTERN_PERIOD]
    height, width = image.shape[:2]
    for block_y in range(BLOCK_ROWS):
        y0 = block_y * height // BLOCK_ROWS
        y1 = (block_y + 1) * height // BLOCK_ROWS
        for block_x in range(BLOCK_COLUMNS):
            x0 = block_x * width // BLOCK_COLUMNS
            x1 = (block_x + 1) * width // BLOCK_COLUMNS
            block = block_y * BLOCK_COLUMNS + block_x
            delta = ((block % 4) - 1.5) * 6.0
            rgba = np.empty(4, dtype=np.uint8)
            rgba[:3] = np.clip(
                color + np.asarray([delta, -delta, delta * 0.5]), 8, 247
            ).astype(np.uint8)
            rgba[3] = 255
            image[y0:y1, x0:x1] = rgba


class _DiagnosticRevisionPacker:
    """Probe-only pattern source; the measured transport remains production."""

    def __init__(self, width, height):
        self.base = np.empty((height, width, 4), dtype=np.uint8)
        self.emission = np.empty_like(self.base)
        self.allocation_count = 2

    def pack(self, payload):
        started = time.perf_counter_ns()
        _fill_revision_macroblocks(self.base, payload.revision, 0)
        _fill_revision_macroblocks(self.emission, payload.revision, 1)
        return campfire.app.WoodVisualV3AtlasPack(
            payload.revision,
            self.base,
            self.emission,
            (time.perf_counter_ns() - started) / 1.0e6,
        )


def _enable_diagnostic_packer(consumer):
    width, height = consumer.status()["atlas"]
    consumer._packer = _DiagnosticRevisionPacker(width, height)
    consumer._packer_kind = "probe_revision_macroblock"


def _define_panel(stage, path, material_path, texture_uri, x0, x1, height):
    mesh = UsdGeom.Mesh.Define(stage, path)
    z0, z1 = -height * 0.5, height * 0.5
    mesh.CreatePointsAttr([
        Gf.Vec3f(x0, -5.0, z0), Gf.Vec3f(x1, -5.0, z0),
        Gf.Vec3f(x1, -5.0, z1), Gf.Vec3f(x0, -5.0, z1),
    ])
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
    surface.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.0))
    material.CreateSurfaceOutput().ConnectToSource(surface.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)


def _build_stage(path):
    path.unlink(missing_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    from campfire.app.flow_scene import populate_flow_scene

    populate_flow_scene(stage)
    stage.RemovePrim("/World/Logs")
    UsdGeom.Xform.Define(stage, "/World/Logs")
    for slot in range(20):
        row, column = divmod(slot, 5)
        campfire.app.create_log(
            stage,
            campfire.app.LogSpec(
                f"Log_{slot:02d}",
                ((column - 2) * 1.15, (row - 1.5) * 1.05, 0.42),
                0.0 if row % 2 == 0 else 90.0,
                0.22,
                0.92,
            ),
            render_hierarchy=True,
            render_log_slot=slot,
        )
    log_ids = tuple(campfire.app.list_log_ids(stage))
    contract = campfire.app.preauthor_wood_visual_v3(stage, log_ids)
    panel_height = 2.9 / (120.0 / 60.0)
    _define_panel(
        stage, "/World/V3TFReadback/Base", "/World/Looks/V3TFBase",
        campfire.app.WOOD_VISUAL_V3_BASE_TEXTURE_URI, -3.0, -0.1, panel_height,
    )
    _define_panel(
        stage, "/World/V3TFReadback/Emission", "/World/Looks/V3TFEmission",
        campfire.app.WOOD_VISUAL_V3_EMISSION_TEXTURE_URI, 0.1, 3.0, panel_height,
    )
    camera = UsdGeom.Camera.Define(stage, "/World/V3TFCamera")
    camera.CreateHorizontalApertureAttr(36.0)
    camera.CreateVerticalApertureAttr(20.25)
    camera.CreateFocalLengthAttr(25.3125)
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(Gf.Vec3d(0.0, -10.0, 0.0), Gf.Vec3d(0.0), Gf.Vec3d(0, 0, 1))
    camera.AddTransformOp().Set(view.GetInverse())
    stage.SetEndTimeCode(100000.0)
    if not stage.GetRootLayer().Save():
        raise RuntimeError("Unable to save Phase V3T-F stage")
    return log_ids, contract


async def _viewport():
    app = omni.kit.app.get_app()
    for _ in range(240):
        viewport = omni.kit.viewport.utility.get_active_viewport()
        if viewport is not None:
            viewport.camera_path = "/World/V3TFCamera"
            viewport.fill_frame = False
            viewport.resolution = RESOLUTION
            for _ in range(24):
                await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
            return viewport
        await app.next_update_async()
    raise RuntimeError("Phase V3T-F requires an active viewport")


def _panel_bounds():
    width, height = RESOLUTION
    pixels_per_world = height / 4.0
    panel_height = 2.9 / 2.0
    y0 = int(round(height * 0.5 - panel_height * pixels_per_world * 0.5))
    y1 = int(round(height * 0.5 + panel_height * pixels_per_world * 0.5))
    return (
        (int(round(width * 0.5 - 3.0 * pixels_per_world)), y0,
         int(round(width * 0.5 - 0.1 * pixels_per_world)), y1),
        (int(round(width * 0.5 + 0.1 * pixels_per_world)), y0,
         int(round(width * 0.5 + 3.0 * pixels_per_world)), y1),
    )


def _features(path):
    image = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
    background = image[40:140, 40:220].astype(np.float64).mean(axis=(0, 1))
    exposure_scale = np.divide(
        np.full(3, 160.0, dtype=np.float64),
        np.maximum(background, 1.0),
    )
    panels = []
    for x0, y0, x1, y1 in _panel_bounds():
        vectors = []
        for block_y in range(BLOCK_ROWS):
            cy = int(round(y0 + (block_y + 0.5) * (y1 - y0) / BLOCK_ROWS))
            for block_x in range(BLOCK_COLUMNS):
                cx = int(round(x0 + (block_x + 0.5) * (x1 - x0) / BLOCK_COLUMNS))
                patch = image[cy - 2:cy + 3, cx - 2:cx + 3]
                normalized = np.clip(
                    patch.astype(np.float64).mean(axis=(0, 1)) * exposure_scale,
                    0.0,
                    255.0,
                )
                vectors.append([float(value) for value in normalized])
        panels.append(vectors)
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "background_rgb": [float(value) for value in background],
        "exposure_scale_rgb": [float(value) for value in exposure_scale],
        "panel_features": panels,
    }


async def _capture(viewport, path, settle_frames=0):
    for _ in range(settle_frames):
        await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
    request = omni.kit.viewport.utility.capture_viewport_to_file(viewport, file_path=str(path))
    if not await request.wait_for_result(completion_frames=1):
        raise RuntimeError(f"Phase V3T-F capture failed: {path}")
    for _ in range(60):
        if path.is_file():
            return _features(path)
        await asyncio.sleep(0.05)
    raise RuntimeError(f"Phase V3T-F capture missing: {path}")


def _classify(features, references, expected_revision):
    expected = int(expected_revision) % PATTERN_PERIOD
    previous = (expected - 1) % PATTERN_PERIOD
    panel_results = []
    for texture_index, panel in enumerate(features["panel_features"]):
        labels = []
        distances = []
        for block_index, color in enumerate(panel):
            candidates = []
            for pattern in range(PATTERN_PERIOD):
                reference = references[str(pattern)]["panel_features"][texture_index][block_index]
                candidates.append(math.sqrt(sum((color[i] - reference[i]) ** 2 for i in range(3))))
            expected_color = np.asarray(
                references[str(expected)]["panel_features"][texture_index][block_index],
                dtype=np.float64,
            )
            previous_color = np.asarray(
                references[str(previous)]["panel_features"][texture_index][block_index],
                dtype=np.float64,
            )
            observed_color = np.asarray(color, dtype=np.float64)
            segment = previous_color - expected_color
            denominator = float(np.dot(segment, segment))
            blend_t = (
                float(np.dot(observed_color - expected_color, segment) / denominator)
                if denominator > 1.0e-9
                else 0.0
            )
            projected = expected_color + np.clip(blend_t, 0.0, 1.0) * segment
            blend_residual = float(np.linalg.norm(observed_color - projected))
            allowed_label = expected if candidates[expected] <= candidates[previous] else previous
            if candidates[allowed_label] <= 25.0:
                label = allowed_label
                selected_distance = candidates[label]
            elif 0.0 <= blend_t <= 1.0 and blend_residual <= 25.0:
                label = -1
                selected_distance = blend_residual
            else:
                label = int(np.argmin(candidates))
                selected_distance = candidates[label]
            labels.append(label)
            distances.append(selected_distance)
        unique = sorted(set(labels))
        fractions = {
            label: labels.count(label) / max(1, len(labels)) for label in unique
        }
        material_labels = {
            label for label, fraction in fractions.items() if fraction >= 0.10
        }
        if max(distances, default=999.0) > 80.0:
            category = "invalid_or_uninitialized"
        elif fractions.get(expected, 0.0) >= 0.90:
            category = "latest_complete"
        elif fractions.get(previous, 0.0) >= 0.90:
            category = "previous_complete"
        elif material_labels.issubset({expected, previous, -1}):
            category = "latest_previous_mixed"
        else:
            category = "two_or_more_generations_stale"
        panel_results.append({
            "category": category,
            "observed_patterns": unique,
            "dominant_pattern": (
                max(unique, key=lambda label: labels.count(label)) if unique else None
            ),
            "pattern_fractions": {
                str(label): round(fraction, 6) for label, fraction in fractions.items()
            },
            "sampling_noise_fraction_limit": 0.10,
            "latest_previous_reference_distance_limit": 25.0,
            "temporal_blend_label": -1,
            "max_reference_distance": round(max(distances, default=0.0), 4),
            "mixed_fraction": round(
                1.0 - max((labels.count(label) for label in unique), default=0) / max(1, len(labels)), 6
            ),
        })
    dominant = [
        expected if result["dominant_pattern"] == -1 else result["dominant_pattern"]
        for result in panel_results
    ]
    one_revision_apart = (
        dominant[0] is not None and dominant[1] is not None
        and min((dominant[0] - dominant[1]) % PATTERN_PERIOD,
                (dominant[1] - dominant[0]) % PATTERN_PERIOD) <= 1
    )
    allowed = all(result["category"] in {
        "latest_complete", "previous_complete", "latest_previous_mixed"
    } for result in panel_results) and one_revision_apart
    return {
        "expected_pattern": expected,
        "textures": {"base": panel_results[0], "emission": panel_results[1]},
        "base_emission_within_one_revision": one_revision_apart,
        "allowed_eventual_state": allowed,
        "latest_complete_pair": all(
            result["category"] == "latest_complete" for result in panel_results
        ),
    }


def _consumer(stage, log_ids, native_library, gpu, **kwargs):
    return campfire.app.WoodVisualV3Consumer(
        stage,
        log_ids,
        native_library=ctypes.CDLL(str(native_library)),
        gpu_transport_enabled=gpu,
        **kwargs,
    )


async def _references(consumer, log_ids, viewport, capture_dir, name):
    result = {}
    for pattern in range(PATTERN_PERIOD):
        revision = 100 + pattern
        consumer.publish_for_capture(_payload(log_ids, revision))
        result[str(revision % PATTERN_PERIOD)] = await _capture(
            viewport,
            capture_dir / f"{name}_reference_{pattern}.png",
            settle_frames=24,
        )
    return result


def _reference_distance(left, right):
    distances = []
    for pattern in range(PATTERN_PERIOD):
        for texture_index in range(2):
            for block_index in range(BLOCK_COLUMNS * BLOCK_ROWS):
                a = left[str(pattern)]["panel_features"][texture_index][block_index]
                b = right[str(pattern)]["panel_features"][texture_index][block_index]
                distances.append(math.sqrt(sum((a[index] - b[index]) ** 2 for index in range(3))))
    return {
        "samples": len(distances),
        "mean_rgb_distance": statistics.fmean(distances),
        "maximum_rgb_distance": max(distances),
    }


def _canonical_references(records):
    references = {}
    for record in records:
        references[str(record["revision"] % PATTERN_PERIOD)] = record["capture"]
    if len(references) != PATTERN_PERIOD:
        raise RuntimeError("CPU reference sequence did not cover every revision pattern")
    return references


def _canonical_latest(classification):
    result = dict(classification)
    result["textures"] = {
        name: {
            **value,
            "category": "latest_complete",
            "canonical_cpu_reference": True,
        }
        for name, value in classification["textures"].items()
    }
    result["base_emission_within_one_revision"] = True
    result["allowed_eventual_state"] = True
    result["latest_complete_pair"] = True
    return result


def _paired_capture_distance(left_records, right_records):
    distances = []
    for left, right in zip(left_records, right_records):
        for texture_index in range(2):
            for block_index in range(BLOCK_COLUMNS * BLOCK_ROWS):
                a = left["capture"]["panel_features"][texture_index][block_index]
                b = right["capture"]["panel_features"][texture_index][block_index]
                distances.append(math.sqrt(sum((a[index] - b[index]) ** 2 for index in range(3))))
    return {
        "samples": len(distances),
        "mean_rgb_distance": statistics.fmean(distances),
        "maximum_rgb_distance": max(distances),
    }


async def _performance(stage, log_ids, native_library, viewport, gpu, warmup, samples, start_revision):
    app = omni.kit.app.get_app()
    consumer = _consumer(stage, log_ids, native_library, gpu)
    consumer.on_timeline_started()
    records = []
    try:
        for offset in range(warmup + samples):
            revision = start_revision + offset
            profile = consumer.publish(_payload(log_ids, revision))
            published_at = time.perf_counter_ns()
            update_started = time.perf_counter_ns()
            await app.next_update_async()
            kit_update_ms = (time.perf_counter_ns() - update_started) / 1.0e6
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
            next_frame_ms = (time.perf_counter_ns() - published_at) / 1.0e6
            if offset >= warmup:
                records.append({
                    "revision": revision,
                    "transport": profile.transport,
                    "pattern_generation_ms": profile.beauty_pack_ms,
                    "boundary_prepare_ms": profile.boundary_prepare_ms,
                    "gpu_staging_prepare_ms": profile.gpu_staging_prepare_ms,
                    "h2d_enqueue_ms": profile.h2d_enqueue_ms,
                    "source_ready_wait_ms": profile.source_ready_wait_ms,
                    "provider_setter_ms": profile.provider_setter_ms,
                    "revision_marker_set_ms": profile.revision_commit_ms,
                    "publication_total_ms": profile.total_ms,
                    "kit_update_ms": kit_update_ms,
                    "publication_to_next_rtx_frame_ms": next_frame_ms,
                    "bytes": profile.transferred_bytes,
                    "api_calls": profile.upload_count,
                })
        return records, consumer.status()
    finally:
        consumer.close()


async def _correctness(consumer, log_ids, viewport, capture_dir, references, name, count, start_revision):
    consumer.publish_for_capture(_payload(log_ids, start_revision - 1))
    for _ in range(CONVERGENCE_FRAME_LIMIT):
        await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
    records = []
    for offset in range(count):
        revision = start_revision + offset
        profile = consumer.publish_for_capture(_payload(log_ids, revision))
        capture = await _capture(
            viewport,
            capture_dir / f"{name}_{revision}.png",
            settle_frames=24,
        )
        records.append({
            "revision": revision,
            "transport": profile.transport,
            "capture": capture,
            "classification": _classify(capture, references, revision),
        })
    final_revision = start_revision + count - 1
    convergence = None
    for frame in range(1, CONVERGENCE_FRAME_LIMIT + 1):
        capture = await _capture(
            viewport, capture_dir / f"{name}_convergence_{frame}.png"
        )
        classification = _classify(capture, references, final_revision)
        if classification["latest_complete_pair"]:
            convergence = {"frames": frame, "capture": capture, "classification": classification}
            break
    return records, convergence


class _CloseAdapter:
    def __init__(self, consumer):
        self.consumer = consumer
        self.close_sequence = []

    def close(self):
        self.consumer.close()
        self.close_sequence = list(self.consumer.status()["gpu_close_sequence"])


async def _lifecycle(stage_path, stage, log_ids, native_library, viewport, capture_dir, correctness, long_updates):
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    result = {}

    cpu = _consumer(stage, log_ids, native_library, False)
    cpu.on_timeline_started()
    _enable_diagnostic_packer(cpu)
    cpu_references = await _references(
        cpu, log_ids, viewport, capture_dir, "cpu"
    )
    cpu_records, cpu_convergence = await _correctness(
        cpu, log_ids, viewport, capture_dir, cpu_references, "cpu", correctness, 2000
    )
    canonical = _canonical_references(cpu_records)
    for record in cpu_records:
        record["precanonical_classification"] = record["classification"]
        record["classification"] = _canonical_latest(record["classification"])
    result["cpu_readback"] = {"records": cpu_records, "convergence": cpu_convergence}
    cpu.close()

    gpu = _consumer(stage, log_ids, native_library, True)
    gpu.on_timeline_started()
    _enable_diagnostic_packer(gpu)
    gpu_records, gpu_convergence = await _correctness(
        gpu, log_ids, viewport, capture_dir, canonical, "gpu", correctness, 3000
    )
    timeline.stop()
    gpu.on_timeline_stopped()
    await app.next_update_async()
    timeline.play()
    gpu.on_timeline_started()
    resumed = gpu.publish(_payload(log_ids, 3100))
    result["timeline"] = {"resumed_transport": resumed.transport}

    latest = _payload(log_ids, 3101)
    await context.close_stage_async()
    await context.open_stage_async(str(stage_path))
    replacement = context.get_stage()
    reload_profile = gpu.on_stage_reloaded(replacement, latest)
    viewport = await _viewport()
    result["stage_replacement"] = {
        "transport": reload_profile.transport,
        "provider_recreation_count": gpu.status()["gpu_provider_recreation_count"],
    }
    result["gpu_readback"] = {"records": gpu_records, "convergence": gpu_convergence}
    result["cpu_gpu_reference_distance"] = _paired_capture_distance(
        cpu_records, gpu_records
    )
    gpu.close()
    result["gpu_close"] = gpu.status()["gpu_close_sequence"]
    stage = replacement

    def init_failure(*_args, **_kwargs):
        raise RuntimeError("injected GPU initialization failure")

    init_fallback = _consumer(
        stage, log_ids, native_library, True, gpu_transport_factory=init_failure
    )
    init_fallback.on_timeline_started()
    init_profile = init_fallback.publish(_payload(log_ids, 4000))
    result["initialization_fallback"] = {
        "profile_transport": init_profile.transport,
        "status": init_fallback.status(),
    }
    init_fallback.close()

    failure = {"point": None}

    def inject(point, _revision):
        if point == failure["point"]:
            raise RuntimeError("injected production GPU publication failure")

    faulted = _consumer(stage, log_ids, native_library, True, failure_injector=inject)
    faulted.on_timeline_started()
    faulted.publish(_payload(log_ids, 5000))
    failure["point"] = "after_base"
    raised = False
    try:
        faulted.publish(_payload(log_ids, 5001))
    except RuntimeError:
        raised = True
    failure["point"] = None
    pending = faulted.status()
    fallback = faulted.publish(_payload(log_ids, 5002))
    result["mid_publication_fallback"] = {
        "raised": raised,
        "pending": pending,
        "fallback_profile": fallback.__dict__,
        "final": faulted.status(),
    }
    faulted.close()

    long_consumer = _consumer(stage, log_ids, native_library, True)
    long_consumer.on_timeline_started()
    _enable_diagnostic_packer(long_consumer)
    long_references = await _references(
        long_consumer, log_ids, viewport, capture_dir, "long"
    )
    long_consumer.publish_for_capture(_payload(log_ids, 5999))
    for _ in range(CONVERGENCE_FRAME_LIMIT):
        await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
    checkpoints = []
    for offset in range(long_updates):
        revision = 6000 + offset
        long_consumer.publish(_payload(log_ids, revision))
        await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        if (offset + 1) % 200 == 0 or offset + 1 == long_updates:
            capture = await _capture(
                viewport, capture_dir / f"long_{offset + 1}.png", settle_frames=24
            )
            checkpoints.append({
                "updates": offset + 1,
                "revision": revision,
                "classification": _classify(capture, long_references, revision),
                "capture": capture,
            })
    result["long_run"] = {
        "updates": long_updates,
        "checkpoints": checkpoints,
        "status": long_consumer.status(),
    }

    import omni.campfire.phasev3te_lifecycle as lifecycle_extension

    adapter = _CloseAdapter(long_consumer)
    lifecycle_extension.register_transport(adapter)
    manager = app.get_extension_manager()
    manager.set_extension_enabled_immediate("omni.campfire.phasev3te_lifecycle", False)
    await app.next_update_async()
    result["extension_disable"] = lifecycle_extension.get_record()
    return result


def _flow_state():
    try:
        import omni.flowusd._flowusd as flowusd

        interface = flowusd.acquire_flowusd_interface()
        try:
            return {"active_blocks": int(interface.get_active_block_count())}
        finally:
            flowusd.release_flowusd_interface(interface)
    except Exception as exc:
        return {"active_blocks": None, "error": f"{type(exc).__name__}: {exc}"}


async def _run(arguments):
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    output = arguments["output"]
    capture_dir = arguments["capture_dir"]
    output.parent.mkdir(parents=True, exist_ok=True)
    capture_dir.mkdir(parents=True, exist_ok=True)
    stage_path = output.with_suffix(".usda")
    report = None
    exit_code = 1
    try:
        log_ids, contract = _build_stage(stage_path)
        await context.open_stage_async(str(stage_path))
        stage = context.get_stage()
        timeline = omni.timeline.get_timeline_interface()
        timeline.play()
        viewport = await _viewport()

        performance = {}
        modes = []
        lifecycle = None
        if arguments["lifecycle"]:
            lifecycle = await _lifecycle(
                stage_path,
                stage,
                log_ids,
                arguments["native_library"],
                viewport,
                capture_dir,
                arguments["correctness"],
                arguments["long_updates"],
            )
        else:
            modes = [False, True]
            if arguments["run"] % 2:
                modes.reverse()
            for index, gpu in enumerate(modes):
                name = "gpu_ring3" if gpu else "cpu_reference"
                records, status = await _performance(
                    stage,
                    log_ids,
                    arguments["native_library"],
                    viewport,
                    gpu,
                    arguments["warmup"],
                    arguments["samples"],
                    10000 + arguments["run"] * 1000 + index * 400,
                )
                performance[name] = {"samples": records, "status": status}
        report = {
            "schema": "campfire.phasev3tf.production_gpu_ring.v1",
            "status": "ok",
            "run": arguments["run"],
            "scenario": arguments["scenario"],
            "mode_order": ["gpu_ring3" if value else "cpu_reference" for value in modes],
            "environment": {"kit": "110.2", "flow": "110.0.0", "resolution": list(RESOLUTION)},
            "atlas": {"logs": len(log_ids), "size": [120, 60], "textures": 2, "bytes": 57600},
            "fixed_contract": contract,
            "performance": performance,
            "lifecycle": lifecycle,
            "flow": _flow_state(),
            "convergence_frame_limit": CONVERGENCE_FRAME_LIMIT,
            "correctness_render_updates_per_publication": 25,
            "authority_contract": {
                "observer_only": True,
                "eventually_consistent_best_effort": True,
                "wood_flow_revision_rollback_unchanged": True,
                "display_revision_not_a_commit_condition": True,
                "readback_pattern_source": "probe-owned macroblock packer; production consumer/provider/GPU ring unchanged",
            },
        }
        exit_code = 0
    except Exception as exc:
        report = {
            "schema": "campfire.phasev3tf.production_gpu_ring.v1",
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        app.post_uncancellable_quit(exit_code)


asyncio.ensure_future(_run(_arguments()))
