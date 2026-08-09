"""Qualify Point surface payload ownership inside ResidentApplicationSession."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import math
import sys
import time
from pathlib import Path

import carb
import omni.kit.app
import omni.kit.viewport.utility
import omni.timeline
import omni.usd
from omni.flowusd import _flowusd
from pxr import Gf, Sdf, Tf, Usd, UsdGeom

import campfire.app


ROOT = Path(__file__).resolve().parents[1]
SURFACE_BENCHMARK = ROOT / "scripts" / "benchmark_resident_surface_point.py"
VIDEO_FRAME_COUNT = 60


def _load_surface_module():
    spec = importlib.util.spec_from_file_location("campfire_phase6cd_surface", SURFACE_BENCHMARK)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load surface benchmark: {SURFACE_BENCHMARK}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


surface = _load_surface_module()
core = surface.core


def _settings():
    settings = carb.settings.get_settings()
    return {
        "native_library": Path(settings.get_as_string("/phase6cd/nativeLibrary")),
        "output": Path(settings.get_as_string("/phase6cd/output")),
        "video_frames": Path(settings.get_as_string("/phase6cd/videoFrames")),
    }


ImmutableSurfacePayload = campfire.app.ImmutableSurfacePayload


class ResidentPointSidecar(campfire.app.ResidentPointSidecar):
    """Supply the fixed Phase 6CD layout to the production sidecar module."""

    def __init__(
        self,
        backend,
        stage,
        emitter_path,
        stage_provider,
        write_observer=None,
        *,
        initial_revision=0,
        initial_layout=None,
    ):
        if initial_layout is None:
            origins, axes = surface._origins_and_axes(backend._np)
        else:
            origins = axes = None
        super().__init__(
            backend,
            stage,
            emitter_path,
            stage_provider,
            origins,
            axes,
            write_observer,
            initial_revision=initial_revision,
            initial_layout=initial_layout,
        )


def _augment_stage(path, log_ids):
    handles = core._build_stage(path, surface.POINT_COUNT, 1)
    stage = Usd.Stage.Open(str(path))
    logs = UsdGeom.Xform.Define(stage, "/World/Logs")
    for index, log_id in enumerate(log_ids):
        cube = UsdGeom.Cube.Define(stage, f"/World/Logs/{log_id}")
        cube.CreateSizeAttr(0.1)
        cube.CreateDisplayColorAttr([Gf.Vec3f(0.3, 0.12, 0.045)])
        cube.AddTranslateOp().Set(Gf.Vec3d(-1.0 + 0.1 * index, -0.8, 0.1))
        prim = cube.GetPrim()
        for name, type_name, value in (
            ("campfire:surfaceTemperatureK", Sdf.ValueTypeNames.Double, 293.15),
            ("campfire:charFraction", Sdf.ValueTypeNames.Double, 0.0),
            ("campfire:remainingMassRatio", Sdf.ValueTypeNames.Double, 1.0),
            ("campfire:weakestSupportRatio", Sdf.ValueTypeNames.Double, 1.0),
            ("campfire:residentRevision", Sdf.ValueTypeNames.Int64, 0),
        ):
            prim.CreateAttribute(name, type_name).Set(value)
    emitter = stage.DefinePrim(campfire.app.FLOW_EMITTER_PATH, "FlowEmitterSphere")
    core._set(emitter, "layer", 0)
    core._set(emitter, "enabled", False)
    for name in ("fuel", "temperature", "smoke", "coupleRateFuel", "coupleRateTemperature", "coupleRateSmoke"):
        core._set(emitter, name, 0.0)
    emitter.CreateAttribute("campfire:residentRevision", Sdf.ValueTypeNames.Int64).Set(0)
    point_emitter = stage.GetPrimAtPath(handles[0]["path"])
    point_emitter.CreateAttribute(
        "campfire:layoutRepresentation", Sdf.ValueTypeNames.Token
    ).Set(campfire.app.RESIDENT_POINT_LAYOUT_REPRESENTATION_LEGACY)
    stage.GetRootLayer().customLayerData = {
        **stage.GetRootLayer().customLayerData,
        "campfire:phase": "phase6cd",
        "campfire:sessionSidecarBuiltBeforeConnection": True,
    }
    if not stage.GetRootLayer().Save():
        raise RuntimeError("Failed to save Phase 6CD stage")
    return handles


async def _capture_one(viewport, path):
    capture = omni.kit.viewport.utility.capture_viewport_to_file(viewport, file_path=str(path))
    if not await capture.wait_for_result(completion_frames=2):
        raise RuntimeError(f"Video frame capture failed: {path}")
    for _ in range(30):
        if path.is_file():
            return path
        await omni.kit.app.get_app().next_update_async()
    raise RuntimeError(f"Video frame was not written: {path}")


async def _run(arguments):
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    output = arguments["output"].resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    video_frames = arguments["video_frames"].resolve()
    video_frames.mkdir(parents=True, exist_ok=True)
    for old in video_frames.glob("frame_*.png"):
        old.unlink()
    stage_path = output.with_suffix(".scene.usda")
    session = None
    listener = None
    flow_interface = None
    report = None
    exit_code = 1
    try:
        models = surface._models()
        log_ids = tuple(model.spec.log_id for model in models)
        handles = _augment_stage(stage_path, log_ids)
        await context.open_stage_async(str(stage_path))
        stage = context.get_stage()
        backend = campfire.app.ResidentNativeBackend(
            models,
            arguments["native_library"],
            dt_seconds=surface.DT_SECONDS,
            heat_flux_w_m2=surface.HEAT_FLUX_W_M2,
        )
        point_failure = {"revision": None}
        primary_failure = {"revision": None, "writes": 0}
        stage_slot = {"stage": stage}

        def point_observer(_index, _name, payload):
            if payload.revision == point_failure["revision"]:
                point_failure["revision"] = None
                raise RuntimeError("Injected Point sidecar publication failure")

        def primary_observer(_index, _name):
            if primary_failure["revision"] == backend.revision:
                primary_failure["writes"] += 1
                if primary_failure["writes"] == 3:
                    primary_failure["revision"] = None
                    raise RuntimeError("Injected primary snapshot publication failure")

        sidecar = ResidentPointSidecar(
            backend,
            stage,
            handles[0]["path"],
            lambda: stage_slot["stage"],
            write_observer=point_observer,
        )
        initial_dry_mass = {
            log_id: sum(cell.dry_wood_mass_kg for cell in model.cells)
            for log_id, model in zip(log_ids, models)
        }
        adapter = campfire.app.UsdResidentSnapshotAdapter(
            stage,
            log_ids,
            initial_dry_mass,
            write_observer=primary_observer,
            cache_usd_handles=True,
            lightweight_commits=True,
            skip_unchanged_derived=True,
            coalesce_lightweight_notices=True,
        )
        session = campfire.app.ResidentApplicationSession(
            backend, adapter, sidecar=sidecar
        )

        resyncs = []
        listener = Tf.Notice.Register(
            Usd.Notice.ObjectsChanged,
            lambda notice, _sender: resyncs.extend(str(path) for path in notice.GetResyncedPaths()),
            stage,
        )
        session.start()
        first = session.step(tick=1)
        point_failure["revision"] = 2
        point_failure_rejected = False
        try:
            session.step(tick=2)
        except RuntimeError as error:
            point_failure_rejected = "Point sidecar" in str(error)
        point_pending = session.status()
        point_failure_payload_id = sidecar.attempt_payload_ids[-1]
        point_failure_digest = sidecar.attempt_payload_digests[-1]
        blocked_tick = False
        try:
            session.step(tick=3)
        except RuntimeError as error:
            blocked_tick = "pending snapshot retry" in str(error)
        session.stop()
        session.start()
        retry_two = session.retry_pending()
        point_retry_payload_id = sidecar.attempt_payload_ids[-1]
        point_retry_digest = sidecar.attempt_payload_digests[-1]

        primary_failure["revision"] = 3
        primary_failure["writes"] = 0
        primary_failure_rejected = False
        try:
            session.step(tick=3)
        except RuntimeError as error:
            primary_failure_rejected = "primary snapshot" in str(error)
        primary_pending = session.status()
        retry_three = session.retry_pending()

        running_layout_rejected = False
        moved_origins = sidecar._producer.origins.copy()
        moved_origins[0, 0] += 0.03
        moved_layout = {"revision": 2, "origins": moved_origins, "axes": sidecar._producer.axes.copy()}
        try:
            session.replace_sidecar_layout(moved_layout)
        except RuntimeError as error:
            running_layout_rejected = "ready or stopped" in str(error)
        positions_before_move = bytes(sidecar._last_snapshot.positions)
        session.stop()
        replaced_layout_revision = session.replace_sidecar_layout(moved_layout)
        session.start()
        moved = session.step(tick=4)
        positions_after_move = bytes(sidecar._last_snapshot.positions)

        viewport = None
        for _ in range(120):
            viewport = omni.kit.viewport.utility.get_active_viewport()
            if viewport is not None:
                break
            await app.next_update_async()
        if viewport is None:
            raise RuntimeError("No active viewport")
        viewport.camera_path = core.CAMERA_PATH
        viewport.fill_frame = False
        viewport.resolution = core.CAPTURE_RESOLUTION
        flow_interface = _flowusd.acquire_flowusd_interface()
        active_blocks = []
        timeline.play()
        next_tick = 5
        for _ in range(90):
            session.step(tick=next_tick)
            next_tick += 1
            await app.next_update_async()
            active_blocks.append(int(flow_interface.get_active_block_count()))
        for frame in range(VIDEO_FRAME_COUNT):
            if frame % 2 == 0:
                session.step(tick=next_tick)
                next_tick += 1
            await app.next_update_async()
            active_blocks.append(int(flow_interface.get_active_block_count()))
            await _capture_one(viewport, video_frames / f"frame_{frame:04d}.png")
        readback = core._readback(flow_interface)
        timeline.pause()
        revisions_before_replacement = (
            session.status()["backend"]["revision"],
            session.status()["adapter"]["revision"],
            session.status()["sidecar"]["revision"],
        )

        stage_slot["stage"] = Usd.Stage.CreateInMemory()
        stage_replacement_rejected = False
        try:
            session.step(tick=next_tick)
        except RuntimeError as error:
            stage_replacement_rejected = "replaced stage" in str(error)
        replacement_pending = session.status()
        close_result = session.close(discard_pending=True)
        session = None

        relevant_resyncs = sorted(
            path for path in set(resyncs)
            if path.startswith(str(core.FLOW_ROOT)) or path.startswith("/World/PointSource")
        )
        gates = {
            "first_snapshot_and_point_revision_commit": first.snapshot.revision == 1,
            "point_failure_rolls_back_before_primary": (
                point_failure_rejected
                and point_pending["backend"]["revision"] == 2
                and point_pending["adapter"]["revision"] == 1
                and point_pending["sidecar"]["revision"] == 1
            ),
            "pending_blocks_next_tick": blocked_tick,
            "point_retry_reuses_exact_payload": (
                retry_two.snapshot.revision == 2
                and point_failure_payload_id == point_retry_payload_id
                and point_failure_digest == point_retry_digest
            ),
            "primary_failure_rolls_sidecar_back": (
                primary_failure_rejected
                and primary_pending["backend"]["revision"] == 3
                and primary_pending["adapter"]["revision"] == 2
                and primary_pending["sidecar"]["revision"] == 2
                and primary_pending["sidecar"]["rollback_count"] == 1
            ),
            "primary_retry_commits_same_revision": (
                retry_three.snapshot.revision == 3
                and sidecar.status()["revision"] >= 3
            ),
            "layout_change_requires_stopped_owner": running_layout_rejected,
            "layout_revision_moves_positions": (
                replaced_layout_revision == 2
                and moved.snapshot.revision == 4
                and positions_before_move != positions_after_move
                and sidecar.status()["committed_layout_revision"] == 2
            ),
            "continuous_video_frames_exact": len(list(video_frames.glob("frame_*.png"))) == VIDEO_FRAME_COUNT,
            "flow_core_and_fields_active": (
                max(active_blocks, default=0) > 0
                and all(readback[name] > 0 for name in ("temperature", "fuel", "burn", "smoke", "velocity"))
            ),
            "no_live_structural_resync_before_replacement": not relevant_resyncs,
            "stage_replacement_fails_closed": (
                stage_replacement_rejected
                and replacement_pending["pending_revision"] == next_tick
                and replacement_pending["adapter"]["revision"] == revisions_before_replacement[1]
                and replacement_pending["sidecar"]["revision"] == revisions_before_replacement[2]
            ),
            "forced_close_records_pending_discard": close_result["pending_discarded"],
            "production_activation_unchanged": True,
        }
        report = {
            "schema_version": 1,
            "phase": "phase6cd",
            "status": "ok" if all(gates.values()) else "failed",
            "scope": {
                "default_off": True,
                "flow_version": core.FLOW_VERSION,
                "point_count": surface.POINT_COUNT,
                "emitter_count": 1,
                "production_activation_changed": False,
                "canonical_scene_changed": False,
            },
            "contract": {
                "owner": "ResidentApplicationSession owner thread",
                "pending_value": "ResidentNativeStep plus identical ImmutableSurfacePayload",
                "publish_order": "Point sidecar then primary snapshot adapter",
                "primary_failure_recovery": "rollback Point sidecar to previous immutable revision",
                "layout_change": "ready/stopped only, monotonic layout revision",
                "stage_replacement": "fail closed before Point writes",
            },
            "checkpoints": {
                "point_failure": point_pending,
                "primary_failure": primary_pending,
                "before_stage_replacement": revisions_before_replacement,
                "stage_replacement": replacement_pending,
                "close": close_result,
            },
            "flow": {
                "active_blocks_peak": max(active_blocks, default=0),
                "readback_words": readback,
                "video_frame_count": VIDEO_FRAME_COUNT,
                "video_frames": str(video_frames),
            },
            "gates": gates,
        }
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if not all(gates.values()):
            raise RuntimeError(f"Phase 6CD gates failed: {[name for name, value in gates.items() if not value]}")
        exit_code = 0
    except asyncio.CancelledError:
        raise
    except Exception as error:
        if report is None:
            output.write_text(
                json.dumps({"schema_version": 1, "phase": "phase6cd", "status": "error", "error": f"{type(error).__name__}: {error}"}, indent=2) + "\n",
                encoding="utf-8",
            )
        carb.log_error(f"[phase6cd] {type(error).__name__}: {error}")
    finally:
        if listener is not None:
            listener.Revoke()
        if flow_interface is not None:
            _flowusd.release_flowusd_interface(flow_interface)
        if session is not None:
            try:
                session.close(discard_pending=True)
            except Exception:
                pass
        app.post_uncancellable_quit(exit_code)


def main():
    asyncio.ensure_future(_run(_settings()))


if __name__ == "__main__":
    main()
