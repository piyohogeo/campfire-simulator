"""Production-neutral visible viewport probe for Phase V3T-K.

No RenderProduct, HydraTexture, capture, encoder, or live stage mutation is used.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import struct
import time
import zlib
from pathlib import Path

import carb
import omni.kit.app
import omni.kit.viewport.utility
import omni.timeline
import omni.usd
from pxr import Gf, PhysxSchema, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade


RESOLUTION = (1280, 720)
MAX_READS = 50000
AA_MODES = {"inherit": None, "performance": 0, "balanced": 1, "quality": 2, "auto": 3, "dlaa": 4}
SETTING_PATHS = (
    "/rtx/post/aa/op",
    "/rtx/post/dlss/execMode",
    "/rtx/post/dlss/enabled",
    "/rtx/pathtracing/dlss/enabled",
    "/rtx-transient/dlssg/enabled",
    "/rtx-transient/dlssg/x3x4supported",
    "/rtx/ecoMode/enabled",
    "/rtx/directLighting/enabled",
    "/rtx/directLighting/sampledLighting/samplesPerPixel",
    "/rtx/directLighting/domeLight/sampleCount",
    "/rtx/shadows/enabled",
    "/rtx/reflections/enabled",
    "/rtx/reflections/sampledLighting/samplesPerPixel",
    "/rtx/reflections/maxReflectionBounces",
    "/rtx/translucency/enabled",
    "/rtx/translucency/maxRefractionBounces",
    "/rtx/indirectDiffuse/enabled",
    "/rtx/indirectDiffuse/maxBounces",
    "/rtx/realtime/optixDenoiser/enabled",
    "/rtx/flow/enabled",
    "/renderer/multiGpu/enabled",
    "/app/runLoops/main/rateLimitEnabled",
    "/app/runLoops/main/rateLimitFrequency",
    "/app/runLoops/main/syncToPresent",
    "/app/runLoops/present/rateLimitEnabled",
    "/app/runLoops/present/rateLimitFrequency",
    "/app/runLoops/present/syncToPresent",
    "/app/runLoops/rendering_0/rateLimitEnabled",
    "/app/runLoops/rendering_0/rateLimitFrequency",
    "/app/runLoops/rendering_0/syncToPresent",
    "/app/runLoopsGlobal/syncToPresent",
    "/persistent/app/viewport/defaults/tickRate",
    "/persistent/simulation/minFrameRate",
    "/renderer/vsync",
    "/app/vsync",
)
DISCOVERY_TOKENS = (
    "aa", "dlss", "dlaa", "resolution", "dynamic", "sample", "bounce",
    "shadow", "denois", "reconstruction", "rendermode", "render_mode",
)


def _arguments():
    settings = carb.settings.get_settings()
    return {
        "output": Path(settings.get_as_string("/phasev3tk/output")).resolve(),
        "condition": settings.get_as_string("/phasev3tk/condition"),
        "aa_mode": settings.get_as_string("/phasev3tk/aaMode"),
        "warmup_seconds": settings.get_as_float("/phasev3tk/warmupSeconds"),
        "measure_seconds": settings.get_as_float("/phasev3tk/measureSeconds"),
        "run": settings.get_as_int("/phasev3tk/run"),
    }


def _json_safe(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    return str(value)


def _walk_settings(value, path, rows):
    if isinstance(value, dict):
        for key, item in value.items():
            _walk_settings(item, f"{path}/{key}", rows)
    elif any(token in path.lower() for token in DISCOVERY_TOKENS):
        rows[path] = _json_safe(value)


def _settings_snapshot(viewport):
    settings = carb.settings.get_settings()
    discovered = {}
    for root in ("/rtx", "/rtx-transient", "/renderer"):
        dictionary = settings.get_settings_dictionary(root)
        _walk_settings(dictionary.get_dict() if dictionary is not None else {}, root, discovered)
    frame_info = dict(viewport.frame_info)
    return {
        "requested_paths": {path: _json_safe(settings.get(path)) for path in SETTING_PATHS},
        "discovered_related_settings": dict(sorted(discovered.items())),
        "renderer_mode": {
            "public_setting_value": _json_safe(settings.get("/renderer/mode")),
            "rtx_setting_value": _json_safe(settings.get("/rtx/rendermode")),
            "viewport_render_product_path": str(viewport.render_product_path),
            "label": "RTX Real-Time 2.0 selected by the existing visible viewport",
        },
        "output_resolution": list(frame_info.get("resolution", viewport.resolution)),
        "internal_render_resolution": None,
        "internal_render_resolution_status": "unavailable through the public ViewportAPI/settings inspected in Kit 110.2",
        "ray_reconstruction_runtime_value": None,
        "ray_reconstruction_status": "no public runtime value found; not inferred from the local UI changelog",
        "frame_generation_requested": False,
    }


def _camera(stage):
    camera = UsdGeom.Camera.Get(stage, "/World/Camera")
    if not camera:
        camera = UsdGeom.Camera.Define(stage, "/World/Camera")
    camera.CreateFocalLengthAttr(35.0)
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(Gf.Vec3d(7.8, -7.8, 5.8), Gf.Vec3d(0.0, 0.0, 1.15), Gf.Vec3d(0, 0, 1))
    attribute = camera.GetPrim().GetAttribute("xformOp:transform")
    if not attribute:
        attribute = UsdGeom.Xformable(camera).MakeMatrixXform().GetAttr()
    attribute.Set(view.GetInverse())


def _write_rgba_png(path, width, height, rgba):
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    row = b"\x00" + bytes(rgba) * width
    payload = b"\x89PNG\r\n\x1a\n"
    payload += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    payload += chunk(b"IDAT", zlib.compress(row * height, 9))
    payload += chunk(b"IEND", b"")
    path.write_bytes(payload)


def _solid_material(stage, path="/World/Looks/SolidWood"):
    material = UsdShade.Material.Define(stage, path)
    surface = UsdShade.Shader.Define(stage, path + "/Surface")
    surface.CreateIdAttr("UsdPreviewSurface")
    surface.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.30, 0.12, 0.045))
    surface.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.62)
    material.CreateSurfaceOutput().ConnectToSource(surface.ConnectableAPI(), "surface")
    return material


def _texture_shader(stage, path, file_path):
    shader = UsdShade.Shader.Define(stage, path)
    shader.CreateIdAttr("UsdUVTexture")
    shader.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(str(file_path)))
    shader.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("raw")
    shader.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("clamp")
    shader.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("clamp")
    shader.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    shader.CreateOutput("a", Sdf.ValueTypeNames.Float)
    return shader


def _static_texture_material(stage, asset_dir):
    base_path = asset_dir / "fixed_base.png"
    emission_path = asset_dir / "fixed_emission.png"
    _write_rgba_png(base_path, 120, 60, (92, 39, 14, 158))
    _write_rgba_png(emission_path, 120, 60, (0, 0, 0, 255))
    path = "/World/Looks/StaticTextureWood"
    material = UsdShade.Material.Define(stage, path)
    surface = UsdShade.Shader.Define(stage, path + "/Surface")
    surface.CreateIdAttr("UsdPreviewSurface")
    reader = UsdShade.Shader.Define(stage, path + "/Reader")
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    base = _texture_shader(stage, path + "/BaseTexture", base_path)
    emission = _texture_shader(stage, path + "/EmissionTexture", emission_path)
    for texture in (base, emission):
        texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
    surface.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(base.ConnectableAPI(), "rgb")
    surface.CreateInput("roughness", Sdf.ValueTypeNames.Float).ConnectToSource(base.ConnectableAPI(), "a")
    surface.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(emission.ConnectableAPI(), "rgb")
    material.CreateSurfaceOutput().ConnectToSource(surface.ConnectableAPI(), "surface")
    return material


def _positions():
    for slot in range(20):
        row, column = divmod(slot, 5)
        yield slot, ((column - 2) * 1.15, (row - 1.5) * 1.05, 0.42), (0.0 if row % 2 == 0 else 90.0)


def _bind(prim, material):
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(material)


def _simple_cylinders(stage, count, material):
    for slot, position, rotation in list(_positions())[:count]:
        cylinder = UsdGeom.Cylinder.Define(stage, f"/World/Logs/Log_{slot:02d}")
        cylinder.CreateAxisAttr(UsdGeom.Tokens.x)
        cylinder.CreateRadiusAttr(0.22)
        cylinder.CreateHeightAttr(0.92)
        cylinder.AddTranslateOp().Set(Gf.Vec3d(*position))
        cylinder.AddRotateZOp().Set(rotation)
        _bind(cylinder.GetPrim(), material)


def _v3_meshes(stage, material=None, rigid=False):
    import campfire.app
    from campfire.app.wood_render_mesh import author_wood_render_mesh

    log_ids = []
    for slot, position, rotation in _positions():
        log_id = f"Log_{slot:02d}"
        log_ids.append(log_id)
        root = UsdGeom.Xform.Define(stage, f"/World/Logs/{log_id}")
        root.AddTranslateOp().Set(Gf.Vec3d(*position))
        root.AddRotateZOp().Set(rotation)
        root_prim = root.GetPrim()
        root_prim.CreateAttribute("campfire:logId", Sdf.ValueTypeNames.String).Set(log_id)
        root_prim.CreateAttribute("campfire:renderRepresentation", Sdf.ValueTypeNames.Token).Set("uv_mesh_v1")
        root_prim.CreateAttribute("campfire:renderAtlasSlot", Sdf.ValueTypeNames.Int).Set(slot)
        render = UsdGeom.Mesh.Define(stage, f"/World/Logs/{log_id}/RenderSurface")
        author_wood_render_mesh(render, 0.22, 0.92, slot)
        if material is not None:
            _bind(render.GetPrim(), material)
        if rigid:
            body = UsdPhysics.RigidBodyAPI.Apply(root_prim)
            body.CreateRigidBodyEnabledAttr(True)
            body.CreateKinematicEnabledAttr(False)
            body.CreateVelocityAttr(Gf.Vec3f(0.0))
            body.CreateAngularVelocityAttr(Gf.Vec3f(0.0))
            UsdPhysics.MassAPI.Apply(root_prim).CreateMassAttr(20.0)
            physx = PhysxSchema.PhysxRigidBodyAPI.Apply(root_prim)
            physx.CreateLinearDampingAttr(0.05)
            physx.CreateAngularDampingAttr(0.20)
            collider = UsdGeom.Cylinder.Define(stage, f"/World/Logs/{log_id}/Collider")
            collider.CreateAxisAttr(UsdGeom.Tokens.x)
            collider.CreateRadiusAttr(0.22)
            collider.CreateHeightAttr(0.92)
            collider.CreateVisibilityAttr(UsdGeom.Tokens.invisible)
            UsdPhysics.CollisionAPI.Apply(collider.GetPrim())
    return log_ids


def _base_stage(path, *, lights=True):
    path.unlink(missing_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    import campfire.app
    campfire.app.populate_fixed_scene(stage)
    stage.RemovePrim("/World/Logs")
    stage.RemovePrim("/World/IgnitionSource")
    UsdGeom.Xform.Define(stage, "/World/Logs")
    UsdGeom.Scope.Define(stage, "/World/Looks")
    if not lights:
        stage.RemovePrim("/World/Lights")
    _camera(stage)
    stage.SetEndTimeCode(1000000.0)
    return stage


def _flow_stage(path, condition, asset_dir):
    path.unlink(missing_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    import campfire.app
    from campfire.app.flow_scene import populate_flow_scene
    populate_flow_scene(stage)
    stage.RemovePrim("/World/Logs")
    UsdGeom.Xform.Define(stage, "/World/Logs")
    # Match the unbound control material authored by the non-Flow V3 stage so
    # the Flow-Prim comparison changes only the prebuilt Flow subtree.
    _solid_material(stage)
    log_ids = _v3_meshes(stage, rigid=True)
    campfire.app.preauthor_wood_visual_v3(stage, log_ids)
    emitter = stage.GetPrimAtPath("/World/Flow/Emitter")
    if condition in {"flow_prims_disabled", "flow_prims_global_off_active"}:
        emitter.GetAttribute("enabled").Set(False)
    if condition == "flow_prims_disabled":
        for prim_path in ("/World/Flow/Simulate", "/World/Flow/flowOffscreen", "/World/Flow/flowRender"):
            stage.GetPrimAtPath(prim_path).SetActive(False)
        custom_data = dict(stage.GetRootLayer().customLayerData)
        render_settings = dict(custom_data.get("renderSettings", {}))
        for key in list(render_settings):
            if str(key).startswith("rtx:flow:"):
                render_settings[key] = False
        custom_data["renderSettings"] = render_settings
        stage.GetRootLayer().customLayerData = custom_data
    elif condition == "flow_simulation_only":
        stage.RemovePrim("/World/Flow/flowRender")
        stage.RemovePrim("/World/Flow/flowOffscreen")
    _camera(stage)
    stage.SetEndTimeCode(1000000.0)
    return stage


def _build_stage(path, condition, asset_dir):
    if condition == "empty_rtx":
        stage = Usd.Stage.CreateNew(str(path))
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        UsdGeom.Xform.Define(stage, "/World")
        _camera(stage)
        return stage
    if condition in {"flow_prims_disabled", "flow_prims_global_off_active", "flow_simulation_only", "flow_volume"}:
        return _flow_stage(path, condition, asset_dir)
    stage = _base_stage(path, lights=condition != "ground_stones_no_lights")
    if condition in {"ground_stones_no_lights", "ground_stones_lit", "ground_stones_shadows_off"}:
        return stage
    solid = _solid_material(stage)
    if condition == "cylinder1_solid":
        _simple_cylinders(stage, 1, solid)
    elif condition == "cylinder20_solid":
        _simple_cylinders(stage, 20, solid)
    elif condition == "v3mesh20_solid":
        _v3_meshes(stage, material=solid)
    elif condition == "v3mesh20_static_texture":
        _v3_meshes(stage, material=_static_texture_material(stage, asset_dir))
    elif condition in {"v3mesh20_dynamic_unprovided", "v3mesh20_dynamic_rigid_stopped", "v3mesh20_dynamic_rigid_play"}:
        import campfire.app
        log_ids = _v3_meshes(stage, rigid=condition.startswith("v3mesh20_dynamic_rigid"))
        campfire.app.preauthor_wood_visual_v3(stage, log_ids)
    else:
        raise ValueError(f"unknown condition: {condition}")
    return stage


def _stage_inventory(stage):
    prims = list(stage.Traverse())
    triangles = 0
    mesh_count = 0
    texture_count = 0
    dynamic_uris = []
    material_count = 0
    rigid_count = 0
    light_count = 0
    flow_count = 0
    for prim in prims:
        if prim.IsA(UsdGeom.Mesh):
            mesh_count += 1
            counts = UsdGeom.Mesh(prim).GetFaceVertexCountsAttr().Get() or []
            triangles += sum(max(0, int(count) - 2) for count in counts)
        if prim.IsA(UsdShade.Material):
            material_count += 1
        if prim.IsA(UsdShade.Shader):
            shader = UsdShade.Shader(prim)
            if shader.GetIdAttr().Get() == "UsdUVTexture":
                texture_count += 1
                value = shader.GetInput("file").Get()
                uri = str(value.path) if value else ""
                if uri.startswith("dynamic://"):
                    dynamic_uris.append(uri)
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            rigid_count += 1
        if prim.HasAPI(UsdLux.LightAPI):
            light_count += 1
        if prim.GetTypeName().startswith("Flow"):
            flow_count += 1
    paths = [str(prim.GetPath()) for prim in prims]
    return {
        "prim_count": len(prims), "mesh_count": mesh_count,
        "authored_mesh_triangle_count": triangles,
        "implicit_cylinder_count": sum(prim.IsA(UsdGeom.Cylinder) for prim in prims),
        "implicit_cylinder_triangle_count": None,
        "material_count": material_count, "texture_count": texture_count,
        "dynamic_uri_count": len(dynamic_uris), "dynamic_uris": dynamic_uris,
        "rigid_body_count": rigid_count, "light_count": light_count,
        "flow_prim_count": flow_count,
        "prim_paths_sha256": hashlib.sha256("\n".join(paths).encode()).hexdigest(),
    }


def _frame_snapshot(viewport):
    info = viewport.frame_info
    return {
        "fps": float(info.get("fps", 0.0)), "frame_number": int(info.get("frame_number", -1)),
        "swh_frame_number": int(info.get("swh_frame_number", -1)),
        "resolution": list(info.get("resolution", ())), "status": int(info.get("status", -1)),
    }


async def _period(app, timeline, viewport, duration, record):
    initial = _frame_snapshot(viewport)
    started_wall_ns = time.time_ns()
    started = time.perf_counter_ns()
    deadline = started + int(duration * 1e9)
    hud = []
    updates = 0
    while time.perf_counter_ns() < deadline:
        await app.next_update_async()
        updates += 1
        if record and len(hud) < MAX_READS:
            hud.append(float(viewport.frame_info.get("fps", 0.0)))
    ended = time.perf_counter_ns()
    return {
        "started_wall_ns": started_wall_ns, "ended_wall_ns": time.time_ns(),
        "wall_seconds": (ended - started) / 1e9, "kit_update_count": updates,
        "hud_fps_values": hud, "initial_frame_info": initial,
        "final_frame_info": _frame_snapshot(viewport),
        "timeline_seconds_end": float(timeline.get_current_time()),
    }


def _apply_effective_settings(condition, aa_mode):
    settings = carb.settings.get_settings()
    # A stopped, unchanged stage otherwise enters RTX Eco Mode and intentionally
    # stops producing visible viewport frames.  Keep continuous rendering enabled
    # only inside this isolated measurement process; no production setting is
    # authored or persisted.
    settings.set_bool("/rtx/ecoMode/enabled", False)
    flow_enabled = condition in {"flow_simulation_only", "flow_volume"}
    settings.set_bool("/rtx/flow/enabled", flow_enabled)
    if condition == "ground_stones_shadows_off":
        settings.set_bool("/rtx/shadows/enabled", False)
    if AA_MODES[aa_mode] is not None:
        settings.set_int("/rtx/post/aa/op", 3)
        settings.set_int("/rtx/post/dlss/execMode", AA_MODES[aa_mode])
    return flow_enabled


async def _run(arguments):
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    report = {"schema": "campfire.phasev3tk.visible-viewport-process.v1", "status": "error"}
    try:
        allowed = {
            "empty_rtx", "ground_stones_no_lights", "ground_stones_lit", "ground_stones_shadows_off",
            "cylinder1_solid", "cylinder20_solid", "v3mesh20_solid", "v3mesh20_static_texture",
            "v3mesh20_dynamic_unprovided", "v3mesh20_dynamic_rigid_stopped", "v3mesh20_dynamic_rigid_play",
            "flow_prims_disabled", "flow_prims_global_off_active", "flow_simulation_only", "flow_volume",
        }
        condition = arguments["condition"]
        aa_mode = arguments["aa_mode"]
        if condition not in allowed or aa_mode not in AA_MODES:
            raise ValueError(f"invalid condition/AA mode: {condition}/{aa_mode}")
        stage_path = arguments["output"].with_suffix(".usda")
        asset_dir = arguments["output"].parent / (arguments["output"].stem + "_assets")
        asset_dir.mkdir(parents=True, exist_ok=True)
        stage = _build_stage(stage_path, condition, asset_dir)
        inventory = _stage_inventory(stage)
        stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))
        stage.SetTimeCodesPerSecond(60.0)
        if not stage.GetRootLayer().Save():
            raise RuntimeError("unable to save Phase V3T-K stage")
        flow_enabled = _apply_effective_settings(condition, aa_mode)
        await context.open_stage_async(str(stage_path))
        viewport = None
        for _ in range(360):
            viewport = omni.kit.viewport.utility.get_active_viewport()
            if viewport is not None:
                break
            await app.next_update_async()
        if viewport is None:
            raise RuntimeError("active visible viewport unavailable")
        viewport.camera_path = "/World/Camera"
        viewport.fill_frame = False
        viewport.resolution = RESOLUTION
        _apply_effective_settings(condition, aa_mode)
        timeline.set_current_time(0.0)
        play = condition in {"v3mesh20_dynamic_rigid_play", "flow_prims_disabled", "flow_prims_global_off_active", "flow_simulation_only", "flow_volume"}
        if play:
            timeline.play()
        else:
            timeline.stop()
        readiness_started = time.perf_counter()
        readiness_updates = 0
        readiness_deadline = readiness_started + 150.0
        while time.perf_counter() < readiness_deadline:
            await app.next_update_async()
            readiness_updates += 1
            if _frame_snapshot(viewport)["frame_number"] >= 0:
                break
        readiness = {
            "wall_seconds": time.perf_counter() - readiness_started,
            "kit_update_count": readiness_updates,
            "frame_info": _frame_snapshot(viewport),
        }
        if readiness["frame_info"]["frame_number"] < 0:
            raise RuntimeError("visible viewport did not produce an initial frame within 150 seconds")
        warmup = await _period(app, timeline, viewport, arguments["warmup_seconds"], False)
        # Some Flow startup work completes during the warmup and may reapply its
        # default RTX setting.  Reassert the requested isolated condition at the
        # measurement boundary, then validate the public effective value.
        _apply_effective_settings(condition, aa_mode)
        await app.next_update_async()
        await app.next_update_async()
        settings_before = _settings_snapshot(viewport)
        expected_exec = AA_MODES[aa_mode]
        if expected_exec is not None:
            actual_aa = settings_before["requested_paths"]["/rtx/post/aa/op"]
            actual_exec = settings_before["requested_paths"]["/rtx/post/dlss/execMode"]
            if actual_aa != 3 or actual_exec != expected_exec:
                raise RuntimeError(f"AA effective-value mismatch: requested={aa_mode} actual={actual_aa}/{actual_exec}")
        if settings_before["requested_paths"]["/rtx/flow/enabled"] is not flow_enabled:
            raise RuntimeError("Flow effective-value mismatch before measurement")
        if settings_before["requested_paths"]["/rtx/ecoMode/enabled"] is not False:
            raise RuntimeError("measurement-only RTX Eco Mode override was not effective")
        timeline_start = float(timeline.get_current_time())
        measured = await _period(app, timeline, viewport, arguments["measure_seconds"], True)
        measured["timeline_seconds_start"] = timeline_start
        settings_after = _settings_snapshot(viewport)
        if settings_before["requested_paths"] != settings_after["requested_paths"]:
            raise RuntimeError("audited RTX setting changed during measurement")
        import omni.flowusd._flowusd as _flowusd
        flow_interface = _flowusd.acquire_flowusd_interface()
        inventory["flow_active_blocks_final"] = int(flow_interface.get_active_block_count())
        report = {
            "schema": "campfire.phasev3tk.visible-viewport-process.v1", "status": "ok",
            "condition": condition, "aa_mode": aa_mode, "run": arguments["run"] + 1,
            "kit": "110.2", "flow": "110.0.0", "resolution": list(RESOLUTION),
            "timeline_playing_during_measurement": play,
            "metric_contract": {
                "average_visible_fps": "ViewportAPI.frame_info frame_number delta / measurement wall time",
                "hud_fps": "public smoothed ViewportAPI.frame_info fps",
                "display_present_fps_measured": False, "raw_frame_p95_p99_measured": False,
                "one_percent_low_measured": False, "additional_render_product_created": False,
                "hydra_texture_created": False, "capture_or_encode_used": False,
                "prim_or_material_changed_during_measurement": False,
            },
            "settings_before": settings_before, "settings_after": settings_after,
            "renderer_readiness": readiness,
            "warmup": {"wall_seconds": warmup["wall_seconds"]}, "measurement": measured,
            "stage": inventory, "production_changed": False,
            "measurement_only_overrides": {"/rtx/ecoMode/enabled": False},
        }
    except Exception as error:
        report = {"schema": "campfire.phasev3tk.visible-viewport-process.v1", "status": "error", "condition": arguments.get("condition"), "aa_mode": arguments.get("aa_mode"), "error": f"{type(error).__name__}: {error}"}
    finally:
        timeline.stop()
        arguments["output"].parent.mkdir(parents=True, exist_ok=True)
        arguments["output"].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        app.post_uncancellable_quit(0 if report["status"] == "ok" else 1)


asyncio.ensure_future(_run(_arguments()))
