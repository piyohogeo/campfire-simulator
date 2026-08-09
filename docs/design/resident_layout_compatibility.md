# Resident layout representation compatibility audit

Status: Phase 6DN implements and qualifies Phase 6DM's minimum production delta for the existing default-off legacy Point path. The rigid-frame producer remains reserved and unconnected.

## Evidence from the current source

The static AST/source audit found ten fields on `ImmutableSurfacePayload` and exactly two constructor sites: one production call in `resident_point_sidecar.py` and one unit-test call. The type is publicly exported. Its digest already includes layout origins, cardinal axes, and all four numeric arrays.

`ResidentApplicationSession.retry_pending()` passes the stored sidecar payload back to `_publish_pair()` without reconstruction. `replace_consumers()` validates revision and consumer state before closing the old adapter and sidecar. This is the correct location for a future representation comparison.

Phase 6DM identified five explicit gaps, all closed by Phase 6DN:

- the immutable payload now has a trailing, legacy-default representation field and includes it in the digest;
- sidecar publication and status expose one immutable representation and reject mismatch before attempt accounting or writes;
- consumer replacement compares representation before closing either old consumer;
- the pre-authored Point stage has the static `campfire:layoutRepresentation` Token;
- owner shared layout state carries the same representation through refresh and stage recovery.

## Minimum first integration delta

The first implementation touches only the five planned code/test areas:

1. `layout_representation` is appended after all existing payload fields with `legacy_cardinal_axes_v1` as its default, preserving current positional and keyword call sites and contributing to the payload digest.
2. `ResidentPointSidecar` owns one immutable representation, publishes it through `status()`, validates the pre-authored stage token at construction, and rejects payload mismatch before attempt accounting, conversion, or USD writes.
3. `ResidentApplicationSession.replace_consumers()` compares old and replacement sidecar representation before closing either old consumer.
4. `campfire:layoutRepresentation` is pre-authored as an `Sdf.ValueTypeNames.Token` before stage connection. The legacy default is `legacy_cardinal_axes_v1`; the future explicit opt-in is `rigid_frame_v1`. Publication never rewrites the token.
5. `ResidentPointApplicationOwner` carries the representation in shared layout state, exported constants keep identifiers stable, and focused tests cover construction, mismatch, layout refresh, publication, and replacement-stage handoff.

## Compatibility and persistence

Wood JSON and `ResidentPublishedSnapshot` remain unchanged because layout representation is application/consumer state, not authoritative wood state. The native ABI also remains unchanged until the rigid-frame producer is connected separately.

Checkpoint schema v1 remains unchanged. Its validated consumer list is `len(log_ids) + 1` and its final consumer is the Sphere Emitter; it does not save or resume the Point sidecar. If Point session persistence is added later, that is a new checkpoint schema version with a mandatory representation field.

USD stage export naturally preserves a pre-authored token, but a legacy Point stage without the token must not be guessed or structurally repaired after connection. Once representation-aware Point mode is enabled, such a stage fails closed and is regenerated or upgraded offline.

The existing stage recovery orchestrator does not need a new authority. Its consumer factory reconstructs the sidecar from shared layout state, and the session already owns the pre-close handoff validation. These are the two places that must agree before a retained pending payload is retried.

## Phase 6DN qualification boundary

The original Phase 6DM audit passed 19/19 gates and qualified the change plan only. Phase 6DN then passed 14/14 source/contract gates and 13/13 real-Kit anonymous-USD runtime gates. The runtime probe verifies explicit legacy Token authoring, matching publication, zero-attempt mismatch rejection, missing/mismatched stage failure, pre-close replacement rejection, matching replacement, and clean close.

The complete regression remains green after the production delta: 8 test processes and 75/75 cases passed in 460.9 seconds. The release build also passed. Point and V3 remain default OFF, Flow remains 110.0.0, and wood JSON, `ResidentPublishedSnapshot`, checkpoint v1, native ABI, physics, revision, rollback, and immutable-snapshot contracts are unchanged.

This qualifies only the representation identity/compatibility guard on the existing legacy producer. It does not qualify `rigid_frame_v1` publication, live legacy-to-frame migration, Point checkpoint persistence, or seamless Flow/renderer recovery. The next independent gate is a default-off rigid-frame producer with byte/revision equivalence; representation must never change within a live session.
