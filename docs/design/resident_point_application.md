# Resident Point application scene boundary

Status: Phase 6CJ qualifies stopped layout refresh and normal-owner stage recovery behind explicit default-off settings. The normal production default remains the existing Sphere path.

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

## Phase 6CJ stopped layout and normal-owner recovery

`ResidentPointApplicationOwner.refresh_layout()` reads the current log transforms only on its owner thread. An unchanged layout does not advance revision. A changed layout delegates to the existing stopped-session sidecar replacement contract, so running or pending sessions continue to fail closed. The interactive timeline callback performs this refresh immediately before a stopped owner enters PLAY.

The owner and recovery consumer factory now retain the same layout mapping object. Layout replacement mutates that mapping only after the sidecar accepts the new monotonic revision. Consequently, a later consumer factory call receives the latest origins, axes, and layout revision instead of the startup layout.

The Phase 6CJ normal-app qualification stopped at Resident revision 300, moved the dry log by 0.04 m, and refreshed layout revision 1 to 2. PhysX settling had changed both log world origins, so the next Point publication changed two complete 360-point log groups, or 720 positions. The gate accepts only whole 360-point groups and rejects partial layout changes.

Revision 301, including layout revision 2, was exported into a separate replacement stage. The existing normal-owner recovery orchestrator observed `closing`, `closed`, `opening`, and `opened`, then rebuilt both consumers from committed revision 301 and current layout revision 2. It resumed without pending work or retry and continued through revision 710. Backend, primary adapter, and Point sidecar revisions matched; Point resync and pending discard remained zero.

All 13 lifecycle and data gates passed. Flow peaked at 427 active blocks. Temperature, fuel, burn, and smoke readbacks contained 3,806,912 words each, velocity contained 2,410,056 words, and all 60 RTX evidence frames were unique. Subsequent frame-by-frame inspection found that the log pose jumps before ignition and that the Flow field is rebuilt after stage replacement. These gates therefore qualify Resident consumer/revision recovery only; they do not qualify seamless Flow-field or visual recovery. The full suite passed 56/56 checks in 301.4 s, collapse coverage completed in 177.9 s, and the default-off Phase 0 capture passed.

The current native layout ABI still accepts horizontal cardinal X/Y logs only. Unsupported arbitrary rotations must not be silently approximated; owner-thread command routing and explicit UI/headless failure reporting remain the next boundary. Point remains default-off.

Reproduction:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_phase6cj_resident_point_recovery.ps1
```

## Phase 6CK owner-thread commands and fail-closed layout UX

`ResidentPointCommandQueue` is a bounded FIFO between callers and the existing
application owner. Submitting a refresh does not inspect USD and is safe from a
non-owner thread. Draining is restricted to the construction/owner thread; only
that operation obtains the current stage and calls the existing
`ResidentPointApplicationOwner.refresh_layout()`. The queue owns no wood values,
Point arrays, pending payload, rollback journal, snapshot, or revision.

UI, timeline PLAY, and headless qualification use the same immutable result
schema and one-line formatter. Results distinguish `layout_replaced`,
`layout_unchanged`, `unsupported_layout`, queue closure/overflow, and unexpected
execution failure. A rejected PLAY transition pauses the timeline and does not
start the Resident session. Shutdown rejects queued work rather than applying it.

The Phase 6CK normal-app run stopped at revision 300 and submitted a 45-degree
dry-log rotation. The command returned `unsupported_layout`; Point positions,
fuels, temperatures, smokes, Point revision, layout revision, layout replace
count, and stopped session state were unchanged. After restoring a cardinal
rotation and moving the log by 0.04 m, the next command advanced layout revision
1 to 2. Simulation resumed through revision 710 with backend, primary adapter,
and Point sidecar equal. Point structural resync remained zero.

All 13 lifecycle and data gates passed. Flow peaked at 427 active blocks; required field readbacks
were non-empty and all 60 RTX evidence frames were unique. Frame inspection later found a one-frame log-pose transition with simultaneous flame disappearance. The command result remains valid, but smooth USD/PhysX/Point/Flow/RTX synchronization is an unresolved defect and was not covered by these gates. The layout ABI remains
limited to horizontal cardinal X/Y logs, and Point remains explicit opt-in. The
next boundary is interactive transform-edit observation and bounded-queue
backpressure; arbitrary rotation support is not implied by this result. The final
suite passed 56/56 checks across eight processes in 290.9 s, collapse coverage
completed in 171.0 s, and release build plus the default-off Phase 0 capture passed.

Reproduction:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_phase6ck_resident_point_commands.ps1
```

## Phase 6CL stopped transform observation and coalescing

`ResidentPointTransformObserver` filters `Usd.Notice.ObjectsChanged` paths to
the configured log `xformOp:*` properties. It reads neither transform values nor
Point state. Notices are accepted only while the Resident session is `ready` or
`stopped`; running physics updates and unrelated USD changes are counted and
ignored. The listener is revoked on stage closing and registered against the
new current stage after opening.

Automatic notice requests call the existing queue with coalescing enabled. If a
layout refresh is already pending, another request returns the same command
sequence instead of consuming queue capacity or a layout revision. The later
owner-thread drain reads the final stage transform once. Manual UI, timeline,
and headless submissions retain their non-coalesced behavior.

The real Phase 6CL run observed 1,507 USD notices. Thirty-one matched target log
transforms: 18 occurred while running and were ignored, while 13 stopped notices
became two commands. Six edits ending at 45 degrees coalesced into one rejected
command with Point arrays and revisions unchanged. Seven notices restoring the
cardinal transform coalesced into one accepted command and advanced layout
revision exactly once from 1 to 2. The queue recorded 13 requests, two submitted
commands, 11 coalesced submissions, two executions, one rejection, and no
pending work.

All 14 lifecycle and data gates passed. Backend, primary, and Point revisions ended at 710, Point
resync remained zero, Flow peaked at 454 active blocks, required field readbacks
were non-empty, and all 60 RTX frames were unique. The capture spans continuous
Resident revisions 651 through 710, but frame inspection found a log jump and simultaneous flame disappearance between adjacent encoded frames. Revision continuity is therefore not evidence of visual or Flow-field continuity. The earlier plume-only interpretation is withdrawn. Real GUI manipulator interaction, observer rebind during an actual stage
recovery, and notice-callback cost remain separate follow-up measurements.

## Phase 6CM continuity-defect reclassification and diagnostic gate

The Phase 6CJ–6CL evidence has been reclassified: layout/revision/consumer gates remain valid, while seamless visual continuity is explicitly unqualified. Dynamic PhysX log poses are authoritative, but the current Point layout is refreshed only while stopped and then remains static. Stage replacement restores Resident consumers and revisions but does not checkpoint the Flow NanoVDB solver field. Neither limitation is an intended production behavior.

Phase 6CM adds a default-off diagnostic setting and frame-aligned telemetry. It records each PhysX log world origin, each contiguous 360-point group centroid, their SI-unit error, Resident tick/revision, timeline state, and Flow active-block count. The first diagnostic run localized a 40.0 mm gap after the stopped layout command: the log transform had changed while the Point array still represented the old layout. The next Resident publication reduced that gap to numerical noise, proving that layout commit and USD Point publication expose two different states. The samples also showed the timeline stopped rather than continuously playing. A viewport-frame barrier is used for evidence samples so later fixes can be evaluated against the same contract. Passing this diagnostic means only that the unresolved defect was reproduced and recorded; `seamless_visual_continuity_qualified` and timeline continuity remain false.

The completed real-Kit run recorded 130 alignment samples. The pre-publication gap was 0.040000000099 m; after revision 301 publication the maximum error was 1.8577e-9 m. All 130 samples reported the timeline stopped. Backend, primary, and Point revisions still ended at 710, Flow peaked at 459 active blocks, and all 60 evidence frames were unique. The 14/14 diagnostic result does not supersede the two explicit false qualifications.

Reproduction:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_phase6cm_resident_point_continuity.ps1
```

## Phase 6CN atomic stopped-layout publication

Phase 6CN removes the state exposure found by Phase 6CM without changing the Resident snapshot authority. The Point prim preauthors `campfire:layoutRevision`. While the owner is stopped, `replace_layout()` updates the native producer layout and the existing `pointPositions` attribute inside one `Sdf.ChangeBlock`, writes the layout revision last, and restores both native and USD values on failure. No live prim or attribute definition is permitted.

The layout-only transaction does not consume a wood revision. In the real run, Resident revision remained 300 while layout revision advanced from 1 to 2; normal publication then continued through revision 710. The pre-first-publication alignment error fell from the Phase 6CM value of 0.040000000099 m to 1.8577e-9 m, and all 130 pose samples remained within the 0.002 m tolerance. Backend, primary, and Point revisions ended at 710, Flow peaked at 439 active blocks, and all 60 RTX frames were unique. The release build, default-off Phase 0, and all eight test processes with 58/58 tests passed.

This is a deliberately partial qualification. The headless Flow/PhysX boundary emitted STOP immediately after each PLAY request, so 0/130 evidence samples were playing. Flow solver-field relocation, checkpointing, replacement-stage restoration, and seamless visual continuity remain unqualified. Passing Phase 6CN means only that a supported stopped layout is visible in the Point array before the next wood tick.

Reproduction:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_phase6cn_resident_point_continuity_fix.ps1
```

Reproduction:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_phase6cl_resident_transform_observer.ps1
```
