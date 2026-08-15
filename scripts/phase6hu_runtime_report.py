"""Durable marker and bounded raw-report adapter used by the Phase 6HU probe."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from phase6hu_atomic_report import AtomicReportError, append_durable_jsonl, atomic_write_json


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class DurableOperationReporter:
    """Keep lifecycle markers durable even when the replaceable snapshot fails."""

    def __init__(self, output: Path, markers: Path, atomic_markers: Path, report: dict, attempt_id: str):
        self.output = Path(output)
        self.markers = Path(markers)
        self.atomic_markers = Path(atomic_markers)
        self.report = report
        self.attempt_id = attempt_id
        self.cleanup_mode = False
        self.raw_report_failure: dict | None = None

    def enter_cleanup(self) -> None:
        self.cleanup_mode = True

    def _atomic_event(self, row: dict) -> None:
        append_durable_jsonl(
            self.atomic_markers,
            {"timestamp_utc": _utc(), "attempt_id": self.attempt_id, **row},
        )

    def mark(self, name: str, **values) -> bool:
        row = {"timestamp_utc": _utc(), "name": name, "attempt_id": self.attempt_id, **values}
        append_durable_jsonl(self.markers, row)
        self.report["last_marker"] = name
        try:
            atomic_write_json(self.output, self.report, event=self._atomic_event)
            return True
        except AtomicReportError as error:
            failure = {
                "reason": error.reason,
                "attempts": error.attempts,
                "winerror": error.winerror,
                "failed_after_marker": name,
            }
            self.raw_report_failure = failure
            self.report["raw_report_failure"] = failure
            self._atomic_event({"event": "raw_report_update_failed", **failure})
            if not self.cleanup_mode:
                raise
            return False

    def try_final_write(self) -> bool:
        try:
            atomic_write_json(self.output, self.report, event=self._atomic_event)
            return True
        except AtomicReportError as error:
            self._atomic_event(
                {
                    "event": "raw_report_final_write_failed",
                    "reason": error.reason,
                    "attempts": error.attempts,
                    "winerror": error.winerror,
                }
            )
            return False
