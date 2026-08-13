# Phase 6FI — bounded startup replacement lifecycle qualification

Phase 6FG and Phase 6FH remain frozen historical evidence. Phase 6FI changes only population orchestration: six representative readback-free A controls are required, while at most two additional launches may replace preserved startup-prerequisite failures. It does not change the four-log fixture, Point payload, Flow, CollisionProxy, startup ordering, observation duration, shutdown order, resource ceilings, memory-waveform policy, or production.

## Pre-runtime population contract

Every launch receives a unique `attemptNN` identity and is classified exactly once as `representative_startup`, `startup_prerequisite_failure`, `operation_failure`, `native_lifecycle_failure`, or `absolute_safety_failure`. The representative target is six, the startup replacement budget is two, and the maximum launch count is eight. No launch directory or attempt number is reused.

Only `startup_prerequisite_failure` consumes the replacement budget and permits the next unique launch. Its full per-frame startup history, source contract, identities, timing, shader/cache log evidence, prior-process interval, GPU selection, resource trace, shutdown result, and cleanup are retained, but it is excluded from the representative lifecycle denominator. A third prerequisite failure, or exhaustion of eight launches before six representative samples, produces `prerequisite_population_incomplete`.

Operation, native lifecycle, and absolute-safety failures are not replaceable. They stop the population immediately without automatic retry. A prerequisite launch that intentionally exits with code 1 after a clean 3-stage shutdown is not mislabeled as a native failure; stage-close timeout, shutdown residual, or cleanup failure still overrides its startup classification.

## Unchanged runtime and safety boundaries

The condition is the Phase 6FH readback-none A control: corrected production-four geometry, `allow_self_center`, offset -0.0125 m, 1,440 total and 1,344 active Points, revision 1, identical source sums, ten fixed sample frames through 320, and a 24-second running-Flow observation. Startup remains representative only when fresh timeline/update samples and exact identities/source are present and active blocks reach 128 by frame 60. Delayed, small-field, stale, no-source, or otherwise nonrepresentative startup is preserved as prerequisite evidence and never treated as a lifecycle pass.

Representative runs retain timeline stop, eight pre-close renderer updates, Flow/Emitter then provider/readback/collector reference release, 180-second stage close, USD disconnect, four post-close updates, extension shutdown, and normal OS exit. Kit remains capped at 14 GiB, the unique tree at 16 GiB, runner and diagnostic processes at 512 MiB each, and physical/commit headroom at 8 GiB. Readback, NumPy, field conversion/persistence, forced GC, private release APIs, production integration, and automatic upload are excluded.

## Bounded native diagnosis

Only a stage-close timeout or shutdown residual may invoke the already-qualified Phase 6FH diagnostic path: cache-only attach/module inventory for 30 seconds, all-thread depth-16 stack for 45 seconds, and detach recovery for 30 seconds, capped at 105 seconds. Output streams directly to bounded files under the existing atomic lock and exact PID/creation-time/path contract. A native lifecycle failure stops the population after one capture. Full dump acquisition is not automatic and requires separate approval.

## Result interpretation

Six representative normal exits mean bounded non-reproduction in six controls, not proof that the stage-close issue does not exist. Only that result can make a new-root Phase 6FG balanced A/B/C population a candidate for explicit approval. Startup-prerequisite incidence is reported independently. Phase 6FG is never started by this phase.

## Runtime result

The new root completed in seven unique launches. Attempts 01, 02, 04, 05, 06, and 07 were representative and all had the identical active-block startup trace at frames 1/60/120: 269/688/1118. They completed stage close, extension shutdown, normal OS exit, exact cleanup, and all absolute resource gates. Their stage-close durations were 2.669803, 6.767686, 2.837978, 8.550828, 2.052714, and 2.026506 seconds (minimum/median/mean/maximum 2.026506/2.753890/4.150919/8.550828 seconds).

Attempt03 was preserved as `startup_prerequisite_failure`. All 120 startup samples were fresh but remained exactly 24 blocks. The Point contract was enabled with revision 1, 1,440 total and 1,344 active Points, fuel 1075.200016, temperature 2688.0, smoke 107.519998, and the same payload SHA-256 as every representative attempt. Stage and payload hashes matched across all seven launches. Timeline and Kit updates advanced, identities remained stable, and RTX 3090 / driver 591.86 were selected. Its previous-process gap was 0.542 seconds, while representative gaps were 0.532–0.563 seconds; all launches recorded 29 shader-cache and six shader/compile-token lines. This phase therefore provides no evidence that gap or those coarse cache counters explain the 24-block state. It does not investigate the trigger further.

Attempt03 closed its stage in 2.514246 seconds and disappeared without forced cleanup, but its intentional startup-gate exit code 1 is not a representative normal-exit sample. It consumed one of the two frozen replacement slots. Startup-prerequisite incidence was 1/7 (14.286%). No second replacement was needed.

Across all seven attempts, operation, native lifecycle, and absolute-safety failures were zero. CDB was never invoked; fatal, access violation, device lost, TDR, dump, automatic upload, and cleanup residual counts were zero. Maximum Kit Private Bytes were 14,574,084,096 and maximum unique-tree Private Bytes were 14,736,871,424, within the unchanged 14/16 GiB ceilings. Minimum available physical memory and commit headroom were 85,795,512,320 and 105,116,684,288 bytes. Production remained unchanged.

The result is `lifecycle_qualification_pass`: Phase 6FG's native stage-close failure did not reproduce in six representative controls. This is bounded non-reproduction only. A new-root Phase 6FG balanced A/B/C population is now a candidate, but remains unstarted and requires explicit approval. Its proposed orchestration should retain the same prerequisite-only replacement rule while keeping operation and native lifecycle failures nonreplaceable.
