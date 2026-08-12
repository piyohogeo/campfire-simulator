# Phase 6FB Point Emitter startup ingestion probe

## Scope and frozen history

Phase 6EY, Phase 6EZ, and Phase 6FA remain immutable. In particular, the Phase 6EZ C1 zero-copy observation is not promoted to a qualification, and the Phase 6FA 24-block run is not reclassified. Phase 6FB changes only diagnostic instrumentation and runs at most two independent, readback-free Kit processes through frame 120. Production code, Point payload, Flow settings, CollisionProxy geometry, wood authority, V3, defaults, and all resource ceilings remain unchanged.

The pre-runtime contract is `campfire.phase6fb.point-emitter-startup-ingestion-contract.v1`, SHA-256 `F31483994DD43A77286312A19A11639BE34BA41AFD60E7E58B04A7034B70E784`. It classifies the fixed four-log fixture as representative only if fresh frame, monotonic timestamp, Kit update, and timeline samples continue through frame 120 and active blocks reach at least 128 by frame 60. A fresh trace remaining between 20 and 32 blocks through frame 60 is `small_field_ingestion`, not a valid steady-state qualification. Missing source input, stale telemetry, incomplete evidence, and lifecycle/resource failures remain fail-closed.

## Read-only historical audit

The historical Phase 6FA representative D0 and small-field D1 stages and payload NPZ files have matching SHA-256 values. Their authored 1,440 total / 1,344 active Points and weighted fuel, temperature, and smoke supply also match. The first differing sample is frame 1: D0 is already 269 blocks and D1 is 24. D1's readback follows its frame-60 sample. Timeline time and per-frame monotonic timestamps advance in D1, so the evidence is inconsistent with stale telemetry and excludes public readback, alias release, or `numpy.asarray(fuel)` as the direct initial cause.

The historical run did not record Kit update numbers, explicit renderer-readiness and Flow-interface acquisition boundaries, or live Emitter wrapper/payload identities. The old representative process had exited only 4.641 seconds before the D1 runner began, but that single interval does not establish cross-process contamination.

## New bounded startup evidence

Phase 6FB preserves the existing startup order: complete the stage and payload offline, connect the USD context, obtain and advance the active viewport for 60 frames, acquire the public Flow interface, reset the stopped timeline, execute 12 Kit updates, then play. It adds flushed markers around every boundary and records all 120 post-play frames with timeline time, Kit update number, active blocks, source revision/counts/sums, stage/Flow/Emitter identities, readiness evidence, and synchronous process memory. There is no public Flow predicate that guarantees source ingestion; `flow_interface_ready` therefore means only that the public interface was acquired, not that the solver consumed the Point payload.

Both new independent processes classified as `representative_ingestion` and produced the same entire 120-frame active-block history. Values at frames 1/30/60/120 were `269 / 505 / 688 / 1118`, with range `269–1124`. Stage SHA-256 `482CB233...53AC`, payload SHA-256 `0D3B074B...C389`, revision 1, enabled state, 1,344 active Points, and source sums fuel `1075.200016`, temperature `2688`, smoke `107.519998` matched. Timeline and Kit update numbers advanced on every sample.

P0 stage connection took 5.094 seconds; P1 took 61.190 seconds, yet both post-play occupancy traces were identical. This disproves a simple claim that a longer stage-open wait necessarily produces the 24-block field. It does not identify which private native readiness or ingestion state caused the historical split. Because both new processes were representative, the predeclared branch did not run a public-field check, cooldown ablation, authoring-order change, or any long stationarity/readback population.

P0/P1 Kit Private Bytes peaked at `14,569,017,344 / 14,526,095,360 bytes` (13.568 / 13.528 GiB), leaving `463,368,192 / 506,290,176 bytes` below the unchanged 14 GiB limit. Tree peaks were `14,733,066,240 / 14,676,037,632 bytes`, under 16 GiB. Stage close completed in `0.482426 / 0.683306 seconds`; both processes reached normal OS exit. Fatal, crash dump, automatic upload, device lost/TDR, CDB invocation, and Kit/CDB/GPU-helper residual counts were zero.

Release build, Phase 0 RTX, and Phase 3 passed. Phase 3 retained dry/wet authority SHA-256 `0dec57f...be10` / `148585f...0d9f`, mass-balance error `0 / 0`, active blocks final/peak `260 / 311`, and peak fuel `1.0`. Focused contracts passed `25/25`; the standard suite passed `78/78` across eight processes in `343.8 seconds`. Production app SHA-256 remained `94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A` before and after both probes.

## Conclusion and next boundary

Observed fact: representative and small-field histories first diverge at the first post-play update, while the authored source is identical and before readback. Strong inference: Phase 6EZ's `np.asarray(fuel)` remains a same-object zero-copy observation and is not the source of that initial divergence. Unconfirmed: the precise native Flow/Point ingestion readiness or cross-process state that yielded the historical 24-block field.

The best current startup candidate is the instrumented order above, coupled with a frame-60 representative-ingestion gate. It is a candidate, not a proven fix, because Phase 6FA broadly used the same order. Before repeated readback can proceed, a separate predeclared Phase must either reproduce the 24-block startup with these new markers or add one-variable startup ordering/readiness probes. Repeated readback, fuel lifetime qualification, and production integration remain blocked. The low-frequency stage-close hang did not recur in Phase 6FB but remains an independent unresolved native lifecycle risk.
