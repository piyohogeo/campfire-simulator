# Resident session ownership of the Point sidecar

Status: Phase 6CD qualified this contract as a default-off technical phase. Production activation, the Sphere Emitter, physics, JSON schemas, dependency versions, defaults, and canonical scenes remain unchanged.

## Ownership and publication order

`ResidentApplicationSession` may now own one optional publication sidecar in addition to the existing `UsdResidentSnapshotAdapter`. The constructor remains backward compatible when no sidecar is supplied. The same owner thread controls both consumers.

For each native step, the session freezes an `ImmutableSurfacePayload` containing revision, tick, layout revision, three owned numeric channel buffers, positions, and a digest. It publishes the Point sidecar first and the primary immutable snapshot second. The revision must match the `ResidentNativeStep` snapshot before either publication begins.

If Point publication fails, the sidecar restores its previous attributes and the primary adapter is not called. If primary publication fails after Point succeeds, the session asks the sidecar to restore its previous immutable revision. In either case the session keeps the exact native step and Point payload as pending, blocks a new tick and normal close, and retries the same payload. This extends the existing lifecycle; it does not replace revision-last publication or adapter rollback.

## Layout and stage rules

Layout replacement is accepted only on the owner thread while the session is `ready` or `stopped`, with no pending publication. The replacement preserves array shapes, increments a monotonic layout revision, and republishes positions with the next value revision. The test moved the first log by 0.03 m and observed changed positions at layout revision 2.

The sidecar captures the stage identity used to bind its pre-existing attribute handles. A different stage is rejected before any Point write. Phase 6CD deliberately closes this probe with an explicit pending discard after proving the fail-closed boundary. Normal reconstruction of both publication consumers on a replacement stage, followed by retry of the retained revision, is the next boundary; it is not claimed here.

No live Prim definition, deletion, relationship, material, layer, or scalar Flow mutation occurs. The fresh stage contains `FlowSimulate`, `FlowOffscreen`, `FlowRender`, one `FlowEmitterPoint`, `UsdGeomPoints`, the diagnostic logs, and the disabled compatibility Sphere before Kit connects. After connection only existing array and revision attributes are updated.

## Flow 110 validation

The fixed test condition is 20 logs, 1,152 Resident cells per log, 360 exposed cells per log, and 7,200 points in one Emitter. The diagnostic thermal state exists to exercise the publication and Flow paths and is not a new physical default.

- Point failure at revision 2 left backend/primary/Point at `2/1/1`; stop/start retry reused the identical payload object and digest and committed `2/2/2`.
- Primary failure at revision 3 rolled Point from 3 back to 2; retry committed all consumers at revision 3.
- After layout replacement and continuous publications, all consumers reached revision 124 before the stage-replacement probe.
- All 14 gates passed, with zero live structural resync and production activation unchanged.
- Flow 110.0.0 reached 1,695 active blocks, and temperature, fuel, burn, smoke, and velocity readbacks were non-empty.
- The standard regression suite passed 50/50 checks across eight processes in 313.3 s; collapse coverage completed in 184.8 s.

The development-log video is an H.264 1280x720 capture at 10 fps for 6 seconds. It contains 60 separately captured Flow/RTX frames and 60 distinct SHA-256 hashes. Ninety warm-up publications let the volume develop before capture; a new Resident/Point revision is published every two capture updates. Capture is excluded from performance measurement. This corrects the earlier three-keyframe presentation: it demonstrates continuous visual evolution, but remains supporting evidence rather than a pass criterion by itself.

## Decision

Session-level pending/retry and rollback can consistently cover the existing primary snapshot and the proposed Point arrays. The contract is therefore qualified for continued default-off work, not for production activation. The next experiment must reconstruct the sidecar and primary adapter against a replacement stage, preserve the pending immutable revision, and prove normal retry without forced discard. Only after that should scheduler or UI integration be considered.

Reproduction:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_phase6cd_resident_surface_session.ps1
```
