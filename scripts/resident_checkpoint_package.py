"""Isolated versioned package format for Resident checkpoint research."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import zipfile
from pathlib import Path


CHECKPOINT_KIND = "campfire.resident.checkpoint"
CHECKPOINT_VERSION = 1
MANIFEST_ENTRY = "manifest.json"
STAGE_ENTRY = "stage.usda"
MAX_ENTRY_BYTES = 64 * 1024 * 1024
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_RESERVED_METADATA_KEYS = {"kind", "schema_version", "stage"}


def canonical_json(value):
    return json.dumps(
        value, allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _zip_info(name):
    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    return info


def _validate_manifest(manifest):
    if manifest.get("kind") != CHECKPOINT_KIND:
        raise ValueError("Unsupported checkpoint kind")
    if manifest.get("schema_version") != CHECKPOINT_VERSION:
        raise ValueError("Unsupported checkpoint schema version")
    revision = manifest.get("revision")
    tick = manifest.get("tick")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ValueError("Checkpoint revision is invalid")
    if isinstance(tick, bool) or not isinstance(tick, int) or tick < -1:
        raise ValueError("Checkpoint tick is invalid")
    log_ids = manifest.get("log_ids")
    if (
        not isinstance(log_ids, list)
        or not log_ids
        or any(not isinstance(log_id, str) or not log_id for log_id in log_ids)
        or len(set(log_ids)) != len(log_ids)
    ):
        raise ValueError("Checkpoint log order is invalid")
    model_hashes = manifest.get("model_state_sha256")
    if (
        not isinstance(model_hashes, dict)
        or set(model_hashes) != set(log_ids)
        or any(
            not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value)
            for value in model_hashes.values()
        )
    ):
        raise ValueError("Checkpoint model-state hashes are invalid")
    consumer_revisions = manifest.get("consumer_revisions")
    if (
        not isinstance(consumer_revisions, list)
        or len(consumer_revisions) != len(log_ids) + 1
        or any(value != revision for value in consumer_revisions)
    ):
        raise ValueError("Checkpoint consumer revisions do not match revision")
    initial_dry_mass = manifest.get("initial_dry_mass_kg")
    if (
        not isinstance(initial_dry_mass, dict)
        or set(initial_dry_mass) != set(log_ids)
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0.0
            for value in initial_dry_mass.values()
        )
    ):
        raise ValueError("Checkpoint initial dry masses are invalid")
    scheduler = manifest.get("scheduler")
    if not isinstance(scheduler, dict):
        raise ValueError("Checkpoint scheduler is invalid")
    dt_seconds = scheduler.get("dt_seconds")
    heat_flux = scheduler.get("heat_flux_w_m2")
    if (
        isinstance(dt_seconds, bool)
        or not isinstance(dt_seconds, (int, float))
        or not math.isfinite(dt_seconds)
        or dt_seconds <= 0.0
        or isinstance(heat_flux, bool)
        or not isinstance(heat_flux, (int, float))
        or not math.isfinite(heat_flux)
    ):
        raise ValueError("Checkpoint scheduler values are invalid")
    native = manifest.get("native")
    abi_version = native.get("abi_version") if isinstance(native, dict) else None
    if (
        isinstance(abi_version, bool)
        or not isinstance(abi_version, int)
        or abi_version < 1
    ):
        raise ValueError("Checkpoint native ABI version is invalid")


def write_checkpoint(path, stage_text, metadata, *, inject_before_replace=False):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    reserved = _RESERVED_METADATA_KEYS.intersection(metadata)
    if reserved:
        raise ValueError(f"Checkpoint metadata uses reserved keys: {sorted(reserved)}")
    stage_bytes = stage_text.encode("utf-8")
    manifest = {
        "kind": CHECKPOINT_KIND,
        "schema_version": CHECKPOINT_VERSION,
        "stage": {
            "entry": STAGE_ENTRY,
            "bytes": len(stage_bytes),
            "sha256": sha256_bytes(stage_bytes),
        },
        **metadata,
    }
    _validate_manifest(manifest)
    manifest_bytes = canonical_json(manifest)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("wb") as stream:
            with zipfile.ZipFile(stream, "w") as archive:
                archive.writestr(_zip_info(MANIFEST_ENTRY), manifest_bytes)
                archive.writestr(_zip_info(STAGE_ENTRY), stage_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        if inject_before_replace:
            raise RuntimeError("Injected checkpoint interruption before replace")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return manifest


def read_checkpoint(path):
    path = Path(path).resolve()
    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        if [info.filename for info in infos] != [MANIFEST_ENTRY, STAGE_ENTRY]:
            raise ValueError("Checkpoint archive entries are not canonical")
        if any(
            info.file_size < 1 or info.file_size > MAX_ENTRY_BYTES for info in infos
        ):
            raise ValueError("Checkpoint archive entry size is invalid")
        manifest_bytes = archive.read(MANIFEST_ENTRY)
        stage_bytes = archive.read(STAGE_ENTRY)
    manifest = json.loads(manifest_bytes)
    _validate_manifest(manifest)
    stage = manifest.get("stage", {})
    if stage.get("entry") != STAGE_ENTRY:
        raise ValueError("Checkpoint stage entry is invalid")
    if stage.get("bytes") != len(stage_bytes):
        raise ValueError("Checkpoint stage byte count mismatch")
    if stage.get("sha256") != sha256_bytes(stage_bytes):
        raise ValueError("Checkpoint stage hash mismatch")
    return manifest, stage_bytes.decode("utf-8")
