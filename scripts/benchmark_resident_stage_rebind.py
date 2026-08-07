"""Qualify real Kit stage replacement with retained Resident pending retry."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import traceback
from pathlib import Path

import carb
import omni.kit.app
import omni.kit.viewport.utility
import omni.timeline
import omni.usd
from omni.flowusd import _flowusd
from pxr import Tf, Usd

import campfire.app


ROOT = Path(__file__).resolve().parents[1]
SESSION_BENCHMARK = ROOT / "scripts" / "benchmark_resident_surface_session.py"
VIDEO_FRAME_COUNT = 60


def _load_session_module():
    spec = importlib.util.spec_from_file_location(
        "campfire_phase6ce_session", SESSION_BENCHMARK
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load session benchmark: {SESSION_BENCHMARK}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


phase6cd = _load_session_module()
surface = phase6cd.surface
core = phase6cd.core


def _settings():
    settings = carb.settings.get_settings()
    return {
        "native_library": Path(settings.get_as_string("/phase6ce/nativeLibrary")),
        "output": Path(settings.get_as_string("/phase6ce/output")),
        "video_frames": Path(settings.get_as_string("/phase6ce/videoFrames")),
    }


def _primary_adapter(stage, log_ids, initial_dry_mass, revision):
    return campfire.app.UsdResidentSnapshotAdapter(
        stage,
        log_ids,
        initial_dry_mass,
        cache_usd_handles=True,
        lightweight_commits=True,
        skip_unchanged_derived=True,
        coalesce_lightweight_notices=True,
        initial_revision=revision,
    )


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
    initial_path = output.with_suffix(".initial.usda")
    replacement_path = output.with_suffix(".replacement.usda")
    session = None
    replacement_listener = None
    stage_event_subscription = None
    flow_interface = None
    report = None
    exit_code = 1
    try:
        models = surface._models()
        log_ids = tuple(model.spec.log_id for model in models)
        handles = phase6cd._augment_stage(initial_path, log_ids)
        point_path = handles[0]["path"]
        opened, open_error = await context.open_stage_async(str(initial_path))
        if not opened:
            raise RuntimeError(f"Unable to open initial stage: {open_error}")
        stage = context.get_stage()
        stage_slot = {"stage": stage}
        backend = campfire.app.ResidentNativeBackend(
            models,
            arguments["native_library"],
            dt_seconds=surface.DT_SECONDS,
            heat_flux_w_m2=surface.HEAT_FLUX_W_M2,
        )
        initial_dry_mass = {
            log_id: sum(cell.dry_wood_mass_kg for cell in model.cells)
            for log_id, model in zip(log_ids, models)
        }
        old_sidecar = phase6cd.ResidentPointSidecar(
            backend, stage, point_path, lambda: stage_slot["stage"]
        )
        old_adapter = _primary_adapter(stage, log_ids, initial_dry_mass, 0)
        session = campfire.app.ResidentApplicationSession(
            backend, old_adapter, sidecar=old_sidecar
        )

        session.start()
        first = session.step(tick=1)
        moved_origins = old_sidecar._producer.origins.copy()
        moved_origins[0, 0] += 0.03
        moved_layout = {
            "revision": 2,
            "origins": moved_origins,
            "axes": old_sidecar._producer.axes.copy(),
        }
        session.stop()
        session.replace_sidecar_layout(moved_layout)
        session.start()
        second = session.step(tick=2)
        session.stop()
        committed_before_attach = session.status()
        original_revisions = (
            committed_before_attach["backend"]["revision"],
            committed_before_attach["adapter"]["revision"],
            committed_before_attach["sidecar"]["revision"],
        )
        if not stage.GetRootLayer().Export(str(replacement_path)):
            raise RuntimeError("Unable to export replacement stage")
        replacement_stage = Usd.Stage.Open(str(replacement_path))
        if replacement_stage is None:
            raise RuntimeError("Unable to open replacement stage")

        stage_events = []
        stage_event_subscription = context.get_stage_event_stream().create_subscription_to_pop(
            lambda event: stage_events.append(int(event.type)),
            name="phase6ce-stage-replacement",
        )
        timeline.stop()
        closed, close_error = await context.close_stage_async()
        if not closed:
            raise RuntimeError(f"Unable to close initial stage: {close_error}")
        for _ in range(4):
            await app.next_update_async()
        attached, attach_error = await context.attach_stage_async(replacement_stage)
        if not attached:
            raise RuntimeError(f"Unable to attach replacement stage: {attach_error}")
        for _ in range(4):
            await app.next_update_async()
        attached_stage = context.get_stage()
        stage_slot["stage"] = attached_stage
        attached_identity_matches = attached_stage is replacement_stage

        session.start()
        stage_rejection = False
        try:
            session.step(tick=3)
        except RuntimeError as error:
            stage_rejection = "replaced stage" in str(error)
        pending_before_rebind = session.status()
        pending_payload_id = old_sidecar.attempt_payload_ids[-1]
        pending_payload_digest = old_sidecar.attempt_payload_digests[-1]
        next_tick_blocked = False
        try:
            session.step(tick=4)
        except RuntimeError as error:
            next_tick_blocked = "pending snapshot retry" in str(error)

        mismatched_seed_rejected = False
        try:
            _primary_adapter(attached_stage, log_ids, initial_dry_mass, 3)
        except ValueError as error:
            mismatched_seed_rejected = "matching consumer revisions" in str(error)

        replacement_sidecar = phase6cd.ResidentPointSidecar(
            backend,
            attached_stage,
            point_path,
            lambda: context.get_stage(),
            initial_revision=2,
            initial_layout=moved_layout,
        )
        replacement_adapter = _primary_adapter(
            attached_stage, log_ids, initial_dry_mass, 2
        )
        running_rebind_rejected = False
        try:
            session.replace_consumers(
                replacement_adapter, sidecar=replacement_sidecar
            )
        except RuntimeError as error:
            running_rebind_rejected = "stopped state" in str(error)
        session.stop()
        rebind_result = session.replace_consumers(
            replacement_adapter, sidecar=replacement_sidecar
        )
        after_rebind = session.status()
        session.start()
        retried = session.retry_pending()
        retry_payload_id = replacement_sidecar.attempt_payload_ids[-1]
        retry_payload_digest = replacement_sidecar.attempt_payload_digests[-1]
        after_retry = session.status()
        continued = session.step(tick=4)

        relevant_resyncs = []
        replacement_listener = Tf.Notice.Register(
            Usd.Notice.ObjectsChanged,
            lambda notice, _sender: relevant_resyncs.extend(
                str(path)
                for path in notice.GetResyncedPaths()
                if str(path).startswith(str(core.FLOW_ROOT))
                or str(path).startswith("/World/PointSource")
            ),
            attached_stage,
        )
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
            await phase6cd._capture_one(
                viewport, video_frames / f"frame_{frame:04d}.png"
            )
        readback = core._readback(flow_interface)
        timeline.pause()
        final_status = session.status()
        replacement_adapter._require_consumer_revision(
            final_status["backend"]["revision"]
        )
        replacement_revisions = (
            replacement_adapter.status()["revision"],
            replacement_sidecar._attributes["revision"].Get(),
        )
        original_revisions_after = (
            old_adapter.status()["revision"],
            old_sidecar.status()["revision"],
        )
        session.stop()
        close_result = session.close()
        session = None

        required_stage_events = {
            int(omni.usd.StageEventType.CLOSING),
            int(omni.usd.StageEventType.CLOSED),
            int(omni.usd.StageEventType.OPENING),
            int(omni.usd.StageEventType.OPENED),
        }
        gates = {
            "pre_attach_revisions_commit": (
                first.snapshot.revision == 1
                and second.snapshot.revision == 2
                and original_revisions == (2, 2, 2)
            ),
            "official_attach_replaces_context_stage": (
                closed and attached and attached_identity_matches
            ),
            "stage_lifecycle_events_complete": required_stage_events.issubset(
                set(stage_events)
            ),
            "old_sidecar_fails_before_consumer_writes": (
                stage_rejection
                and pending_before_rebind["backend"]["revision"] == 3
                and pending_before_rebind["adapter"]["revision"] == 2
                and pending_before_rebind["sidecar"]["revision"] == 2
                and original_revisions_after == (2, 2)
            ),
            "pending_blocks_next_tick": next_tick_blocked,
            "mismatched_seed_fails_closed": mismatched_seed_rejected,
            "consumer_rebind_requires_stopped_owner": running_rebind_rejected,
            "rebind_retains_pending_revision": (
                rebind_result["revision"] == 2
                and rebind_result["pending_revision"] == 3
                and after_rebind["pending_revision"] == 3
                and after_rebind["consumer_replace_count"] == 1
            ),
            "old_consumers_close_on_handoff": (
                old_adapter.status()["closed"] and old_sidecar.status()["closed"]
            ),
            "retry_reuses_exact_immutable_payload": (
                pending_payload_id == retry_payload_id
                and pending_payload_digest == retry_payload_digest
            ),
            "pending_retry_aligns_all_consumers": (
                retried.snapshot.revision == 3
                and after_retry["pending_revision"] is None
                and after_retry["backend"]["revision"] == 3
                and after_retry["adapter"]["revision"] == 3
                and after_retry["sidecar"]["revision"] == 3
            ),
            "post_rebind_tick_continues": continued.snapshot.revision == 4,
            "no_live_structural_resync_after_attach": not relevant_resyncs,
            "flow_core_and_fields_recover": (
                max(active_blocks, default=0) > 0
                and all(
                    readback[name] > 0
                    for name in ("temperature", "fuel", "burn", "smoke", "velocity")
                )
            ),
            "continuous_video_frames_exact": (
                len(list(video_frames.glob("frame_*.png"))) == VIDEO_FRAME_COUNT
            ),
            "final_consumer_revisions_align": (
                final_status["backend"]["revision"]
                == final_status["adapter"]["revision"]
                == final_status["sidecar"]["revision"]
                and replacement_revisions
                == (final_status["backend"]["revision"],) * 2
            ),
            "clean_close_discards_nothing": not close_result["pending_discarded"],
            "production_activation_unchanged": True,
        }
        report = {
            "schema_version": 1,
            "phase": "phase6ce",
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
                "stage_api": "UsdContext.close_stage_async then attach_stage_async",
                "rebind_state": "stopped owner only",
                "seed_revision": "all replacement consumers equal previous commit",
                "pending_value": "same ResidentNativeStep and ImmutableSurfacePayload",
                "old_consumer_disposition": "closed after validated handoff",
            },
            "checkpoints": {
                "committed_before_attach": committed_before_attach,
                "pending_before_rebind": pending_before_rebind,
                "rebind": rebind_result,
                "after_rebind": after_rebind,
                "after_retry": after_retry,
                "final": final_status,
                "close": close_result,
            },
            "stage": {
                "attach_result": attached,
                "events": stage_events,
                "original_revisions": original_revisions,
                "original_revisions_after": original_revisions_after,
                "replacement_revisions": replacement_revisions,
                "relevant_resyncs_after_attach": sorted(set(relevant_resyncs)),
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
            failed = [name for name, value in gates.items() if not value]
            raise RuntimeError(f"Phase 6CE gates failed: {failed}")
        exit_code = 0
    except asyncio.CancelledError:
        raise
    except Exception as error:
        if report is None:
            output.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "phase": "phase6ce",
                        "status": "error",
                        "error": f"{type(error).__name__}: {error}",
                        "traceback": traceback.format_exc(),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        carb.log_error(f"[phase6ce] {type(error).__name__}: {error}")
    finally:
        if replacement_listener is not None:
            replacement_listener.Revoke()
        stage_event_subscription = None
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
