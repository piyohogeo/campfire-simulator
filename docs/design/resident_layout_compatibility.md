# Resident layout representation compatibility audit

Status: Phase 6DM defines the minimum future production delta. It does not implement or qualify that delta.

## Evidence from the current source

The static AST/source audit found ten fields on `ImmutableSurfacePayload` and exactly two constructor sites: one production call in `resident_point_sidecar.py` and one unit-test call. The type is publicly exported. Its digest already includes layout origins, cardinal axes, and all four numeric arrays.

`ResidentApplicationSession.retry_pending()` passes the stored sidecar payload back to `_publish_pair()` without reconstruction. `replace_consumers()` validates revision and consumer state before closing the old adapter and sidecar. This is the correct location for a future representation comparison.

Five gaps are explicit:

- the immutable payload has no representation field;
- sidecar publication and status expose no representation contract;
- consumer replacement compares revision but not representation;
- the pre-authored Point stage has layout and Resident revisions but no representation token;
- owner shared layout state contains only revision, origins, and cardinal axes.

## Minimum first integration delta

The first implementation should touch only five code/test areas:

1. Append a defaulted `layout_representation` field after all existing payload fields, preserving current positional and keyword call sites. Include it in the payload digest.
2. Give `ResidentPointSidecar` one immutable representation, publish it through `status()`, validate the pre-authored stage token at construction, and reject payload mismatch before attempt accounting, conversion, or USD writes.
3. In `ResidentApplicationSession.replace_consumers()`, compare old and replacement sidecar representation before closing either old consumer.
4. Pre-author `campfire:layoutRepresentation` as an `Sdf.ValueTypeNames.Token` before stage connection. The legacy default is `legacy_cardinal_axes_v1`; the future explicit opt-in is `rigid_frame_v1`. The token is never changed during a live session.
5. Carry the representation in `ResidentPointApplicationOwner` shared layout state, export stable constants, and add constructor, mismatch, rollback, retry, and replacement-stage tests.

## Compatibility and persistence

Wood JSON and `ResidentPublishedSnapshot` remain unchanged because layout representation is application/consumer state, not authoritative wood state. The native ABI also remains unchanged until the rigid-frame producer is connected separately.

Checkpoint schema v1 remains unchanged. Its validated consumer list is `len(log_ids) + 1` and its final consumer is the Sphere Emitter; it does not save or resume the Point sidecar. If Point session persistence is added later, that is a new checkpoint schema version with a mandatory representation field.

USD stage export naturally preserves a pre-authored token, but a legacy Point stage without the token must not be guessed or structurally repaired after connection. Once representation-aware Point mode is enabled, such a stage fails closed and is regenerated or upgraded offline.

The existing stage recovery orchestrator does not need a new authority. Its consumer factory reconstructs the sidecar from shared layout state, and the session already owns the pre-close handoff validation. These are the two places that must agree before a retained pending payload is retried.

## Qualification boundary

The audit passed 19/19 gates and production extension hashes were unchanged. This qualifies the change plan only. It does not qualify production fields, the USD token, frame-mode publication, Point checkpoint persistence, or live legacy-to-frame migration.

The complete regression remained green: 8 test processes and 59/59 cases passed in 369.3 seconds, including 213.4 seconds of collapse coverage.
