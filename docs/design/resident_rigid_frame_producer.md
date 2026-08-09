# Resident rigid-frame producer

Status: Phase 6DO qualifies the additive producer behind the existing default-off Point path. It does not enable Point, migrate a live session, or reopen V3T-C.

## Boundary

`rigid_frame_v1` carries one immutable right-handed orthonormal frame per log. Each frame is stored as flattened local-X, local-Y, and local-Z world directions. Origins and frames are sampled together from the log physics transform. The native layout kernel computes every surface position as:

```text
origin + axial_position * frame_x
       + radial_cosine   * frame_y
       + radial_sine     * frame_z
```

The new `campfire_native_surface_layout_frames` export is additive. The historical `campfire_native_surface_layout` export and legacy cardinal behavior remain unchanged. A legacy producer does not resolve the new symbol, so an existing legacy-only native library remains loadable for the legacy path.

## Immutable lifecycle

The representation is selected when the producer, sidecar, and stage consumer are constructed. A rigid payload contains frames and no cardinal axes; a legacy payload contains cardinal axes and no frames. The representation and frame values participate in the immutable payload digest.

Layout candidates are built in scratch storage. Only a successful USD transaction commits the native position array and its origin/frame metadata. A failed publication restores the previous USD arrays, committed revision, and native layout. Exact failed-payload retry remains allowed. Export/open recovery reconstructs a matching rigid consumer, while cross-representation recovery fails before replacing the old consumers.

Changing representation in a live session remains forbidden. Stop and rebuild the session and its stage consumers instead.

## Qualification

The Phase 6DO real native/Kit probe passed 15/15 gates:

- identity-X legacy and rigid positions are byte-identical;
- fuel, temperature, and smoke arrays are byte-identical;
- all 720 point addresses remain producer-owned and stable;
- a 37-degree rotation matches an independent float32 reference with `0.0 m` maximum error;
- reflection and invalid frames fail without mutating committed state;
- revision-last publication, injected rollback, exact retry, explicit rollback, and republish retain existing semantics;
- export/open reconstructs a matching rigid consumer and cross-representation recovery fails closed.

Byte equivalence is deliberately not claimed for historical legacy-Y. That mapping is a reflection and therefore cannot equal a proper right-handed rigid frame. This is a documented compatibility boundary, not a numerical tolerance issue.

## Non-changes and next gate

Wood authority, physical equations, wood JSON, `ResidentPublishedSnapshot`, checkpoint v1, Flow 110.0.0, collision, Emitter schemas, revision rules, and production defaults are unchanged. Point and V3 remain default OFF; Sphere remains the production emitter.

The next independent gate is application-owner orchestration of a newly created rigid session. It must remain opt-in and must prove transform refresh, stage replacement, and shutdown without introducing a runtime representation switch.
