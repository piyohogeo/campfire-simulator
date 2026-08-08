"""Exercise an isolated immutable legacy/frame payload contract.

This probe imports the production ResidentApplicationSession implementation by
file path, but deliberately supplies prototype-only backend and consumer
objects.  No production module is edited or monkey-patched.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import statistics
import struct
import sys
import time
from dataclasses import FrozenInstanceError, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SESSION_SOURCE = (
    ROOT
    / "source"
    / "extensions"
    / "campfire.app"
    / "campfire"
    / "app"
    / "resident_application_session.py"
)
REPRESENTATIONS = ("legacy_cardinal_axes_v1", "rigid_frame_v1")
POINT_COUNT = 720


def _load_session_class():
    spec = importlib.util.spec_from_file_location(
        "campfire_phase6dl_session", SESSION_SOURCE
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Resident session: {SESSION_SOURCE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.ResidentApplicationSession


ResidentApplicationSession = _load_session_class()


def _finite_triplet(value):
    return (
        type(value) is tuple
        and len(value) == 3
        and all(math.isfinite(float(component)) for component in value)
    )


def _basis_is_rigid(frame):
    if type(frame) is not tuple or len(frame) != 9:
        return False
    if not all(math.isfinite(float(component)) for component in frame):
        return False
    x = frame[0:3]
    y = frame[3:6]
    z = frame[6:9]
    dot = lambda a, b: sum(float(a[i]) * float(b[i]) for i in range(3))
    cross = (
        x[1] * y[2] - x[2] * y[1],
        x[2] * y[0] - x[0] * y[2],
        x[0] * y[1] - x[1] * y[0],
    )
    return (
        all(abs(dot(axis, axis) - 1.0) <= 1.0e-9 for axis in (x, y, z))
        and all(abs(dot(a, b)) <= 1.0e-9 for a, b in ((x, y), (x, z), (y, z)))
        and dot(cross, z) > 1.0 - 1.0e-9
    )


@dataclass(frozen=True)
class PrototypeLayoutDescriptor:
    representation: str
    revision: int
    origins: tuple
    cardinal_axes: tuple = ()
    rigid_frames: tuple = ()

    def __post_init__(self):
        if self.representation not in REPRESENTATIONS:
            raise ValueError("Unknown surface layout representation")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int):
            raise TypeError("Layout revision must be an integer")
        if self.revision <= 0:
            raise ValueError("Layout revision must be positive")
        if type(self.origins) is not tuple or not self.origins:
            raise TypeError("Layout origins must be a non-empty immutable tuple")
        if not all(_finite_triplet(origin) for origin in self.origins):
            raise ValueError("Layout origins must contain finite triplets")
        if type(self.cardinal_axes) is not tuple or type(self.rigid_frames) is not tuple:
            raise TypeError("Layout representation data must be immutable tuples")
        if self.representation == "legacy_cardinal_axes_v1":
            if self.rigid_frames or len(self.cardinal_axes) != len(self.origins):
                raise ValueError("Legacy layout requires only one cardinal axis per origin")
            if any(type(axis) is not int or axis not in (0, 1) for axis in self.cardinal_axes):
                raise ValueError("Legacy cardinal axes must contain only 0 or 1")
        else:
            if self.cardinal_axes or len(self.rigid_frames) != len(self.origins):
                raise ValueError("Frame layout requires only one rigid frame per origin")
            if not all(_basis_is_rigid(frame) for frame in self.rigid_frames):
                raise ValueError("Frame layout requires right-handed orthonormal bases")

    def digest(self):
        value = (
            self.representation,
            self.revision,
            self.origins,
            self.cardinal_axes,
            self.rigid_frames,
        )
        return hashlib.sha256(repr(value).encode("ascii")).hexdigest()


@dataclass(frozen=True)
class PrototypeSurfacePayload:
    revision: int
    tick: int
    layout: PrototypeLayoutDescriptor
    point_count: int
    positions: bytes
    fuels: bytes
    temperatures: bytes
    smokes: bytes

    def __post_init__(self):
        if self.revision <= 0 or self.tick < 0 or self.point_count <= 0:
            raise ValueError("Payload revision, tick, or point count is invalid")
        if not isinstance(self.layout, PrototypeLayoutDescriptor):
            raise TypeError("Payload requires an immutable layout descriptor")
        values = (self.positions, self.fuels, self.temperatures, self.smokes)
        if any(type(value) is not bytes for value in values):
            raise TypeError("Payload arrays must be immutable bytes")
        if len(self.positions) != self.point_count * 12:
            raise ValueError("Payload position byte count is invalid")
        if any(len(value) != self.point_count * 4 for value in values[1:]):
            raise ValueError("Payload channel byte count is invalid")

    def digest(self):
        value = hashlib.sha256()
        value.update(struct.pack("<qqq", self.revision, self.tick, self.point_count))
        value.update(self.layout.digest().encode("ascii"))
        for field in (self.positions, self.fuels, self.temperatures, self.smokes):
            value.update(field)
        return value.hexdigest()


@dataclass(frozen=True)
class _Snapshot:
    revision: int
    tick: int


@dataclass(frozen=True)
class _Step:
    snapshot: _Snapshot


def _float_bytes(count, callback):
    return b"".join(struct.pack("<f", float(callback(index))) for index in range(count))


def _payload_arrays(revision):
    positions = _float_bytes(
        POINT_COUNT * 3,
        lambda index: (index % 17) * 0.001 + revision * 0.00001,
    )
    fuels = _float_bytes(POINT_COUNT, lambda index: 0.2 + (index % 7) * 0.01)
    temperatures = _float_bytes(
        POINT_COUNT, lambda index: 293.15 + (index % 360) * 0.5
    )
    smokes = _float_bytes(POINT_COUNT, lambda index: (index % 5) * 0.02)
    return positions, fuels, temperatures, smokes


class _Backend:
    def __init__(self):
        self.revision = 0
        self.tick = -1
        self.closed = False

    def step(self, *, tick):
        if self.closed:
            raise RuntimeError("Backend is closed")
        if tick <= self.tick:
            raise ValueError("Tick must advance")
        self.revision += 1
        self.tick = tick
        return _Step(_Snapshot(self.revision, tick))

    def status(self):
        return {"revision": self.revision, "tick": self.tick, "closed": self.closed}

    def close(self):
        self.closed = True
        return {"revision": self.revision, "tick": self.tick}


class _Adapter:
    def __init__(self, initial_revision=0, fail_once_revision=None):
        self.revision = initial_revision
        self.fail_once_revision = fail_once_revision
        self.active = False
        self.closed = False

    def on_timeline_started(self):
        if self.closed:
            raise RuntimeError("Adapter is closed")
        self.active = True

    def on_timeline_stopped(self):
        self.active = False

    def publish(self, snapshot):
        if snapshot.revision != self.revision + 1:
            raise ValueError("Adapter revision is not consecutive")
        if snapshot.revision == self.fail_once_revision:
            self.fail_once_revision = None
            raise RuntimeError("Injected primary publication failure")
        self.revision = snapshot.revision

    def status(self):
        return {
            "revision": self.revision,
            "active": self.active,
            "closed": self.closed,
        }

    def close(self):
        already_closed = self.closed
        self.active = False
        self.closed = True
        return not already_closed


class _Sidecar:
    def __init__(self, layout, initial_revision=0):
        self.layout = layout
        self.revision = initial_revision
        self.closed = False
        self.rollback_count = 0
        self.attempts = []
        self.last_payload = None
        self._history = []

    def prepare(self, snapshot):
        arrays = _payload_arrays(snapshot.revision)
        return PrototypeSurfacePayload(
            revision=snapshot.revision,
            tick=snapshot.tick,
            layout=self.layout,
            point_count=POINT_COUNT,
            positions=arrays[0],
            fuels=arrays[1],
            temperatures=arrays[2],
            smokes=arrays[3],
        )

    def publish(self, payload):
        if self.closed:
            raise RuntimeError("Sidecar is closed")
        if payload.layout.representation != self.layout.representation:
            raise ValueError("Surface representation mismatch")
        if payload.layout.digest() != self.layout.digest():
            raise ValueError("Surface layout descriptor mismatch")
        if payload.revision != self.revision + 1:
            raise ValueError("Sidecar revision is not consecutive")
        self.attempts.append({"id": id(payload), "digest": payload.digest()})
        self._history.append((self.revision, self.last_payload))
        self.revision = payload.revision
        self.last_payload = payload

    def rollback_last_commit(self, revision):
        if self.revision != revision or not self._history:
            raise RuntimeError("Sidecar rollback boundary is invalid")
        self.revision, self.last_payload = self._history.pop()
        self.rollback_count += 1

    def status(self):
        return {
            "revision": self.revision,
            "layout_revision": self.layout.revision,
            "representation": self.layout.representation,
            "layout_digest": self.layout.digest(),
            "rollback_count": self.rollback_count,
            "closed": self.closed,
        }

    def close(self):
        already_closed = self.closed
        self.closed = True
        return not already_closed


class _RepresentationGuard:
    def __init__(self, session, layout):
        self.session = session
        self.layout = layout
        self.rejected_switches = 0

    def require_same_representation(self, layout):
        if layout.representation != self.layout.representation:
            self.rejected_switches += 1
            raise ValueError("Resident layout representation is fixed for the session")

    def replace_consumers(self, adapter, sidecar):
        self.require_same_representation(sidecar.layout)
        if sidecar.layout.digest() != self.layout.digest():
            raise ValueError("Replacement layout descriptor does not match committed layout")
        return self.session.replace_consumers(adapter, sidecar=sidecar)


def _layout(representation):
    origins = ((-0.25, 0.0, 0.16), (0.25, 0.0, 0.16))
    if representation == "legacy_cardinal_axes_v1":
        return PrototypeLayoutDescriptor(representation, 1, origins, (0, 1), ())
    return PrototypeLayoutDescriptor(
        representation,
        1,
        origins,
        (),
        (
            (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
            (0.0, 1.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.0, 1.0),
        ),
    )


def _equivalent_layout(layout):
    return PrototypeLayoutDescriptor(
        layout.representation,
        layout.revision,
        tuple(tuple(value) for value in layout.origins),
        tuple(layout.cardinal_axes),
        tuple(tuple(value) for value in layout.rigid_frames),
    )


def _exercise(representation):
    layout = _layout(representation)
    opposite = next(value for value in REPRESENTATIONS if value != representation)
    backend = _Backend()
    adapter = _Adapter(fail_once_revision=2)
    sidecar = _Sidecar(layout)
    session = ResidentApplicationSession(backend, adapter, sidecar=sidecar)
    guard = _RepresentationGuard(session, layout)
    session.start()
    first = session.step(tick=1)
    committed_digest = sidecar.last_payload.digest()
    failure_seen = False
    try:
        session.step(tick=2)
    except RuntimeError as error:
        failure_seen = "Injected primary" in str(error)
    pending = session.status()
    pending_attempt = sidecar.attempts[-1]
    blocked_next_tick = False
    try:
        session.step(tick=3)
    except RuntimeError as error:
        blocked_next_tick = "pending snapshot retry" in str(error)
    session.stop()

    wrong_adapter = _Adapter(initial_revision=1)
    wrong_sidecar = _Sidecar(_layout(opposite), initial_revision=1)
    switch_rejected = False
    try:
        guard.replace_consumers(wrong_adapter, wrong_sidecar)
    except ValueError as error:
        switch_rejected = "fixed for the session" in str(error)
    old_open_after_rejection = not adapter.closed and not sidecar.closed

    recovered_layout = _equivalent_layout(layout)
    replacement_adapter = _Adapter(initial_revision=1)
    replacement_sidecar = _Sidecar(recovered_layout, initial_revision=1)
    rebind = guard.replace_consumers(replacement_adapter, replacement_sidecar)
    after_rebind = session.status()
    session.start()
    retried = session.retry_pending()
    retry_attempt = replacement_sidecar.attempts[-1]
    after_retry = session.status()
    continued = session.step(tick=3)
    final = session.status()
    session.stop()
    close = session.close()

    return {
        "representation": representation,
        "layout_digest": layout.digest(),
        "replacement_layout_equal": recovered_layout == layout,
        "replacement_layout_same_object": recovered_layout is layout,
        "first_revision": first.snapshot.revision,
        "failure_seen": failure_seen,
        "committed_digest_before_failure": committed_digest,
        "pending": pending,
        "rollback_exact": (
            pending["sidecar"]["revision"] == 1
            and pending["sidecar"]["rollback_count"] == 1
            and sidecar.last_payload.digest() == committed_digest
        ),
        "blocked_next_tick": blocked_next_tick,
        "switch_rejected": switch_rejected,
        "old_consumers_open_after_switch_rejection": old_open_after_rejection,
        "old_consumers_closed_after_valid_rebind": adapter.closed and sidecar.closed,
        "rebind": rebind,
        "after_rebind": after_rebind,
        "retry_revision": retried.snapshot.revision,
        "retry_same_payload_object": pending_attempt["id"] == retry_attempt["id"],
        "retry_same_payload_digest": pending_attempt["digest"] == retry_attempt["digest"],
        "after_retry": after_retry,
        "continued_revision": continued.snapshot.revision,
        "final": final,
        "close": close,
        "rejected_switches": guard.rejected_switches,
    }


def _percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    invalid_mixed_rejected = False
    try:
        PrototypeLayoutDescriptor(
            "legacy_cardinal_axes_v1",
            1,
            ((0.0, 0.0, 0.0),),
            (0,),
            ((1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),),
        )
    except ValueError:
        invalid_mixed_rejected = True

    legacy_layout = _layout("legacy_cardinal_axes_v1")
    frame_layout = _layout("rigid_frame_v1")
    arrays = _payload_arrays(1)
    legacy_payload = PrototypeSurfacePayload(1, 1, legacy_layout, POINT_COUNT, *arrays)
    frame_payload = PrototypeSurfacePayload(1, 1, frame_layout, POINT_COUNT, *arrays)
    frozen_rejected = False
    try:
        legacy_payload.revision = 99
    except FrozenInstanceError:
        frozen_rejected = True

    wrong_publish = _Sidecar(legacy_layout)
    writes_before = len(wrong_publish.attempts)
    wrong_payload_rejected = False
    try:
        wrong_publish.publish(frame_payload)
    except ValueError as error:
        wrong_payload_rejected = "representation mismatch" in str(error)

    digest_timings = []
    for _ in range(500):
        started = time.perf_counter_ns()
        legacy_payload.digest()
        digest_timings.append((time.perf_counter_ns() - started) / 1_000_000.0)

    scenarios = {representation: _exercise(representation) for representation in REPRESENTATIONS}
    gates = {
        "representation_metadata_is_exclusive": invalid_mixed_rejected,
        "payload_arrays_are_immutable": frozen_rejected and all(type(value) is bytes for value in arrays),
        "same_numeric_arrays_are_shared_by_comparison": (
            legacy_payload.positions == frame_payload.positions
            and legacy_payload.fuels == frame_payload.fuels
            and legacy_payload.temperatures == frame_payload.temperatures
            and legacy_payload.smokes == frame_payload.smokes
        ),
        "representation_descriptor_participates_in_payload_digest": legacy_payload.digest() != frame_payload.digest(),
        "wrong_representation_fails_before_write": wrong_payload_rejected and len(wrong_publish.attempts) == writes_before,
    }
    for prefix, scenario in (("legacy", scenarios[REPRESENTATIONS[0]]), ("frame", scenarios[REPRESENTATIONS[1]])):
        gates.update(
            {
                f"{prefix}_first_revision_commits": scenario["first_revision"] == 1,
                f"{prefix}_primary_failure_rolls_sidecar_back": scenario["failure_seen"] and scenario["rollback_exact"],
                f"{prefix}_pending_blocks_next_tick": scenario["blocked_next_tick"],
                f"{prefix}_representation_switch_rejected_atomically": (
                    scenario["switch_rejected"]
                    and scenario["old_consumers_open_after_switch_rejection"]
                    and scenario["rejected_switches"] == 1
                ),
                f"{prefix}_equivalent_descriptor_recovers": (
                    scenario["replacement_layout_equal"]
                    and not scenario["replacement_layout_same_object"]
                    and scenario["old_consumers_closed_after_valid_rebind"]
                    and scenario["rebind"]["pending_revision"] == 2
                ),
                f"{prefix}_retry_reuses_exact_payload": (
                    scenario["retry_same_payload_object"]
                    and scenario["retry_same_payload_digest"]
                    and scenario["retry_revision"] == 2
                ),
                f"{prefix}_revision_chain_continues": (
                    scenario["after_retry"]["backend"]["revision"]
                    == scenario["after_retry"]["adapter"]["revision"]
                    == scenario["after_retry"]["sidecar"]["revision"]
                    == 2
                    and scenario["continued_revision"] == 3
                    and scenario["final"]["backend"]["revision"]
                    == scenario["final"]["adapter"]["revision"]
                    == scenario["final"]["sidecar"]["revision"]
                    == 3
                    and not scenario["close"]["pending_discarded"]
                ),
            }
        )

    report = {
        "schema_version": 1,
        "phase": "phase6dl",
        "status": "ok" if all(gates.values()) else "failed",
        "scope": {
            "prototype_only": True,
            "production_import": str(SESSION_SOURCE.relative_to(ROOT)),
            "point_count": POINT_COUNT,
            "flow_or_usd_used": False,
        },
        "representations": {
            "legacy": REPRESENTATIONS[0],
            "frame": REPRESENTATIONS[1],
            "legacy_layout_digest": legacy_layout.digest(),
            "frame_layout_digest": frame_layout.digest(),
            "same_numeric_array_bytes": sum(len(value) for value in arrays),
            "payload_digest_distinct": legacy_payload.digest() != frame_payload.digest(),
        },
        "digest_timing_ms": {
            "samples": len(digest_timings),
            "mean": statistics.fmean(digest_timings),
            "p95": _percentile(digest_timings, 0.95),
            "max": max(digest_timings),
        },
        "scenarios": scenarios,
        "gates": {"checks": gates},
        "decisions": {
            "representation_fixed_for_session": True,
            "retry_reuses_original_payload": True,
            "replacement_accepts_equal_descriptor_not_identity": True,
            "live_representation_migration_qualified": False,
            "production_integration_qualified": False,
        },
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not all(gates.values()):
        failed = [name for name, passed in gates.items() if not passed]
        raise RuntimeError(f"Phase 6DL gates failed: {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
