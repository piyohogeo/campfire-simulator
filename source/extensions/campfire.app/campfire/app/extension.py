"""Campfire Simulator application bootstrap and headless validation extension."""

import asyncio
import json
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
from .wood import get_log_world_position, list_log_ids


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
            if phase == "phase2":
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
                if phase == "phase2":
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

    @staticmethod
    def _write_summary(output_dir: Path, summary: dict) -> None:
        (output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
