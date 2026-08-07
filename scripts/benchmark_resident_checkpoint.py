"""Create, reject, and resume an isolated Resident checkpoint package in Kit."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import zipfile
from pathlib import Path

import carb
import omni.kit.app
from pxr import Sdf, Usd

import campfire.app
from campfire.app.phase3_scene import (
    PHASE3_EXTERNAL_HEAT_FLUX_W_M2,
    PHASE3_MODEL_DT_SECONDS,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resident_checkpoint_package import (
    MANIFEST_ENTRY,
    STAGE_ENTRY,
    canonical_json,
    read_checkpoint,
    sha256_bytes,
    write_checkpoint,
)


def _arguments():
    settings = carb.settings.get_settings()
    return (
        Path(settings.get_as_string("/phase6by/nativeLibrary")),
        Path(settings.get_as_string("/phase6by/outputDir")),
    )


def _model_hash(model):
    return sha256_bytes(canonical_json(model.to_dict()))


def _initial_dry_mass(models, log_ids):
    return {
        log_id: sum(
            cell.dry_wood_mass_kg + cell.char_mass_kg + cell.ash_mass_kg
            for cell in model.cells
        )
        + model.emitted_pyrolysis_gas_kg
        + model.emitted_char_gas_kg
        for log_id, model in zip(log_ids, models)
    }


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


def _open_stage(stage_text):
    layer = Sdf.Layer.CreateAnonymous("resident-checkpoint.usda")
    if not layer.ImportFromString(stage_text):
        raise ValueError("Checkpoint USDA could not be imported")
    return Usd.Stage.Open(layer)


async def _run(native_library, output_dir):
    app = omni.kit.app.get_app()
    exit_code = 1
    report = None
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "resident_checkpoint_raw.json"
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
        initial_dry_mass = _initial_dry_mass(models, log_ids)
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
            cache_usd_handles=True,
            lightweight_commits=True,
            skip_unchanged_derived=True,
            coalesce_lightweight_notices=True,
        )
        adapter.on_timeline_started()
        for tick in range(1, 4):
            result = backend.step(tick=tick)
            adapter.publish(result.snapshot)
        adapter.on_timeline_stopped()
        adapter.close()
        shutdown = backend.close()
        for log_id, model in zip(log_ids, models):
            campfire.app.save_model_to_prim(
                model, stage.GetPrimAtPath(f"/World/Logs/{log_id}")
            )

        metadata = {
            "revision": 3,
            "tick": 3,
            "log_ids": list(log_ids),
            "model_state_sha256": {
                log_id: _model_hash(model) for log_id, model in zip(log_ids, models)
            },
            "consumer_revisions": list(_consumer_revisions(stage, log_ids)),
            "initial_dry_mass_kg": initial_dry_mass,
            "scheduler": {
                "dt_seconds": PHASE3_MODEL_DT_SECONDS,
                "heat_flux_w_m2": PHASE3_EXTERNAL_HEAT_FLUX_W_M2,
            },
            "native": {"abi_version": shutdown["abi_version"]},
        }
        checkpoint = output_dir / "resident_checkpoint.campfire-checkpoint"
        stage_text = stage.GetRootLayer().ExportToString()
        manifest = write_checkpoint(checkpoint, stage_text, metadata)
        checkpoint_sha_before_interruption = hashlib.sha256(
            checkpoint.read_bytes()
        ).hexdigest()
        interrupted_write_rejected = False
        try:
            write_checkpoint(
                checkpoint,
                stage_text + "\n# interrupted candidate\n",
                metadata,
                inject_before_replace=True,
            )
        except RuntimeError:
            interrupted_write_rejected = True
        interrupted_write_preserved_checkpoint = (
            hashlib.sha256(checkpoint.read_bytes()).hexdigest()
            == checkpoint_sha_before_interruption
        )

        loaded_manifest, loaded_stage_text = read_checkpoint(checkpoint)
        with zipfile.ZipFile(checkpoint, "r") as archive:
            canonical_two_entry_package = archive.namelist() == [
                MANIFEST_ENTRY,
                STAGE_ENTRY,
            ]
        restored_stage = _open_stage(loaded_stage_text)
        restored_models = tuple(
            campfire.app.load_model_from_prim(
                restored_stage.GetPrimAtPath(f"/World/Logs/{log_id}")
            )
            for log_id in log_ids
        )
        model_hashes_exact = all(
            _model_hash(model) == loaded_manifest["model_state_sha256"][log_id]
            for log_id, model in zip(log_ids, restored_models)
        )
        consumer_revisions_exact = (
            _consumer_revisions(restored_stage, log_ids) == (3, 3, 3)
        )
        restored_backend = campfire.app.ResidentNativeBackend(
            restored_models,
            native_library,
            dt_seconds=loaded_manifest["scheduler"]["dt_seconds"],
            heat_flux_w_m2=loaded_manifest["scheduler"]["heat_flux_w_m2"],
            initial_revision=loaded_manifest["revision"],
            initial_tick=loaded_manifest["tick"],
        )
        restored_adapter = campfire.app.UsdResidentSnapshotAdapter(
            restored_stage,
            log_ids,
            loaded_manifest["initial_dry_mass_kg"],
            cache_usd_handles=True,
            lightweight_commits=True,
            skip_unchanged_derived=True,
            coalesce_lightweight_notices=True,
            initial_revision=loaded_manifest["revision"],
        )
        restored_adapter.on_timeline_started()
        fourth = restored_backend.step(tick=4)
        restored_adapter.publish(fourth.snapshot)
        resume_revision_continuous = (
            fourth.snapshot.revision == 4
            and _consumer_revisions(restored_stage, log_ids) == (4, 4, 4)
        )
        restored_adapter.close()
        restored_backend.close()

        tampered = output_dir / "tampered.campfire-checkpoint"
        with zipfile.ZipFile(checkpoint, "r") as source, zipfile.ZipFile(
            tampered, "w"
        ) as target:
            target.writestr(MANIFEST_ENTRY, source.read(MANIFEST_ENTRY))
            target.writestr(STAGE_ENTRY, source.read(STAGE_ENTRY) + b"\n# tampered\n")
        tampered_stage_rejected = False
        tampered_stage_rejection = None
        try:
            read_checkpoint(tampered)
        except ValueError as error:
            tampered_stage_rejected = True
            tampered_stage_rejection = str(error)

        wrong_revision = output_dir / "wrong-revision.campfire-checkpoint"
        wrong_metadata = dict(metadata)
        wrong_metadata["revision"] = 4
        wrong_metadata["consumer_revisions"] = [4, 4, 4]
        write_checkpoint(wrong_revision, stage_text, wrong_metadata)
        wrong_revision_rejected = False
        try:
            wrong_manifest, wrong_stage_text = read_checkpoint(wrong_revision)
            campfire.app.UsdResidentSnapshotAdapter(
                _open_stage(wrong_stage_text),
                log_ids,
                wrong_manifest["initial_dry_mass_kg"],
                initial_revision=wrong_manifest["revision"],
            )
        except ValueError as error:
            wrong_revision_rejected = "matching consumer revisions" in str(error)

        gates = {
            "canonical_two_entry_package": canonical_two_entry_package,
            "stage_hash_validated": loaded_manifest["stage"] == manifest["stage"],
            "model_hashes_exact": model_hashes_exact,
            "consumer_revisions_exact": consumer_revisions_exact,
            "interrupted_write_rejected": interrupted_write_rejected,
            "interrupted_write_preserved_checkpoint": interrupted_write_preserved_checkpoint,
            "tampered_stage_rejected": tampered_stage_rejected,
            "wrong_revision_rejected": wrong_revision_rejected,
            "resume_revision_continuous": resume_revision_continuous,
        }
        report = {
            "schema_version": 1,
            "phase": "phase6by",
            "status": "ok" if all(gates.values()) else "failed",
            "scope": {
                "production_code_changed": False,
                "production_default_changed": False,
                "existing_wood_json_schema_changed": False,
                "automatic_resume_enabled": False,
            },
            "package": {
                "path": str(checkpoint),
                "bytes": checkpoint.stat().st_size,
                "stage_uncompressed_bytes": manifest["stage"]["bytes"],
                "entries": [MANIFEST_ENTRY, STAGE_ENTRY],
                "revision": manifest["revision"],
                "tick": manifest["tick"],
                "log_count": len(log_ids),
                "tampered_stage_rejection": tampered_stage_rejection,
            },
            "gates": gates,
            "decision": {
                "format_feasibility": "qualified",
                "production_adoption": "deferred",
                "reason": "Checkpoint persistence is proven, but product save/resume policy and UI are not defined.",
            },
        }
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if not all(gates.values()):
            raise RuntimeError("Phase 6BY checkpoint gate failed")
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
                        "phase": "phase6by",
                        "status": "error",
                        "error": f"{type(error).__name__}: {error}",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        carb.log_error(f"[phase6by] {type(error).__name__}: {error}")
    finally:
        app.post_uncancellable_quit(exit_code)


native_library, output_dir = _arguments()
asyncio.ensure_future(_run(native_library, output_dir))
