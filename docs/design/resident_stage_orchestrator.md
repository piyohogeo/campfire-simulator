# Resident stage recovery orchestrator

Status: Phase 6CF qualified owner-thread stage recovery orchestration as a default-off, production-but-unactivated boundary. It does not activate the Point Emitter path or change the production Sphere Emitter, physics, JSON schemas, defaults, canonical scenes, Kit, or Flow versions.

## Responsibility and state

`ResidentStageRecoveryOrchestrator` owns only the replacement transition. The existing `ResidentApplicationSession` remains the authority for the native step, immutable primary snapshot, immutable Point payload, pending revision, consumer revisions, and rollback/retry lifecycle.

The orchestrator accepts injected session, USD context, timeline, consumer factory, and next-update collaborators. It is bound to its construction thread and progresses through `idle`, `closing`, `opening`, `rebuilding`, then `running` or `stopped`. A normal exception enters `faulted`; cancellation and process-level exceptions are not converted into recovery faults.

## Qualified transition

1. Confirm the session is `running` or `stopped`, remember whether it should resume, stop it when necessary, and stop the timeline.
2. Call `UsdContext.close_stage_async()`, then drain four Kit updates.
3. Call `UsdContext.attach_stage_async(replacement_stage)`, then drain four Kit updates.
4. Require the ordered event subsequence `closing`, `closed`, `opening`, `opened` and exact replacement-stage identity.
5. Ask the consumer factory for a primary adapter and Point sidecar seeded at the last committed consumer revision.
6. Use the existing stopped-owner `replace_consumers()` validation. Old consumers close only after both replacements pass validation.
7. Start the session when required and retry the already-owned pending step and Point payload before accepting another tick.

If consumer construction fails after the replacement stage is attached, the session remains stopped, the pending value stays owned by the session, and the old consumers remain open. `retry_recovery()` repeats only consumer construction and the validated handoff against that already-attached stage. It does not repeat close/attach or rebuild the pending value.

## Real Kit and Flow result

The Phase 6CF scenario used Flow 110.0.0, 20 logs × 1,152 cells, 360 surface samples per log, and one 7,200-point emitter. An injected Point publication failure created backend/primary/Point revisions `3 / 2 / 2` with pending revision 3. The real Kit stage event stream delivered the complete ordered lifecycle while the orchestrator performed four updates after close and four after attach.

The first consumer factory call failed deliberately after attach. The session stayed stopped with pending revision 3 and consumer replacement count 0. The retry called the same factory with the same attached stage and revision seed 2, closed the old consumers only after validation, and reused the exact pending payload identity and SHA-256 digest. Backend, primary, and Point reached revision 3; the next tick committed revision 4, and continued execution reached revision 124.

All 19 gates passed. Flow reached 1,258 active blocks with non-empty temperature, fuel, burn, smoke, and velocity readbacks. No relevant live structural resync occurred after recovery. Clean close discarded no pending value. The real RTX development-log capture contains 60 frames at 1280×720 and 10 fps; 56 frame hashes are unique. Capture is evidence for visible continuity, not a performance measurement.

The standard regression suite passed 51/51 checks across eight processes in 308.4 s; collapse coverage completed in 181.9 s.

## Decision

Scheduler-driven recovery is qualified as a reusable default-off boundary. Production activation remains deferred until the Point consumer itself is selected for production. At that decision, integration must reuse this lifecycle rather than introduce live Prim deletion/redefinition or a second pending/revision authority.

Reproduction:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_phase6cf_resident_stage_orchestrator.ps1
```
