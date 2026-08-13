# Phase 6FC Point Emitter startup reproduction and ordering audit

## Frozen boundary and contract

Phase 6EY, 6EZ, 6FA, and 6FB remain frozen. Phase 6FC is production-neutral and uses the same corrected four-log geometry, 1,440-Point payload, 1,344 active Points, Point policy, Flow settings, renderer, resource ceilings, and shared shutdown/CDB lifecycle. It performs no public field readback, conversion, repeated readback, long D0/D1/D2 population, or production integration.

The pre-runtime contract is `campfire.phase6fc.point-emitter-startup-reproduction-contract.v1`, SHA-256 `32BF37AC317ABB7894744163BBB08AD5AA5CD71AA26C28678BA4461F02C07832`. The baseline order is complete offline stage/payload authoring, USD-context connection, 60 active-viewport frames, public Flow-interface acquisition, stopped timeline reset, 12 stopped Kit updates, timeline play, frames 1 through 120, and the existing bounded shutdown sequence. Representative ingestion requires fresh frame/timestamp/update/timeline evidence and at least 128 active blocks by frame 60. A fresh 20 through 32-block field remains a diagnostic `small_field_ingestion`, not a successful startup. Delayed ingestion, stale telemetry, no source, and lifecycle failure are distinct fail-closed outcomes.

The first root stopped before Kit launch because the orchestration layer passed an empty `PreviousProcessExitUtc` option without a value. The resource guard recorded process absence and formal sample count zero. The root was retained and not reused. A minimal launch correction omits that optional argument for the first process; the unchanged frozen contract then restarted from a new empty root.

## Six-process reproduction result

All six baseline processes classified as `representative_ingestion` and reached normal OS exit. Every baseline produced the same complete active-block history; frames 1/30/60/120 were `269 / 505 / 688 / 1118`. The 24-block reproduction count is `0/6` (`0%`). This finite result does not establish that the historical condition is resolved.

The six stage-connection times ranged from `0.428168` to `5.435748 seconds`; the five measurable prior-exit-to-next-process-start intervals ranged from `6.016208` to `8.902099 seconds`. Occupancy histories were identical, so a numerical correlation with stage time or process interval is undefined and no association was observed. B01, treated only as the first process in the empty root, was identical to B02 through B06. Bounded logs exposed the same shader/cache fingerprint count but no public positive cold/warm cache state, so cache warmth is not claimed.

Within every process, stage, Flow-interface, Emitter wrapper, Points wrapper, payload hashes, and frame/update identities remained stable. The generated stage was byte-identical across all Phase 6FC conditions. Compared with Phase 6FB, its raw layer differs only in the diagnostic `campfire:phase` custom metadata; after removing that field, normalized SHA-256 is the same (`790FD078...671B`). Point payload SHA-256 remains `0D3B074B...C389`.

## One-variable ordering ablations

- A0 baseline control reproduced `269 / 505 / 688 / 1118`.
- A1 moved only Flow-interface acquisition from before to after the 12 stopped updates. Its complete history was identical to A0. This tested public wrapper acquisition timing, not an internal Flow-consumption readiness predicate.
- A2 removed only the 12 stopped updates. Its frames 1/30/60/120 were `176 / 402 / 611 / 1066`; the first divergence was the first post-play sample. It still crossed the representative threshold by frame 1 and remained representative. The updates therefore affect how much Flow work is visible at the first observed frame but are not shown to be the trigger for the historical 24-block lock.
- A3 retained the 12 stopped updates and inserted exactly one extra update at the boundary before play. Its frames were `269 / 517 / 705 / 1117`; the first difference from A0 occurred at frame 2. It remained representative.

Observed fact: none of the tested Flow-interface/12-update/play boundaries reproduced small-field or delayed ingestion. Strong inference: public Flow-interface acquisition position is not decisive in this fixed sequence, while stopped Kit updates affect initial scheduling progress. Unconfirmed: the native ingestion trigger, internal source-consumption readiness, and any rare per-process state that produced the historical 24-block allocation.

## Lifecycle, resources, and monitoring proposal

All ten formal processes completed stage close and normal OS exit. Stage close ranged `0.127394` to `8.401451 seconds` (mean `3.171354 seconds`). CDB invocation, fatal, dump, automatic upload, device lost/TDR, and cleanup residual counts were zero. Maximum Kit Private Bytes were `14,565,556,224 bytes` (13.564 GiB), leaving `466,829,312 bytes` below the unchanged 14 GiB ceiling. Maximum unique-tree Private Bytes were `14,728,912,896 bytes`, below 16 GiB.

A future production monitor may use `startup_pending`, `representative_ready`, `small_field_detected`, `recovery_pending`, `recovery_failed`, and `running`. For this fixed diagnostic fixture only, frame 60 below 128 blocks is a reasonable anomaly candidate. It is not sufficient for automatic recovery: fresh timeline/telemetry, correct Point revision/count/supply, enabled Emitter, stable expected stage/Flow identity, resource headroom, and delayed-ingestion exclusion are also required. Any future recovery must be limited (for example, once), durably marked, and must not enter a restart loop.

Automatic reinitialization is not ready for implementation. The failure did not reproduce, a safe recovery operation has not been established, and no independent recovery lifecycle qualification covers stage close and normal OS exit. Phase 6EZ's same-object zero-copy observation remains unchanged, but one fuel alias lifetime and repeated readback remain unqualified until the startup anomaly can be reproduced or a stronger public liveness/readiness boundary is established.

Final regression passed the Release build, Phase 0 RTX, Phase 3, focused diagnostic/shutdown contracts `82/82`, and the standard suite `78/78` across eight processes in `328.2 seconds`. Phase 3 retained dry/wet authority SHA-256 `0dec57f...be10` / `148585f...0d9f`, mass-balance error `0 / 0`, Flow active blocks final/peak `269 / 358`, and peak fuel `1.0`. Production app SHA-256 remained `94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`.
