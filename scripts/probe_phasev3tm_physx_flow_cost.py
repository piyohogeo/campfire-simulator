"""Phase V3T-M production-neutral PhysX/Flow fixed-cost decomposition.

The stage is fully authored before it is connected.  The measurement reads only
the existing visible viewport and never creates a RenderProduct or HydraTexture.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

import carb
import omni.kit.app
import omni.kit.viewport.utility
import omni.timeline
import omni.usd
from omni.physx import get_physx_simulation_interface
from pxr import Gf, PhysxSchema, Sdf, Tf, Usd, UsdGeom, UsdPhysics


sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_phasev3tk_rtx_stage_cost as phase_k  # noqa: E402


RESOLUTION = (1280, 720)
PHYSX_CONDITIONS = {
    "physx_none_stop",
    "physx_none_play",
    "physx_scene_only",
    "physx_kinematic20",
    "physx_dynamic20_sleep",
    "physx_dynamic20_move_no_collision",
    "physx_dynamic20_collision",
    "physx_collapse20",
}
FLOW_CONDITIONS = {
    "flow_no_prims",
    "flow_empty_xform",
    "flow_all_inactive",
    "flow_simulate_only_no_emitter",
    "flow_offscreen_only",
    "flow_render_only",
    "flow_shadow_raymarch_only",
    "flow_relationship_none",
    "flow_relationship_incremental_unavailable",
    "flow_layer_enabled_only",
    "flow_layer_pathtracing_only",
    "flow_layer_reflections_only",
    "flow_layer_translucency_only",
    "flow_global_off_active",
    "flow_global_on_emitter_off",
    "flow_simulation_active_blocks",
    "flow_volume",
}


def _arguments():
    settings = carb.settings.get_settings()
    return {
        "output": Path(settings.get_as_string("/phasev3tm/output")).resolve(),
        "condition": settings.get_as_string("/phasev3tm/condition"),
        "warmup_seconds": settings.get_as_float("/phasev3tm/warmupSeconds"),
        "measure_seconds": settings.get_as_float("/phasev3tm/measureSeconds"),
        "run": settings.get_as_int("/phasev3tm/run"),
        "settled_transforms": settings.get_as_string("/phasev3tm/settledTransformsPath"),
        "preset": settings.get_as_string("/phasev3tm/preset"),
        "lifecycle_marker": Path(settings.get_as_string("/phasev3tm/lifecycleMarker")).resolve(),
    }


def _marker(path, event, **details):
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"event": event, "wall_time_ns": time.time_ns(), **details}
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def _remove_physics(stage):
    remove = []
    for prim in stage.Traverse():
        if prim.IsA(UsdPhysics.Scene):
            remove.append(str(prim.GetPath()))
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            prim.RemoveAPI(UsdPhysics.RigidBodyAPI)
        if prim.HasAPI(UsdPhysics.CollisionAPI):
            prim.RemoveAPI(UsdPhysics.CollisionAPI)
    for path in sorted(remove, key=len, reverse=True):
        stage.RemovePrim(path)


def _physics_scene(stage, gravity=True):
    scene = UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
    scene.CreateGravityDirectionAttr(Gf.Vec3f(0.0, 0.0, -1.0))
    scene.CreateGravityMagnitudeAttr(9.81 if gravity else 0.0)
    return scene


def _matrix_values(matrix):
    return [float(matrix[row][column]) for row in range(4) for column in range(4)]


def _matrix_from_values(values):
    matrix = Gf.Matrix4d(1.0)
    for row in range(4):
        for column in range(4):
            matrix[row][column] = float(values[row * 4 + column])
    return matrix


def _log_paths(stage):
    root = stage.GetPrimAtPath("/World/Logs")
    return [str(child.GetPath()) for child in root.GetChildren()] if root else []


def _transforms(stage):
    values = {}
    for path in _log_paths(stage):
        prim = stage.GetPrimAtPath(path)
        values[path] = _matrix_values(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
    return values


def _apply_transforms(stage, source_path):
    if not source_path:
        return False
    source = Path(source_path)
    if not source.is_file():
        raise RuntimeError(f"settled transform source unavailable: {source}")
    payload = json.loads(source.read_text(encoding="utf-8-sig"))
    for path, values in payload["transforms"].items():
        prim = stage.GetPrimAtPath(path)
        if prim:
            xform = UsdGeom.Xformable(prim)
            xform.ClearXformOpOrder()
            xform.MakeMatrixXform().Set(_matrix_from_values(values))
    return True


def _collapse_initial(stage):
    for index, path in enumerate(_log_paths(stage)):
        prim = stage.GetPrimAtPath(path)
        xform = UsdGeom.Xformable(prim)
        matrix = xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        translation = matrix.ExtractTranslation()
        translation[2] += 0.45 + 0.18 * (index % 5)
        rotation = Gf.Rotation(Gf.Vec3d(0, 0, 1), 18.0 * (index % 4))
        new_matrix = Gf.Matrix4d(rotation, translation)
        xform.ClearXformOpOrder()
        xform.MakeMatrixXform().Set(new_matrix)


def _pair_collision_layout(stage):
    positions = list(phase_k._positions())
    for index, path in enumerate(_log_paths(stage)):
        _slot, position, rotation = positions[index]
        xform = UsdGeom.Xformable(stage.GetPrimAtPath(path))
        xform.ClearXformOpOrder()
        xform.AddTranslateOp().Set(Gf.Vec3d(*position))
        xform.AddRotateZOp().Set(rotation)


def _apply_body(stage, path, *, kinematic, collision, moving, report_contacts):
    prim = stage.GetPrimAtPath(path)
    body = UsdPhysics.RigidBodyAPI.Apply(prim)
    body.CreateRigidBodyEnabledAttr(True)
    body.CreateKinematicEnabledAttr(kinematic)
    velocity = Gf.Vec3f((1.0 if int(path[-2:]) % 2 == 0 else -1.0) if moving else 0.0, 0.0, 0.0)
    body.CreateVelocityAttr(velocity)
    body.CreateAngularVelocityAttr(Gf.Vec3f(0.0))
    UsdPhysics.MassAPI.Apply(prim).CreateMassAttr(20.0)
    physx = PhysxSchema.PhysxRigidBodyAPI.Apply(prim)
    physx.CreateLinearDampingAttr(0.05)
    physx.CreateAngularDampingAttr(0.20)
    if not moving and not kinematic:
        create_sleep_threshold = getattr(physx, "CreateSleepThresholdAttr", None)
        if create_sleep_threshold is not None:
            create_sleep_threshold(1000.0)
    if collision:
        collider = UsdGeom.Cylinder.Define(stage, path + "/Collider")
        collider.CreateAxisAttr(UsdGeom.Tokens.x)
        collider.CreateRadiusAttr(0.22)
        collider.CreateHeightAttr(0.92)
        collider.CreateVisibilityAttr(UsdGeom.Tokens.invisible)
        UsdPhysics.CollisionAPI.Apply(collider.GetPrim())
        if report_contacts:
            PhysxSchema.PhysxContactReportAPI.Apply(prim).CreateThresholdAttr(0.0)


def _build_physx_stage(path, asset_dir, condition, settled_path):
    stage = phase_k._base_stage(path, lights=True)
    _remove_physics(stage)
    material = phase_k._static_texture_material(stage, asset_dir)
    phase_k._v3_meshes(stage, material=material, rigid=False)
    settled_applied = _apply_transforms(stage, settled_path)
    if condition == "settle_capture":
        _collapse_initial(stage)
        _physics_scene(stage, gravity=True)
        for log_path in _log_paths(stage):
            _apply_body(stage, log_path, kinematic=False, collision=True, moving=False, report_contacts=False)
    elif condition == "physx_none_stop" or condition == "physx_none_play":
        pass
    elif condition == "physx_scene_only":
        _physics_scene(stage, gravity=False)
    elif condition == "physx_kinematic20":
        _physics_scene(stage, gravity=False)
        for log_path in _log_paths(stage):
            _apply_body(stage, log_path, kinematic=True, collision=False, moving=False, report_contacts=False)
    elif condition == "physx_dynamic20_sleep":
        _physics_scene(stage, gravity=False)
        for log_path in _log_paths(stage):
            _apply_body(stage, log_path, kinematic=False, collision=False, moving=False, report_contacts=False)
    elif condition == "physx_dynamic20_move_no_collision":
        _pair_collision_layout(stage)
        _physics_scene(stage, gravity=False)
        for log_path in _log_paths(stage):
            _apply_body(stage, log_path, kinematic=False, collision=False, moving=True, report_contacts=False)
    elif condition == "physx_dynamic20_collision":
        _pair_collision_layout(stage)
        _physics_scene(stage, gravity=False)
        for log_path in _log_paths(stage):
            _apply_body(stage, log_path, kinematic=False, collision=True, moving=True, report_contacts=True)
    elif condition == "physx_collapse20":
        _collapse_initial(stage)
        _physics_scene(stage, gravity=True)
        for log_path in _log_paths(stage):
            _apply_body(stage, log_path, kinematic=False, collision=True, moving=False, report_contacts=True)
    else:
        raise ValueError(f"unknown PhysX condition: {condition}")
    return stage, settled_applied


def _set_flow_layer(stage, enabled_keys):
    keys = (
        "rtx:flow:enabled",
        "rtx:flow:pathTracingEnabled",
        "rtx:flow:rayTracedReflectionsEnabled",
        "rtx:flow:rayTracedTranslucencyEnabled",
    )
    custom = dict(stage.GetRootLayer().customLayerData)
    render = dict(custom.get("renderSettings", {}))
    for key in keys:
        render[key] = key in enabled_keys
    custom["renderSettings"] = render
    stage.GetRootLayer().customLayerData = custom


def _set_active(stage, path, value):
    prim = stage.GetPrimAtPath(path)
    if prim:
        prim.SetActive(value)


def _flow_relationships(stage):
    rows = []
    for prim in stage.Traverse():
        for relationship in prim.GetRelationships():
            rows.append({"path": str(relationship.GetPath()), "targets": [str(value) for value in relationship.GetTargets()]})
    return rows


def _build_flow_stage(path, asset_dir, condition, settled_path):
    if condition in {"flow_no_prims", "flow_empty_xform"}:
        stage = phase_k._base_stage(path, lights=True)
        _remove_physics(stage)
        phase_k._v3_meshes(stage, material=phase_k._static_texture_material(stage, asset_dir), rigid=False)
        _apply_transforms(stage, settled_path)
        if condition == "flow_empty_xform":
            UsdGeom.Xform.Define(stage, "/World/Flow")
        return stage
    stage = phase_k._flow_stage(path, "flow_volume", asset_dir)
    material = phase_k._static_texture_material(stage, asset_dir)
    for log_path in _log_paths(stage):
        render_surface = stage.GetPrimAtPath(log_path + "/RenderSurface")
        if render_surface:
            phase_k._bind(render_surface, material)
    stage.RemovePrim("/World/Looks/WoodVisualV3")
    _remove_physics(stage)
    _apply_transforms(stage, settled_path)
    emitter = stage.GetPrimAtPath("/World/Flow/Emitter")
    if emitter:
        emitter.GetAttribute("enabled").Set(False)
    simulate, offscreen, render = "/World/Flow/Simulate", "/World/Flow/flowOffscreen", "/World/Flow/flowRender"
    for prim_path in (simulate, offscreen, render):
        _set_active(stage, prim_path, False)
    _set_flow_layer(stage, set())
    if condition == "flow_all_inactive":
        pass
    elif condition == "flow_simulate_only_no_emitter":
        _set_active(stage, simulate, True)
        _set_flow_layer(stage, {"rtx:flow:enabled"})
    elif condition == "flow_offscreen_only":
        _set_active(stage, offscreen, True)
        _set_flow_layer(stage, {"rtx:flow:enabled"})
    elif condition == "flow_render_only":
        _set_active(stage, render, True)
        _set_flow_layer(stage, {"rtx:flow:enabled"})
    elif condition == "flow_shadow_raymarch_only":
        _set_active(stage, offscreen, True)
        _set_active(stage, render, True)
        _set_flow_layer(stage, {"rtx:flow:enabled"})
    elif condition in {"flow_relationship_none", "flow_relationship_incremental_unavailable"}:
        pass
    elif condition == "flow_layer_enabled_only":
        _set_flow_layer(stage, {"rtx:flow:enabled"})
    elif condition == "flow_layer_pathtracing_only":
        _set_flow_layer(stage, {"rtx:flow:pathTracingEnabled"})
    elif condition == "flow_layer_reflections_only":
        _set_flow_layer(stage, {"rtx:flow:rayTracedReflectionsEnabled"})
    elif condition == "flow_layer_translucency_only":
        _set_flow_layer(stage, {"rtx:flow:rayTracedTranslucencyEnabled"})
    elif condition == "flow_global_off_active":
        for prim_path in (simulate, offscreen, render):
            _set_active(stage, prim_path, True)
        _set_flow_layer(stage, set())
    elif condition == "flow_global_on_emitter_off":
        for prim_path in (simulate, offscreen, render):
            _set_active(stage, prim_path, True)
        _set_flow_layer(stage, {
            "rtx:flow:enabled", "rtx:flow:pathTracingEnabled",
            "rtx:flow:rayTracedReflectionsEnabled", "rtx:flow:rayTracedTranslucencyEnabled",
        })
    elif condition == "flow_simulation_active_blocks":
        _set_active(stage, simulate, True)
        _set_flow_layer(stage, {"rtx:flow:enabled"})
        emitter.GetAttribute("enabled").Set(True)
    elif condition == "flow_volume":
        for prim_path in (simulate, offscreen, render):
            _set_active(stage, prim_path, True)
        _set_flow_layer(stage, {
            "rtx:flow:enabled", "rtx:flow:pathTracingEnabled",
            "rtx:flow:rayTracedReflectionsEnabled", "rtx:flow:rayTracedTranslucencyEnabled",
        })
        emitter.GetAttribute("enabled").Set(True)
    else:
        raise ValueError(f"unknown Flow condition: {condition}")
    return stage


def _flow_global_enabled(condition):
    return condition in {
        "flow_simulate_only_no_emitter", "flow_offscreen_only", "flow_render_only",
        "flow_shadow_raymarch_only", "flow_layer_enabled_only", "flow_global_on_emitter_off",
        "flow_simulation_active_blocks", "flow_volume",
    }


def _timeline_play(condition):
    return condition != "physx_none_stop"


def _stage_inventory(stage, condition):
    inventory = phase_k._stage_inventory(stage)
    flow_prims = [prim for prim in stage.Traverse() if prim.GetTypeName().startswith("Flow")]
    relationships = _flow_relationships(stage)
    root_data = dict(stage.GetRootLayer().customLayerData)
    render_settings = dict(root_data.get("renderSettings", {}))
    emitter = stage.GetPrimAtPath("/World/Flow/Emitter")
    inventory.update({
        "condition": condition,
        "flow_active_prim_paths": [str(prim.GetPath()) for prim in flow_prims if prim.IsActive()],
        "flow_inactive_prim_paths": [str(prim.GetPath()) for prim in flow_prims if not prim.IsActive()],
        "flow_relationship_count": len(relationships),
        "flow_relationships": relationships,
        "root_layer_flow_settings": {key: value for key, value in render_settings.items() if str(key).startswith("rtx:flow:")},
        "emitter_enabled": bool(emitter.GetAttribute("enabled").Get()) if emitter else None,
        "canonical_relationship_incremental_status": (
            "not_applicable: the fixed Flow 110.0.0 Sphere scene authors zero relationships"
            if condition == "flow_relationship_incremental_unavailable" else None
        ),
    })
    return inventory


def _frame(viewport):
    info = viewport.frame_info
    return {"fps": float(info.get("fps", 0.0)), "frame_number": int(info.get("frame_number", -1)), "resolution": list(info.get("resolution", ())) }


async def _ready(app, viewport):
    deadline = time.perf_counter() + 240.0
    previous = -1
    consecutive = 0
    updates = 0
    started = time.perf_counter()
    while time.perf_counter() < deadline:
        await app.next_update_async()
        updates += 1
        current = _frame(viewport)["frame_number"]
        if current > previous and previous >= 0:
            consecutive += 1
        elif current != previous:
            consecutive = 0
        previous = current
        if consecutive >= 8:
            return {"wall_seconds": time.perf_counter() - started, "kit_updates": updates, "consecutive_increments": consecutive, "frame": _frame(viewport)}
    raise RuntimeError("visible viewport failed the eight-consecutive-frame readiness gate")


async def _period(app, timeline, viewport, duration, flow_interface, notice_state, record):
    initial = _frame(viewport)
    initial_time = float(timeline.get_current_time())
    started_wall_ns = time.time_ns()
    started = time.perf_counter_ns()
    deadline = started + int(duration * 1e9)
    hud = []
    active_blocks = []
    updates = 0
    while time.perf_counter_ns() < deadline:
        await app.next_update_async()
        updates += 1
        if record:
            hud.append(float(viewport.frame_info.get("fps", 0.0)))
            active_blocks.append(int(flow_interface.get_active_block_count()))
    ended = time.perf_counter_ns()
    return {
        "started_wall_ns": started_wall_ns,
        "ended_wall_ns": time.time_ns(),
        "wall_seconds": (ended - started) / 1e9,
        "kit_update_count": updates,
        "hud_fps_values": hud,
        "initial_frame_info": initial,
        "final_frame_info": _frame(viewport),
        "timeline_seconds_start": initial_time,
        "timeline_seconds_end": float(timeline.get_current_time()),
        "active_block_samples": active_blocks,
        "usd_notice_count": notice_state["notices"],
        "usd_notice_changed_path_count": notice_state["changed_paths"],
    }


async def _run(arguments):
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    settings = carb.settings.get_settings()
    report = {"schema": "campfire.phasev3tm.visible-viewport-process.v1", "status": "error"}
    contact_subscription = None
    notice_subscription = None
    try:
        condition = arguments["condition"]
        preset = arguments["preset"]
        if preset not in {"Performance", "AutoBaseline"}:
            raise ValueError(f"invalid Phase V3T-M preset: {preset}")
        expected_dlss = 0 if preset == "Performance" else 3
        expected_bounces = 2 if preset == "Performance" else 4
        _marker(arguments["lifecycle_marker"], "probe_started", condition=condition, preset=preset)
        allowed = PHYSX_CONDITIONS | FLOW_CONDITIONS | {"settle_capture"}
        if condition not in allowed:
            raise ValueError(f"invalid Phase V3T-M condition: {condition}")
        stage_path = arguments["output"].with_suffix(".usda")
        asset_dir = arguments["output"].parent / (arguments["output"].stem + "_assets")
        asset_dir.mkdir(parents=True, exist_ok=True)
        if condition in PHYSX_CONDITIONS or condition == "settle_capture":
            stage, settled_applied = _build_physx_stage(stage_path, asset_dir, condition, arguments["settled_transforms"])
        else:
            stage = _build_flow_stage(stage_path, asset_dir, condition, arguments["settled_transforms"])
            settled_applied = bool(arguments["settled_transforms"])
        phase_k._camera(stage)
        stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))
        stage.SetTimeCodesPerSecond(60.0)
        stage.SetEndTimeCode(1000000.0)
        inventory = _stage_inventory(stage, condition)
        inventory["prim_paths_sha256"] = hashlib.sha256("\n".join(str(prim.GetPath()) for prim in stage.Traverse()).encode()).hexdigest()
        if not stage.GetRootLayer().Save():
            raise RuntimeError("unable to save Phase V3T-M stage")
        _marker(arguments["lifecycle_marker"], "stage_authored_before_connection", stage=str(stage_path))

        flow_global = _flow_global_enabled(condition)
        _marker(arguments["lifecycle_marker"], "stage_connection_begin")
        await context.open_stage_async(str(stage_path))
        _marker(arguments["lifecycle_marker"], "stage_connection_complete")
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
        current_stage = context.get_stage()
        notice_state = {"notices": 0, "changed_paths": 0}

        def on_objects_changed(notice, _sender):
            notice_state["notices"] += 1
            notice_state["changed_paths"] += len(notice.GetChangedInfoOnlyPaths()) + len(notice.GetResyncedPaths())

        notice_subscription = Tf.Notice.Register(Usd.Notice.ObjectsChanged, on_objects_changed, current_stage)
        contact_state = {"events": 0, "points": 0}

        def on_contacts(headers, _data):
            contact_state["events"] += len(headers)
            contact_state["points"] += sum(int(header.num_contact_data) for header in headers)

        contact_subscription = get_physx_simulation_interface().subscribe_contact_report_events(on_contacts)
        timeline.set_current_time(0.0)
        if _timeline_play(condition) or condition == "settle_capture":
            timeline.play()
        else:
            timeline.stop()
        readiness = await _ready(app, viewport)
        import omni.flowusd._flowusd as _flowusd
        flow_interface = _flowusd.acquire_flowusd_interface()
        warmup = await _period(app, timeline, viewport, arguments["warmup_seconds"], flow_interface, notice_state, False)
        if condition == "settle_capture":
            timeline.stop()
            await app.next_update_async()
        audited = {
            "/rtx/rendermode": settings.get("/rtx/rendermode"),
            "/rtx/flow/enabled": settings.get("/rtx/flow/enabled"),
            "/rtx/post/aa/op": settings.get("/rtx/post/aa/op"),
            "/rtx/post/dlss/execMode": settings.get("/rtx/post/dlss/execMode"),
            "/rtx/rtpt/maxBounces": settings.get("/rtx/rtpt/maxBounces"),
            "/rtx/ambientOcclusion/enabled": settings.get("/rtx/ambientOcclusion/enabled"),
            "/app/vsync": settings.get("/app/vsync"),
            "/app/runLoops/main/rateLimitFrequency": settings.get("/app/runLoops/main/rateLimitFrequency"),
            "/app/runLoops/rendering_0/rateLimitFrequency": settings.get("/app/runLoops/rendering_0/rateLimitFrequency"),
            "/app/runLoops/present/rateLimitFrequency": settings.get("/app/runLoops/present/rateLimitFrequency"),
            "/app/uploadDumpsOnStartup": settings.get("/app/uploadDumpsOnStartup"),
            "/crashreporter/preserveDump": settings.get("/crashreporter/preserveDump"),
            "/crashreporter/skipOldDumpUpload": settings.get("/crashreporter/skipOldDumpUpload"),
            "/crashreporter/devOnlyOverridePrivacyAndForceUpload": settings.get("/crashreporter/devOnlyOverridePrivacyAndForceUpload"),
            "/crashreporter/url": settings.get("/crashreporter/url"),
            "/physics/updateToUsd": settings.get("/physics/updateToUsd"),
            "/physics/fabricEnabled": settings.get("/physics/fabricEnabled"),
        }
        expected = {
            "/rtx/rendermode": "RealTimePathTracing",
            "/rtx/flow/enabled": flow_global,
            "/rtx/post/aa/op": 3,
            "/rtx/post/dlss/execMode": expected_dlss,
            "/rtx/rtpt/maxBounces": expected_bounces,
        }
        if condition in PHYSX_CONDITIONS or condition == "settle_capture":
            expected.update({"/physics/updateToUsd": True, "/physics/fabricEnabled": False})
        mismatches = {key: {"expected": value, "actual": audited[key]} for key, value in expected.items() if audited[key] != value}
        crash_expected = {
            "/app/uploadDumpsOnStartup": False,
            "/crashreporter/preserveDump": True,
            "/crashreporter/skipOldDumpUpload": True,
            "/crashreporter/devOnlyOverridePrivacyAndForceUpload": False,
            "/crashreporter/url": "",
        }
        mismatches.update({key: {"expected": value, "actual": audited[key]} for key, value in crash_expected.items() if audited[key] != value})
        if mismatches:
            raise RuntimeError(f"effective setting mismatch: {mismatches}")
        _marker(arguments["lifecycle_marker"], "measurement_begin")
        notice_state["notices"] = 0
        notice_state["changed_paths"] = 0
        contact_state["events"] = 0
        contact_state["points"] = 0
        start_transforms = _transforms(current_stage)
        measured = await _period(app, timeline, viewport, arguments["measure_seconds"], flow_interface, notice_state, True)
        end_transforms = _transforms(current_stage)
        _marker(arguments["lifecycle_marker"], "measurement_complete")
        changed = sum(
            1 for path, before in start_transforms.items()
            if path in end_transforms and any(abs(a - b) > 1.0e-6 for a, b in zip(before, end_transforms[path]))
        )
        blocks = measured["active_block_samples"]
        inventory.update({
            "flow_global_enabled": flow_global,
            "flow_active_blocks_final": blocks[-1] if blocks else 0,
            "flow_active_blocks_peak": max(blocks, default=0),
            "settled_reference_applied": settled_applied,
        })
        report = {
            "schema": "campfire.phasev3tm.visible-viewport-process.v1",
            "status": "ok",
            "condition": condition,
            "run": arguments["run"] + 1,
            "kit": "110.2",
            "flow": "110.0.0",
            "resolution": list(RESOLUTION),
            "preset": preset,
            "timeline_playing_during_measurement": bool(timeline.is_playing()),
            "metric_contract": {
                "visible_fps_source": "public ViewportAPI.frame_info frame delta / wall time",
                "frame_time_source": "1000 / average visible FPS",
                "display_present_fps_measured": False,
                "raw_frame_p95_p99_measured": False,
                "physx_simulation_time_measured": False,
                "hydra_sync_time_measured": False,
                "tlas_update_time_measured": False,
                "gpu_dispatch_presence_measured": False,
                "additional_render_product_created": False,
                "hydra_texture_created": False,
                "capture_or_encode_used": False,
                "topology_changed_during_measurement": False,
            },
            "effective_settings": audited,
            "renderer_readiness": readiness,
            "warmup": {"wall_seconds": warmup["wall_seconds"]},
            "measurement": measured,
            "stage": inventory,
            "physx_observation": {
                "rigid_body_count": inventory["rigid_body_count"],
                "changed_transform_count": changed,
                "contact_report_event_count": contact_state["events"],
                "contact_point_count": contact_state["points"],
                "sleeping_body_count_public_api": None,
                "sleeping_body_count_status": "unavailable from the inspected public Kit 110.2 Python interface; transform stability is reported separately",
                "active_body_count_public_api": None,
            },
            "settled_transforms": {
                "source": arguments["settled_transforms"] or None,
                "transforms": end_transforms if condition == "settle_capture" else None,
            },
            "production_changed": False,
            "power_limit_changed": False,
        }
    except Exception as error:
        report = {
            "schema": "campfire.phasev3tm.visible-viewport-process.v1",
            "status": "error",
            "condition": arguments.get("condition"),
            "error": f"{type(error).__name__}: {error}",
        }
    finally:
        _marker(arguments["lifecycle_marker"], "shutdown_begin", status=report["status"])
        timeline.stop()
        arguments["output"].parent.mkdir(parents=True, exist_ok=True)
        arguments["output"].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _marker(arguments["lifecycle_marker"], "quit_requested", status=report["status"])
        app.post_uncancellable_quit(0 if report["status"] == "ok" else 1)


asyncio.ensure_future(_run(_arguments()))
