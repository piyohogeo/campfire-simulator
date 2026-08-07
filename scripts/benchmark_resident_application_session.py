"""Exercise the production ResidentApplicationSession with real Kit/native objects."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

import carb
import omni.kit.app
from pxr import Usd

import campfire.app
from campfire.app.phase3_scene import (
    PHASE3_EXTERNAL_HEAT_FLUX_W_M2,
    PHASE3_MODEL_DT_SECONDS,
)


def _arguments():
    settings = carb.settings.get_settings()
    return (
        Path(settings.get_as_string("/phase6ca/nativeLibrary")),
        Path(settings.get_as_string("/phase6ca/output")),
    )


def _consumer_revisions(stage, log_ids):
    return tuple(
        stage.GetPrimAtPath(f"/World/Logs/{log_id}")
        .GetAttribute("campfire:residentRevision")
        .Get()
        for log_id in log_ids
    ) + (
        stage.GetPrimAtPath(campfire.app.FLOW_EMITTER_PATH)
        .GetAttribute("campfire:residentRevision")
        .Get(),
    )


def _create_session(stage, log_ids, models, native_library, observer):
    initial_dry_mass = {
        log_id: sum(
            cell.dry_wood_mass_kg + cell.char_mass_kg + cell.ash_mass_kg
            for cell in model.cells
        )
        for log_id, model in zip(log_ids, models)
    }
    backend = campfire.app.ResidentNativeBackend(
        models,
        native_library,
        dt_seconds=PHASE3_MODEL_DT_SECONDS,
        heat_flux_w_m2=PHASE3_EXTERNAL_HEAT_FLUX_W_M2,
    )
    adapter = campfire.app.UsdResidentSnapshotAdapter(
        stage,
        log_ids,
        initial_dry_mass,
        write_observer=observer,
        cache_usd_handles=True,
        lightweight_commits=True,
        skip_unchanged_derived=True,
        coalesce_lightweight_notices=True,
    )
    return campfire.app.ResidentApplicationSession(backend, adapter)


async def _run(native_library, output):
    app = omni.kit.app.get_app()
    exit_code = 1
    report = None
    output.parent.mkdir(parents=True, exist_ok=True)
    session = None
    forced_session = None
    try:
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(stage)
        log_ids = (campfire.app.PHASE3_DRY_LOG_ID, campfire.app.PHASE3_WET_LOG_ID)
        models = tuple(
            campfire.app.load_model_from_prim(
                stage.GetPrimAtPath(f"/World/Logs/{log_id}")
            )
            for log_id in log_ids
        )
        failure = {"enabled": False, "revision_writes": 0}

        def observer(_write_index, name):
            if failure["enabled"] and name == "campfire:residentRevision":
                failure["revision_writes"] += 1
                if failure["revision_writes"] == 3:
                    raise RuntimeError("Injected session publication failure")

        session = _create_session(stage, log_ids, models, native_library, observer)
        ready_status = session.status()
        step_before_start_rejected = False
        try:
            session.step(tick=1)
        except RuntimeError as error:
            step_before_start_rejected = "state running" in str(error)

        session.start()
        first = session.step(tick=1)
        first_revisions = _consumer_revisions(stage, log_ids)
        failure["enabled"] = True
        failure["revision_writes"] = 0
        publication_failure_rejected = False
        try:
            session.step(tick=2)
        except RuntimeError as error:
            publication_failure_rejected = "session publication failure" in str(error)
        failure["enabled"] = False
        pending_status = session.status()
        pending_revisions = _consumer_revisions(stage, log_ids)

        new_step_blocked = False
        try:
            session.step(tick=3)
        except RuntimeError as error:
            new_step_blocked = "pending snapshot retry" in str(error)
        close_with_pending_blocked = False
        try:
            session.close()
        except RuntimeError as error:
            close_with_pending_blocked = "refuses to close" in str(error)

        stopped = session.stop()
        stopped_again = session.stop()
        session.start()
        retried = session.retry_pending()
        retry_revisions = _consumer_revisions(stage, log_ids)
        third = session.step(tick=3)
        third_revisions = _consumer_revisions(stage, log_ids)
        final_status = session.status()

        thread_errors = []

        def other_thread_status():
            try:
                session.status()
            except Exception as error:
                thread_errors.append(f"{type(error).__name__}: {error}")

        worker = threading.Thread(target=other_thread_status)
        worker.start()
        worker.join()
        first_close = session.close()
        second_close = session.close()
        session = None

        forced_stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(forced_stage)
        forced_models = tuple(
            campfire.app.load_model_from_prim(
                forced_stage.GetPrimAtPath(f"/World/Logs/{log_id}")
            )
            for log_id in log_ids
        )
        forced_failure = {"revision_writes": 0}

        def forced_observer(_write_index, name):
            if name == "campfire:residentRevision":
                forced_failure["revision_writes"] += 1
                if forced_failure["revision_writes"] == 3:
                    raise RuntimeError("Injected forced-close publication failure")

        forced_session = _create_session(
            forced_stage, log_ids, forced_models, native_library, forced_observer
        )
        forced_session.start()
        try:
            forced_session.step(tick=1)
        except RuntimeError:
            pass
        forced_close = forced_session.close(discard_pending=True)
        forced_session = None

        gates = {
            "ready_without_side_effects": (
                ready_status["state"] == "ready"
                and ready_status["backend"]["revision"] == 0
                and ready_status["adapter"]["revision"] == 0
            ),
            "step_before_start_rejected": step_before_start_rejected,
            "first_commit_consistent": (
                first.snapshot.revision == 1 and first_revisions == (1, 1, 1)
            ),
            "publication_failure_rejected": publication_failure_rejected,
            "pending_snapshot_owned": (
                pending_status["pending_revision"] == 2
                and pending_status["backend"]["revision"] == 2
                and pending_status["adapter"]["revision"] == 1
            ),
            "failed_publication_replayed_usd": pending_revisions == (1, 1, 1),
            "new_step_blocked_while_pending": new_step_blocked,
            "close_with_pending_blocked": close_with_pending_blocked,
            "stop_restart_idempotent": stopped and not stopped_again,
            "pending_retry_committed": (
                retried.snapshot.revision == 2 and retry_revisions == (2, 2, 2)
            ),
            "next_step_continuous": (
                third.snapshot.revision == 3 and third_revisions == (3, 3, 3)
            ),
            "session_counters_exact": (
                final_status["step_count"] == 3
                and final_status["publish_count"] == 3
                and final_status["publish_failure_count"] == 1
                and final_status["retry_count"] == 1
                and final_status["start_count"] == 2
                and final_status["stop_count"] == 1
            ),
            "owner_thread_enforced": (
                len(thread_errors) == 1 and "owner thread" in thread_errors[0]
            ),
            "clean_close_idempotent": (
                not first_close["already_closed"]
                and not first_close["pending_discarded"]
                and second_close["already_closed"]
            ),
            "forced_close_is_explicit": (
                forced_close["pending_discarded"]
                and not forced_close["already_closed"]
            ),
        }
        report = {
            "schema_version": 1,
            "phase": "phase6ca",
            "status": "ok" if all(gates.values()) else "failed",
            "scope": {
                "production_module_added": True,
                "production_activation_added": False,
                "existing_phase3_validation_replaced": False,
                "production_default_changed": False,
                "checkpoint_ui_added": False,
            },
            "contract": {
                "owner": "one Kit thread owns backend and adapter",
                "states": ["ready", "running", "stopped", "closed"],
                "pending_policy": "block new steps and normal close until immutable snapshot retry succeeds",
                "forced_close_policy": "discard_pending=True only",
            },
            "sequence": {
                "first_revision": first.snapshot.revision,
                "pending_revision": pending_status["pending_revision"],
                "retried_revision": retried.snapshot.revision,
                "final_revision": third.snapshot.revision,
                "final_status": final_status,
                "owner_thread_error": thread_errors,
            },
            "gates": gates,
            "decision": {
                "owner_contract": "qualified",
                "interactive_activation": "deferred",
                "reason": "Frame scheduling, stage replacement, and UI command ownership are not connected yet.",
            },
        }
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if not all(gates.values()):
            raise RuntimeError("Phase 6CA application-session gate failed")
        exit_code = 0
    except asyncio.CancelledError:
        raise
    except Exception as error:
        if report is not None:
            report["execution_error"] = f"{type(error).__name__}: {error}"
            output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        else:
            output.write_text(
                json.dumps(
                    {
                        "phase": "phase6ca",
                        "status": "error",
                        "error": f"{type(error).__name__}: {error}",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        carb.log_error(f"[phase6ca] {type(error).__name__}: {error}")
    finally:
        for candidate in (session, forced_session):
            if candidate is not None:
                try:
                    candidate.close(discard_pending=True)
                except Exception as close_error:
                    carb.log_error(f"[phase6ca] cleanup failed: {close_error}")
        app.post_uncancellable_quit(exit_code)


native_library, output = _arguments()
asyncio.ensure_future(_run(native_library, output))
