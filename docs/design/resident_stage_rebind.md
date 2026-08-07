# Resident replacement-stage consumer rebind

Status: Phase 6CE qualified replacement-stage recovery as a default-off technical boundary. Production activation, the Sphere Emitter, physics, JSON schemas, dependency versions, defaults, and canonical scenes remain unchanged.

## Supported sequence

The session owner uses the public Kit 110 USD context APIs in this order:

1. stop `ResidentApplicationSession` and the Kit timeline;
2. persist or otherwise construct a complete replacement stage whose primary and Point consumer revisions equal the last committed revision;
3. call `UsdContext.close_stage_async()`, drain Kit updates, then call `UsdContext.attach_stage_async(replacement_stage)`;
4. allow the old Point sidecar to detect the changed stage before any write, retaining the new native step and immutable Point payload as pending;
5. construct a new `UsdResidentSnapshotAdapter` and Point sidecar against the replacement stage, seeded at the last committed revision;
6. while stopped, call `ResidentApplicationSession.replace_consumers()`;
7. start the session and retry the retained pending value before accepting another tick.

`replace_consumers()` requires the owner thread and stopped state. It rejects a missing adapter, a change in sidecar presence, an active or closed replacement adapter, and any primary or Point revision mismatch. Only after all validation succeeds are the old consumers closed and the new consumers installed. Pending `ResidentNativeStep` and `ImmutableSurfacePayload` objects remain owned by the session and are not rebuilt.

## Kit 110 stage boundary

The local SDK documents and tests `UsdContext.attach_stage_async`. Directly attaching the replacement while the Flow/Hydra stage was still open caused a native Kit 110 crash in `UsdContext::unregisterViewOverrideToHydraEngines`. The qualified route therefore uses explicit `close_stage_async`, four update drains, and then `attach_stage_async`. This is a lifecycle constraint of the fixed Kit/Flow environment, not a reason to change dependency versions.

The experiment observes the complete closing, closed, opening, and opened event set. It does not retain or inspect a closed `Usd.Stage` wrapper: closing invalidates that lifetime boundary. The replacement adapter constructor verifies every primary consumer revision, while the sidecar constructor verifies the Point revision and restores the current layout state before handoff.

## Result

- Before replacement, backend, primary adapter, and Point sidecar were all at revision 2 with layout revision 2.
- The first post-replacement step advanced the backend to revision 3; the old Point sidecar rejected the new stage before writes, leaving both consumers at revision 2 and blocking another tick.
- A deliberately mismatched primary seed was rejected before handoff.
- The stopped handoff retained pending revision 3, closed both old consumers, and installed consumers seeded at revision 2.
- Retry reused the exact same immutable payload object and SHA-256 digest and aligned backend, primary, and Point revisions at 3. The next tick committed revision 4 normally.
- Continued execution reached revision 124, 1,269 Flow active blocks, and non-empty temperature, fuel, burn, smoke, and velocity readbacks. No relevant live structural resync occurred after attach.
- All 18 gates passed and clean close discarded no pending value.
- The standard regression suite passed 50/50 checks across eight processes in 291.6 s; collapse coverage completed in 172.2 s.

The development-log video contains 60 separately captured 1280x720 Flow/RTX frames encoded at 10 fps for 6 seconds. All 60 frame hashes are distinct. Capture occurs after replacement recovery and is excluded from performance measurement.

## Decision and next boundary

Explicit replacement-stage recovery is qualified for continued default-off integration. The next boundary is scheduler-driven orchestration of stop, stage event handling, consumer construction, rebind, and retry. That automation must preserve the same validation and must not silently discard pending work. UI integration and production Point activation remain deferred.

Reproduction:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_phase6ce_resident_stage_rebind.ps1
```
