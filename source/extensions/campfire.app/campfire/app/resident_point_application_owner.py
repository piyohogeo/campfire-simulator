"""Normal-application owner for the default-off Resident Point path."""

from __future__ import annotations

import threading

from .resident_application_session import ResidentApplicationSession
from .resident_point_scene import (
    RESIDENT_POINT_EMITTER_PATH,
    resident_point_frame_layout_for_logs,
    resident_point_layout_for_logs,
)
from .resident_point_sidecar import (
    RESIDENT_POINT_LAYOUT_REPRESENTATION_LEGACY,
    RESIDENT_POINT_LAYOUT_REPRESENTATION_RIGID_FRAME,
    ResidentPointSidecar,
)
from .resident_snapshot_adapter import UsdResidentSnapshotAdapter
from .resident_stage_recovery import ResidentStageRecoveryOrchestrator
from .wood import get_log_world_position


class ResidentPointApplicationOwner:
    """Own one backend/session/Point consumer/recovery composition.

    The owner adds no revision or pending-value authority.  It only assigns the
    next tick and delegates publication and recovery to the already-qualified
    session and orchestrator contracts.
    """

    def __init__(
        self,
        session,
        orchestrator,
        *,
        layout_state=None,
        log_ids=(),
        dynamic_translation_enabled=False,
        skip_unchanged_translation_layout=False,
    ):
        if session is None or orchestrator is None:
            raise ValueError("Resident Point application owner requires collaborators")
        self._owner_thread_id = threading.get_ident()
        self._session = session
        self._orchestrator = orchestrator
        self._start_count = 0
        self._stop_count = 0
        self._step_count = 0
        self._layout_replace_count = 0
        self._close_result = None
        self._layout_state = layout_state or {"revision": 1}
        self._layout_state.setdefault(
            "representation", RESIDENT_POINT_LAYOUT_REPRESENTATION_LEGACY
        )
        self._log_ids = tuple(log_ids)
        self._dynamic_translation_enabled = bool(dynamic_translation_enabled)
        self._skip_unchanged_translation_layout = bool(
            skip_unchanged_translation_layout
        )

    @classmethod
    def compose(
        cls,
        backend,
        stage,
        stage_context,
        timeline,
        next_update,
        layout,
        *,
        track_dynamic_translation=False,
        skip_unchanged_translation_layout=False,
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
            "axes": layout.get("axes", ()),
            "frames": layout.get("frames", ()),
            "representation": layout.get(
                "representation", RESIDENT_POINT_LAYOUT_REPRESENTATION_LEGACY
            ),
        }

        def make_consumers(target_stage, revision):
            translation_provider = None
            if track_dynamic_translation:
                translation_provider = lambda: tuple(
                    tuple(
                        float(component)
                        for component in get_log_world_position(target_stage, log_id)
                    )
                    for log_id in log_ids
                )
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
                    translation_provider=translation_provider,
                    layout_state=layout_state,
                    skip_unchanged_translation_layout=(
                        skip_unchanged_translation_layout
                    ),
                    layout_representation=layout_state["representation"],
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
            return cls(
                session,
                orchestrator,
                layout_state=layout_state,
                log_ids=log_ids,
                dynamic_translation_enabled=track_dynamic_translation,
                skip_unchanged_translation_layout=(
                    skip_unchanged_translation_layout
                ),
            )
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
        representation = layout.get(
            "representation", self._layout_state["representation"]
        )
        if representation != self._layout_state["representation"]:
            raise ValueError(
                "Resident Point layout representation cannot change in a session"
            )
        revision = self._session.replace_sidecar_layout(layout)
        # Keep this object identity: the recovery consumer factory closes over
        # the same mapping and must see the latest stopped-owner layout.
        self._layout_state.clear()
        self._layout_state.update(
            {
                "revision": revision,
                "origins": tuple(layout["origins"]),
                "axes": tuple(layout.get("axes", ())),
                "frames": tuple(layout.get("frames", ())),
                "representation": representation,
            }
        )
        self._layout_replace_count += 1
        return revision

    def refresh_layout(self, stage):
        """Refresh changed cardinal log transforms while the session is stopped."""

        self._require_owner()
        if not self._log_ids:
            raise RuntimeError("Resident Point owner has no application logs")
        if (
            self._layout_state["representation"]
            == RESIDENT_POINT_LAYOUT_REPRESENTATION_LEGACY
        ):
            candidate = resident_point_layout_for_logs(stage, self._log_ids)
            orientation_key = "axes"
        elif (
            self._layout_state["representation"]
            == RESIDENT_POINT_LAYOUT_REPRESENTATION_RIGID_FRAME
        ):
            candidate = resident_point_frame_layout_for_logs(stage, self._log_ids)
            orientation_key = "frames"
        else:
            raise ValueError("Resident Point owner layout representation is invalid")
        origins = tuple(candidate["origins"])
        orientation = tuple(candidate[orientation_key])
        previous_origins = tuple(self._layout_state.get("origins", ()))
        previous_orientation = tuple(self._layout_state.get(orientation_key, ()))
        if candidate["representation"] != self._layout_state["representation"]:
            raise ValueError(
                "Resident Point refreshed layout representation does not match"
            )
        origins_equal = len(origins) == len(previous_origins) and all(
            all(
                abs(left - right) <= 1.0e-9
                for left, right in zip(current, previous)
            )
            for current, previous in zip(origins, previous_origins)
        )
        result = {
            "origins": origins,
            "axes": tuple(candidate.get("axes", ())),
            "frames": tuple(candidate.get("frames", ())),
            "representation": candidate["representation"],
        }
        if origins_equal and orientation == previous_orientation:
            return {
                **result,
                "changed": False,
                "revision": self._layout_state["revision"],
            }
        layout = {
            **result,
            "revision": int(self._layout_state["revision"]) + 1,
        }
        revision = self.replace_layout(layout)
        return {
            **result,
            "changed": True,
            "revision": revision,
        }

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
            "layout_replace_count": self._layout_replace_count,
            "closed": self._close_result is not None,
            "session": self._session.status(),
            "orchestrator": self._orchestrator.status(),
            "layout_revision": self._layout_state["revision"],
            "layout_origins": self._layout_state.get("origins"),
            "layout_axes": self._layout_state.get("axes"),
            "layout_frames": self._layout_state.get("frames"),
            "layout_representation": self._layout_state["representation"],
            "log_ids": self._log_ids,
            "dynamic_translation_enabled": self._dynamic_translation_enabled,
            "skip_unchanged_translation_layout": (
                self._skip_unchanged_translation_layout
            ),
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
