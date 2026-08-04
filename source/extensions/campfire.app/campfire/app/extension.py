"""Campfire Simulator application bootstrap and headless validation extension."""

import asyncio
import csv
import json
import math
import statistics
import struct
import time
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
from pxr import Gf, UsdPhysics, UsdUtils

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
from .combustion import flow_source_from_model, load_model_from_prim, save_model_to_prim
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
from .wood import get_log_world_position, list_log_ids
from .calibration import (
    run_nist_plywood_calibration,
    write_calibration_svg,
    write_holdout_svg,
    write_layer_profile_svg,
    write_replicate_holdout_svg,
)
from .phase6_scene import (
    apply_phase6_calibration,
    export_phase6_stage,
    populate_phase6_scene,
)


SETTINGS_ROOT = "/exts/campfire.app"
CAPTURE_RESOLUTION = (1280, 720)


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
        extension_manager = omni.kit.app.get_app().get_extension_manager()
        self._extension_path = Path(extension_manager.get_extension_path(ext_id)).resolve()
        self._control_window = None
        self._startup_task = asyncio.ensure_future(self._initialize())
        carb.log_info("[campfire.app] Extension startup")

    def on_shutdown(self):
        if self._startup_task and not self._startup_task.done():
            self._startup_task.cancel()
        self._startup_task = None
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
        try:
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
                populate_phase3_scene(stage)
                scene_path = export_phase3_stage(
                    stage, repo_root / "assets" / "scenes" / "phase3_thermal.usda"
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
            carb.log_info(f"[campfire.app] {phase} scene exported to {scene_path}")

            viewport = await self._get_viewport()
            if viewport is not None:
                viewport.camera_path = CAMERA_PATH
                viewport.fill_frame = False
                viewport.resolution = CAPTURE_RESOLUTION

            if capture_requested:
                if viewport is None:
                    raise RuntimeError(f"No active viewport is available for {phase} capture")
                await self._wait_for_capture_resolution(viewport)
                if phase == "phase6":
                    await self._capture_phase6(viewport, stage, scene_path)
                elif phase == "phase5":
                    await self._run_phase5(viewport, stage, scene_path)
                elif phase == "phase4":
                    await self._capture_phase4(viewport, stage, scene_path)
                elif phase == "phase3":
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
        candidates_path = output_dir / "top_candidates.csv"
        with candidates_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=(
                    "rank",
                    "score_rmse_relative",
                    "radiant_absorptivity",
                    "pyrolysis_start_temperature_k",
                    "pyrolysis_full_temperature_k",
                    "pyrolysis_max_fraction_s",
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
        flow_interface = _flowusd.acquire_flowusd_interface()
        dry_prim = stage.GetPrimAtPath(f"/World/Logs/{PHASE3_DRY_LOG_ID}")
        wet_prim = stage.GetPrimAtPath(f"/World/Logs/{PHASE3_WET_LOG_ID}")
        dry_model = load_model_from_prim(dry_prim)
        wet_model = load_model_from_prim(wet_prim)
        models = {"dry": dry_model, "wet": wet_model}
        ignition_seconds = {"dry": None, "wet": None}
        peak_gas_rate_kg_s = {"dry": 0.0, "wet": 0.0}
        model_step_times_ms = []
        flow_adapter_times_ms = []
        update_times_ms = []
        active_block_counts = []
        images = []
        rows = []

        try:
            simulation_started = time.perf_counter()
            for step_index in range(1, PHASE3_TOTAL_STEPS + 1):
                model_started = time.perf_counter()
                dry_result = dry_model.step(
                    PHASE3_MODEL_DT_SECONDS, PHASE3_EXTERNAL_HEAT_FLUX_W_M2
                )
                wet_result = wet_model.step(
                    PHASE3_MODEL_DT_SECONDS, PHASE3_EXTERNAL_HEAT_FLUX_W_M2
                )
                model_step_times_ms.append(
                    (time.perf_counter() - model_started) * 1000.0
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

                source = flow_source_from_model(dry_model, dry_result)

                dry_metrics = dry_model.metrics()
                wet_metrics = wet_model.metrics()
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

                update_flow = (
                    step_index % PHASE3_FLOW_UPDATE_INTERVAL_STEPS == 0
                    or step_index in PHASE3_CAPTURE_STEPS
                )
                if update_flow:
                    adapter_started = time.perf_counter()
                    update_flow_source(stage, PHASE3_DRY_LOG_ID, source)
                    if step_index % 10 == 0 or step_index in PHASE3_CAPTURE_STEPS:
                        apply_model_visual_state(dry_prim, dry_model)
                        apply_model_visual_state(wet_prim, wet_model)
                    flow_adapter_times_ms.append(
                        (time.perf_counter() - adapter_started) * 1000.0
                    )
                    update_started = time.perf_counter()
                    await omni.kit.app.get_app().next_update_async()
                    update_times_ms.append(
                        (time.perf_counter() - update_started) * 1000.0
                    )
                    active_block_counts.append(
                        int(flow_interface.get_active_block_count())
                    )

                    if step_index in PHASE3_CAPTURE_STEPS:
                        image_path = output_dir / f"frame_{step_index:04d}.png"
                        resolution = await self._capture_image(viewport, image_path)
                        images.append(
                            {
                                "step": step_index,
                                "model_time_seconds": dry_result.elapsed_seconds,
                                "path": str(image_path),
                                "resolution": list(resolution),
                                "dry_flow_fuel": source.fuel,
                            }
                        )

            simulation_elapsed = time.perf_counter() - simulation_started
            save_model_to_prim(dry_model, dry_prim)
            save_model_to_prim(wet_model, wet_prim)
            final_stage_path = export_stage(stage, output_dir / "final_stage.usda")
            metrics_path = output_dir / "wood_metrics.csv"
            with metrics_path.open("w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)

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
                }

            summary = {
                "status": "ok",
                "phase": "phase3",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "scene": str(scene_path),
                "final_stage": str(final_stage_path),
                "metrics_csv": str(metrics_path),
                "camera": str(CAMERA_PATH),
                "resolution": list(CAPTURE_RESOLUTION),
                "images": images,
                "scenario": {
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
            _flowusd.release_flowusd_interface(flow_interface)

    @staticmethod
    def _write_summary(output_dir: Path, summary: dict) -> None:
        (output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
