"""Owner-thread orchestration for default-off Resident stage recovery."""

from __future__ import annotations

import inspect
import threading


class ResidentStageRecoveryOrchestrator:
    """Close, attach, rebuild, rebind, and retry one Resident session safely."""

    _REQUIRED_EVENTS = ("closing", "closed", "opening", "opened")

    def __init__(
        self,
        session,
        stage_context,
        timeline,
        consumer_factory,
        next_update,
        *,
        drain_updates=4,
    ):
        if any(
            value is None
            for value in (
                session,
                stage_context,
                timeline,
                consumer_factory,
                next_update,
            )
        ):
            raise ValueError("Resident stage recovery requires all collaborators")
        if (
            isinstance(drain_updates, bool)
            or not isinstance(drain_updates, int)
            or drain_updates < 1
        ):
            raise ValueError("Resident stage recovery drain count must be positive")
        self._owner_thread_id = threading.get_ident()
        self._session = session
        self._stage_context = stage_context
        self._timeline = timeline
        self._consumer_factory = consumer_factory
        self._next_update = next_update
        self._drain_updates = drain_updates
        self._state = "idle"
        self._observed_events = []
        self._resume_running = False
        self._attached_stage = None
        self._attempt_count = 0
        self._success_count = 0
        self._failure_count = 0
        self._recovery_retry_count = 0
        self._last_error = None
        self._last_result = None

    def _require_owner(self):
        if threading.get_ident() != self._owner_thread_id:
            raise RuntimeError("Resident stage recovery must run on its owner thread")

    @staticmethod
    def _unpack_result(result, operation):
        if not isinstance(result, tuple) or len(result) != 2:
            raise RuntimeError(f"Resident stage {operation} returned an invalid result")
        success, error = result
        if not success:
            raise RuntimeError(f"Resident stage {operation} failed: {error}")

    async def _drain(self):
        for _ in range(self._drain_updates):
            result = self._next_update()
            if inspect.isawaitable(result):
                await result

    def observe_stage_event(self, event_name):
        self._require_owner()
        if event_name in self._REQUIRED_EVENTS:
            self._observed_events.append(event_name)

    def _events_complete(self):
        position = 0
        for event_name in self._observed_events:
            if event_name == self._REQUIRED_EVENTS[position]:
                position += 1
                if position == len(self._REQUIRED_EVENTS):
                    return True
        return False

    def _record_failure(self, error):
        self._state = "faulted"
        self._failure_count += 1
        self._last_error = f"{type(error).__name__}: {error}"

    def _finalize_attached_stage(self):
        self._require_owner()
        if self._attached_stage is None:
            raise RuntimeError("Resident stage recovery has no attached stage")
        committed_revision = self._session.status()["adapter"]["revision"]
        adapter, sidecar = self._consumer_factory(
            self._attached_stage, committed_revision
        )
        rebind = self._session.replace_consumers(adapter, sidecar=sidecar)
        session_started = False
        pending_retried = False
        if self._resume_running or rebind["pending_revision"] is not None:
            self._session.start()
            session_started = True
        if rebind["pending_revision"] is not None:
            self._session.retry_pending()
            pending_retried = True
        if not self._resume_running and session_started:
            self._session.stop()
        self._state = "running" if self._resume_running else "stopped"
        self._success_count += 1
        self._last_error = None
        self._last_result = {
            "committed_revision": committed_revision,
            "pending_revision": rebind["pending_revision"],
            "pending_retried": pending_retried,
            "session_state": self._session.status()["state"],
            "consumer_replace_count": rebind["consumer_replace_count"],
            "observed_events": tuple(self._observed_events),
        }
        return dict(self._last_result)

    async def replace_stage(self, replacement_stage):
        self._require_owner()
        if self._state not in ("idle", "running", "stopped"):
            raise RuntimeError("Resident stage recovery is already active or faulted")
        if replacement_stage is None:
            raise ValueError("Resident stage recovery requires a replacement stage")
        session_state = self._session.status()["state"]
        if session_state not in ("running", "stopped"):
            raise RuntimeError("Resident stage recovery requires a running or stopped session")
        self._attempt_count += 1
        self._resume_running = session_state == "running"
        self._observed_events = []
        self._attached_stage = None
        self._last_error = None
        try:
            if session_state == "running":
                self._session.stop()
            self._timeline.stop()
            self._state = "closing"
            self._unpack_result(
                await self._stage_context.close_stage_async(), "close"
            )
            await self._drain()
            self._state = "opening"
            self._unpack_result(
                await self._stage_context.attach_stage_async(replacement_stage),
                "attach",
            )
            await self._drain()
            if not self._events_complete():
                raise RuntimeError("Resident stage lifecycle events are incomplete")
            attached_stage = self._stage_context.get_stage()
            if attached_stage is not replacement_stage:
                raise RuntimeError("Resident stage context attached an unexpected stage")
            self._attached_stage = attached_stage
            self._state = "rebuilding"
            return self._finalize_attached_stage()
        except Exception as error:
            self._record_failure(error)
            raise

    def retry_recovery(self):
        self._require_owner()
        if self._state != "faulted" or self._attached_stage is None:
            raise RuntimeError("Resident stage recovery has no retryable attached stage")
        self._recovery_retry_count += 1
        self._state = "rebuilding"
        try:
            return self._finalize_attached_stage()
        except Exception as error:
            self._record_failure(error)
            raise

    def status(self):
        self._require_owner()
        return {
            "state": self._state,
            "attempt_count": self._attempt_count,
            "success_count": self._success_count,
            "failure_count": self._failure_count,
            "recovery_retry_count": self._recovery_retry_count,
            "drain_updates": self._drain_updates,
            "observed_events": tuple(self._observed_events),
            "attached_stage_available": self._attached_stage is not None,
            "last_error": self._last_error,
            "last_result": (
                dict(self._last_result) if self._last_result is not None else None
            ),
        }
