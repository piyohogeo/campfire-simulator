"""Campfire Simulator application bootstrap and headless validation extension."""

import asyncio
import csv
import hashlib
import json
import math
import statistics
import struct
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.ext
import omni.kit.app
import omni.kit.viewport.utility
import omni.timeline
import omni.usd
from omni.flowusd import _flowusd
from omni.physx import get_physx_simulation_interface
from omni.physx.bindings._physx import SETTING_UPDATE_TO_USD
from pxr import Gf, Tf, Usd, UsdPhysics, UsdUtils

from .controls import CampfireControlWindow
from .flow_scene import (
    EMITTER_END,
    EMITTER_START,
    FLOW_EMITTER_PATH,
    FLOW_SIMULATE_PATH,
    FLOW_VERSION,
    PHASE1_CAPTURE_FRAMES,
    PHASE1_TOTAL_FRAMES,
    emitter_position_for_frame,
    export_flow_stage,
    populate_flow_scene,
)
from .scene import CAMERA_PATH, export_stage, populate_fixed_scene
from .phase2_scene import (
    PHASE2_ADDED_LOG_ID,
    PHASE2_ADD_FRAME,
    PHASE2_CAPTURE_FRAMES,
    PHASE2_EMITTER_OFFSET_M,
    PHASE2_FIXED_DT_SECONDS,
    PHASE2_SPAWN_POSITION_M,
    PHASE2_TOTAL_FRAMES,
    add_scenario_log,
    export_phase2_stage,
    populate_phase2_scene,
    set_emitter_follow,
)
from .phase3_scene import (
    PHASE3_CAPTURE_STEPS,
    PHASE3_DRY_LOG_ID,
    PHASE3_EXTERNAL_HEAT_FLUX_W_M2,
    PHASE3_FLOW_UPDATE_INTERVAL_STEPS,
    PHASE3_IGNITION_RATE_KG_S,
    PHASE3_MODEL_DT_SECONDS,
    PHASE3_TOTAL_STEPS,
    PHASE3_WET_LOG_ID,
    apply_model_visual_state,
    export_phase3_stage,
    populate_phase3_scene,
    update_flow_source,
)
from .combustion import (
    FlowSourceState,
    NUMPY_ARRAY_BACKEND,
    PYTHON_ARRAY_BACKEND,
    flow_source_from_model,
    load_model_from_prim,
    save_model_to_prim,
)
from .air_supply import run_stack_air_comparison
from .phase4_scene import export_phase4_stage, populate_phase4_scene
from .phase5_scene import (
    PHASE5_FIXED_DT_SECONDS,
    PHASE5_JOINT_PATH,
    PHASE5_POST_CAPTURE_FRAME,
    PHASE5_PRE_CAPTURE_FRAME,
    PHASE5_RELEASE_FRAME,
    PHASE5_SEGMENT_PATHS,
    export_phase5_stage,
    populate_phase5_scene,
    release_phase5_structure,
)
from .support import burn_to_support_failure, run_collapse_reignition_scenario
from .performance import summarize_timing_ms
from .resident_snapshot_adapter import (
    ResidentPublishedSnapshot,
    UsdResidentSnapshotAdapter,
    published_row_from_python_model,
)
from .resident_native_backend import ResidentNativeBackend
from .resident_point_application_owner import ResidentPointApplicationOwner
from .resident_point_scene import (
    RESIDENT_POINT_APPLICATION_SETTING,
    RESIDENT_POINT_EMITTER_PATH,
    configure_resident_point_application_scene,
    preauthor_resident_snapshot_consumers,
    resident_point_application_enabled,
    resident_point_layout_for_logs,
)
from .resident_point_sidecar import ResidentNativeSurfaceProducer
from .wood import get_log_world_position, list_log_ids
from .char_depth_experiment import (
    create_char_depth_dry_run_package,
    evaluate_char_depth_dry_run_package,
    evaluate_char_depth_lab_handoff,
)
from .calibration import (
    run_nist_plywood_calibration,
    write_calibration_svg,
    write_char_depth_benchmark_svg,
    write_char_depth_measurement_protocol_svg,
    write_char_depth_experiment_plan_svg,
    write_char_depth_dry_run_svg,
    write_char_depth_lab_handoff_svg,
    write_char_geometry_svg,
    write_gas_transport_readiness_svg,
    write_holdout_svg,
    write_layer_profile_svg,
    write_kinetics_svg,
    write_replicate_holdout_svg,
    write_tar_residence_sensitivity_svg,
)
from .phase6_scene import (
    apply_phase6_calibration,
    export_phase6_stage,
    populate_phase6_scene,
)


SETTINGS_ROOT = "/exts/campfire.app"
CAPTURE_RESOLUTION = (1280, 720)
PHASE3_DEBUG_EXTENSION_IDS = (
    "omni.kit.developer.bundle",
    "omni.kit.dev.utilities.bundle",
    "omni.kit.debug.vscode",
    "omni.kit.debug.python",
)


def _find_repo_root(extension_path: Path) -> Path:
    for candidate in (extension_path, *extension_path.parents):
        if (candidate / "DESIGN.md").is_file():
            return candidate
    raise RuntimeError(f"Could not locate repository root from {extension_path}")


def _read_png_resolution(image_path: Path) -> tuple[int, int]:
    with image_path.open("rb") as image_file:
        header = image_file.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError(f"Viewport capture is not a valid PNG: {image_path}")
    return struct.unpack(">II", header[16:24])


def _vector_as_list(value) -> list[float]:
    return [round(float(component), 6) for component in value]


class CampfireAppExtension(omni.ext.IExt):
    """Create a deterministic stage and optionally run its headless validation."""

    def on_startup(self, ext_id):
        self._extension_start_perf = time.perf_counter()
        self._startup_timing = {}
        extension_manager = omni.kit.app.get_app().get_extension_manager()
        self._extension_path = Path(extension_manager.get_extension_path(ext_id)).resolve()
        self._control_window = None
        self._resident_snapshot_adapter = None
        self._resident_point_owner = None
        self._resident_point_stage_subscription = None
        self._resident_point_timeline_subscription = None
        self._resident_point_update_subscription = None
        self._resident_point_last_step_perf = None
        self._startup_task = asyncio.ensure_future(self._initialize())
        carb.log_info("[campfire.app] Extension startup")

    def on_shutdown(self):
        if self._startup_task and not self._startup_task.done():
            self._startup_task.cancel()
        self._startup_task = None
        self._resident_point_update_subscription = None
        self._resident_point_timeline_subscription = None
        self._resident_point_stage_subscription = None
        if self._resident_point_owner is not None:
            try:
                self._resident_point_owner.close()
            except Exception as exc:
                carb.log_error(
                    f"[campfire.app] Resident Point owner shutdown failed: {exc}"
                )
                try:
                    self._resident_point_owner.close(discard_pending=True)
                except Exception as discard_exc:
                    carb.log_error(
                        "[campfire.app] Resident Point pending discard failed: "
                        f"{discard_exc}"
                    )
            self._resident_point_owner = None
        if self._resident_snapshot_adapter is not None:
            try:
                self._resident_snapshot_adapter.close()
            except Exception as exc:
                carb.log_error(
                    f"[campfire.app] Resident snapshot adapter shutdown failed: {exc}"
                )
            self._resident_snapshot_adapter = None
        if self._control_window is not None:
            self._control_window.destroy()
            self._control_window = None
        carb.log_info("[campfire.app] Extension shutdown")

    async def _initialize(self):
        settings = carb.settings.get_settings()
        if not settings.get_as_bool(f"{SETTINGS_ROOT}/autoCreateScene"):
            return

        capture_requested = settings.get_as_bool(f"{SETTINGS_ROOT}/captureOnStartup")
        quit_after_capture = settings.get_as_bool(f"{SETTINGS_ROOT}/quitAfterCapture")
        phase = settings.get_as_string(f"{SETTINGS_ROOT}/phase") or "phase0"
        point_application_enabled = resident_point_application_enabled(settings)
        try:
            if point_application_enabled and phase != "phase3":
                raise ValueError(
                    "Resident Point application is available only for Phase 3"
                )
            scene_setup_started = time.perf_counter()
            context = omni.usd.get_context()
            for _ in range(30):
                if context.get_stage() is not None:
                    break
                await omni.kit.app.get_app().next_update_async()
            if context.get_stage() is None:
                await context.new_stage_async()

            stage = context.get_stage()
            repo_root = _find_repo_root(self._extension_path)
            if phase == "phase6":
                populate_phase6_scene(stage)
                scene_path = export_phase6_stage(
                    stage, repo_root / "assets" / "scenes" / "phase6_calibration.usda"
                )
            elif phase == "phase5":
                settings.set("/rtx/flow/enabled", True)
                populate_phase5_scene(stage)
                scene_path = export_phase5_stage(
                    stage, repo_root / "assets" / "scenes" / "phase5_collapse.usda"
                )
            elif phase == "phase4":
                settings.set("/rtx/flow/enabled", True)
                populate_phase4_scene(stage)
                scene_path = export_phase4_stage(
                    stage, repo_root / "assets" / "scenes" / "phase4_air.usda"
                )
            elif phase == "phase3":
                settings.set("/rtx/flow/enabled", True)
                configured_scene_output_dir = settings.get_as_string(
                    f"{SETTINGS_ROOT}/sceneOutputDir"
                )
                phase3_scene_dir = (
                    Path(configured_scene_output_dir).resolve()
                    if configured_scene_output_dir
                    else repo_root / "assets" / "scenes"
                )
                if point_application_enabled:
                    stage, scene_path = await self._initialize_resident_point_stage(
                        context,
                        phase3_scene_dir / "phase3_point_application.usda",
                        capture_requested=capture_requested,
                    )
                else:
                    populate_phase3_scene(stage)
                    scene_path = export_phase3_stage(
                        stage, phase3_scene_dir / "phase3_thermal.usda"
                    )
            elif phase == "phase2":
                settings.set("/rtx/flow/enabled", True)
                populate_phase2_scene(stage)
                scene_path = export_phase2_stage(
                    stage, repo_root / "assets" / "scenes" / "phase2_rigid.usda"
                )
            elif phase == "phase1":
                settings.set("/rtx/flow/enabled", True)
                populate_flow_scene(stage)
                scene_path = export_flow_stage(
                    stage, repo_root / "assets" / "scenes" / "phase1_flow.usda"
                )
            elif phase == "phase0":
                populate_fixed_scene(stage)
                scene_path = export_stage(
                    stage, repo_root / "assets" / "scenes" / "phase0.usda"
                )
            else:
                raise ValueError(f"Unsupported campfire validation phase: {phase}")
            self._startup_timing["scene_build_export_seconds"] = round(
                time.perf_counter() - scene_setup_started, 4
            )
            carb.log_info(f"[campfire.app] {phase} scene exported to {scene_path}")

            viewport_setup_started = time.perf_counter()
            viewport = await self._get_viewport()
            if viewport is not None:
                viewport.camera_path = CAMERA_PATH
                viewport.fill_frame = False
                viewport.resolution = CAPTURE_RESOLUTION
            self._startup_timing["viewport_setup_seconds"] = round(
                time.perf_counter() - viewport_setup_started, 4
            )

            if capture_requested:
                if viewport is None:
                    raise RuntimeError(f"No active viewport is available for {phase} capture")
                capture_readiness_started = time.perf_counter()
                await self._wait_for_capture_resolution(viewport)
                self._startup_timing["capture_resolution_wait_seconds"] = round(
                    time.perf_counter() - capture_readiness_started, 4
                )
                if phase == "phase6":
                    await self._capture_phase6(viewport, stage, scene_path)
                elif phase == "phase5":
                    await self._run_phase5(viewport, stage, scene_path)
                elif phase == "phase4":
                    await self._capture_phase4(viewport, stage, scene_path)
                elif phase == "phase3":
                    if point_application_enabled:
                        await self._run_resident_point_application(
                            viewport, stage, scene_path
                        )
                    else:
                        await self._run_phase3(viewport, stage, scene_path)
                elif phase == "phase2":
                    await self._run_phase2(viewport, stage, scene_path)
                elif phase == "phase1":
                    await self._run_phase1(viewport, stage, scene_path)
                else:
                    await self._capture_phase0(viewport, scene_path)

            if phase == "phase2" and not capture_requested:
                self._control_window = CampfireControlWindow()

            if capture_requested and quit_after_capture:
                settings.set("/app/fastShutdown", True)
                omni.kit.app.get_app().post_uncancellable_quit(0)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            carb.log_error(f"[campfire.app] {phase} initialization failed: {exc}")
            if capture_requested and quit_after_capture:
                omni.kit.app.get_app().post_uncancellable_quit(1)

    async def _initialize_resident_point_stage(
        self, context, scene_path: Path, *, capture_requested: bool
    ):
        """Build the complete opt-in Point stage before connecting it to Kit."""

        settings = carb.settings.get_settings()
        native_library_path = settings.get_as_string(
            f"{SETTINGS_ROOT}/residentNativeLibraryPath"
        )
        if not native_library_path:
            raise ValueError(
                "Resident Point application requires residentNativeLibraryPath"
            )
        scene_path = scene_path.resolve()
        scene_path.parent.mkdir(parents=True, exist_ok=True)
        scene_path.unlink(missing_ok=True)
        offline_stage = Usd.Stage.CreateNew(str(scene_path))
        backend = None
        try:
            populate_phase3_scene(offline_stage)
            log_ids = (PHASE3_DRY_LOG_ID, PHASE3_WET_LOG_ID)
            models = tuple(
                load_model_from_prim(
                    offline_stage.GetPrimAtPath(f"/World/Logs/{log_id}")
                )
                for log_id in log_ids
            )
            backend = ResidentNativeBackend(
                models,
                Path(native_library_path).resolve(),
                dt_seconds=PHASE3_MODEL_DT_SECONDS,
                heat_flux_w_m2=PHASE3_EXTERNAL_HEAT_FLUX_W_M2,
            )
            layout = resident_point_layout_for_logs(offline_stage, log_ids)
            producer = ResidentNativeSurfaceProducer(
                backend, layout["origins"], layout["axes"]
            )
            producer.build_layout()
            scene_contract = configure_resident_point_application_scene(
                offline_stage, producer.positions
            )
            preauthor_resident_snapshot_consumers(offline_stage, log_ids)
            offline_stage.GetRootLayer().customLayerData = {
                **offline_stage.GetRootLayer().customLayerData,
                "campfire:phase": "phase6ci",
                "campfire:flowVersion": FLOW_VERSION,
                "campfire:stageBuiltBeforeConnection": True,
                "campfire:normalApplicationOwner": True,
            }
            if not offline_stage.GetRootLayer().Save():
                raise RuntimeError(
                    f"Failed to save Resident Point application stage: {scene_path}"
                )
            del producer
            del offline_stage

            if context.get_stage() is not None:
                # The app's empty-stage template may expose a stage object just
                # before its asynchronous OPENED transition.  Let that startup
                # transaction finish before requesting the opt-in replacement.
                for _ in range(60):
                    await omni.kit.app.get_app().next_update_async()
                closed = False
                close_error = None
                for _ in range(120):
                    closed, close_error = await context.close_stage_async()
                    if closed and not close_error:
                        break
                    if "already in progress" not in str(close_error).lower():
                        break
                    await omni.kit.app.get_app().next_update_async()
                if not closed or close_error:
                    raise RuntimeError(
                        "Unable to close the initial stage before Resident Point "
                        f"connection: {close_error}"
                    )
                for _ in range(4):
                    await omni.kit.app.get_app().next_update_async()
            opened, open_error = await context.open_stage_async(str(scene_path))
            if not opened or open_error:
                raise RuntimeError(
                    f"Unable to connect Resident Point stage: {open_error}"
                )
            for _ in range(4):
                await omni.kit.app.get_app().next_update_async()
            stage = context.get_stage()
            if stage is None:
                raise RuntimeError("Resident Point stage connection returned no stage")

            timeline = omni.timeline.get_timeline_interface()
            owner = ResidentPointApplicationOwner.compose(
                backend,
                stage,
                context,
                timeline,
                omni.kit.app.get_app().next_update_async,
                layout,
            )
            backend = None
            self._resident_point_owner = owner
            event_names = {
                int(omni.usd.StageEventType.CLOSING): "closing",
                int(omni.usd.StageEventType.CLOSED): "closed",
                int(omni.usd.StageEventType.OPENING): "opening",
                int(omni.usd.StageEventType.OPENED): "opened",
            }

            def observe_stage_event(event):
                current_owner = self._resident_point_owner
                event_name = event_names.get(int(event.type))
                if current_owner is not None and event_name is not None:
                    current_owner.observe_stage_event(event_name)

            self._resident_point_stage_subscription = (
                context.get_stage_event_stream().create_subscription_to_pop(
                    observe_stage_event, name="campfire-resident-point-stage"
                )
            )
            if not capture_requested:
                self._bind_resident_point_interactive_lifecycle(timeline)
            carb.log_info(
                "[campfire.app] Resident Point stage connected after complete "
                f"offline authoring: points={scene_contract['point_count']}"
            )
            return stage, scene_path
        except Exception:
            if self._resident_point_owner is not None:
                try:
                    self._resident_point_owner.close(discard_pending=True)
                finally:
                    self._resident_point_owner = None
            elif backend is not None:
                backend.close()
            raise

    def _bind_resident_point_interactive_lifecycle(self, timeline):
        """Bind the normal interactive timeline without adding state authority."""

        event_names = {
            int(omni.timeline.TimelineEventType.PLAY): "play",
            int(omni.timeline.TimelineEventType.PAUSE): "pause",
            int(omni.timeline.TimelineEventType.STOP): "stop",
        }

        def observe_timeline(event):
            owner = self._resident_point_owner
            name = event_names.get(int(event.type))
            if owner is None or name is None:
                return
            try:
                state = owner.status()["session"]["state"]
                if name == "play" and state in ("ready", "stopped"):
                    owner.start()
                    self._resident_point_last_step_perf = time.perf_counter()
                elif name in ("pause", "stop") and state == "running":
                    owner.stop()
            except Exception as exc:
                carb.log_error(
                    f"[campfire.app] Resident Point timeline transition failed: {exc}"
                )

        self._resident_point_timeline_subscription = (
            timeline.get_timeline_event_stream().create_subscription_to_pop(
                observe_timeline, 0, "campfire-resident-point-timeline"
            )
        )

        def update_resident_point(_event):
            owner = self._resident_point_owner
            if owner is None:
                return
            try:
                if owner.status()["session"]["state"] != "running":
                    return
                now = time.perf_counter()
                previous = self._resident_point_last_step_perf
                if previous is None or now - previous >= PHASE3_MODEL_DT_SECONDS:
                    owner.step()
                    self._resident_point_last_step_perf = now
            except Exception as exc:
                carb.log_error(
                    f"[campfire.app] Resident Point interactive step failed: {exc}"
                )

        self._resident_point_update_subscription = (
            omni.kit.app.get_app()
            .get_update_event_stream()
            .create_subscription_to_pop(
                update_resident_point, name="campfire-resident-point-update"
            )
        )
        if timeline.is_playing():
            self._resident_point_owner.start()
            self._resident_point_last_step_perf = time.perf_counter()

    async def _get_viewport(self):
        viewport = None
        for _ in range(120):
            viewport = omni.kit.viewport.utility.get_active_viewport()
            if viewport is not None:
                break
            await omni.kit.app.get_app().next_update_async()
        return viewport

    async def _wait_for_capture_resolution(self, viewport):
        for _ in range(60):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
            if tuple(viewport.resolution) == CAPTURE_RESOLUTION:
                return
            await omni.kit.app.get_app().next_update_async()
        raise RuntimeError(
            f"Viewport resolution did not settle at {CAPTURE_RESOLUTION}: "
            f"{tuple(viewport.resolution)}"
        )

    def _output_dir(self) -> Path:
        settings = carb.settings.get_settings()
        configured_output = settings.get(f"{SETTINGS_ROOT}/outputDir")
        repo_root = _find_repo_root(self._extension_path)
        output_dir = (
            Path(configured_output).resolve()
            if configured_output
            else repo_root / "artifacts" / "phase0" / "latest"
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    async def _capture_image(self, viewport, image_path: Path) -> tuple[int, int]:
        capture = omni.kit.viewport.utility.capture_viewport_to_file(
            viewport, file_path=str(image_path)
        )
        if not await capture.wait_for_result(completion_frames=60):
            raise RuntimeError("Viewport capture did not complete successfully")
        for _ in range(10):
            if image_path.is_file():
                break
            await omni.kit.app.get_app().next_update_async()
        if not image_path.is_file():
            raise RuntimeError(f"Viewport capture was not written: {image_path}")

        image_resolution = _read_png_resolution(image_path)
        if image_resolution != CAPTURE_RESOLUTION:
            raise RuntimeError(
                f"Captured PNG resolution is {image_resolution}, expected "
                f"{CAPTURE_RESOLUTION}"
            )
        return image_resolution

    async def _capture_fast_image(self, viewport, image_path: Path) -> tuple[int, int]:
        """Capture one animation frame without the static-scene settle delay."""

        capture = omni.kit.viewport.utility.capture_viewport_to_file(
            viewport, file_path=str(image_path)
        )
        if not await capture.wait_for_result(completion_frames=2):
            raise RuntimeError(f"Animation frame capture failed: {image_path}")
        for _ in range(30):
            if image_path.is_file():
                break
            await omni.kit.app.get_app().next_update_async()
        if not image_path.is_file():
            raise RuntimeError(f"Animation frame was not written: {image_path}")
        resolution = _read_png_resolution(image_path)
        if resolution != CAPTURE_RESOLUTION:
            raise RuntimeError(
                f"Animation PNG resolution is {resolution}, expected "
                f"{CAPTURE_RESOLUTION}"
            )
        return resolution

    async def _run_resident_point_application(
        self, viewport, stage, scene_path: Path
    ):
        """Qualify the normal extension-owned Resident Point composition."""

        owner = self._resident_point_owner
        if owner is None:
            raise RuntimeError("Resident Point application owner is unavailable")
        output_dir = self._output_dir()
        video_frames_dir = output_dir / "video_frames"
        video_frames_dir.mkdir(parents=True, exist_ok=True)
        for old_frame in video_frames_dir.glob("frame_*.png"):
            old_frame.unlink()
        timeline = omni.timeline.get_timeline_interface()
        flow_interface = None
        listener = None
        point_resyncs = []
        point_changes = []
        point_prefix = str(RESIDENT_POINT_EMITTER_PATH)

        def observe_point_changes(notice, _sender):
            point_resyncs.extend(
                str(path)
                for path in notice.GetResyncedPaths()
                if str(path).startswith(point_prefix)
            )
            point_changes.extend(
                str(path)
                for path in notice.GetChangedInfoOnlyPaths()
                if str(path).startswith(point_prefix)
            )

        try:
            listener = Tf.Notice.Register(
                Usd.Notice.ObjectsChanged, observe_point_changes, stage
            )
            timeline.stop()
            timeline.set_current_time(0.0)
            owner.start()
            timeline.play()
            flow_interface = _flowusd.acquire_flowusd_interface()
            active_blocks = []
            result = None
            warmup_steps = 650
            frame_count = 60
            for tick in range(1, warmup_steps + 1):
                result = owner.step()
                if tick % 5 == 0:
                    await omni.kit.app.get_app().next_update_async()
                    active_blocks.append(
                        int(flow_interface.get_active_block_count())
                    )
            for frame_index in range(frame_count):
                result = owner.step()
                await omni.kit.app.get_app().next_update_async()
                active_blocks.append(int(flow_interface.get_active_block_count()))
                await self._capture_fast_image(
                    viewport,
                    video_frames_dir / f"frame_{frame_index:04d}.png",
                )
            timeline.pause()
            await omni.kit.app.get_app().next_update_async()
            raw_readback = flow_interface.get_latest_nanovdb_readback()
            readback_names = (
                "temperature",
                "fuel",
                "burn",
                "smoke",
                "velocity",
                "divergence",
            )
            readback = {}
            for index, name in enumerate(readback_names):
                value = raw_readback[index] if index < len(raw_readback) else []
                readback[name] = int(getattr(value, "size", len(value)))
            owner.stop()
            stopped_status = owner.status()
            session_status = stopped_status["session"]
            revisions = (
                session_status["backend"]["revision"],
                session_status["adapter"]["revision"],
                session_status["sidecar"]["revision"],
            )
            close_result = owner.close()
            self._resident_point_owner = None
            frame_paths = sorted(video_frames_dir.glob("frame_*.png"))
            unique_frames = len(
                {
                    hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in frame_paths
                }
            )
            allowed_point_properties = {
                f"{point_prefix}.pointPositions",
                f"{point_prefix}.pointFuels",
                f"{point_prefix}.pointTemperatures",
                f"{point_prefix}.pointSmokes",
                f"{point_prefix}.campfire:residentRevision",
            }
            unexpected_point_changes = sorted(
                set(point_changes).difference(allowed_point_properties)
            )
            point_prim = stage.GetPrimAtPath(RESIDENT_POINT_EMITTER_PATH)
            gates = {
                "explicit_setting_enabled": resident_point_application_enabled(
                    carb.settings.get_settings()
                ),
                "normal_extension_owner_composed": (
                    stopped_status["start_count"] == 1
                    and stopped_status["stop_count"] == 1
                    and stopped_status["step_count"] == warmup_steps + frame_count
                ),
                "complete_schema_connected": (
                    bool(point_prim)
                    and point_prim.GetTypeName() == "FlowEmitterPoint"
                    and len(point_prim.GetAttribute("pointPositions").Get()) == 720
                ),
                "only_existing_point_properties_changed_live": (
                    not point_resyncs and not unexpected_point_changes
                ),
                "consumer_revisions_match": len(set(revisions)) == 1,
                "final_revision_matches_steps": revisions[0]
                == warmup_steps + frame_count,
                "flow_core_active": max(active_blocks, default=0) > 0,
                "fuel_temperature_smoke_present": all(
                    readback[name] > 0
                    for name in ("fuel", "temperature", "smoke", "burn")
                ),
                "continuous_video": (
                    len(frame_paths) == frame_count and unique_frames >= 55
                ),
                "clean_shutdown": (
                    not close_result["session"]["backend"]["active"]
                    and close_result["session"]["adapter_closed"]
                    and close_result["session"]["sidecar_closed"]
                ),
            }
            summary = {
                "schema_version": 1,
                "status": "ok" if all(gates.values()) else "failed",
                "phase": "phase6ci",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "scene": str(scene_path),
                "scope": {
                    "flow_version": FLOW_VERSION,
                    "default_off": True,
                    "normal_application": True,
                    "stage_built_before_connection": True,
                    "point_count": 720,
                    "surface_points_per_log": 360,
                    "log_count": 2,
                    "emitter_count": 1,
                    "canonical_scene_changed": False,
                },
                "lifecycle": {
                    "owner": stopped_status,
                    "close": close_result,
                    "stage_event_subscription_installed": (
                        self._resident_point_stage_subscription is not None
                    ),
                    "timeline_paused_after_run": not timeline.is_playing(),
                },
                "publication": {
                    "revisions": revisions,
                    "point_resyncs": sorted(set(point_resyncs)),
                    "point_changed_properties": sorted(set(point_changes)),
                    "unexpected_point_changes": unexpected_point_changes,
                },
                "flow": {
                    "active_blocks_peak": max(active_blocks, default=0),
                    "readback_words": readback,
                    "video_frame_count": len(frame_paths),
                    "unique_video_frame_hashes": unique_frames,
                    "final_tick": result.snapshot.tick if result else None,
                },
                "gates": gates,
            }
            self._write_summary(output_dir, summary)
            if not all(gates.values()):
                failed = [name for name, passed in gates.items() if not passed]
                raise RuntimeError(f"Phase 6CI gates failed: {failed}")
            carb.log_info(
                "[campfire.app] Phase 6CI complete: "
                f"revision={revisions[0]}, activeBlocks={max(active_blocks)}"
            )
        finally:
            if listener is not None:
                listener.Revoke()
            if flow_interface is not None:
                _flowusd.release_flowusd_interface(flow_interface)
            if self._resident_point_owner is owner:
                try:
                    owner.close(discard_pending=True)
                finally:
                    self._resident_point_owner = None

    async def _capture_phase0(self, viewport, scene_path: Path):
        output_dir = self._output_dir()
        for _ in range(8):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)

        image_path = output_dir / "frame_0000.png"
        image_resolution = await self._capture_image(viewport, image_path)
        settings = carb.settings.get_settings()
        summary = {
            "status": "ok",
            "phase": "phase0",
            "quit_after_capture": settings.get_as_bool(f"{SETTINGS_ROOT}/quitAfterCapture"),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "scene": str(scene_path),
            "image": str(image_path),
            "camera": str(CAMERA_PATH),
            "resolution": list(image_resolution),
        }
        self._write_summary(output_dir, summary)
        carb.log_info(f"[campfire.app] Phase 0 capture written to {image_path}")

    async def _capture_phase4(self, viewport, stage, scene_path: Path):
        output_dir = self._output_dir()
        for _ in range(8):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        image_path = output_dir / "frame_0000.png"
        image_resolution = await self._capture_image(viewport, image_path)
        comparison_started = time.perf_counter()
        comparison = run_stack_air_comparison()
        comparison_wall_seconds = time.perf_counter() - comparison_started
        final_stage_path = export_stage(stage, output_dir / "final_stage.usda")
        summary = {
            "status": "ok",
            "phase": "phase4",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "scene": str(scene_path),
            "final_stage": str(final_stage_path),
            "image": str(image_path),
            "resolution": list(image_resolution),
            "comparison_wall_seconds": round(comparison_wall_seconds, 4),
            "comparison": comparison,
        }
        self._write_summary(output_dir, summary)
        carb.log_info(
            "[campfire.app] Phase 4 comparison complete: "
            f"denseO2={comparison['dense']['oxygen_factor']:.4f}, "
            f"cabinO2={comparison['cabin']['oxygen_factor']:.4f}"
        )

    async def _capture_phase6(self, viewport, stage, scene_path: Path):
        """Calibrate against the fixed NIST subset and visualize the result."""

        output_dir = self._output_dir()
        calibration_started = time.perf_counter()
        calibration = run_nist_plywood_calibration()
        calibration_wall_seconds = time.perf_counter() - calibration_started
        apply_phase6_calibration(stage, calibration)

        for _ in range(8):
            await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
        image_path = output_dir / "frame_0000.png"
        image_resolution = await self._capture_image(viewport, image_path)
        report_path = write_calibration_svg(
            calibration, output_dir / "calibration_report.svg"
        )
        holdout_report_path = write_holdout_svg(
            calibration, output_dir / "holdout_report.svg"
        )
        replicate_holdout_report_path = write_replicate_holdout_svg(
            calibration, output_dir / "replicate_holdout_report.svg"
        )
        layer_profile_report_path = write_layer_profile_svg(
            calibration, output_dir / "layer_profile_report.svg"
        )
        kinetics_report_path = write_kinetics_svg(
            calibration, output_dir / "kinetics_report.svg"
        )
        tar_residence_sensitivity_report_path = (
            write_tar_residence_sensitivity_svg(
                calibration,
                output_dir / "tar_residence_sensitivity_report.svg",
            )
        )
        gas_transport_readiness_report_path = write_gas_transport_readiness_svg(
            calibration,
            output_dir / "gas_transport_readiness_report.svg",
        )
        char_geometry_report_path = write_char_geometry_svg(
            calibration,
            output_dir / "char_geometry_report.svg",
        )
        char_depth_benchmark_report_path = write_char_depth_benchmark_svg(
            calibration,
            output_dir / "char_depth_benchmark_report.svg",
        )
        char_depth_measurement_protocol_report_path = (
            write_char_depth_measurement_protocol_svg(
                calibration,
                output_dir / "char_depth_measurement_protocol_report.svg",
            )
        )
        char_depth_experiment_plan_report_path = write_char_depth_experiment_plan_svg(
            calibration,
            output_dir / "char_depth_experiment_plan_report.svg",
        )
        dry_run_directory = create_char_depth_dry_run_package(
            "CF6O-F035-T0060-R01",
            output_dir / "char_depth_offline_dry_run",
        )
        dry_run_readiness = evaluate_char_depth_dry_run_package(dry_run_directory)
        dry_run_readiness_dict = asdict(dry_run_readiness)
        char_depth_dry_run_report_path = write_char_depth_dry_run_svg(
            dry_run_readiness_dict,
            output_dir / "char_depth_dry_run_report.svg",
        )
        lab_handoff_readiness = evaluate_char_depth_lab_handoff()
        lab_handoff_readiness_dict = asdict(lab_handoff_readiness)
        char_depth_lab_handoff_report_path = write_char_depth_lab_handoff_svg(
            lab_handoff_readiness_dict,
            output_dir / "char_depth_lab_handoff_report.svg",
        )
        candidates_path = output_dir / "top_candidates.csv"
        with candidates_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=(
                    "rank",
                    "score_rmse_relative",
                    *calibration["top_candidates"][0]["parameters"].keys(),
                ),
            )
            writer.writeheader()
            for rank, candidate in enumerate(calibration["top_candidates"], start=1):
                writer.writerow(
                    {
                        "rank": rank,
                        "score_rmse_relative": candidate["score_rmse_relative"],
                        **candidate["parameters"],
                    }
                )
        final_stage_path = export_stage(stage, output_dir / "final_stage.usda")
        summary = {
            "status": "ok",
            "phase": "phase6",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "scene": str(scene_path),
            "final_stage": str(final_stage_path),
            "image": str(image_path),
            "report": str(report_path),
            "holdout_report": str(holdout_report_path),
            "replicate_holdout_report": str(replicate_holdout_report_path),
            "layer_profile_report": str(layer_profile_report_path),
            "kinetics_report": str(kinetics_report_path),
            "tar_residence_sensitivity_report": str(
                tar_residence_sensitivity_report_path
            ),
            "gas_transport_readiness_report": str(
                gas_transport_readiness_report_path
            ),
            "char_geometry_report": str(char_geometry_report_path),
            "char_depth_benchmark_report": str(
                char_depth_benchmark_report_path
            ),
            "char_depth_measurement_protocol_report": str(
                char_depth_measurement_protocol_report_path
            ),
            "char_depth_experiment_plan_report": str(
                char_depth_experiment_plan_report_path
            ),
            "char_depth_dry_run_directory": str(dry_run_directory),
            "char_depth_dry_run_report": str(char_depth_dry_run_report_path),
            "char_depth_dry_run_readiness": dry_run_readiness_dict,
            "char_depth_lab_handoff_report": str(
                char_depth_lab_handoff_report_path
            ),
            "char_depth_lab_handoff_readiness": lab_handoff_readiness_dict,
            "top_candidates_csv": str(candidates_path),
            "resolution": list(image_resolution),
            "calibration_wall_seconds": round(calibration_wall_seconds, 4),
            "calibration": calibration,
        }
        self._write_summary(output_dir, summary)
        carb.log_info(
            "[campfire.app] Phase 6 calibration complete: "
            f"baseline={calibration['baseline']['score_rmse_relative']:.4f}, "
            f"best={calibration['best']['score_rmse_relative']:.4f}"
        )

    async def _run_phase5(self, viewport, stage, scene_path: Path):
        """Release a thermally failed joint and validate the PhysX collapse."""

        output_dir = self._output_dir()
        settings = carb.settings.get_settings()
        physics = get_physx_simulation_interface()
        flow_interface = _flowusd.acquire_flowusd_interface()
        stage_id = UsdUtils.StageCache.Get().GetId(stage).ToLongInt()
        attached_before = int(physics.get_attached_stage())
        attached_here = attached_before != stage_id
        previous_update_to_usd = settings.get_as_bool(SETTING_UPDATE_TO_USD)
        previous_fabric = settings.get_as_bool("/physics/fabricEnabled")

        numerical_started = time.perf_counter()
        combustion = run_collapse_reignition_scenario()
        failed_model, failure, _, _ = burn_to_support_failure()
        numerical_wall_seconds = time.perf_counter() - numerical_started
        release_positions = None
        segment_updates = None
        physics_times_ms = []
        active_block_counts = []
        images = []

        try:
            settings.set(SETTING_UPDATE_TO_USD, True)
            settings.set("/physics/fabricEnabled", False)
            if attached_here:
                physics.attach_stage(stage_id)

            for frame in range(1, PHASE5_POST_CAPTURE_FRAME + 1):
                if frame == PHASE5_RELEASE_FRAME:
                    release_positions = {
                        path: _vector_as_list(
                            get_log_world_position(stage, path.rsplit("/", 1)[-1])
                        )
                        for path in PHASE5_SEGMENT_PATHS
                    }
                    physics.detach_stage()
                    segment_updates = release_phase5_structure(
                        stage, failed_model, failure
                    )
                    physics.attach_stage(stage_id)

                physics_started = time.perf_counter()
                physics.simulate(PHASE5_FIXED_DT_SECONDS, frame * PHASE5_FIXED_DT_SECONDS)
                physics.fetch_results()
                physics_times_ms.append(
                    (time.perf_counter() - physics_started) * 1000.0
                )
                await omni.kit.app.get_app().next_update_async()
                active_block_counts.append(int(flow_interface.get_active_block_count()))

                if frame in (PHASE5_PRE_CAPTURE_FRAME, PHASE5_POST_CAPTURE_FRAME):
                    image_path = output_dir / f"frame_{frame:04d}.png"
                    resolution = await self._capture_image(viewport, image_path)
                    images.append(
                        {
                            "frame": frame,
                            "state": "supported" if frame < PHASE5_RELEASE_FRAME else "collapsed",
                            "path": str(image_path),
                            "resolution": list(resolution),
                        }
                    )

            final_positions = {
                path: _vector_as_list(
                    get_log_world_position(stage, path.rsplit("/", 1)[-1])
                )
                for path in PHASE5_SEGMENT_PATHS
            }
            displacements = {}
            vertical_drops = {}
            for path in PHASE5_SEGMENT_PATHS:
                before = Gf.Vec3d(*release_positions[path])
                after = Gf.Vec3d(*final_positions[path])
                displacements[path] = float((after - before).GetLength())
                vertical_drops[path] = float(before[2] - after[2])

            final_stage_path = export_stage(stage, output_dir / "final_stage.usda")
            measured = physics_times_ms[30:]
            summary = {
                "status": "ok",
                "phase": "phase5",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "scene": str(scene_path),
                "final_stage": str(final_stage_path),
                "resolution": list(CAPTURE_RESOLUTION),
                "images": images,
                "combustion": combustion,
                "structure": {
                    "joint_path": PHASE5_JOINT_PATH,
                    "constraint_released": not bool(
                        stage.GetPrimAtPath(PHASE5_JOINT_PATH)
                    ),
                    "release_frame": PHASE5_RELEASE_FRAME,
                    "failed_section": failure.weakest_section,
                    "support_ratio_at_release": failure.weakest_support_ratio,
                    "failure_threshold": failure.failure_threshold,
                    "segment_updates": [
                        {
                            "path": update.path,
                            "mass_kg": update.mass_kg,
                            "mass_ratio": update.mass_ratio,
                            "collider_radius_m": update.collider_radius_m,
                        }
                        for update in segment_updates
                    ],
                },
                "rigid_body": {
                    "fixed_dt_seconds": PHASE5_FIXED_DT_SECONDS,
                    "simulation_steps": PHASE5_POST_CAPTURE_FRAME,
                    "release_positions_m": release_positions,
                    "final_positions_m": final_positions,
                    "displacement_m": displacements,
                    "vertical_drop_m": vertical_drops,
                    "collapsed": max(displacements.values()) > 0.08,
                },
                "flow": {
                    "active_blocks_final": active_block_counts[-1],
                    "active_blocks_peak": max(active_block_counts, default=0),
                },
                "timing": {
                    "numerical_wall_seconds": round(numerical_wall_seconds, 4),
                    "physics_mean_ms": round(statistics.fmean(measured), 4),
                    "physics_p95_ms": round(
                        sorted(measured)[min(len(measured) - 1, int(len(measured) * 0.95))],
                        4,
                    ),
                },
            }
            self._write_summary(output_dir, summary)
            carb.log_info(
                "[campfire.app] Phase 5 complete: "
                f"support={failure.weakest_support_ratio:.4f}, "
                f"reignitionGain={combustion['reignition_gain']:.3f}, "
                f"collapsed={summary['rigid_body']['collapsed']}"
            )
        finally:
            if attached_here and int(physics.get_attached_stage()) == stage_id:
                physics.detach_stage()
            settings.set(SETTING_UPDATE_TO_USD, previous_update_to_usd)
            settings.set("/physics/fabricEnabled", previous_fabric)
            _flowusd.release_flowusd_interface(flow_interface)

    async def _run_phase1(self, viewport, stage, scene_path: Path):
        output_dir = self._output_dir()
        timeline = omni.timeline.get_timeline_interface()
        emitter_position = stage.GetPrimAtPath(FLOW_EMITTER_PATH).GetAttribute("position")
        flow_interface = _flowusd.acquire_flowusd_interface()
        frame_times_ms = []
        active_block_counts = []
        images = []
        readback_error = None
        readback_query_ms = None

        try:
            timeline.stop()
            timeline.set_current_time(0.0)
            timeline.play()
            simulation_started = time.perf_counter()

            for frame in range(1, PHASE1_TOTAL_FRAMES + 1):
                emitter_position.Set(emitter_position_for_frame(frame))
                frame_started = time.perf_counter()
                # Match NVIDIA Flow's own golden-image tests: advance the Kit
                # update loop while the timeline is playing.  Viewport capture
                # below waits for renderer completion separately.
                await omni.kit.app.get_app().next_update_async()
                frame_times_ms.append((time.perf_counter() - frame_started) * 1000.0)
                active_block_counts.append(int(flow_interface.get_active_block_count()))

                if frame in PHASE1_CAPTURE_FRAMES:
                    image_path = output_dir / f"frame_{frame:04d}.png"
                    resolution = await self._capture_image(viewport, image_path)
                    images.append(
                        {
                            "frame": frame,
                            "path": str(image_path),
                            "resolution": list(resolution),
                            "emitter_position": _vector_as_list(emitter_position.Get()),
                        }
                    )

            simulation_elapsed = time.perf_counter() - simulation_started
            timeline.pause()

            try:
                readback_started = time.perf_counter()
                raw_readback = flow_interface.get_latest_nanovdb_readback()
                readback_query_ms = (time.perf_counter() - readback_started) * 1000.0
                channel_names = (
                    "temperature",
                    "fuel",
                    "burn",
                    "smoke",
                    "velocity",
                    "divergence",
                )
                word_counts = {}
                for index, channel in enumerate(channel_names):
                    value = raw_readback[index] if index < len(raw_readback) else []
                    word_counts[channel] = int(getattr(value, "size", len(value)))
            except Exception as exc:
                word_counts = {channel: 0 for channel in channel_names}
                readback_error = str(exc)

            measured_frames = frame_times_ms[30:]
            sorted_frame_times = sorted(measured_frames)
            p95_index = min(
                len(sorted_frame_times) - 1,
                int(len(sorted_frame_times) * 0.95),
            )
            final_position = emitter_position.Get()
            max_blocks = int(flow_interface.get_max_block_count())
            final_blocks = active_block_counts[-1] if active_block_counts else 0
            peak_blocks = max(active_block_counts, default=0)

            summary = {
                "status": "ok",
                "phase": "phase1",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "scene": str(scene_path),
                "camera": str(CAMERA_PATH),
                "resolution": list(CAPTURE_RESOLUTION),
                "images": images,
                "flow": {
                    "extension": "omni.flowusd",
                    "version": FLOW_VERSION,
                    "emitter_type": "FlowEmitterSphere",
                    "density_cell_size_m": 0.025,
                    "simulation_frames": PHASE1_TOTAL_FRAMES,
                    "simulation_wall_seconds": round(simulation_elapsed, 4),
                    "force_simulate": bool(
                        stage.GetPrimAtPath(FLOW_SIMULATE_PATH)
                        .GetAttribute("forceSimulate")
                        .Get()
                    ),
                    "active_blocks_final": final_blocks,
                    "active_blocks_peak": peak_blocks,
                    "max_blocks": max_blocks,
                },
                "emitter_motion": {
                    "start_m": _vector_as_list(EMITTER_START),
                    "end_m": _vector_as_list(final_position),
                    "expected_end_m": _vector_as_list(EMITTER_END),
                    "moved": Gf.IsClose(final_position, EMITTER_END, 1e-5),
                },
                "collision": {
                    "physics_collision_enabled": bool(
                        stage.GetPrimAtPath(FLOW_SIMULATE_PATH)
                        .GetAttribute("physicsCollisionEnabled")
                        .Get()
                    ),
                    "static_log_colliders": sum(
                        1
                        for log in stage.GetPrimAtPath("/World/Logs").GetChildren()
                        if log.HasAPI(UsdPhysics.CollisionAPI)
                    ),
                    "method": "USD PhysicsCollisionAPI consumed by Flow",
                },
                "timing": {
                    "scope": "end-to-end viewport update including Flow and RTX",
                    "warmup_frames_excluded": 30,
                    "mean_frame_ms": round(statistics.fmean(measured_frames), 4),
                    "p95_frame_ms": round(sorted_frame_times[p95_index], 4),
                    "flow_gpu_kernel_ms": None,
                    "flow_gpu_kernel_timing_available": False,
                    "timeline_current_time_seconds": round(
                        float(timeline.get_current_time()), 6
                    ),
                    "timeline_was_playing": bool(timeline.is_playing()),
                },
                "nano_vdb_readback": {
                    "available": any(count > 0 for count in word_counts.values()),
                    "cpu_readback_enabled": True,
                    "query_ms": (
                        round(readback_query_ms, 4)
                        if readback_query_ms is not None
                        else None
                    ),
                    "channel_word_counts": word_counts,
                    "error": readback_error,
                    "assessment": (
                        "Raw NanoVDB channel buffers reached CPU; direct world-space "
                        "point sampling requires a dedicated NanoVDB adapter."
                        if any(count > 0 for count in word_counts.values())
                        else "CPU readback was enabled, but no channel buffer was returned."
                    ),
                },
            }
            self._write_summary(output_dir, summary)
            carb.log_info(
                "[campfire.app] Phase 1 complete: "
                f"peakBlocks={peak_blocks}, meanFrameMs={summary['timing']['mean_frame_ms']}"
            )
        finally:
            timeline.pause()
            _flowusd.release_flowusd_interface(flow_interface)

    async def _run_phase2(self, viewport, stage, scene_path: Path):
        """Run fixed-step PhysX, add one log, and keep Flow on that body."""

        output_dir = self._output_dir()
        settings = carb.settings.get_settings()
        physics = get_physx_simulation_interface()
        flow_interface = _flowusd.acquire_flowusd_interface()
        stage_id = UsdUtils.StageCache.Get().GetId(stage).ToLongInt()
        attached_before = int(physics.get_attached_stage())
        attached_here = attached_before != stage_id
        previous_update_to_usd = settings.get_as_bool(SETTING_UPDATE_TO_USD)
        previous_fabric = settings.get_as_bool("/physics/fabricEnabled")

        physics_times_ms = []
        physics_simulate_times_ms = []
        physics_fetch_times_ms = []
        update_times_ms = []
        positions = []
        emitter_errors_m = []
        active_block_counts = []
        images = []
        added_ids_before = list_log_ids(stage)

        try:
            settings.set(SETTING_UPDATE_TO_USD, True)
            settings.set("/physics/fabricEnabled", False)
            if attached_here:
                physics.attach_stage(stage_id)

            simulation_started = time.perf_counter()
            for frame in range(1, PHASE2_TOTAL_FRAMES + 1):
                if frame == PHASE2_ADD_FRAME:
                    physics.detach_stage()
                    add_scenario_log(stage)
                    physics.attach_stage(stage_id)

                physics_started = time.perf_counter()
                physics.simulate(
                    PHASE2_FIXED_DT_SECONDS, frame * PHASE2_FIXED_DT_SECONDS
                )
                fetch_started = time.perf_counter()
                physics.fetch_results()
                fetch_finished = time.perf_counter()
                physics_simulate_times_ms.append(
                    (fetch_started - physics_started) * 1000.0
                )
                physics_fetch_times_ms.append(
                    (fetch_finished - fetch_started) * 1000.0
                )
                physics_times_ms.append(
                    (fetch_finished - physics_started) * 1000.0
                )

                update_started = time.perf_counter()
                if frame >= PHASE2_ADD_FRAME:
                    log_position = get_log_world_position(stage, PHASE2_ADDED_LOG_ID)
                    emitter_position = set_emitter_follow(stage, PHASE2_ADDED_LOG_ID)
                    expected_emitter = Gf.Vec3f(log_position) + PHASE2_EMITTER_OFFSET_M
                    emitter_errors_m.append(
                        float((emitter_position - expected_emitter).GetLength())
                    )
                    positions.append(_vector_as_list(log_position))

                await omni.kit.app.get_app().next_update_async()
                update_times_ms.append((time.perf_counter() - update_started) * 1000.0)
                active_block_counts.append(int(flow_interface.get_active_block_count()))

                if frame in PHASE2_CAPTURE_FRAMES:
                    image_path = output_dir / f"frame_{frame:04d}.png"
                    resolution = await self._capture_image(viewport, image_path)
                    images.append(
                        {
                            "frame": frame,
                            "path": str(image_path),
                            "resolution": list(resolution),
                            "added_log_position_m": (
                                positions[-1] if positions else None
                            ),
                        }
                    )

            simulation_elapsed = time.perf_counter() - simulation_started
            final_stage_path = export_stage(stage, output_dir / "final_stage.usda")

            final_position = Gf.Vec3d(*positions[-1])
            settle_reference = Gf.Vec3d(*positions[-60])
            settled_displacement = float((final_position - settle_reference).GetLength())
            horizontal_radius = (
                final_position[0] ** 2 + final_position[1] ** 2
            ) ** 0.5
            dropped_distance = PHASE2_SPAWN_POSITION_M[2] - final_position[2]
            all_ids = list_log_ids(stage)

            physics_sorted = sorted(physics_times_ms[30:])
            update_sorted = sorted(update_times_ms[30:])
            p95_index = min(len(physics_sorted) - 1, int(len(physics_sorted) * 0.95))
            update_p95_index = min(
                len(update_sorted) - 1, int(len(update_sorted) * 0.95)
            )
            summary = {
                "status": "ok",
                "phase": "phase2",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "scene": str(scene_path),
                "final_stage": str(final_stage_path),
                "camera": str(CAMERA_PATH),
                "resolution": list(CAPTURE_RESOLUTION),
                "images": images,
                "logs": {
                    "ids_before_add": added_ids_before,
                    "ids_after_add": all_ids,
                    "count_before_add": len(added_ids_before),
                    "count_after_add": len(all_ids),
                    "added_log_id": PHASE2_ADDED_LOG_ID,
                    "identity_preserved": all(
                        log_id in all_ids for log_id in added_ids_before
                    ),
                },
                "rigid_body": {
                    "fixed_dt_seconds": PHASE2_FIXED_DT_SECONDS,
                    "simulation_steps": PHASE2_TOTAL_FRAMES,
                    "simulation_wall_seconds": round(simulation_elapsed, 4),
                    "spawn_position_m": list(PHASE2_SPAWN_POSITION_M),
                    "final_position_m": _vector_as_list(final_position),
                    "dropped_distance_m": round(float(dropped_distance), 6),
                    "settled_displacement_last_second_m": round(
                        settled_displacement, 6
                    ),
                    "settled": settled_displacement < 0.03,
                    "inside_stone_ring": horizontal_radius < 1.30,
                    "resting_above_ground": final_position[2] > 0.15,
                },
                "emitter_follow": {
                    "samples": len(emitter_errors_m),
                    "offset_m": _vector_as_list(PHASE2_EMITTER_OFFSET_M),
                    "max_error_m": round(max(emitter_errors_m, default=0.0), 9),
                    "followed": max(emitter_errors_m, default=1.0) < 1e-5,
                },
                "flow": {
                    "active_blocks_final": active_block_counts[-1],
                    "active_blocks_peak": max(active_block_counts, default=0),
                },
                "timing": {
                    "warmup_steps_excluded": 30,
                    "physics_mean_ms": round(
                        statistics.fmean(physics_times_ms[30:]), 4
                    ),
                    "physics_p95_ms": round(physics_sorted[p95_index], 4),
                    "physics_simulate_mean_ms": round(
                        statistics.fmean(physics_simulate_times_ms[30:]), 4
                    ),
                    "physics_fetch_mean_ms": round(
                        statistics.fmean(physics_fetch_times_ms[30:]), 4
                    ),
                    "flow_and_render_update_mean_ms": round(
                        statistics.fmean(update_times_ms[30:]), 4
                    ),
                    "flow_and_render_update_p95_ms": round(
                        update_sorted[update_p95_index], 4
                    ),
                },
            }
            self._write_summary(output_dir, summary)
            carb.log_info(
                "[campfire.app] Phase 2 complete: "
                f"drop={summary['rigid_body']['dropped_distance_m']}m, "
                f"settled={summary['rigid_body']['settled']}, "
                f"physicsMeanMs={summary['timing']['physics_mean_ms']}"
            )
        finally:
            if attached_here and int(physics.get_attached_stage()) == stage_id:
                physics.detach_stage()
            settings.set(SETTING_UPDATE_TO_USD, previous_update_to_usd)
            settings.set("/physics/fabricEnabled", previous_fabric)
            _flowusd.release_flowusd_interface(flow_interface)

    async def _run_phase3(self, viewport, stage, scene_path: Path):
        """Compare dry/wet wood and drive Flow from released volatile mass."""

        output_dir = self._output_dir()
        settings = carb.settings.get_settings()
        extension_manager = omni.kit.app.get_app().get_extension_manager()
        debug_extension_status = {
            extension_id: bool(extension_manager.is_extension_enabled(extension_id))
            for extension_id in PHASE3_DEBUG_EXTENSION_IDS
        }
        array_backend = (
            settings.get_as_string(f"{SETTINGS_ROOT}/woodArrayBackend")
            or PYTHON_ARRAY_BACKEND
        )
        profile_wood_internals = settings.get_as_bool(
            f"{SETTINGS_ROOT}/woodInternalTiming"
        )
        profile_sensible_heat = settings.get_as_bool(
            f"{SETTINGS_ROOT}/woodSensibleHeatTiming"
        )
        python_constant_heat_capacity_fast_path = settings.get_as_bool(
            f"{SETTINGS_ROOT}/pythonConstantHeatCapacityFastPath"
        )
        python_homogeneous_heat_capacity_fast_path = settings.get_as_bool(
            f"{SETTINGS_ROOT}/pythonHomogeneousHeatCapacityFastPath"
        )
        python_inline_homogeneous_sensible_heat_capacity_fast_path = (
            settings.get_as_bool(
                f"{SETTINGS_ROOT}/pythonInlineHomogeneousSensibleHeatCapacityFastPath"
            )
        )
        python_slotted_wood_cell_storage = settings.get_as_bool(
            f"{SETTINGS_ROOT}/pythonSlottedWoodCellStorage"
        )
        collect_wood_state_diagnostics = settings.get_as_bool(
            f"{SETTINGS_ROOT}/woodStateDiagnostics"
        )
        python_surface_boundary_fast_path = settings.get_as_bool(
            f"{SETTINGS_ROOT}/pythonSurfaceBoundaryFastPath"
        )
        python_state_clamp_fast_path = settings.get_as_bool(
            f"{SETTINGS_ROOT}/pythonStateClampFastPath"
        )
        defer_cell_phase_updates = settings.get_as_bool(
            f"{SETTINGS_ROOT}/deferCellPhaseUpdates"
        )
        compact_runtime_metrics = settings.get_as_bool(
            f"{SETTINGS_ROOT}/compactRuntimeMetrics"
        )
        precomputed_runtime_topology = settings.get_as_bool(
            f"{SETTINGS_ROOT}/precomputedRuntimeTopology"
        )
        capture_video_frames = settings.get_as_bool(
            f"{SETTINGS_ROOT}/captureVideoFrames"
        )
        resident_snapshot_adapter_enabled = settings.get_as_bool(
            f"{SETTINGS_ROOT}/residentSnapshotAdapterEnabled"
        )
        resident_snapshot_timing_enabled = settings.get_as_bool(
            f"{SETTINGS_ROOT}/residentSnapshotTimingEnabled"
        )
        resident_snapshot_handle_cache_enabled = settings.get_as_bool(
            f"{SETTINGS_ROOT}/residentSnapshotHandleCacheEnabled"
        )
        resident_snapshot_lightweight_commit_enabled = settings.get_as_bool(
            f"{SETTINGS_ROOT}/residentSnapshotLightweightCommitEnabled"
        )
        resident_snapshot_skip_unchanged_enabled = settings.get_as_bool(
            f"{SETTINGS_ROOT}/residentSnapshotSkipUnchangedEnabled"
        )
        resident_snapshot_lightweight_tail_timing_enabled = settings.get_as_bool(
            f"{SETTINGS_ROOT}/residentSnapshotLightweightTailTimingEnabled"
        )
        resident_snapshot_lightweight_notice_coalescing_requested = settings.get_as_bool(
            f"{SETTINGS_ROOT}/residentSnapshotLightweightNoticeCoalescingEnabled"
        )
        resident_snapshot_lightweight_notice_coalescing_enabled = (
            resident_snapshot_lightweight_commit_enabled
            and resident_snapshot_lightweight_notice_coalescing_requested
        )
        resident_snapshot_lightweight_notice_tracking_enabled = settings.get_as_bool(
            f"{SETTINGS_ROOT}/residentSnapshotLightweightNoticeTrackingEnabled"
        )
        resident_native_backend_enabled = settings.get_as_bool(
            f"{SETTINGS_ROOT}/residentNativeBackendEnabled"
        )
        resident_native_library_path = settings.get_as_string(
            f"{SETTINGS_ROOT}/residentNativeLibraryPath"
        )
        video_frame_interval_steps = settings.get_as_int(
            f"{SETTINGS_ROOT}/videoFrameIntervalSteps"
        )
        if video_frame_interval_steps <= 0:
            video_frame_interval_steps = 20
        if array_backend not in (PYTHON_ARRAY_BACKEND, NUMPY_ARRAY_BACKEND):
            raise ValueError(f"Unsupported wood-step array backend: {array_backend}")
        if collect_wood_state_diagnostics and defer_cell_phase_updates:
            raise ValueError(
                "Wood state diagnostics are incompatible with deferred cell phases"
            )
        if profile_sensible_heat and not profile_wood_internals:
            raise ValueError("Sensible-heat timing requires wood internal timing")
        if profile_sensible_heat and array_backend != PYTHON_ARRAY_BACKEND:
            raise ValueError("Sensible-heat timing requires the Python backend")
        if (
            python_constant_heat_capacity_fast_path
            and array_backend != PYTHON_ARRAY_BACKEND
        ):
            raise ValueError(
                "Constant heat-capacity fast path requires the Python backend"
            )
        if (
            python_homogeneous_heat_capacity_fast_path
            and not python_constant_heat_capacity_fast_path
        ):
            raise ValueError(
                "Homogeneous heat-capacity fast path requires the constant-model "
                "fast path"
            )
        if (
            python_inline_homogeneous_sensible_heat_capacity_fast_path
            and not python_homogeneous_heat_capacity_fast_path
        ):
            raise ValueError(
                "Inline homogeneous sensible heat-capacity fast path requires "
                "the homogeneous heat-capacity fast path"
            )
        if profile_sensible_heat and not python_surface_boundary_fast_path:
            raise ValueError("Sensible-heat timing requires the fast surface path")
        if resident_snapshot_timing_enabled and not resident_snapshot_adapter_enabled:
            raise ValueError(
                "Resident snapshot timing requires the resident snapshot adapter"
            )
        if (
            resident_snapshot_handle_cache_enabled
            and not resident_snapshot_adapter_enabled
        ):
            raise ValueError(
                "Resident snapshot handle cache requires the resident snapshot adapter"
            )
        if resident_snapshot_lightweight_commit_enabled and not (
            resident_snapshot_adapter_enabled
            and resident_snapshot_handle_cache_enabled
        ):
            raise ValueError(
                "Resident snapshot lightweight commits require the adapter and handle cache"
            )
        if (
            resident_snapshot_lightweight_commit_enabled
            and resident_snapshot_timing_enabled
        ):
            raise ValueError(
                "Resident snapshot lightweight commits cannot use detailed transaction timing"
            )
        if (
            resident_snapshot_skip_unchanged_enabled
            and not resident_snapshot_lightweight_commit_enabled
        ):
            raise ValueError(
                "Resident snapshot unchanged-value skipping requires lightweight commits"
            )
        if (
            resident_snapshot_lightweight_tail_timing_enabled
            and not resident_snapshot_lightweight_commit_enabled
        ):
            raise ValueError(
                "Resident snapshot lightweight tail timing requires lightweight commits"
            )
        if resident_snapshot_lightweight_notice_tracking_enabled and not (
            resident_snapshot_lightweight_commit_enabled
            and resident_snapshot_handle_cache_enabled
        ):
            raise ValueError(
                "Resident snapshot lightweight notice tracking requires lightweight commits and handle cache"
            )
        if resident_native_backend_enabled and not resident_snapshot_adapter_enabled:
            raise ValueError(
                "Resident native backend requires the resident snapshot adapter"
            )
        if resident_native_backend_enabled and not resident_native_library_path:
            raise ValueError("Resident native backend requires an explicit library path")
        if resident_native_backend_enabled and (
            profile_wood_internals
            or profile_sensible_heat
            or collect_wood_state_diagnostics
        ):
            raise ValueError(
                "Resident native backend does not support Python wood instrumentation"
            )
        flow_interface = _flowusd.acquire_flowusd_interface()
        dry_prim = stage.GetPrimAtPath(f"/World/Logs/{PHASE3_DRY_LOG_ID}")
        wet_prim = stage.GetPrimAtPath(f"/World/Logs/{PHASE3_WET_LOG_ID}")
        dry_model = load_model_from_prim(dry_prim)
        wet_model = load_model_from_prim(wet_prim)
        models = {"dry": dry_model, "wet": wet_model}
        if python_slotted_wood_cell_storage:
            for model in models.values():
                model.use_slotted_cell_storage()
        runtime_topologies = (
            {
                name: model.capture_runtime_topology()
                for name, model in models.items()
            }
            if precomputed_runtime_topology
            else {"dry": None, "wet": None}
        )
        resident_native_backend = None
        resident_native_backend_status = None
        resident_native_export_ms = 0.0
        if resident_native_backend_enabled:
            resident_native_backend = ResidentNativeBackend(
                (dry_model, wet_model),
                resident_native_library_path,
                dt_seconds=PHASE3_MODEL_DT_SECONDS,
                heat_flux_w_m2=PHASE3_EXTERNAL_HEAT_FLUX_W_M2,
            )
        resident_adapter = None
        resident_timeline = None
        resident_timeline_was_playing = False
        resident_timeline_previous_time = 0.0
        resident_adapter_stopped = False
        resident_adapter_status = None
        resident_final_usd_state = None
        resident_transaction_profiles = ()
        resident_lightweight_tail_profiles = ()
        if resident_snapshot_adapter_enabled:
            resident_timeline = omni.timeline.get_timeline_interface()
            resident_timeline_was_playing = bool(resident_timeline.is_playing())
            resident_timeline_previous_time = float(
                resident_timeline.get_current_time()
            )
            log_ids = (PHASE3_DRY_LOG_ID, PHASE3_WET_LOG_ID)
            initial_dry_mass_kg = {
                log_id: sum(
                    cell.dry_wood_mass_kg + cell.char_mass_kg + cell.ash_mass_kg
                    for cell in model.cells
                )
                + model.emitted_pyrolysis_gas_kg
                + model.emitted_char_gas_kg
                for log_id, model in zip(log_ids, (dry_model, wet_model))
            }
            resident_adapter = UsdResidentSnapshotAdapter(
                stage,
                log_ids,
                initial_dry_mass_kg,
                profile_transactions=resident_snapshot_timing_enabled,
                cache_usd_handles=resident_snapshot_handle_cache_enabled,
                lightweight_commits=resident_snapshot_lightweight_commit_enabled,
                skip_unchanged_derived=resident_snapshot_skip_unchanged_enabled,
                profile_lightweight_tails=(
                    resident_snapshot_lightweight_tail_timing_enabled
                ),
                coalesce_lightweight_notices=(
                    resident_snapshot_lightweight_notice_coalescing_enabled
                ),
                track_lightweight_notices=(
                    resident_snapshot_lightweight_notice_tracking_enabled
                ),
            )
            self._resident_snapshot_adapter = resident_adapter
        ignition_seconds = {"dry": None, "wet": None}
        peak_gas_rate_kg_s = {"dry": 0.0, "wet": 0.0}
        model_step_times_ms = []
        metrics_times_ms = []
        source_mapping_times_ms = []
        row_build_times_ms = []
        flow_adapter_times_ms = []
        flow_emitter_usd_times_ms = []
        wood_visual_usd_times_ms = []
        resident_snapshot_usd_times_ms = []
        resident_snapshot_build_times_ms = []
        resident_snapshot_transaction_times_ms = []
        update_times_ms = []
        flow_update_steps = []
        active_block_query_times_ms = []
        capture_times_ms = []
        video_capture_times_ms = []
        step_loop_times_ms = []
        wood_internal_times_ms: dict[str, list[float]] = {}
        sensible_heat_internal_times_ms: dict[str, list[float]] = {}
        wood_state_diagnostics = (
            {"dry": {}, "wet": {}} if collect_wood_state_diagnostics else {}
        )
        active_block_counts = []
        images = []
        video_frames = []
        rows = []
        video_frames_dir = output_dir / "video_frames"
        if capture_video_frames:
            video_frames_dir.mkdir(parents=True, exist_ok=True)

        try:
            if resident_adapter is not None:
                resident_timeline.stop()
                resident_timeline.set_current_time(0.0)
                resident_timeline.play()
                resident_adapter.on_timeline_started()
            extension_to_scenario_seconds = (
                time.perf_counter() - self._extension_start_perf
            )
            simulation_started = time.perf_counter()
            for step_index in range(1, PHASE3_TOTAL_STEPS + 1):
                step_loop_started = time.perf_counter()
                model_started = time.perf_counter()
                dry_internal_timing = {} if profile_wood_internals else None
                wet_internal_timing = {} if profile_wood_internals else None
                dry_sensible_heat_timing = {} if profile_sensible_heat else None
                wet_sensible_heat_timing = {} if profile_sensible_heat else None
                native_step = None
                if resident_native_backend is not None:
                    native_step = resident_native_backend.step(tick=step_index)
                    dry_result, wet_result = native_step.results
                else:
                    dry_result = dry_model.step(
                        PHASE3_MODEL_DT_SECONDS,
                        PHASE3_EXTERNAL_HEAT_FLUX_W_M2,
                        timing_ms=dry_internal_timing,
                        sensible_heat_timing_ms=dry_sensible_heat_timing,
                        array_backend=array_backend,
                        python_surface_boundary_fast_path=(
                            python_surface_boundary_fast_path
                        ),
                        state_diagnostics=(
                            wood_state_diagnostics["dry"]
                            if collect_wood_state_diagnostics
                            else None
                        ),
                        python_state_clamp_fast_path=python_state_clamp_fast_path,
                        update_cell_phases=not defer_cell_phase_updates,
                        python_constant_heat_capacity_fast_path=(
                            python_constant_heat_capacity_fast_path
                        ),
                        python_homogeneous_heat_capacity_fast_path=(
                            python_homogeneous_heat_capacity_fast_path
                        ),
                        python_inline_homogeneous_sensible_heat_capacity_fast_path=(
                            python_inline_homogeneous_sensible_heat_capacity_fast_path
                        ),
                    )
                    wet_result = wet_model.step(
                        PHASE3_MODEL_DT_SECONDS,
                        PHASE3_EXTERNAL_HEAT_FLUX_W_M2,
                        timing_ms=wet_internal_timing,
                        sensible_heat_timing_ms=wet_sensible_heat_timing,
                        array_backend=array_backend,
                        python_surface_boundary_fast_path=(
                            python_surface_boundary_fast_path
                        ),
                        state_diagnostics=(
                            wood_state_diagnostics["wet"]
                            if collect_wood_state_diagnostics
                            else None
                        ),
                        python_state_clamp_fast_path=python_state_clamp_fast_path,
                        update_cell_phases=not defer_cell_phase_updates,
                        python_constant_heat_capacity_fast_path=(
                            python_constant_heat_capacity_fast_path
                        ),
                        python_homogeneous_heat_capacity_fast_path=(
                            python_homogeneous_heat_capacity_fast_path
                        ),
                        python_inline_homogeneous_sensible_heat_capacity_fast_path=(
                            python_inline_homogeneous_sensible_heat_capacity_fast_path
                        ),
                    )
                model_step_times_ms.append(
                    (time.perf_counter() - model_started) * 1000.0
                )
                if (
                    dry_internal_timing is not None
                    and wet_internal_timing is not None
                ):
                    if dry_internal_timing.keys() != wet_internal_timing.keys():
                        raise RuntimeError(
                            "Dry and wet wood internal timing segments differ"
                        )
                    for segment in dry_internal_timing:
                        wood_internal_times_ms.setdefault(segment, []).append(
                            dry_internal_timing[segment]
                            + wet_internal_timing[segment]
                        )
                if (
                    dry_sensible_heat_timing is not None
                    and wet_sensible_heat_timing is not None
                ):
                    if (
                        dry_sensible_heat_timing.keys()
                        != wet_sensible_heat_timing.keys()
                    ):
                        raise RuntimeError(
                            "Dry and wet sensible-heat timing segments differ"
                        )
                    for segment in dry_sensible_heat_timing:
                        sensible_heat_internal_times_ms.setdefault(
                            segment, []
                        ).append(
                            dry_sensible_heat_timing[segment]
                            + wet_sensible_heat_timing[segment]
                        )
                results = {"dry": dry_result, "wet": wet_result}

                for name, result in results.items():
                    peak_gas_rate_kg_s[name] = max(
                        peak_gas_rate_kg_s[name], result.pyrolysis_gas_rate_kg_s
                    )
                    if (
                        ignition_seconds[name] is None
                        and result.pyrolysis_gas_rate_kg_s
                        > PHASE3_IGNITION_RATE_KG_S
                    ):
                        ignition_seconds[name] = result.elapsed_seconds

                metrics_started = time.perf_counter()
                if native_step is not None:
                    dry_published, wet_published = native_step.snapshot.rows
                    dry_metrics = {
                        "surface_mean_temperature_k": dry_published.surface_mean_temperature_k,
                        "moisture_mass_kg": dry_published.moisture_mass_kg,
                        "dry_wood_mass_kg": dry_published.dry_wood_mass_kg,
                        "char_mass_kg": dry_published.char_mass_kg,
                        "ash_mass_kg": dry_published.ash_mass_kg,
                    }
                    wet_metrics = {
                        "surface_mean_temperature_k": wet_published.surface_mean_temperature_k,
                        "moisture_mass_kg": wet_published.moisture_mass_kg,
                        "dry_wood_mass_kg": wet_published.dry_wood_mass_kg,
                        "char_mass_kg": wet_published.char_mass_kg,
                        "ash_mass_kg": wet_published.ash_mass_kg,
                    }
                elif compact_runtime_metrics:
                    dry_metrics = dry_model.runtime_metrics(runtime_topologies["dry"])
                    wet_metrics = wet_model.runtime_metrics(runtime_topologies["wet"])
                else:
                    dry_metrics = dry_model.metrics()
                    wet_metrics = wet_model.metrics()
                metrics_times_ms.append(
                    (time.perf_counter() - metrics_started) * 1000.0
                )
                source_mapping_started = time.perf_counter()
                if native_step is not None:
                    source = FlowSourceState(
                        fuel=dry_published.flow_fuel,
                        temperature=dry_published.flow_temperature,
                        smoke=dry_published.flow_smoke,
                        pyrolysis_gas_rate_kg_s=(
                            dry_published.pyrolysis_gas_rate_kg_s
                        ),
                    )
                else:
                    source = flow_source_from_model(
                        dry_model,
                        dry_result,
                        surface_temperature_k=dry_metrics[
                            "surface_mean_temperature_k"
                        ],
                    )
                source_mapping_times_ms.append(
                    (time.perf_counter() - source_mapping_started) * 1000.0
                )
                row_build_started = time.perf_counter()
                rows.append(
                    {
                        "time_s": round(dry_result.elapsed_seconds, 6),
                        "dry_surface_temperature_k": dry_metrics[
                            "surface_mean_temperature_k"
                        ],
                        "dry_moisture_kg": dry_metrics["moisture_mass_kg"],
                        "dry_wood_kg": dry_metrics["dry_wood_mass_kg"],
                        "dry_char_kg": dry_metrics["char_mass_kg"],
                        "dry_ash_kg": dry_metrics["ash_mass_kg"],
                        "dry_pyrolysis_gas_rate_kg_s": dry_result.pyrolysis_gas_rate_kg_s,
                        "wet_surface_temperature_k": wet_metrics[
                            "surface_mean_temperature_k"
                        ],
                        "wet_moisture_kg": wet_metrics["moisture_mass_kg"],
                        "wet_wood_kg": wet_metrics["dry_wood_mass_kg"],
                        "wet_char_kg": wet_metrics["char_mass_kg"],
                        "wet_ash_kg": wet_metrics["ash_mass_kg"],
                        "wet_pyrolysis_gas_rate_kg_s": wet_result.pyrolysis_gas_rate_kg_s,
                        "flow_fuel": source.fuel,
                        "flow_temperature": source.temperature,
                    }
                )
                row_build_times_ms.append(
                    (time.perf_counter() - row_build_started) * 1000.0
                )

                update_flow = (
                    step_index % PHASE3_FLOW_UPDATE_INTERVAL_STEPS == 0
                    or step_index in PHASE3_CAPTURE_STEPS
                    or (
                        capture_video_frames
                        and step_index % video_frame_interval_steps == 0
                    )
                )
                if update_flow:
                    flow_update_steps.append(step_index)
                    adapter_started = time.perf_counter()
                    if resident_adapter is not None:
                        snapshot_build_started = time.perf_counter()
                        if native_step is not None:
                            snapshot = native_step.snapshot
                        else:
                            wet_source = flow_source_from_model(
                                wet_model,
                                wet_result,
                                surface_temperature_k=wet_metrics[
                                    "surface_mean_temperature_k"
                                ],
                            )
                            snapshot = ResidentPublishedSnapshot(
                                revision=step_index,
                                tick=step_index,
                                log_ids=(PHASE3_DRY_LOG_ID, PHASE3_WET_LOG_ID),
                                rows=(
                                    published_row_from_python_model(
                                        dry_model, dry_metrics, source
                                    ),
                                    published_row_from_python_model(
                                        wet_model, wet_metrics, wet_source
                                    ),
                                ),
                            )
                        resident_snapshot_build_times_ms.append(
                            (time.perf_counter() - snapshot_build_started) * 1000.0
                        )
                        transaction_started = time.perf_counter()
                        resident_adapter.publish(snapshot)
                        resident_snapshot_transaction_times_ms.append(
                            (time.perf_counter() - transaction_started) * 1000.0
                        )
                        resident_snapshot_usd_times_ms.append(
                            (time.perf_counter() - adapter_started) * 1000.0
                        )
                    else:
                        flow_emitter_started = time.perf_counter()
                        update_flow_source(stage, PHASE3_DRY_LOG_ID, source)
                        flow_emitter_usd_times_ms.append(
                            (time.perf_counter() - flow_emitter_started) * 1000.0
                        )
                        if step_index % 10 == 0 or step_index in PHASE3_CAPTURE_STEPS:
                            wood_visual_started = time.perf_counter()
                            apply_model_visual_state(
                                dry_prim,
                                dry_model,
                                dry_metrics,
                                initial_dry_mass_kg=(
                                    runtime_topologies["dry"].initial_dry_mass_kg
                                    if runtime_topologies["dry"] is not None
                                    else None
                                ),
                            )
                            apply_model_visual_state(
                                wet_prim,
                                wet_model,
                                wet_metrics,
                                initial_dry_mass_kg=(
                                    runtime_topologies["wet"].initial_dry_mass_kg
                                    if runtime_topologies["wet"] is not None
                                    else None
                                ),
                            )
                            wood_visual_usd_times_ms.append(
                                (time.perf_counter() - wood_visual_started) * 1000.0
                            )
                    flow_adapter_times_ms.append(
                        (time.perf_counter() - adapter_started) * 1000.0
                    )
                    update_started = time.perf_counter()
                    await omni.kit.app.get_app().next_update_async()
                    update_times_ms.append(
                        (time.perf_counter() - update_started) * 1000.0
                    )
                    active_block_query_started = time.perf_counter()
                    active_block_count = int(flow_interface.get_active_block_count())
                    active_block_query_times_ms.append(
                        (time.perf_counter() - active_block_query_started) * 1000.0
                    )
                    active_block_counts.append(active_block_count)

                    if step_index in PHASE3_CAPTURE_STEPS:
                        image_path = output_dir / f"frame_{step_index:04d}.png"
                        capture_started = time.perf_counter()
                        resolution = await self._capture_image(viewport, image_path)
                        capture_wall_seconds = time.perf_counter() - capture_started
                        capture_times_ms.append(capture_wall_seconds * 1000.0)
                        images.append(
                            {
                                "step": step_index,
                                "model_time_seconds": dry_result.elapsed_seconds,
                                "path": str(image_path),
                                "resolution": list(resolution),
                                "dry_flow_fuel": source.fuel,
                                "capture_wall_seconds": round(
                                    capture_wall_seconds, 4
                                ),
                            }
                        )
                    if (
                        capture_video_frames
                        and step_index % video_frame_interval_steps == 0
                    ):
                        video_frame_index = len(video_frames) + 1
                        video_frame_path = (
                            video_frames_dir / f"frame_{video_frame_index:04d}.png"
                        )
                        video_capture_started = time.perf_counter()
                        video_resolution = await self._capture_image(
                            viewport, video_frame_path
                        )
                        video_capture_wall_seconds = (
                            time.perf_counter() - video_capture_started
                        )
                        video_capture_times_ms.append(
                            video_capture_wall_seconds * 1000.0
                        )
                        video_frames.append(
                            {
                                "index": video_frame_index,
                                "step": step_index,
                                "model_time_seconds": dry_result.elapsed_seconds,
                                "path": str(video_frame_path),
                                "resolution": list(video_resolution),
                                "dry_flow_fuel": source.fuel,
                                "capture_wall_seconds": round(
                                    video_capture_wall_seconds, 4
                                ),
                            }
                        )
                step_loop_times_ms.append(
                    (time.perf_counter() - step_loop_started) * 1000.0
                )

            if resident_native_backend is not None:
                resident_native_backend_status = resident_native_backend.close()
                resident_native_export_ms = resident_native_backend_status["export_ms"]

            if resident_adapter is not None:
                resident_adapter.on_timeline_stopped()
                resident_timeline.pause()
                resident_adapter_stopped = True
                resident_adapter_status = resident_adapter.status()
                resident_transaction_profiles = (
                    resident_adapter.transaction_profiles()
                )
                resident_lightweight_tail_profiles = (
                    resident_adapter.lightweight_tail_profiles()
                )
                emitter = stage.GetPrimAtPath(FLOW_EMITTER_PATH)
                resident_final_usd_state = {
                    "emitter": {
                        "revision": emitter.GetAttribute(
                            "campfire:residentRevision"
                        ).Get(),
                        "fuel": emitter.GetAttribute("fuel").Get(),
                        "temperature": emitter.GetAttribute("temperature").Get(),
                        "smoke": emitter.GetAttribute("smoke").Get(),
                    },
                    "logs": {
                        log_id: {
                            "revision": prim.GetAttribute(
                                "campfire:residentRevision"
                            ).Get(),
                            "surface_temperature_k": prim.GetAttribute(
                                "campfire:surfaceTemperatureK"
                            ).Get(),
                            "char_fraction": prim.GetAttribute(
                                "campfire:charFraction"
                            ).Get(),
                            "remaining_mass_ratio": prim.GetAttribute(
                                "campfire:remainingMassRatio"
                            ).Get(),
                            "weakest_support_ratio": prim.GetAttribute(
                                "campfire:weakestSupportRatio"
                            ).Get(),
                        }
                        for log_id, prim in (
                            (PHASE3_DRY_LOG_ID, dry_prim),
                            (PHASE3_WET_LOG_ID, wet_prim),
                        )
                    },
                }
                revisions = [resident_final_usd_state["emitter"]["revision"]]
                revisions.extend(
                    state["revision"]
                    for state in resident_final_usd_state["logs"].values()
                )
                resident_final_usd_state["revision_consistent"] = (
                    len(set(revisions)) == 1
                    and revisions[0] == resident_adapter_status["revision"]
                )

            phase_refresh_started = time.perf_counter()
            if defer_cell_phase_updates:
                dry_model.refresh_cell_phases()
                wet_model.refresh_cell_phases()
            final_phase_refresh_seconds = time.perf_counter() - phase_refresh_started
            simulation_elapsed = time.perf_counter() - simulation_started
            persistence_started = time.perf_counter()
            save_model_to_prim(dry_model, dry_prim)
            save_model_to_prim(wet_model, wet_prim)
            persistence_seconds = time.perf_counter() - persistence_started
            export_started = time.perf_counter()
            final_stage_path = export_stage(stage, output_dir / "final_stage.usda")
            export_seconds = time.perf_counter() - export_started
            metrics_path = output_dir / "wood_metrics.csv"
            csv_started = time.perf_counter()
            with metrics_path.open("w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            csv_seconds = time.perf_counter() - csv_started
            metrics_csv_sha256 = hashlib.sha256(metrics_path.read_bytes()).hexdigest()
            finalization_seconds = persistence_seconds + export_seconds + csv_seconds

            model_measured = model_step_times_ms[20:]
            model_sorted = sorted(model_measured)
            update_measured = update_times_ms[20:]
            update_sorted = sorted(update_measured)
            adapter_measured = flow_adapter_times_ms[2:]
            adapter_sorted = sorted(adapter_measured)
            model_p95_index = min(
                len(model_sorted) - 1, int(len(model_sorted) * 0.95)
            )
            update_p95_index = min(
                len(update_sorted) - 1, int(len(update_sorted) * 0.95)
            )
            adapter_p95_index = min(
                len(adapter_sorted) - 1, int(len(adapter_sorted) * 0.95)
            )
            step_warmup_samples = 20
            flow_warmup_samples = 4
            visual_warmup_samples = 2
            resident_transaction_profile = None
            if resident_transaction_profiles:
                profile_warmup_samples = flow_warmup_samples
                operation_fields = (
                    "total_ms",
                    "validation_ms",
                    "prim_lookup_ms",
                    "payload_preparation_ms",
                    "attribute_lookup_ms",
                    "old_value_capture_ms",
                    "journal_append_ms",
                    "attribute_set_ms",
                    "value_audit_ms",
                    "write_observer_ms",
                    "commit_ms",
                    "rollback_ms",
                    "unattributed_ms",
                )
                group_names = tuple(
                    name for name, _value in resident_transaction_profiles[0].group_ms
                )
                attribute_names = tuple(
                    name
                    for name, _value in resident_transaction_profiles[0].attribute_ms
                )
                measured_profiles = resident_transaction_profiles[
                    profile_warmup_samples:
                ]
                group_dispositions = [
                    {
                        name: (changed, unchanged)
                        for name, changed, unchanged in profile.group_write_disposition
                    }
                    for profile in measured_profiles
                ]
                attribute_dispositions = [
                    dict(profile.attribute_write_disposition)
                    for profile in measured_profiles
                ]
                attribute_set_disposition = {}
                for name in attribute_names:
                    attribute_set_disposition[name] = {}
                    for disposition_name in ("changed", "unchanged"):
                        disposition_values = [
                            dict(profile.attribute_set_detail_ms)[name]
                            for profile, disposition in zip(
                                measured_profiles, attribute_dispositions
                            )
                            if disposition[name] == disposition_name
                        ]
                        attribute_set_disposition[name][disposition_name] = (
                            summarize_timing_ms(disposition_values, 0)
                            if disposition_values
                            else None
                        )
                resident_transaction_profile = {
                    "sample_count": len(measured_profiles),
                    "warmup_samples_excluded": profile_warmup_samples,
                    "status_counts": {
                        status: sum(
                            profile.status == status
                            for profile in resident_transaction_profiles
                        )
                        for status in ("committed", "rolled_back")
                    },
                    "operations": {
                        name: summarize_timing_ms(
                            [
                                getattr(profile, name)
                                for profile in resident_transaction_profiles
                            ],
                            profile_warmup_samples,
                        )
                        for name in operation_fields
                    },
                    "groups": {
                        name: summarize_timing_ms(
                            [
                                dict(profile.group_ms)[name]
                                for profile in resident_transaction_profiles
                            ],
                            profile_warmup_samples,
                        )
                        for name in group_names
                    },
                    "attributes": {
                        name: summarize_timing_ms(
                            [
                                dict(profile.attribute_ms)[name]
                                for profile in resident_transaction_profiles
                            ],
                            profile_warmup_samples,
                        )
                        for name in attribute_names
                    },
                    "attribute_set": {
                        name: summarize_timing_ms(
                            [
                                dict(profile.attribute_set_detail_ms)[name]
                                for profile in resident_transaction_profiles
                            ],
                            profile_warmup_samples,
                        )
                        for name in attribute_names
                    },
                    "attribute_set_disposition": attribute_set_disposition,
                    "counts": {
                        name: {
                            "minimum": min(getattr(profile, name) for profile in measured_profiles),
                            "maximum": max(getattr(profile, name) for profile in measured_profiles),
                        }
                        for name in (
                            "write_count",
                            "changed_write_count",
                            "unchanged_write_count",
                            "existing_property_count",
                            "created_property_count",
                            "authored_old_value_count",
                        )
                    },
                    "write_disposition": {
                        "changed": sum(
                            profile.changed_write_count
                            for profile in measured_profiles
                        ),
                        "unchanged": sum(
                            profile.unchanged_write_count
                            for profile in measured_profiles
                        ),
                        "groups": {
                            name: {
                                "changed": sum(
                                    disposition[name][0]
                                    for disposition in group_dispositions
                                ),
                                "unchanged": sum(
                                    disposition[name][1]
                                    for disposition in group_dispositions
                                ),
                            }
                            for name in group_dispositions[0]
                        },
                        "attributes": {
                            name: {
                                "changed": sum(
                                    disposition[name] == "changed"
                                    for disposition in attribute_dispositions
                                ),
                                "unchanged": sum(
                                    disposition[name] == "unchanged"
                                    for disposition in attribute_dispositions
                                ),
                            }
                            for name in attribute_dispositions[0]
                        },
                    },
                }
            resident_lightweight_tail_profile = None
            if resident_lightweight_tail_profiles:
                tail_warmup_samples = max(0, flow_warmup_samples - 1)
                measured_tail_profiles = resident_lightweight_tail_profiles[
                    tail_warmup_samples:
                ]
                tail_operation_fields = (
                    "total_ms",
                    "validation_ms",
                    "prim_lookup_ms",
                    "payload_preparation_ms",
                    "attribute_lookup_ms",
                    "attribute_set_ms",
                    "write_observer_ms",
                    "commit_ms",
                    "recovery_ms",
                    "unattributed_ms",
                )
                tail_group_names = tuple(
                    sorted(
                        {
                            name
                            for profile in measured_tail_profiles
                            for name, _value in profile.group_ms
                        }
                    )
                )
                flow_samples_by_step = {
                    step: {
                        "outer_transaction_ms": transaction_ms,
                        "flow_render_update_ms": update_ms,
                        "active_block_count": active_count,
                    }
                    for step, transaction_ms, update_ms, active_count in zip(
                        flow_update_steps,
                        resident_snapshot_transaction_times_ms,
                        update_times_ms,
                        active_block_counts,
                    )
                }
                tail_samples = []
                for profile in measured_tail_profiles:
                    correlated = flow_samples_by_step[profile.tick]
                    tail_samples.append(
                        {
                            "revision": profile.revision,
                            "tick": profile.tick,
                            "status": profile.status,
                            "profile_total_ms": profile.total_ms,
                            "outer_transaction_ms": correlated[
                                "outer_transaction_ms"
                            ],
                            "flow_render_update_ms": correlated[
                                "flow_render_update_ms"
                            ],
                            "active_block_count": correlated[
                                "active_block_count"
                            ],
                            "operations_ms": {
                                name: getattr(profile, name)
                                for name in tail_operation_fields
                            },
                            "groups_ms": dict(profile.group_ms),
                            "write_count": profile.write_count,
                            "skipped_write_count": profile.skipped_write_count,
                            "group_write_disposition": {
                                name: {"written": written, "skipped": skipped}
                                for name, written, skipped in (
                                    profile.group_write_disposition
                                )
                            },
                        }
                    )
                resident_lightweight_tail_profile = {
                    "sample_count": len(measured_tail_profiles),
                    "warmup_samples_excluded": tail_warmup_samples + 1,
                    "seed_transaction_profiled": False,
                    "status_counts": {
                        status: sum(
                            profile.status == status
                            for profile in resident_lightweight_tail_profiles
                        )
                        for status in ("committed", "recovered", "faulted")
                    },
                    "operations": {
                        name: summarize_timing_ms(
                            [
                                getattr(profile, name)
                                for profile in measured_tail_profiles
                            ]
                        )
                        for name in tail_operation_fields
                    },
                    "groups": {
                        name: summarize_timing_ms(
                            [
                                dict(profile.group_ms).get(name, 0.0)
                                for profile in measured_tail_profiles
                            ]
                        )
                        for name in tail_group_names
                    },
                    "counts": {
                        name: {
                            "minimum": min(
                                getattr(profile, name)
                                for profile in measured_tail_profiles
                            ),
                            "maximum": max(
                                getattr(profile, name)
                                for profile in measured_tail_profiles
                            ),
                        }
                        for name in ("write_count", "skipped_write_count")
                    },
                    "samples": tail_samples,
                }
            startup_known_seconds = sum(self._startup_timing.values())
            startup_timing = {
                **self._startup_timing,
                "extension_to_scenario_seconds": round(
                    extension_to_scenario_seconds, 4
                ),
                "unattributed_extension_seconds": round(
                    max(0.0, extension_to_scenario_seconds - startup_known_seconds),
                    4,
                ),
            }
            detailed_timing = {
                "step_loop": summarize_timing_ms(
                    step_loop_times_ms, step_warmup_samples
                ),
                "wood_model_step": summarize_timing_ms(
                    model_step_times_ms, step_warmup_samples
                ),
                "wood_metrics": summarize_timing_ms(
                    metrics_times_ms, step_warmup_samples
                ),
                "flow_source_mapping": summarize_timing_ms(
                    source_mapping_times_ms, step_warmup_samples
                ),
                "csv_row_build": summarize_timing_ms(
                    row_build_times_ms, step_warmup_samples
                ),
                "flow_emitter_usd": (
                    summarize_timing_ms(
                        flow_emitter_usd_times_ms, flow_warmup_samples
                    )
                    if flow_emitter_usd_times_ms
                    else None
                ),
                "wood_visual_usd": (
                    summarize_timing_ms(
                        wood_visual_usd_times_ms, visual_warmup_samples
                    )
                    if wood_visual_usd_times_ms
                    else None
                ),
                "resident_snapshot_usd": (
                    summarize_timing_ms(
                        resident_snapshot_usd_times_ms, flow_warmup_samples
                    )
                    if resident_snapshot_usd_times_ms
                    else None
                ),
                "resident_snapshot_build": (
                    summarize_timing_ms(
                        resident_snapshot_build_times_ms, flow_warmup_samples
                    )
                    if resident_snapshot_build_times_ms
                    else None
                ),
                "resident_snapshot_transaction": (
                    summarize_timing_ms(
                        resident_snapshot_transaction_times_ms,
                        flow_warmup_samples,
                    )
                    if resident_snapshot_transaction_times_ms
                    else None
                ),
                "kit_flow_render_update": summarize_timing_ms(
                    update_times_ms, flow_warmup_samples
                ),
                "active_block_query": summarize_timing_ms(
                    active_block_query_times_ms, flow_warmup_samples
                ),
                "viewport_capture": summarize_timing_ms(capture_times_ms),
            }
            wood_internal_timing = {
                segment: summarize_timing_ms(values, step_warmup_samples)
                for segment, values in wood_internal_times_ms.items()
            }
            sensible_heat_internal_timing = {
                segment: summarize_timing_ms(values, step_warmup_samples)
                for segment, values in sensible_heat_internal_times_ms.items()
            }

            model_summaries = {}
            for name, model in models.items():
                metrics = model.metrics()
                model_summaries[name] = {
                    **{key: round(value, 9) if isinstance(value, float) else value
                       for key, value in metrics.items()},
                    "ignition_seconds": (
                        round(ignition_seconds[name], 6)
                        if ignition_seconds[name] is not None
                        else None
                    ),
                    "peak_pyrolysis_gas_rate_kg_s": round(
                        peak_gas_rate_kg_s[name], 9
                    ),
                    "all_values_finite": all(
                        math.isfinite(cell.temperature_k)
                        and math.isfinite(cell.current_mass_kg)
                        for cell in model.cells
                    ),
                    "non_negative_mass": all(
                        min(
                            cell.moisture_mass_kg,
                            cell.dry_wood_mass_kg,
                            cell.char_mass_kg,
                            cell.ash_mass_kg,
                        )
                        >= 0.0
                        for cell in model.cells
                    ),
                    "authoritative_state_sha256": hashlib.sha256(
                        json.dumps(
                            model.to_dict(),
                            allow_nan=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        ).encode("utf-8")
                    ).hexdigest(),
                }

            summary = {
                "status": "ok",
                "phase": "phase3",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "scene": str(scene_path),
                "final_stage": str(final_stage_path),
                "metrics_csv": str(metrics_path),
                "metrics_csv_sha256": metrics_csv_sha256,
                "camera": str(CAMERA_PATH),
                "resolution": list(CAPTURE_RESOLUTION),
                "images": images,
                "video_frames": {
                    "enabled": capture_video_frames,
                    "interval_steps": video_frame_interval_steps,
                    "model_seconds_per_frame": round(
                        PHASE3_MODEL_DT_SECONDS * video_frame_interval_steps, 6
                    ),
                    "frames": video_frames,
                    "capture_timing": (
                        summarize_timing_ms(video_capture_times_ms)
                        if video_capture_times_ms
                        else {
                            "sample_count": 0,
                            "warmup_samples_excluded": 0,
                            "total_ms": 0.0,
                            "mean_ms": 0.0,
                            "p95_ms": 0.0,
                            "max_ms": 0.0,
                        }
                    ),
                },
                "startup": startup_timing,
                "scenario": {
                    "wood_array_backend": array_backend,
                    "wood_internal_timing_enabled": profile_wood_internals,
                    "wood_sensible_heat_timing_enabled": profile_sensible_heat,
                    "python_constant_heat_capacity_fast_path": (
                        python_constant_heat_capacity_fast_path
                    ),
                    "python_homogeneous_heat_capacity_fast_path": (
                        python_homogeneous_heat_capacity_fast_path
                    ),
                    "python_inline_homogeneous_sensible_heat_capacity_fast_path": (
                        python_inline_homogeneous_sensible_heat_capacity_fast_path
                    ),
                    "python_slotted_wood_cell_storage": (
                        python_slotted_wood_cell_storage
                    ),
                    "wood_state_diagnostics_enabled": (
                        collect_wood_state_diagnostics
                    ),
                    "wood_state_diagnostics": wood_state_diagnostics,
                    "python_surface_boundary_fast_path": (
                        python_surface_boundary_fast_path
                    ),
                    "python_state_clamp_fast_path": python_state_clamp_fast_path,
                    "deferred_cell_phase_updates": defer_cell_phase_updates,
                    "compact_runtime_metrics": compact_runtime_metrics,
                    "precomputed_runtime_topology": precomputed_runtime_topology,
                    "resident_snapshot_adapter": {
                        "enabled": resident_snapshot_adapter_enabled,
                        "transaction_timing_enabled": (
                            resident_snapshot_timing_enabled
                        ),
                        "handle_cache_enabled": (
                            resident_snapshot_handle_cache_enabled
                        ),
                        "lightweight_commit_enabled": (
                            resident_snapshot_lightweight_commit_enabled
                        ),
                        "skip_unchanged_derived_enabled": (
                            resident_snapshot_skip_unchanged_enabled
                        ),
                        "lightweight_tail_timing_enabled": (
                            resident_snapshot_lightweight_tail_timing_enabled
                        ),
                        "lightweight_notice_coalescing_enabled": (
                            resident_snapshot_lightweight_notice_coalescing_enabled
                        ),
                        "lightweight_notice_tracking_enabled": (
                            resident_snapshot_lightweight_notice_tracking_enabled
                        ),
                        "producer": (
                            "resident_native_backend"
                            if resident_native_backend_enabled
                            else "python_contract_bridge"
                            if resident_snapshot_adapter_enabled
                            else "disabled"
                        ),
                        "native_producer_connected": resident_native_backend_enabled,
                        "native_backend": {
                            "enabled": resident_native_backend_enabled,
                            "library_path": (
                                resident_native_library_path
                                if resident_native_backend_enabled
                                else ""
                            ),
                            "status_after_close": resident_native_backend_status,
                            "shutdown_export_ms": resident_native_export_ms,
                        },
                        "status_after_timeline_stop": resident_adapter_status,
                        "final_usd_state": resident_final_usd_state,
                        "transaction_profile": resident_transaction_profile,
                        "lightweight_tail_profile": (
                            resident_lightweight_tail_profile
                        ),
                    },
                    "final_phase_refresh_seconds": round(
                        final_phase_refresh_seconds, 6
                    ),
                    "zero_area_cell_count": {
                        name: sum(
                            cell.external_area_m2 * cell.surface_exposure == 0.0
                            for cell in model.cells
                        )
                        for name, model in models.items()
                    },
                    "debug_extension_status": debug_extension_status,
                    "debugger_free": not any(debug_extension_status.values()),
                    "model_dt_seconds": PHASE3_MODEL_DT_SECONDS,
                    "flow_update_interval_steps": PHASE3_FLOW_UPDATE_INTERVAL_STEPS,
                    "flow_update_interval_seconds": (
                        PHASE3_MODEL_DT_SECONDS * PHASE3_FLOW_UPDATE_INTERVAL_STEPS
                    ),
                    "steps": PHASE3_TOTAL_STEPS,
                    "model_duration_seconds": round(dry_model.elapsed_seconds, 6),
                    "external_heat_flux_w_m2": PHASE3_EXTERNAL_HEAT_FLUX_W_M2,
                    "simulation_wall_seconds": round(simulation_elapsed, 4),
                },
                "wood": model_summaries,
                "comparison": {
                    "both_ignited": all(
                        ignition_seconds[name] is not None for name in models
                    ),
                    "wet_ignition_delayed": (
                        ignition_seconds["dry"] is not None
                        and ignition_seconds["wet"] is not None
                        and ignition_seconds["wet"] > ignition_seconds["dry"]
                    ),
                    "wet_delay_seconds": (
                        round(ignition_seconds["wet"] - ignition_seconds["dry"], 6)
                        if all(ignition_seconds[name] is not None for name in models)
                        else None
                    ),
                },
                "flow": {
                    "input_owner": "wood thermal model",
                    "active_blocks_final": active_block_counts[-1],
                    "active_blocks_peak": max(active_block_counts, default=0),
                    "peak_fuel_input": round(max(row["flow_fuel"] for row in rows), 6),
                },
                "timing": {
                    "warmup_steps_excluded": 20,
                    "two_log_model_step_mean_ms": round(
                        statistics.fmean(model_measured), 4
                    ),
                    "two_log_model_step_p95_ms": round(
                        model_sorted[model_p95_index], 4
                    ),
                    "flow_adapter_update_mean_ms": round(
                        statistics.fmean(adapter_measured), 4
                    ),
                    "flow_adapter_update_p95_ms": round(
                        adapter_sorted[adapter_p95_index], 4
                    ),
                    "flow_and_render_update_mean_ms": round(
                        statistics.fmean(update_measured), 4
                    ),
                    "flow_and_render_update_p95_ms": round(
                        update_sorted[update_p95_index], 4
                    ),
                    "segments": detailed_timing,
                    "wood_model_internal_segments": wood_internal_timing,
                    "wood_sensible_heat_segments": sensible_heat_internal_timing,
                    "wood_model_internal_total_mean_ms": round(
                        sum(
                            segment["mean_ms"]
                            for segment in wood_internal_timing.values()
                        ),
                        4,
                    ),
                    "finalization": {
                        "model_persistence_seconds": round(
                            persistence_seconds, 4
                        ),
                        "stage_export_seconds": round(export_seconds, 4),
                        "metrics_csv_seconds": round(csv_seconds, 4),
                        "total_seconds": round(finalization_seconds, 4),
                    },
                },
            }
            self._write_summary(output_dir, summary)
            carb.log_info(
                "[campfire.app] Phase 3 complete: "
                f"dryIgnition={ignition_seconds['dry']}s, "
                f"wetIgnition={ignition_seconds['wet']}s, "
                f"modelMeanMs={summary['timing']['two_log_model_step_mean_ms']}"
            )
        finally:
            try:
                if resident_native_backend is not None:
                    resident_native_backend.close()
                if resident_adapter is not None:
                    if not resident_adapter_stopped:
                        resident_adapter.on_timeline_stopped()
                    resident_adapter.close()
                    self._resident_snapshot_adapter = None
                if resident_timeline is not None:
                    resident_timeline.pause()
                    resident_timeline.set_current_time(
                        resident_timeline_previous_time
                    )
                    if resident_timeline_was_playing:
                        resident_timeline.play()
            finally:
                _flowusd.release_flowusd_interface(flow_interface)

    @staticmethod
    def _write_summary(output_dir: Path, summary: dict) -> None:
        (output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
