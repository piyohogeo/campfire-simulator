# Phase 6FS B-first release-after-close qualification

## Frozen boundary

Phase 6FR is frozen at commit `a55b49b`. Its first formal A (`release-before-close`) process reached representative startup with the fixed corrected-four S93 payload, no readback or capture, and remained inside every resource ceiling. `close_stage_async()` then timed out after 180.0144794 seconds. Stack-first CDB captured all 149 threads: the main close path was in `omni_usd!UsdManager::destroyContext+0x160`, while a loader thread waited in `RtlAcquireSRWLockExclusive` from the `loadRenderSettingsFromStage`/`closeStage` path. The lock owner is unknown, the accepted NGX signature matched 0/5 tokens, explicit detach and exact cleanup completed, and B was not started. Phase 6FS does not reclassify that result or restart Phase 6FO.

## Frozen experiment

The machine contract is `scripts/phase6fs_release_after_close_contract.json`; its SHA-256 sidecar is authoritative before runtime. The only formal condition is B, in three independent processes:

1. stop the timeline;
2. perform eight renderer updates;
3. retain stage, viewport, Flow interface, volume provider, Emitter prim, collector list/map, and the disabled capture-provider slot in an explicit ownership container;
4. call and await `close_stage_async()`;
5. verify USD context detach;
6. perform four post-close renderer updates;
7. release every Python-owned reference slot in a fixed order;
8. observe extension shutdown, Kit shutdown, normal OS exit, and zero residual processes.

The fixed physical input is the corrected four-log fixture, S93 `allow_self_center`, 1,344 active of 1,440 Points, payload SHA-256 `0D3B074B7BE3E482E8702A126A11619D87F587C4848C80D4A3162A11B876C389`, frames 60/96, readback zero, and capture zero. The shared Phase 6FO case runner and probe implement the sequence through the existing release-order argument; the shutdown body is not copied into a B-specific probe.

The ownership report records each retained slot's type and identity. Weak references are recorded where the object type supports them. Weak-reference survival is diagnostic rather than a hard failure because USD/Kit may own the same object independently. The hard condition is that the explicit container and all probe-owned local aliases are empty after release. Forced garbage collection is prohibited.

## Diagnostics and safety

The Phase 6FR stack-first CDB implementation is unchanged. Before Kit, Phase 6FS performs one stoppable wait-target smoke only. A timeout uses exact PID, creation time, and absolute executable path; captures a bounded all-thread stack before an independent module pass; explicitly detaches in a separate pass; uses only the local symbol cache; and writes bounded stdout/stderr directly to files. It does not create a full dump, wait for Microsoft symbols, enable uploads, or register a postmortem debugger.

The unchanged ceilings are 14 GiB Kit Private Bytes, 16 GiB unique-tree Private Bytes, 512 MiB runner, 512 MiB diagnostic child, and 8 GiB physical/commit headroom floors. Stage close remains bounded at 180 seconds. A stage-close timeout, resource breach, fatal/dump/upload/device-lost/TDR, marker inversion, CDB/detach failure, exact-cleanup failure, or residual process is nonreplaceable and stops the population. Only the previously frozen startup-prerequisite replacement budget of one process applies.

## Decision rule

Three normal B processes with the complete marker order, retained-through-post-close evidence, cleared Python-owned slots, no CDB invocation, and zero residuals qualify `release-after-close` only as a strong candidate for another limited qualification. They do not change production shutdown order and do not prove the native lifecycle issue is eliminated. One matching timeout means reference release order is insufficient; the captured stack is compared with Phase 6FR and the experiment stops without repetition.

Even on success, this phase does not restart Phase 6FO, run S93/S100 scalar or transport comparisons, change 14/16 GiB limits, make a video, or enter roadmap P4. It only determines whether a separate memory-ceiling qualification may proceed while the low-frequency native lifecycle risk remains explicitly monitored.

## Runtime result

The frozen population completed 3/3 without a startup replacement. Every process used the same payload SHA-256, reached 688 active blocks at frame 60 and 948 at frame 96, performed zero readbacks and zero captures, retained all required references through USD detach and four post-close updates, cleared every Python-owned slot, observed both extension-shutdown callbacks, exited with code zero, and left no observed descendant process. Stage-close times were 2.9165363, 2.2236896, and 21.8791366 seconds. No run approached the 180-second timeout and CDB was not invoked.

Weak references remained alive for the USD Stage, volume provider, and Emitter prim after the probe cleared its aliases; the Flow interface weak reference was dead. This is evidence of independent SDK/framework ownership, not a Python-owned alias leak: the explicit ownership container had eight false/empty slots, local aliases were empty, extension shutdown completed, OS exit was normal, and residual-process count was zero in every run. The weak-reference values remain telemetry and are not rewritten as object-destruction proof.

Kit Private Bytes peaked at 14,941,323,264, 14,880,235,520, and 14,887,927,808 bytes (13.915, 13.858, and 13.865 GiB). The smallest margin to the unchanged 14 GiB ceiling was 91,062,272 bytes (86.844 MiB). Unique-tree peaks were 15,105,253,376, 15,031,345,152, and 15,051,411,456 bytes; runner peaks were 109,060,096, 117,436,416, and 109,248,512 bytes; diagnostic-child peaks were 16,936,960, 16,891,904, and 17,104,896 bytes. Physical-memory and commit-headroom minima remained above 75.79 GiB and 93.79 GiB. Fatal, dump, upload, device-lost, TDR, CDB, cleanup, and residual counts were zero.

Therefore `release-after-close` is a strong candidate shutdown order for a separate limited qualification, not a production change and not proof that the low-frequency native issue is eliminated. The 21.879-second third close also demonstrates real normal-run latency variation. Lifecycle can now be separated from the next memory-ceiling qualification under this candidate order, while stack-first CDB remains armed for natural recurrence. Phase 6FO is still stopped; 14 GiB is still the active Kit ceiling, 16 GiB is not adopted, and S93/S100 comparison, video, and P4 did not run.

Post-run verification passed: Release build in 8.26 seconds; Phase 0 RTX with exit code zero; Phase 3 with dry/wet mass-balance error zero, authoritative hashes present, wood-owned Flow input, and 262/337 final/peak active blocks; focused Phase 6F contracts 154/154; the standard eight-process suite 78/78 in 342.4 seconds; and devlog validation (`refs=457`, `ids=275`, `json=227`, `svg=177`, `zip=2`). The production app SHA-256 remained `94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`. No production/default file is in the Phase 6FS diff, no new video was made, the latest-demo manifest is unchanged, and final Kit/CDB/nvidia-smi plus guard-observed Phase 6FS residual counts are zero.
