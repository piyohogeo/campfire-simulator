# Resident layout representation lifecycle spike

Status: Phase 6DL qualifies an isolated lifecycle contract only. Production integration and live legacy-to-frame migration remain unqualified.

## Purpose

Phase 6DJ proved that the historical Y layout is a reflection, and Phase 6DK proved that a proper USD-derived rigid frame preserves stable surface-cell channel identity. The remaining risk is lifecycle ambiguity: a pending or recovered payload must never be interpreted under a different layout representation merely because its numeric arrays have compatible sizes.

The Phase 6DL probe imports the production `ResidentApplicationSession` implementation unchanged and supplies prototype-only backend and consumer objects. It does not modify or monkey-patch production code and does not run USD, Flow, a renderer, or a native DLL.

## Prototype data contract

`PrototypeLayoutDescriptor` is frozen and has one of two exclusive representations:

- `legacy_cardinal_axes_v1`: immutable origins plus one cardinal axis value per log;
- `rigid_frame_v1`: immutable origins plus one right-handed orthonormal basis per log.

A descriptor containing both axis and frame metadata is invalid. Representation, layout revision, origins, and the selected representation data participate in the descriptor digest. The immutable surface payload incorporates that digest before hashing position, fuel, temperature, and smoke bytes. Consequently, equal numeric array bytes cannot conceal a layout-mode change.

The prototype uses 720 points and 17,280 bytes of numeric arrays. Five hundred payload SHA-256 samples measured p95 `0.0141 ms`. This is isolated Python hashing and is not a USD publication or Flow performance result.

## Lifecycle exercised independently for both representations

1. Commit revision 1 to the sidecar and primary consumer.
2. Build and sidecar-commit revision 2, then inject a primary publication failure.
3. Roll the sidecar back exactly to revision 1 and retain revision 2 as pending.
4. Reject the next tick while pending work exists.
5. Stop the owner and reject a replacement sidecar using the other representation before closing either old consumer.
6. Reconstruct an equal descriptor as a different Python object and accept same-representation consumer replacement.
7. Retry the exact pending payload object and digest as revision 2.
8. Continue normally to revision 3 and close without discarding pending work.

All backend, primary, and sidecar revisions aligned at 2 after retry and at 3 after the following step. The replacement descriptor is compared by canonical value/digest, not Python identity, so a replacement stage may reconstruct it safely.

The complete regression remained green: 8 test processes and 59/59 cases passed in 342.6 seconds, including 200.9 seconds of collapse coverage.

## Decision

The session-lifetime representation rule is qualified in isolation. It requires three eventual production checks: payload construction must freeze the representation, a sidecar must reject a payload whose descriptor differs before any USD write, and consumer replacement must reject a representation change before closing old consumers.

This result does not qualify adding fields to the existing `ImmutableSurfacePayload`, changing checkpoint or JSON schema, authoring a representation token into USD, connecting the rigid-frame native producer, or switching a live legacy session. Those choices require a separate minimum-diff design and compatibility audit.
