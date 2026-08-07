"""Isolated owner-thread Resident session for explicit checkpoint research."""

from __future__ import annotations

import threading
from pathlib import Path

from pxr import Sdf, Usd

import campfire.app

from resident_checkpoint_package import (
    canonical_json,
    read_checkpoint,
    sha256_bytes,
    write_checkpoint,
)


def _open_stage(stage_text):
    layer = Sdf.Layer.CreateAnonymous("resident-session-checkpoint.usda")
    if not layer.ImportFromString(stage_text):
        raise ValueError("Checkpoint USDA could not be imported")
    return Usd.Stage.Open(layer)


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


class ResidentCheckpointSession:
    """Own one backend/adapter pair and serialize explicit save barriers."""

    def __init__(
        self,
        stage,
        log_ids,
        models,
        native_library,
        *,
        dt_seconds,
        heat_flux_w_m2,
        initial_revision=0,
        initial_tick=-1,
        initial_dry_mass_kg=None,
        expected_abi_version=None,
    ):
        self._owner_thread_id = threading.get_ident()
        self._stage = stage
        self._log_ids = tuple(log_ids)
        self._models = tuple(models)
        self._native_library = Path(native_library).resolve()
        self._dt_seconds = float(dt_seconds)
        self._heat_flux_w_m2 = float(heat_flux_w_m2)
        self._initial_dry_mass_kg = dict(
            initial_dry_mass_kg
            if initial_dry_mass_kg is not None
            else _initial_dry_mass(self._models, self._log_ids)
        )
        self._backend = campfire.app.ResidentNativeBackend(
            self._models,
            self._native_library,
            dt_seconds=self._dt_seconds,
            heat_flux_w_m2=self._heat_flux_w_m2,
            initial_revision=initial_revision,
            initial_tick=initial_tick,
        )
        abi_version = self._backend.status()["abi_version"]
        if expected_abi_version is not None and abi_version != expected_abi_version:
            self._backend.close()
            raise ValueError("Checkpoint native ABI version does not match runtime")
        self._adapter = campfire.app.UsdResidentSnapshotAdapter(
            self._stage,
            self._log_ids,
            self._initial_dry_mass_kg,
            cache_usd_handles=True,
            lightweight_commits=True,
            skip_unchanged_derived=True,
            coalesce_lightweight_notices=True,
            initial_revision=initial_revision,
        )
        self._state = "ready"
        self._save_count = 0
        self._failed_save_count = 0
        self._pause_count = 0
        self._resume_count = 0
        self._close_result = None

    @classmethod
    def from_checkpoint(cls, path, native_library):
        manifest, stage_text = read_checkpoint(path)
        stage = _open_stage(stage_text)
        log_ids = tuple(manifest["log_ids"])
        models = tuple(
            campfire.app.load_model_from_prim(
                stage.GetPrimAtPath(f"/World/Logs/{log_id}")
            )
            for log_id in log_ids
        )
        if any(
            _model_hash(model) != manifest["model_state_sha256"][log_id]
            for log_id, model in zip(log_ids, models)
        ):
            raise ValueError("Checkpoint model-state hash mismatch")
        return cls(
            stage,
            log_ids,
            models,
            native_library,
            dt_seconds=manifest["scheduler"]["dt_seconds"],
            heat_flux_w_m2=manifest["scheduler"]["heat_flux_w_m2"],
            initial_revision=manifest["revision"],
            initial_tick=manifest["tick"],
            initial_dry_mass_kg=manifest["initial_dry_mass_kg"],
            expected_abi_version=manifest["native"]["abi_version"],
        )

    @property
    def stage(self):
        return self._stage

    def _require_owner(self):
        if threading.get_ident() != self._owner_thread_id:
            raise RuntimeError("Resident checkpoint session must run on its owner thread")

    def _require_state(self, expected):
        self._require_owner()
        if self._state != expected:
            raise RuntimeError(
                f"Resident checkpoint session requires state {expected}, got {self._state}"
            )

    def start(self):
        self._require_state("ready")
        self._adapter.on_timeline_started()
        self._state = "running"

    def step(self, *, tick):
        self._require_state("running")
        result = self._backend.step(tick=tick)
        self._adapter.publish(result.snapshot)
        return result

    def save(self, path, *, inject_before_replace=False):
        self._require_state("running")
        backend_status = self._backend.status()
        adapter_status = self._adapter.status()
        revision = backend_status["revision"]
        if (
            revision != adapter_status["revision"]
            or backend_status["tick"] < 0
            or _consumer_revisions(self._stage, self._log_ids)
            != (revision,) * (len(self._log_ids) + 1)
        ):
            raise RuntimeError("Resident checkpoint save requires a committed boundary")

        self._adapter.on_timeline_stopped()
        self._state = "saving"
        self._pause_count += 1
        try:
            export_ms = self._backend.export_all()
            clone = _open_stage(self._stage.GetRootLayer().ExportToString())
            for log_id, model in zip(self._log_ids, self._models):
                campfire.app.save_model_to_prim(
                    model, clone.GetPrimAtPath(f"/World/Logs/{log_id}")
                )
            metadata = {
                "revision": revision,
                "tick": backend_status["tick"],
                "log_ids": list(self._log_ids),
                "model_state_sha256": {
                    log_id: _model_hash(model)
                    for log_id, model in zip(self._log_ids, self._models)
                },
                "consumer_revisions": list(
                    _consumer_revisions(clone, self._log_ids)
                ),
                "initial_dry_mass_kg": self._initial_dry_mass_kg,
                "scheduler": {
                    "dt_seconds": self._dt_seconds,
                    "heat_flux_w_m2": self._heat_flux_w_m2,
                },
                "native": {"abi_version": backend_status["abi_version"]},
            }
            manifest = write_checkpoint(
                path,
                clone.GetRootLayer().ExportToString(),
                metadata,
                inject_before_replace=inject_before_replace,
            )
            self._save_count += 1
            return {"manifest": manifest, "export_ms": export_ms}
        except Exception:
            self._failed_save_count += 1
            raise
        finally:
            self._adapter.on_timeline_started()
            self._state = "running"
            self._resume_count += 1

    def status(self):
        self._require_owner()
        return {
            "state": self._state,
            "save_count": self._save_count,
            "failed_save_count": self._failed_save_count,
            "pause_count": self._pause_count,
            "resume_count": self._resume_count,
            "backend": self._backend.status(),
            "adapter": self._adapter.status(),
        }

    def close(self):
        self._require_owner()
        if self._state == "closed":
            return {**self._close_result, "already_closed": True}
        if self._state == "running":
            self._adapter.on_timeline_stopped()
        self._adapter.close()
        backend_close = self._backend.close()
        self._state = "closed"
        self._close_result = {
            "already_closed": False,
            "backend": backend_close,
            "save_count": self._save_count,
            "failed_save_count": self._failed_save_count,
        }
        return dict(self._close_result)
