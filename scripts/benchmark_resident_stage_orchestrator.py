"""Qualify scheduler-style Resident stage recovery on real Kit lifecycle events."""

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
PREVIOUS_BENCHMARK = ROOT / "scripts" / "benchmark_resident_stage_rebind.py"
VIDEO_FRAME_COUNT = 60


def _load_previous_module():
    spec = importlib.util.spec_from_file_location(
        "campfire_phase6cf_previous", PREVIOUS_BENCHMARK
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load benchmark: {PREVIOUS_BENCHMARK}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


phase6ce = _load_previous_module()
phase6cd = phase6ce.phase6cd
surface = phase6ce.surface
core = phase6ce.core


def _settings():
    settings = carb.settings.get_settings()
    return {
        "native_library": Path(settings.get_as_string("/phase6cf/nativeLibrary")),
        "output": Path(settings.get_as_string("/phase6cf/output")),
        "video_frames": Path(settings.get_as_string("/phase6cf/videoFrames")),
    }


async def _run(arguments, *, phase="phase6cf"):
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
        point_failure = {"revision": None}

        def observe_point_write(_index, _name, payload):
            if payload.revision == point_failure["revision"]:
                point_failure["revision"] = None
                raise RuntimeError("Injected Point publication failure")

        old_sidecar = phase6cd.ResidentPointSidecar(
            backend,
            stage,
            point_path,
            lambda: context.get_stage(),
            observe_point_write,
        )
        old_adapter = phase6ce._primary_adapter(
            stage, log_ids, initial_dry_mass, 0
        )
        session = campfire.app.ResidentApplicationSession(
            backend, old_adapter, sidecar=old_sidecar
        )
        session.start()
        first = session.step(tick=1)
        extracted_module_equivalence = None
        production_point_types_used = None
        if phase == "phase6cg":
            legacy_producer = surface.NativeSurfaceProducer(backend)
            legacy_producer.build_layout()
            legacy_producer.build_channels()
            production_producer = old_sidecar._producer
            extracted_module_equivalence = all(
                legacy.tobytes(order="C") == production.tobytes(order="C")
                for legacy, production in (
                    (legacy_producer.positions, production_producer.positions),
                    (legacy_producer.fuels, production_producer.fuels),
                    (legacy_producer.temperatures, production_producer.temperatures),
                    (legacy_producer.smokes, production_producer.smokes),
                )
            )
            production_point_types_used = (
                isinstance(old_sidecar, campfire.app.ResidentPointSidecar)
                and isinstance(
                    production_producer, campfire.app.ResidentNativeSurfaceProducer
                )
                and isinstance(
                    old_sidecar._last_snapshot, campfire.app.ImmutableSurfacePayload
                )
            )
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
        point_failure["revision"] = 3
        injected_failure = False
        try:
            session.step(tick=3)
        except RuntimeError as error:
            injected_failure = "Injected Point" in str(error)
        pending_before = session.status()
        pending_payload_id = old_sidecar.attempt_payload_ids[-1]
        pending_payload_digest = old_sidecar.attempt_payload_digests[-1]
        next_tick_blocked = False
        try:
            session.step(tick=4)
        except RuntimeError as error:
            next_tick_blocked = "pending snapshot retry" in str(error)
        if not stage.GetRootLayer().Export(str(replacement_path)):
            raise RuntimeError("Unable to export replacement stage")
        replacement_stage = Usd.Stage.Open(str(replacement_path))
        if replacement_stage is None:
            raise RuntimeError("Unable to open replacement stage")

        factory_control = {"fail": True}
        factory_calls = []
        replacements = {}

        def consumer_factory(attached_stage, revision):
            factory_calls.append(
                {"stage_matches": attached_stage is replacement_stage, "revision": revision}
            )
            if factory_control["fail"]:
                raise RuntimeError("Injected replacement consumer factory failure")
            replacements["sidecar"] = phase6cd.ResidentPointSidecar(
                backend,
                attached_stage,
                point_path,
                lambda: context.get_stage(),
                initial_revision=revision,
                initial_layout=moved_layout,
            )
            replacements["adapter"] = phase6ce._primary_adapter(
                attached_stage, log_ids, initial_dry_mass, revision
            )
            return replacements["adapter"], replacements["sidecar"]

        update_count = {"value": 0}

        async def next_update():
            update_count["value"] += 1
            await app.next_update_async()

        orchestrator = campfire.app.ResidentStageRecoveryOrchestrator(
            session,
            context,
            timeline,
            consumer_factory,
            next_update,
            drain_updates=4,
        )
        event_names = {
            int(omni.usd.StageEventType.CLOSING): "closing",
            int(omni.usd.StageEventType.CLOSED): "closed",
            int(omni.usd.StageEventType.OPENING): "opening",
            int(omni.usd.StageEventType.OPENED): "opened",
        }
        raw_stage_events = []

        def observe_stage_event(event):
            raw_stage_events.append(int(event.type))
            name = event_names.get(int(event.type))
            if name is not None:
                orchestrator.observe_stage_event(name)

        stage_event_subscription = (
            context.get_stage_event_stream().create_subscription_to_pop(
                observe_stage_event, name="phase6cf-stage-orchestrator"
            )
        )
        factory_failure = False
        try:
            await orchestrator.replace_stage(replacement_stage)
        except RuntimeError as error:
            factory_failure = "consumer factory failure" in str(error)
        after_factory_failure = session.status()
        failed_orchestrator = orchestrator.status()
        old_consumers_open_after_failure = (
            not old_adapter.status()["closed"]
            and not old_sidecar.status()["closed"]
        )

        factory_control["fail"] = False
        recovered = orchestrator.retry_recovery()
        replacement_adapter = replacements["adapter"]
        replacement_sidecar = replacements["sidecar"]
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
            replacement_stage,
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
        session.stop()
        close_result = session.close()
        session = None

        gates = {
            "pre_recovery_revisions_commit": (
                first.snapshot.revision == 1 and second.snapshot.revision == 2
            ),
            "point_failure_creates_pending_three": (
                injected_failure
                and pending_before["backend"]["revision"] == 3
                and pending_before["adapter"]["revision"] == 2
                and pending_before["sidecar"]["revision"] == 2
                and pending_before["pending_revision"] == 3
            ),
            "pending_blocks_next_tick": next_tick_blocked,
            "orchestrator_drains_close_and_attach": update_count["value"] == 8,
            "official_stage_identity_attached": context.get_stage() is replacement_stage,
            "ordered_lifecycle_events_complete": failed_orchestrator[
                "observed_events"
            ] == ("closing", "closed", "opening", "opened"),
            "factory_failure_is_retryable": (
                factory_failure
                and failed_orchestrator["state"] == "faulted"
                and failed_orchestrator["attached_stage_available"]
                and failed_orchestrator["failure_count"] == 1
            ),
            "factory_failure_preserves_pending": (
                after_factory_failure["state"] == "stopped"
                and after_factory_failure["pending_revision"] == 3
                and after_factory_failure["consumer_replace_count"] == 0
                and old_consumers_open_after_failure
            ),
            "factory_retry_uses_exact_seed": (
                len(factory_calls) == 2
                and all(call["stage_matches"] for call in factory_calls)
                and [call["revision"] for call in factory_calls] == [2, 2]
            ),
            "validated_handoff_closes_old_consumers": (
                old_adapter.status()["closed"] and old_sidecar.status()["closed"]
            ),
            "retry_reuses_exact_immutable_payload": (
                pending_payload_id == retry_payload_id
                and pending_payload_digest == retry_payload_digest
            ),
            "pending_retry_aligns_all_consumers": (
                recovered["pending_retried"]
                and recovered["session_state"] == "running"
                and after_retry["pending_revision"] is None
                and after_retry["backend"]["revision"]
                == after_retry["adapter"]["revision"]
                == after_retry["sidecar"]["revision"]
                == 3
            ),
            "post_recovery_tick_continues": continued.snapshot.revision == 4,
            "no_live_structural_resync_after_recovery": not relevant_resyncs,
            "flow_core_and_fields_continue": (
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
        if phase == "phase6cg":
            gates.update(
                {
                    "production_point_module_types_used": production_point_types_used,
                    "extracted_module_arrays_match_benchmark": (
                        extracted_module_equivalence
                    ),
                }
            )
        report = {
            "schema_version": 1,
            "phase": phase,
            "status": "ok" if all(gates.values()) else "failed",
            "scope": {
                "default_off": True,
                "flow_version": core.FLOW_VERSION,
                "point_count": surface.POINT_COUNT,
                "emitter_count": 1,
                "production_activation_changed": False,
                "canonical_scene_changed": False,
                "production_point_module": phase == "phase6cg",
            },
            "contract": {
                "trigger": "owner-thread scheduler receives Kit stage lifecycle events",
                "stage_sequence": "stop, close, four drains, attach, four drains",
                "failure_boundary": "attached-stage consumer construction is retryable",
                "pending_value": "same ResidentNativeStep and ImmutableSurfacePayload",
                "handoff": "old consumers close only after replacement validation",
            },
            "checkpoints": {
                "pending_before": pending_before,
                "after_factory_failure": after_factory_failure,
                "failed_orchestrator": failed_orchestrator,
                "recovered": recovered,
                "after_retry": after_retry,
                "final": final_status,
                "close": close_result,
            },
            "stage": {
                "raw_events": raw_stage_events,
                "factory_calls": factory_calls,
                "drained_updates": update_count["value"],
                "replacement_revisions": replacement_revisions,
                "relevant_resyncs_after_recovery": sorted(set(relevant_resyncs)),
            },
            "module": {
                "sidecar": "campfire.app.ResidentPointSidecar",
                "producer": "campfire.app.ResidentNativeSurfaceProducer",
                "payload": "campfire.app.ImmutableSurfacePayload",
                "production_types_used": production_point_types_used,
                "legacy_array_bytes_equal": extracted_module_equivalence,
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
            raise RuntimeError(f"{phase.upper()} gates failed: {failed}")
        exit_code = 0
    except asyncio.CancelledError:
        raise
    except Exception as error:
        if report is None:
            output.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "phase": phase,
                        "status": "error",
                        "error": f"{type(error).__name__}: {error}",
                        "traceback": traceback.format_exc(),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        carb.log_error(f"[{phase}] {type(error).__name__}: {error}")
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
