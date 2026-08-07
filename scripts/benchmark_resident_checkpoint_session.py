"""Exercise a non-terminal explicit Resident checkpoint save barrier in Kit."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resident_checkpoint_package import read_checkpoint
from resident_checkpoint_session import ResidentCheckpointSession


def _arguments():
    settings = carb.settings.get_settings()
    return (
        Path(settings.get_as_string("/phase6bz/nativeLibrary")),
        Path(settings.get_as_string("/phase6bz/outputDir")),
    )


def _stage_hash(stage):
    return hashlib.sha256(
        stage.GetRootLayer().ExportToString().encode("utf-8")
    ).hexdigest()


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


async def _run(native_library, output_dir):
    app = omni.kit.app.get_app()
    exit_code = 1
    report = None
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "resident_checkpoint_session_raw.json"
    session = None
    resumed = None
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
        session = ResidentCheckpointSession(
            stage,
            log_ids,
            models,
            native_library,
            dt_seconds=PHASE3_MODEL_DT_SECONDS,
            heat_flux_w_m2=PHASE3_EXTERNAL_HEAT_FLUX_W_M2,
        )
        session.start()
        session.step(tick=1)

        previous = output_dir / "previous.campfire-checkpoint"
        live_stage_before_save = _stage_hash(stage)
        first_save = session.save(previous)
        live_stage_unchanged = _stage_hash(stage) == live_stage_before_save
        first_status = session.status()
        previous_sha = hashlib.sha256(previous.read_bytes()).hexdigest()

        session.step(tick=2)
        checkpoint = output_dir / "resume-source.campfire-checkpoint"
        second_stage_before_save = _stage_hash(stage)
        second_save = session.save(checkpoint)
        second_stage_unchanged = _stage_hash(stage) == second_stage_before_save
        loaded_manifest, _ = read_checkpoint(checkpoint)

        owner_thread_error = []

        def wrong_thread_save():
            try:
                session.save(checkpoint)
            except Exception as error:
                owner_thread_error.append(f"{type(error).__name__}: {error}")

        worker = threading.Thread(target=wrong_thread_save)
        worker.start()
        worker.join()

        failed_save_rejected = False
        try:
            session.save(previous, inject_before_replace=True)
        except RuntimeError as error:
            failed_save_rejected = "Injected checkpoint interruption" in str(error)
        failed_save_preserved_previous = (
            hashlib.sha256(previous.read_bytes()).hexdigest() == previous_sha
        )
        post_failure_status = session.status()

        continuous_third = session.step(tick=3)
        continuous_revisions = _consumer_revisions(stage, log_ids)
        first_close = session.close()
        second_close = session.close()
        closed_save_rejected = False
        try:
            session.save(checkpoint)
        except RuntimeError as error:
            closed_save_rejected = "requires state running" in str(error)

        resumed = ResidentCheckpointSession.from_checkpoint(
            checkpoint, native_library
        )
        resume_initial_status = resumed.status()
        resumed.start()
        resumed_third = resumed.step(tick=3)
        resumed_revisions = _consumer_revisions(resumed.stage, log_ids)
        resumed_close = resumed.close()

        gates = {
            "live_stage_isolated_from_save": (
                live_stage_unchanged and second_stage_unchanged
            ),
            "save_is_non_terminal": (
                first_status["state"] == "running"
                and first_status["backend"]["active"]
                and first_status["backend"]["revision"] == 1
            ),
            "save_revision_stable": (
                first_save["manifest"]["revision"] == 1
                and second_save["manifest"]["revision"] == 2
                and loaded_manifest["revision"] == 2
                and loaded_manifest["tick"] == 2
            ),
            "owner_thread_enforced": (
                len(owner_thread_error) == 1
                and "owner thread" in owner_thread_error[0]
            ),
            "failed_save_rejected": failed_save_rejected,
            "failed_save_preserved_previous": failed_save_preserved_previous,
            "failed_save_session_resumed": (
                post_failure_status["state"] == "running"
                and post_failure_status["backend"]["revision"] == 2
                and post_failure_status["adapter"]["revision"] == 2
            ),
            "continuous_session_reaches_revision_3": (
                continuous_third.snapshot.revision == 3
                and continuous_revisions == (3, 3, 3)
            ),
            "resume_seed_exact": (
                resume_initial_status["state"] == "ready"
                and resume_initial_status["backend"]["revision"] == 2
                and resume_initial_status["backend"]["tick"] == 2
                and resume_initial_status["adapter"]["revision"] == 2
            ),
            "resumed_step_matches_continuous": (
                resumed_third == continuous_third
                and resumed_revisions == (3, 3, 3)
            ),
            "close_is_idempotent": (
                not first_close["already_closed"]
                and second_close["already_closed"]
                and not resumed_close["already_closed"]
            ),
            "closed_save_rejected": closed_save_rejected,
        }
        report = {
            "schema_version": 1,
            "phase": "phase6bz",
            "status": "ok" if all(gates.values()) else "failed",
            "scope": {
                "production_code_changed": False,
                "production_default_changed": False,
                "automatic_save_enabled": False,
                "automatic_resume_enabled": False,
            },
            "session": {
                "ownership": "one owner thread; backend + adapter + stage",
                "save_barrier": [
                    "stop adapter publication",
                    "export resident SoA to Python mirror",
                    "clone live stage",
                    "save existing model JSON to clone",
                    "atomic checkpoint replace",
                    "resume adapter publication",
                ],
                "successful_saves": post_failure_status["save_count"],
                "failed_saves": post_failure_status["failed_save_count"],
                "pause_count": post_failure_status["pause_count"],
                "resume_count": post_failure_status["resume_count"],
                "checkpoint_bytes": checkpoint.stat().st_size,
                "save_export_ms": [
                    first_save["export_ms"],
                    second_save["export_ms"],
                ],
                "continuous_revision": continuous_third.snapshot.revision,
                "resumed_revision": resumed_third.snapshot.revision,
            },
            "diagnostics": {
                "owner_thread_error": owner_thread_error,
                "first_close_export_count": first_close["backend"]["export_count"],
                "resumed_close_export_count": resumed_close["backend"]["export_count"],
            },
            "gates": gates,
            "decision": {
                "session_owner_feasibility": "qualified",
                "production_adoption": "deferred",
                "reason": "The current application has no persistent interactive Resident session owner or user save policy.",
            },
        }
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if not all(gates.values()):
            raise RuntimeError("Phase 6BZ checkpoint session gate failed")
        session = None
        resumed = None
        exit_code = 0
    except asyncio.CancelledError:
        raise
    except Exception as error:
        if report is not None:
            report["execution_error"] = f"{type(error).__name__}: {error}"
            report_path.write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )
        else:
            report_path.write_text(
                json.dumps(
                    {
                        "phase": "phase6bz",
                        "status": "error",
                        "error": f"{type(error).__name__}: {error}",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        carb.log_error(f"[phase6bz] {type(error).__name__}: {error}")
    finally:
        for candidate in (session, resumed):
            if candidate is not None:
                try:
                    candidate.close()
                except Exception as close_error:
                    carb.log_error(f"[phase6bz] cleanup failed: {close_error}")
        app.post_uncancellable_quit(exit_code)


native_library, output_dir = _arguments()
asyncio.ensure_future(_run(native_library, output_dir))
