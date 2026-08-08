"""Normal-application owner for the default-off Resident Point path."""

from __future__ import annotations

import threading

from .resident_application_session import ResidentApplicationSession
from .resident_point_scene import RESIDENT_POINT_EMITTER_PATH
from .resident_point_sidecar import ResidentPointSidecar
from .resident_snapshot_adapter import UsdResidentSnapshotAdapter
from .resident_stage_recovery import ResidentStageRecoveryOrchestrator


class ResidentPointApplicationOwner:
    """Own one backend/session/Point consumer/recovery composition.

    The owner adds no revision or pending-value authority.  It only assigns the
    next tick and delegates publication and recovery to the already-qualified
    session and orchestrator contracts.
    """

    def __init__(self, session, orchestrator):
        if session is None or orchestrator is None:
            raise ValueError("Resident Point application owner requires collaborators")
        self._owner_thread_id = threading.get_ident()
        self._session = session
        self._orchestrator = orchestrator
        self._start_count = 0
        self._stop_count = 0
        self._step_count = 0
        self._close_result = None
        self._layout_state = {"revision": 1}
        self._log_ids = ()

    @classmethod
    def compose(
        cls,
        backend,
        stage,
        stage_context,
        timeline,
        next_update,
        layout,
    ):
        if backend is None or stage is None:
            raise ValueError("Resident Point application composition is incomplete")
        log_ids = tuple(model.spec.log_id for model in backend.models)
        initial_dry_mass = {
            log_id: sum(
                cell.dry_wood_mass_kg + cell.char_mass_kg + cell.ash_mass_kg
                for cell in model.cells
            )
            + model.emitted_pyrolysis_gas_kg
            + model.emitted_char_gas_kg
            for log_id, model in zip(log_ids, backend.models)
        }
        layout_state = {
            "revision": int(layout["revision"]),
            "origins": layout["origins"],
            "axes": layout["axes"],
        }

        def make_consumers(target_stage, revision):
            adapter = UsdResidentSnapshotAdapter(
                target_stage,
                log_ids,
                initial_dry_mass,
                cache_usd_handles=True,
                lightweight_commits=True,
                skip_unchanged_derived=True,
                coalesce_lightweight_notices=True,
                initial_revision=revision,
            )
            try:
                sidecar = ResidentPointSidecar(
                    backend,
                    target_stage,
                    RESIDENT_POINT_EMITTER_PATH,
                    stage_context.get_stage,
                    initial_revision=revision,
                    initial_layout=layout_state,
                )
            except Exception:
                adapter.close()
                raise
            return adapter, sidecar

        adapter = None
        sidecar = None
        try:
            adapter, sidecar = make_consumers(stage, backend.revision)
            session = ResidentApplicationSession(backend, adapter, sidecar=sidecar)
            orchestrator = ResidentStageRecoveryOrchestrator(
                session,
                stage_context,
                timeline,
                make_consumers,
                next_update,
                drain_updates=4,
            )
            owner = cls(session, orchestrator)
            owner._layout_state = layout_state
            owner._log_ids = log_ids
            return owner
        except Exception:
            if sidecar is not None:
                sidecar.close()
            if adapter is not None:
                adapter.close()
            backend.close()
            raise

    def _require_owner(self):
        if threading.get_ident() != self._owner_thread_id:
            raise RuntimeError("Resident Point application owner must use its owner thread")

    def start(self):
        self._require_owner()
        state = self._session.status()["state"]
        if state == "running":
            return False
        self._session.start()
        self._start_count += 1
        return True

    def stop(self):
        self._require_owner()
        state = self._session.status()["state"]
        if state in ("ready", "stopped"):
            return False
        stopped = self._session.stop()
        if stopped:
            self._stop_count += 1
        return stopped

    def step(self):
        self._require_owner()
        backend_status = self._session.status()["backend"]
        result = self._session.step(tick=int(backend_status["tick"]) + 1)
        self._step_count += 1
        return result

    def replace_layout(self, layout):
        self._require_owner()
        revision = self._session.replace_sidecar_layout(layout)
        self._layout_state = {
            "revision": revision,
            "origins": layout["origins"],
            "axes": layout["axes"],
        }
        return revision

    def observe_stage_event(self, event_name):
        self._require_owner()
        self._orchestrator.observe_stage_event(event_name)

    async def replace_stage(self, replacement_stage):
        self._require_owner()
        return await self._orchestrator.replace_stage(replacement_stage)

    def retry_recovery(self):
        self._require_owner()
        return self._orchestrator.retry_recovery()

    def status(self):
        self._require_owner()
        return {
            "start_count": self._start_count,
            "stop_count": self._stop_count,
            "step_count": self._step_count,
            "closed": self._close_result is not None,
            "session": self._session.status(),
            "orchestrator": self._orchestrator.status(),
            "layout_revision": self._layout_state["revision"],
            "log_ids": self._log_ids,
        }

    def close(self, *, discard_pending=False):
        self._require_owner()
        if self._close_result is not None:
            return {**self._close_result, "already_closed": True}
        result = self._session.close(discard_pending=discard_pending)
        self._close_result = {
            "already_closed": False,
            "session": result,
        }
        return dict(self._close_result)
