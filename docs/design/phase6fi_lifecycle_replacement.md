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
