"""Bounded Windows-safe atomic JSON replacement for Phase 6HU diagnostics.

The durable JSONL lifecycle stream remains the source of truth.  This helper
only makes the bounded snapshot replace robust against short-lived Windows
sharing conflicts and refuses concurrent writers.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator


MAX_JSON_BYTES = 1024 * 1024
RETRYABLE_WINDOWS_ERRORS = frozenset((5, 32, 33))
BACKOFF_SECONDS = (0.010, 0.020, 0.040, 0.080)
MAX_ATTEMPTS = 1 + len(BACKOFF_SECONDS)
MAX_ELAPSED_SECONDS = 0.250


class AtomicReportError(RuntimeError):
    """Fail-closed atomic snapshot error with a stable machine reason."""

    def __init__(self, reason: str, *, attempts: int = 0, winerror: int | None = None):
        super().__init__(reason)
        self.reason = reason
        self.attempts = attempts
        self.winerror = winerror


def canonical_bytes(payload: dict) -> bytes:
    if not isinstance(payload, dict):
        raise AtomicReportError("payload_type_invalid")
    try:
        data = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError) as error:
        raise AtomicReportError("payload_json_invalid") from error
    if not data or len(data) > MAX_JSON_BYTES:
        raise AtomicReportError("payload_size_invalid")
    return data


def append_durable_jsonl(path: Path, row: dict) -> None:
    data = (json.dumps(row, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    if len(data) > 16 * 1024:
        raise AtomicReportError("marker_row_oversize")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _winerror(error: BaseException) -> int | None:
    value = getattr(error, "winerror", None)
    if value is None and isinstance(error, PermissionError):
        value = getattr(error, "errno", None)
    return int(value) if isinstance(value, int) else None


def _retryable(error: BaseException) -> bool:
    value = _winerror(error)
    return value in RETRYABLE_WINDOWS_ERRORS


@contextmanager
def writer_lease(path: Path) -> Iterator[Path]:
    lease = path.with_name(path.name + ".writer.lock")
    lease.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(str(lease), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise AtomicReportError("concurrent_writer_rejected") from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(f"{os.getpid()}:{threading.get_ident()}\n".encode("ascii"))
            stream.flush()
            os.fsync(stream.fileno())
        yield lease
    finally:
        try:
            lease.unlink()
        except FileNotFoundError:
            pass


def atomic_write_json(
    path: Path,
    payload: dict,
    *,
    event: Callable[[dict], None] | None = None,
) -> dict:
    """Write a bounded JSON snapshot with targeted, elapsed-bounded retries.

    Retries apply only to Windows sharing/access errors 5, 32, and 33.  A
    unique same-directory temporary and an exclusive writer lease prevent
    temporary-name collisions and ambiguous multi-writer ordering.
    """

    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_bytes(payload)
    token = f"{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}"
    temporary = path.with_name(path.name + ".partial." + token)
    started = time.monotonic()
    attempts = 0
    last_error: BaseException | None = None

    def emit(kind: str, **values) -> None:
        if event is not None:
            event({"event": kind, "attempt": attempts, **values})

    with writer_lease(path):
        try:
            with temporary.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            for index in range(MAX_ATTEMPTS):
                attempts = index + 1
                try:
                    os.replace(temporary, path)
                    elapsed = time.monotonic() - started
                    emit("atomic_replace_complete", elapsed_seconds=elapsed, bytes=len(data))
                    return {
                        "attempts": attempts,
                        "elapsed_seconds": elapsed,
                        "bytes": len(data),
                        "temporary_name": temporary.name,
                    }
                except OSError as error:
                    last_error = error
                    elapsed = time.monotonic() - started
                    value = _winerror(error)
                    if not _retryable(error):
                        emit("atomic_replace_nonretryable", elapsed_seconds=elapsed, winerror=value)
                        raise AtomicReportError("atomic_replace_nonretryable", attempts=attempts, winerror=value) from error
                    if index >= len(BACKOFF_SECONDS) or elapsed >= MAX_ELAPSED_SECONDS:
                        break
                    delay = min(BACKOFF_SECONDS[index], max(0.0, MAX_ELAPSED_SECONDS - elapsed))
                    emit("atomic_replace_retry", elapsed_seconds=elapsed, winerror=value, backoff_seconds=delay)
                    if delay > 0.0:
                        time.sleep(delay)
            elapsed = time.monotonic() - started
            value = _winerror(last_error) if last_error is not None else None
            emit("atomic_replace_exhausted", elapsed_seconds=elapsed, winerror=value)
            raise AtomicReportError("atomic_replace_retry_exhausted", attempts=attempts, winerror=value) from last_error
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

