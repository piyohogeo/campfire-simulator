# Resident Point application scene boundary

Status: Phase 6CI qualifies the normal application owner behind the same explicit default-off setting. The normal production default remains the existing Sphere path.

## Scene contract

`resident_point_scene.py` owns structural Point authoring. Before a stage is connected to Kit it:

- retains the existing `FlowEmitterSphere` consumer but disables its Flow contribution;
- authors one `UsdGeomPoints` source and one `FlowEmitterPoint`;
- authors layer 0, the `pointsPrim` relationship, material binding, five Point arrays, and `campfire:residentRevision`;
- enables NanoVDB readback only in this isolated qualification scene;
- records that structural authoring happened before stage connection.

The opt-in is `/exts/campfire.app/residentPointApplicationEnabled`. It is `false` in both application configurations. With no opt-in, Phase 3 contains the unchanged enabled Sphere and no Point Prim. The canonical Phase 3 USDA is not rewritten.

After connection, `ResidentPointSidecar` updates only the existing `pointPositions`, `pointFuels`, `pointTemperatures`, `pointSmokes`, and revision attributes. Layout positions are published once and remain unchanged until a stopped-owner layout replacement. No live Prim deletion or redefinition is permitted.

## Flow 110 result

The real Kit run first connected and closed an unmodified Sphere fallback scene. It then built a separate Point scene offline from the authoritative two-log Phase 3 model. Each log has 1,152 cells and 360 exposed surface cells, giving one 720-point emitter.

The Resident backend, primary USD adapter, Point sidecar, and session ran for 710 revisions. Backend, primary consumer, and Point consumer all stopped at revision 710. Point publication caused no structural resync and changed only pre-existing Point properties. The session stopped without pending work; native export, adapter close, and sidecar close all succeeded before Kit shutdown.

Flow reached 382 active blocks. Temperature, fuel, burn, and smoke NanoVDB readbacks each contained 3,412,752 words; velocity contained 2,225,240 words. The timeline emitted `PLAY` followed by `STOP`: the stage reached its authored end during the intentionally slow capture sequence, so `STOP` is the valid terminal event rather than `PAUSE`.

The 60-frame, 1280x720 RTX evidence video has 60 unique frame hashes. It visibly contains fire and smoke emerging from the two log surfaces. Capture and the initial RTX shader warm-up are evidence costs, not performance measurements.

The standard Phase 6CH regression suite passed 54/54 checks across eight processes in 291.4 s; collapse coverage completed in 171.6 s.

## Decision

The pre-connection structure, explicit opt-in, Sphere fallback, timeline transition, live-update boundary, Flow rendering, and clean Resident shutdown are qualified. This does not activate Point in the normal application owner. The next step is to compose the already-qualified backend/session/sidecar/recovery objects behind the same setting in the normal app, preserving the current revision, rollback, immutable snapshot, and stage-recovery contracts.

The observed Flow Fabric warning that `pointTemperatures` was not found during initial cache setup remains recorded as a Flow 110 integration warning. USD authoring, Flow active blocks, field readback, and rendered fire/smoke all succeeded, so it is not an activation failure, but the normal owner integration should keep this warning under regression observation.

Reproduction:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_phase6ch_resident_point_application.ps1
```

## Phase 6CI normal owner composition

`ResidentPointApplicationOwner` composes the existing native backend, primary snapshot adapter, Point sidecar, session, and recovery orchestrator. It creates no additional pending, rollback, snapshot, or revision authority. Its only scheduling responsibility is assigning the next tick on the construction thread.

When the existing setting is enabled for Phase 3, the normal extension builds an isolated USDA offline, pre-authors the complete Point and primary-consumer schema, saves it, waits for Kit's initial empty-stage transaction, and only then connects the completed stage. The setting remains invalid for other phases. With the setting disabled, the existing Sphere Phase 3 and all canonical scenes are unchanged.

The normal `campfire.simulator.kit` owner completed 710 steps with backend, primary adapter, and Point sidecar revisions all at 710. There were no publish failures, retries, rollbacks, pending snapshots, or Point resyncs. Shutdown exported the native state once and closed both consumers. Flow peaked at 383 active blocks; temperature, fuel, burn, smoke, and velocity readbacks were non-empty. All 60 RTX evidence frames were unique.

The stage-recovery orchestrator and real stage-event subscription are composed into the normal owner, but Phase 6CI does not duplicate the replacement-stage failure/retry experiment already qualified in Phase 6CF. Interactive log-layout refresh and one normal-owner recovery exercise remain the next boundary. Point stays default-off and the Flow 110 initial-cache warning remains under observation.

The full suite passed 56/56 checks across eight processes in 310.5 s; collapse coverage completed in 183.2 s. The default-off Phase 0 application capture also passed.

Reproduction:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_phase6ci_resident_point_owner.ps1
```
