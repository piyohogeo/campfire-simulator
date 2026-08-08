"""Owner-thread command boundary for stopped Resident Point layout edits."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ResidentPointCommandResult:
    """Immutable result shared by interactive UI and headless qualification."""

    sequence: int
    command: str
    source: str
    status: str
    code: str
    message: str
    layout_revision: int | None = None
    layout_changed: bool | None = None

    @property
    def accepted(self) -> bool:
        return self.status == "accepted"

    def to_dict(self) -> dict:
        return {**asdict(self), "accepted": self.accepted}


def format_resident_point_command_result(result: ResidentPointCommandResult) -> str:
    """Return the one-line result text used by both UI and logs."""

    prefix = "Applied" if result.accepted else "Rejected"
    revision = (
        f" · layout revision {result.layout_revision}"
        if result.layout_revision is not None
        else ""
    )
    return f"{prefix} #{result.sequence} [{result.code}]{revision}: {result.message}"


class ResidentPointCommandQueue:
    """Queue layout commands while keeping all USD work on the owner thread.

    ``submit_refresh_layout`` only appends a small immutable command and may be
    called from another thread.  ``drain`` is the sole execution boundary and
    must run on the thread that constructed the queue and application owner.
    The queue owns no wood values, Point arrays, revision, or rollback state.
    """

    def __init__(self, owner, stage_provider, *, max_pending=32, max_results=64):
        if owner is None or not callable(stage_provider):
            raise ValueError("Resident Point command queue requires collaborators")
        if max_pending < 1 or max_results < 1:
            raise ValueError("Resident Point command queue bounds must be positive")
        self._owner_thread_id = threading.get_ident()
        self._owner = owner
        self._stage_provider = stage_provider
        self._max_pending = int(max_pending)
        self._pending = deque()
        self._results = deque(maxlen=int(max_results))
        self._delivery_results = deque()
        self._next_sequence = 1
        self._submitted_count = 0
        self._executed_count = 0
        self._rejected_count = 0
        self._closed = False
        self._lock = threading.Lock()

    def _require_owner_thread(self):
        if threading.get_ident() != self._owner_thread_id:
            raise RuntimeError("Resident Point commands must drain on the owner thread")

    def submit_refresh_layout(self, *, source="api") -> int:
        """Queue a stopped-layout refresh without reading the USD stage."""

        source = str(source).strip()
        if not source:
            raise ValueError("Resident Point command source must not be empty")
        with self._lock:
            sequence = self._next_sequence
            self._next_sequence += 1
            self._submitted_count += 1
            if self._closed:
                self._append_rejection_locked(
                    sequence, source, "queue_closed", "Command queue is closed."
                )
            elif len(self._pending) >= self._max_pending:
                self._append_rejection_locked(
                    sequence, source, "queue_full", "Command queue is full."
                )
            else:
                self._pending.append((sequence, "refresh_layout", source))
            return sequence

    def _append_rejection_locked(self, sequence, source, code, message):
        result = ResidentPointCommandResult(
            sequence,
            "refresh_layout",
            source,
            "rejected",
            code,
            message,
        )
        self._results.append(result)
        self._delivery_results.append(result)
        self._rejected_count += 1

    def drain(self, *, max_commands=None) -> tuple[ResidentPointCommandResult, ...]:
        """Execute pending commands against the current stage on the owner thread."""

        self._require_owner_thread()
        if max_commands is not None and max_commands < 1:
            raise ValueError("max_commands must be positive")
        completed = []
        while max_commands is None or len(completed) < max_commands:
            with self._lock:
                pending_sequence = self._pending[0][0] if self._pending else None
                delivery_sequence = (
                    self._delivery_results[0].sequence
                    if self._delivery_results
                    else None
                )
                if pending_sequence is None and delivery_sequence is None:
                    break
                if delivery_sequence is not None and (
                    pending_sequence is None or delivery_sequence < pending_sequence
                ):
                    completed.append(self._delivery_results.popleft())
                    continue
                sequence, command, source = self._pending.popleft()
            try:
                stage = self._stage_provider()
                if stage is None:
                    raise RuntimeError("Resident Point stage is unavailable")
                layout = self._owner.refresh_layout(stage)
                changed = bool(layout["changed"])
                result = ResidentPointCommandResult(
                    sequence,
                    command,
                    source,
                    "accepted",
                    "layout_replaced" if changed else "layout_unchanged",
                    "Stopped log layout was committed."
                    if changed
                    else "Stopped log layout already matches the Point layout.",
                    int(layout["revision"]),
                    changed,
                )
            except ValueError as exc:
                result = ResidentPointCommandResult(
                    sequence,
                    command,
                    source,
                    "rejected",
                    "unsupported_layout",
                    str(exc),
                )
            except Exception as exc:
                result = ResidentPointCommandResult(
                    sequence,
                    command,
                    source,
                    "failed",
                    "execution_failed",
                    str(exc),
                )
            with self._lock:
                self._results.append(result)
                self._executed_count += 1
                if not result.accepted:
                    self._rejected_count += 1
            completed.append(result)
        return tuple(completed)

    def results_since(self, sequence=0) -> tuple[ResidentPointCommandResult, ...]:
        """Return retained results newer than ``sequence`` without consuming them."""

        with self._lock:
            return tuple(result for result in self._results if result.sequence > sequence)

    def status(self) -> dict:
        with self._lock:
            return {
                "closed": self._closed,
                "pending_count": len(self._pending),
                "retained_result_count": len(self._results),
                "submitted_count": self._submitted_count,
                "executed_count": self._executed_count,
                "rejected_count": self._rejected_count,
                "next_sequence": self._next_sequence,
                "owner_thread_id": self._owner_thread_id,
            }

    def close(self) -> tuple[ResidentPointCommandResult, ...]:
        """Reject queued work explicitly; never apply it during shutdown."""

        self._require_owner_thread()
        rejected = []
        with self._lock:
            self._closed = True
            while self._pending:
                sequence, command, source = self._pending.popleft()
                result = ResidentPointCommandResult(
                    sequence,
                    command,
                    source,
                    "rejected",
                    "queue_closed",
                    "Command was discarded because the queue closed.",
                )
                self._results.append(result)
                self._rejected_count += 1
                rejected.append(result)
        return tuple(rejected)
