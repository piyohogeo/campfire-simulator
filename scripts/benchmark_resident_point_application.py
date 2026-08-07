"""Qualify the default-off pre-authored Resident Point application scene."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import carb
import omni.kit.app
import omni.kit.viewport.utility
import omni.timeline
import omni.usd
from omni.flowusd import _flowusd
from pxr import Tf, Usd, UsdGeom, UsdShade

import campfire.app
from campfire.app.phase3_scene import (
    PHASE3_EXTERNAL_HEAT_FLUX_W_M2,
    PHASE3_MODEL_DT_SECONDS,
)


FLOW_VERSION = "110.0.0"
CAPTURE_RESOLUTION = (1280, 720)
VIDEO_FRAME_COUNT = 60
WARMUP_STEPS = 650
LOG_IDS = (campfire.app.PHASE3_DRY_LOG_ID, campfire.app.PHASE3_WET_LOG_ID)


def _settings():
    settings = carb.settings.get_settings()
    return settings, {
        "native_library": Path(settings.get_as_string("/phase6ch/nativeLibrary")),
        "output": Path(settings.get_as_string("/phase6ch/output")),
        "video_frames": Path(settings.get_as_string("/phase6ch/videoFrames")),
    }


def _new_phase3_stage(path):
    path.unlink(missing_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    campfire.app.populate_phase3_scene(stage)
    return stage


def _models(stage):
    return tuple(
        campfire.app.load_model_from_prim(
            stage.GetPrimAtPath(f"/World/Logs/{log_id}")
        )
        for log_id in LOG_IDS
    )


def _layout_inputs(stage, np):
    origins = np.asarray(
        [
            tuple(campfire.app.get_log_world_position(stage, log_id))
            for log_id in LOG_IDS
        ],
        dtype=np.float64,
    )
    # Both authoritative Phase 3 logs are cylinders whose local axial direction
    # is +X and whose authored Z rotation is zero.
    axes = np.asarray([0, 0], dtype=np.uint32)
    return origins, axes


def _save(stage, path):
    if not stage.GetRootLayer().Save():
        raise RuntimeError(f"Failed to save offline application stage: {path}")


def _readback(flow_interface):
    names = ("temperature", "fuel", "burn", "smoke", "velocity", "divergence")
    raw = flow_interface.get_latest_nanovdb_readback()
    result = {}
    for index, name in enumerate(names):
        value = raw[index] if index < len(raw) else []
        result[name] = int(getattr(value, "size", len(value)))
    return result


async def _capture(viewport, path):
    capture = omni.kit.viewport.utility.capture_viewport_to_file(
        viewport, file_path=str(path)
    )
    if not await capture.wait_for_result(completion_frames=2):
        raise RuntimeError(f"Point application frame capture failed: {path}")
    for _ in range(30):
        if path.is_file():
            return
        await omni.kit.app.get_app().next_update_async()
    raise RuntimeError(f"Point application frame was not written: {path}")


async def _run(settings, arguments):
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    output = arguments["output"].resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    video_frames = arguments["video_frames"].resolve()
    video_frames.mkdir(parents=True, exist_ok=True)
    for old_frame in video_frames.glob("frame_*.png"):
        old_frame.unlink()
    fallback_path = output.with_suffix(".fallback.usda")
    point_path = output.with_suffix(".point.usda")
    session = None
    listener = None
    timeline_subscription = None
    flow_interface = None
    report = None
    exit_code = 1
    try:
        opt_in = campfire.app.resident_point_application_enabled(settings)
        if not opt_in:
            raise RuntimeError("Phase 6CH requires the explicit Point application opt-in")

        fallback_stage = _new_phase3_stage(fallback_path)
        fallback_contract = {
            "sphere_type": fallback_stage.GetPrimAtPath(
                campfire.app.FLOW_EMITTER_PATH
            ).GetTypeName(),
            "sphere_enabled": fallback_stage.GetPrimAtPath(
                campfire.app.FLOW_EMITTER_PATH
            ).GetAttribute("enabled").Get(),
            "point_exists": bool(
                fallback_stage.GetPrimAtPath(
                    campfire.app.RESIDENT_POINT_EMITTER_PATH
                )
            ),
        }
        _save(fallback_stage, fallback_path)
        del fallback_stage
        opened, open_error = await context.open_stage_async(str(fallback_path))
        if not opened or open_error:
            raise RuntimeError(f"Sphere fallback stage failed to connect: {open_error}")
        connected_fallback = context.get_stage()
        fallback_contract["connected"] = bool(connected_fallback)
        fallback_contract["connected_sphere_enabled"] = connected_fallback.GetPrimAtPath(
            campfire.app.FLOW_EMITTER_PATH
        ).GetAttribute("enabled").Get()
        closed, close_error = await context.close_stage_async()
        if not closed or close_error:
            raise RuntimeError(f"Sphere fallback stage failed to close: {close_error}")

        offline_stage = _new_phase3_stage(point_path)
        models = _models(offline_stage)
        backend = campfire.app.ResidentNativeBackend(
            models,
            arguments["native_library"],
            dt_seconds=PHASE3_MODEL_DT_SECONDS,
            heat_flux_w_m2=PHASE3_EXTERNAL_HEAT_FLUX_W_M2,
        )
        origins, axes = _layout_inputs(offline_stage, backend._np)
        producer = campfire.app.ResidentNativeSurfaceProducer(
            backend, origins, axes
        )
        producer.build_layout()
        scene_contract = campfire.app.configure_resident_point_application_scene(
            offline_stage, producer.positions
        )
        offline_stage.GetRootLayer().customLayerData = {
            **offline_stage.GetRootLayer().customLayerData,
            "campfire:phase": "phase6ch",
            "campfire:flowVersion": FLOW_VERSION,
            "campfire:stageBuiltBeforeConnection": True,
        }
        _save(offline_stage, point_path)
        del offline_stage

        opened, open_error = await context.open_stage_async(str(point_path))
        if not opened or open_error:
            raise RuntimeError(f"Point application stage failed to connect: {open_error}")
        stage = context.get_stage()
        emitter = stage.GetPrimAtPath(campfire.app.RESIDENT_POINT_EMITTER_PATH)
        source = stage.GetPrimAtPath(campfire.app.RESIDENT_POINT_SOURCE_PATH)
        relationship = emitter.GetRelationship("pointsPrim")
        bound_material, _ = UsdShade.MaterialBindingAPI(source).ComputeBoundMaterial()
        connected_contract = {
            "emitter_type": emitter.GetTypeName(),
            "source_is_points": source.IsA(UsdGeom.Points),
            "layer": emitter.GetAttribute("layer").Get(),
            "relationship_targets": [str(path) for path in relationship.GetTargets()],
            "material": str(bound_material.GetPath()) if bound_material else None,
            "point_count": len(emitter.GetAttribute("pointPositions").Get()),
            "sphere_retained": bool(stage.GetPrimAtPath(campfire.app.FLOW_EMITTER_PATH)),
            "sphere_enabled": stage.GetPrimAtPath(
                campfire.app.FLOW_EMITTER_PATH
            ).GetAttribute("enabled").Get(),
        }

        stage_slot = {"stage": stage}
        sidecar = campfire.app.ResidentPointSidecar(
            backend,
            stage,
            campfire.app.RESIDENT_POINT_EMITTER_PATH,
            lambda: stage_slot["stage"],
            origins,
            axes,
        )
        initial_dry_mass = {
            log_id: sum(cell.dry_wood_mass_kg for cell in model.cells)
            for log_id, model in zip(LOG_IDS, models)
        }
        adapter = campfire.app.UsdResidentSnapshotAdapter(
            stage,
            LOG_IDS,
            initial_dry_mass,
            cache_usd_handles=True,
            lightweight_commits=True,
            skip_unchanged_derived=True,
            coalesce_lightweight_notices=True,
        )
        session = campfire.app.ResidentApplicationSession(
            backend, adapter, sidecar=sidecar
        )

        point_resyncs = []
        point_changes = []
        point_prefix = str(campfire.app.RESIDENT_POINT_EMITTER_PATH)

        def observe(notice, _sender):
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

        listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, observe, stage)
        timeline_events = []
        timeline_event_names = {
            int(omni.timeline.TimelineEventType.PLAY): "PLAY",
            int(omni.timeline.TimelineEventType.PAUSE): "PAUSE",
            int(omni.timeline.TimelineEventType.STOP): "STOP",
        }

        def observe_timeline(event):
            name = timeline_event_names.get(event.type)
            if name is not None:
                timeline_events.append(name)

        timeline_subscription = (
            timeline.get_timeline_event_stream().create_subscription_to_pop(
                observe_timeline, 0, "phase6ch timeline probe"
            )
        )
        viewport = None
        for _ in range(120):
            viewport = omni.kit.viewport.utility.get_active_viewport()
            if viewport is not None:
                break
            await app.next_update_async()
        if viewport is None:
            raise RuntimeError("No viewport for Resident Point application qualification")
        viewport.camera_path = campfire.app.CAMERA_PATH
        viewport.fill_frame = False
        viewport.resolution = CAPTURE_RESOLUTION

        timeline.stop()
        timeline.set_current_time(0.0)
        session.start()
        timeline.play()
        timeline_playing_during_run = bool(timeline.is_playing())
        flow_interface = _flowusd.acquire_flowusd_interface()
        active_blocks = []
        for tick in range(1, WARMUP_STEPS + 1):
            session.step(tick=tick)
            if tick % 5 == 0:
                await app.next_update_async()
                active_blocks.append(int(flow_interface.get_active_block_count()))

        for frame in range(VIDEO_FRAME_COUNT):
            tick = WARMUP_STEPS + frame + 1
            result = session.step(tick=tick)
            await app.next_update_async()
            active_blocks.append(int(flow_interface.get_active_block_count()))
            await _capture(viewport, video_frames / f"frame_{frame:04d}.png")
        timeline.pause()
        await app.next_update_async()
        readback = _readback(flow_interface)
        session.stop()
        stopped_status = session.status()
        revisions = (
            stopped_status["backend"]["revision"],
            stopped_status["adapter"]["revision"],
            stopped_status["sidecar"]["revision"],
        )
        close_result = session.close()
        session = None
        timeline_paused_after_run = not timeline.is_playing()
        listener.Revoke()
        listener = None
        _flowusd.release_flowusd_interface(flow_interface)
        flow_interface = None
        unique_frames = len(
            {
                hashlib.sha256(path.read_bytes()).hexdigest()
                for path in video_frames.glob("frame_*.png")
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
        gates = {
            "explicit_setting_enabled": opt_in,
            "sphere_fallback_connects_unchanged": (
                fallback_contract["sphere_type"] == "FlowEmitterSphere"
                and fallback_contract["sphere_enabled"]
                and not fallback_contract["point_exists"]
                and fallback_contract["connected"]
                and fallback_contract["connected_sphere_enabled"]
            ),
            "point_graph_complete_before_connection": (
                scene_contract["point_count"] == 720
                and scene_contract["emitter_count"] == 1
                and connected_contract["emitter_type"] == "FlowEmitterPoint"
                and connected_contract["source_is_points"]
            ),
            "layer_zero": connected_contract["layer"] == 0,
            "relationship_connected": connected_contract["relationship_targets"]
            == [str(campfire.app.RESIDENT_POINT_SOURCE_PATH)],
            "material_bound": connected_contract["material"]
            == "/World/Materials/ResidentPointSource",
            "fallback_sphere_retained_disabled": (
                connected_contract["sphere_retained"]
                and not connected_contract["sphere_enabled"]
            ),
            "timeline_started_and_stopped": (
                (timeline_playing_during_run or "PLAY" in timeline_events)
                and timeline_paused_after_run
                and any(event in timeline_events for event in ("PAUSE", "STOP"))
                and stopped_status["start_count"] == 1
                and stopped_status["stop_count"] == 1
            ),
            "consumer_revisions_match": len(set(revisions)) == 1,
            "only_existing_point_properties_changed_live": (
                not point_resyncs and not unexpected_point_changes
            ),
            "flow_core_active": max(active_blocks, default=0) > 0,
            "fuel_temperature_smoke_present": all(
                readback[name] > 0
                for name in ("fuel", "temperature", "smoke", "burn")
            ),
            "continuous_video": (
                len(list(video_frames.glob("frame_*.png"))) == VIDEO_FRAME_COUNT
                and unique_frames >= 55
            ),
            "clean_shutdown": (
                not close_result["backend"]["active"]
                and close_result["adapter_closed"]
                and close_result["sidecar_closed"]
                and context.get_stage() is stage
            ),
        }
        report = {
            "schema_version": 1,
            "phase": "phase6ch",
            "status": "ok" if all(gates.values()) else "failed",
            "scope": {
                "flow_version": FLOW_VERSION,
                "default_off": True,
                "point_count": scene_contract["point_count"],
                "surface_points_per_log": 360,
                "log_count": len(LOG_IDS),
                "emitter_count": 1,
                "canonical_scene_changed": False,
                "production_default_changed": False,
            },
            "fallback": fallback_contract,
            "scene": {**scene_contract, **connected_contract},
            "lifecycle": {
                "timeline_playing_during_run": timeline_playing_during_run,
                "timeline_paused_after_run": timeline_paused_after_run,
                "timeline_events": timeline_events,
                "stopped_session": stopped_status,
                "close": close_result,
                "stage_release": "Kit shutdown after Resident resources close",
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
                "video_frame_count": VIDEO_FRAME_COUNT,
                "unique_video_frame_hashes": unique_frames,
                "final_tick": result.snapshot.tick,
            },
            "gates": gates,
        }
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if not all(gates.values()):
            failed = [name for name, passed in gates.items() if not passed]
            raise RuntimeError(f"Phase 6CH gates failed: {failed}")
        exit_code = 0
    except asyncio.CancelledError:
        raise
    except Exception as error:
        if report is None:
            output.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "phase": "phase6ch",
                        "status": "error",
                        "error": f"{type(error).__name__}: {error}",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        carb.log_error(f"[phase6ch] {type(error).__name__}: {error}")
    finally:
        if listener is not None:
            listener.Revoke()
        timeline_subscription = None
        if flow_interface is not None:
            _flowusd.release_flowusd_interface(flow_interface)
        if session is not None:
            try:
                session.close(discard_pending=True)
            except Exception:
                pass
        app.post_uncancellable_quit(exit_code)


def main():
    settings, arguments = _settings()
    asyncio.ensure_future(_run(settings, arguments))


if __name__ == "__main__":
    main()
