"""Owner-thread lifecycle for a persistent Resident backend/consumer pair."""

from __future__ import annotations

import threading


class ResidentApplicationSession:
    """Serialize native stepping, USD publication, retry, stop, and close.

    The session is deliberately independent of UI and checkpoint policy.  It
    owns already-constructed backend and adapter instances so the finite Phase
    3 validation scenario can remain unchanged while an interactive owner is
    qualified separately.
    """

    def __init__(self, backend, adapter, *, sidecar=None):
        if backend is None or adapter is None:
            raise ValueError("Resident application session requires backend and adapter")
        self._owner_thread_id = threading.get_ident()
        self._backend = backend
        self._adapter = adapter
        self._sidecar = sidecar
        self._state = "ready"
        self._pending_step = None
        self._pending_sidecar = None
        self._step_count = 0
        self._publish_count = 0
        self._publish_failure_count = 0
        self._retry_count = 0
        self._start_count = 0
        self._stop_count = 0
        self._close_result = None

    def _prepare_sidecar(self, result):
        if self._sidecar is None:
            return None
        payload = self._sidecar.prepare(result.snapshot)
        if getattr(payload, "revision", None) != result.snapshot.revision:
            raise RuntimeError("Resident sidecar revision must match snapshot revision")
        return payload

    def _publish_pair(self, result, sidecar_payload):
        sidecar_committed = False
        if self._sidecar is not None:
            self._sidecar.publish(sidecar_payload)
            sidecar_committed = True
        try:
            self._adapter.publish(result.snapshot)
        except Exception:
            if sidecar_committed:
                self._sidecar.rollback_last_commit(result.snapshot.revision)
            raise

    def _require_owner(self):
        if threading.get_ident() != self._owner_thread_id:
            raise RuntimeError("Resident application session must run on its owner thread")

    def _require_state(self, expected):
        self._require_owner()
        if self._state != expected:
            raise RuntimeError(
                f"Resident application session requires state {expected}, got {self._state}"
            )

    def start(self):
        self._require_owner()
        if self._state not in ("ready", "stopped"):
            raise RuntimeError(
                "Resident application session can start only from ready or stopped"
            )
        self._adapter.on_timeline_started()
        self._state = "running"
        self._start_count += 1

    def stop(self):
        self._require_owner()
        if self._state == "stopped":
            return False
        if self._state != "running":
            raise RuntimeError("Resident application session can stop only while running")
        self._adapter.on_timeline_stopped()
        self._state = "stopped"
        self._stop_count += 1
        return True

    def replace_sidecar_layout(self, layout):
        self._require_owner()
        if self._sidecar is None or not hasattr(self._sidecar, "replace_layout"):
            raise RuntimeError("Resident application session has no replaceable sidecar layout")
        if self._state not in ("ready", "stopped"):
            raise RuntimeError("Resident sidecar layout replacement requires ready or stopped state")
        if self._pending_step is not None:
            raise RuntimeError("Resident sidecar layout replacement refuses a pending snapshot")
        return self._sidecar.replace_layout(layout)

    def step(self, *, tick):
        self._require_state("running")
        if self._pending_step is not None:
            raise RuntimeError(
                "Resident application session requires pending snapshot retry"
            )
        result = self._backend.step(tick=tick)
        self._step_count += 1
        sidecar_payload = None
        try:
            sidecar_payload = self._prepare_sidecar(result)
            self._publish_pair(result, sidecar_payload)
        except Exception:
            self._pending_step = result
            self._pending_sidecar = sidecar_payload
            self._publish_failure_count += 1
            raise
        self._publish_count += 1
        return result

    def retry_pending(self):
        self._require_state("running")
        if self._pending_step is None:
            raise RuntimeError("Resident application session has no pending snapshot")
        result = self._pending_step
        self._retry_count += 1
        sidecar_payload = self._pending_sidecar
        if self._sidecar is not None and sidecar_payload is None:
            sidecar_payload = self._prepare_sidecar(result)
            self._pending_sidecar = sidecar_payload
        self._publish_pair(result, sidecar_payload)
        self._pending_step = None
        self._pending_sidecar = None
        self._publish_count += 1
        return result

    def status(self):
        self._require_owner()
        pending_revision = (
            self._pending_step.snapshot.revision
            if self._pending_step is not None
            else None
        )
        return {
            "state": self._state,
            "pending_revision": pending_revision,
            "pending_sidecar_revision": (
                getattr(self._pending_sidecar, "revision", None)
                if self._pending_sidecar is not None
                else None
            ),
            "step_count": self._step_count,
            "publish_count": self._publish_count,
            "publish_failure_count": self._publish_failure_count,
            "retry_count": self._retry_count,
            "start_count": self._start_count,
            "stop_count": self._stop_count,
            "backend": self._backend.status(),
            "adapter": self._adapter.status(),
            "sidecar": self._sidecar.status() if self._sidecar is not None else None,
        }

    def close(self, *, discard_pending=False):
        self._require_owner()
        if self._state == "closed":
            return {**self._close_result, "already_closed": True}
        if self._pending_step is not None and not discard_pending:
            raise RuntimeError(
                "Resident application session refuses to close with a pending snapshot"
            )
        pending_discarded = self._pending_step is not None
        if self._state == "running":
            self.stop()
        backend_close = self._backend.close()
        adapter_close = self._adapter.close()
        sidecar_close = self._sidecar.close() if self._sidecar is not None else None
        self._pending_step = None
        self._pending_sidecar = None
        self._state = "closed"
        self._close_result = {
            "already_closed": False,
            "pending_discarded": pending_discarded,
            "backend": backend_close,
            "adapter_closed": adapter_close,
            "sidecar_closed": sidecar_close,
        }
        return dict(self._close_result)
