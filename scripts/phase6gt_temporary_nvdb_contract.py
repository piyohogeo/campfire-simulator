"""Pure helpers for the Phase 6GT one-file temporary NanoVDB boundary."""

from __future__ import annotations

import time
from pathlib import Path


TEMPORARY_FILENAME = "phase6gt_slot0_temperature_once.nvdb"
MAXIMUM_FILE_BYTES = 256 * 1024 * 1024
POLL_TIMEOUT_SECONDS = 10.0
POLL_INTERVAL_SECONDS = 0.05


def exact_temporary_path(artifact_directory: Path) -> Path:
    root = Path(artifact_directory).resolve()
    path = (root / TEMPORARY_FILENAME).resolve()
    if path.parent != root or path.name != TEMPORARY_FILENAME:
        raise ValueError("temporary NanoVDB path escaped the process artifact directory")
    return path


def require_absent(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"temporary NanoVDB path already exists: {path}")


def require_save_return(value) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"save_volume return must be bool, got {type(value).__name__}")
    if not value:
        raise RuntimeError("save_volume returned false")
    return value


def poll_nonempty_file(
    path: Path,
    *,
    timeout_seconds: float = POLL_TIMEOUT_SECONDS,
    interval_seconds: float = POLL_INTERVAL_SECONDS,
    maximum_file_bytes: int = MAXIMUM_FILE_BYTES,
) -> dict:
    if timeout_seconds <= 0 or interval_seconds <= 0:
        raise ValueError("poll bounds must be positive")
    started = time.monotonic()
    while True:
        exists = path.is_file()
        size = int(path.stat().st_size) if exists else 0
        elapsed = time.monotonic() - started
        if exists and size > 0:
            if size > maximum_file_bytes:
                raise RuntimeError(
                    f"temporary NanoVDB exceeded {maximum_file_bytes} bytes: {size}"
                )
            return {
                "elapsed_seconds": elapsed,
                "file_exists": True,
                "file_size_bytes": size,
                "maximum_file_bytes": maximum_file_bytes,
                "within_limit": True,
            }
        if elapsed >= timeout_seconds:
            raise TimeoutError(
                f"temporary NanoVDB was not nonempty within {timeout_seconds} seconds"
            )
        time.sleep(min(interval_seconds, max(0.0, timeout_seconds - elapsed)))


def delete_exact_temporary(path: Path, artifact_directory: Path) -> dict:
    expected = exact_temporary_path(artifact_directory)
    if path.resolve() != expected:
        raise ValueError("refusing to delete a path other than the exact Phase 6GT temporary file")
    existed_before = path.is_file()
    size_before = int(path.stat().st_size) if existed_before else 0
    if existed_before:
        path.unlink()
    exists_after = path.exists()
    if exists_after:
        raise RuntimeError("temporary NanoVDB deletion did not remove the exact file")
    return {
        "file_existed_before_delete": existed_before,
        "file_size_before_delete_bytes": size_before,
        "file_exists_after_delete": False,
        "deleted": existed_before,
    }
