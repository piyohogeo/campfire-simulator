# Phase 6HQ canonical lifecycle classification and pre-proxy safe stop

## Frozen history and contract

Phase 6HP remains frozen at `92dfe5a`. Its raw guard, parent summary,
classification, contract, and artifacts were inspected read-only and were not
rewritten or reused as Phase 6HQ runtime evidence. Phase 6HQ uses contract
`campfire.phase6hq.cleanup-assisted-app-ready-and-proxy-contract.v1`, SHA-256
`E14A19A7B68E02792D54DB7757A4EB444362F11391023C3319ABE052507C0477`,
and new fixture/smoke roots.

The new evaluator separates `natural_clean_exit`, the narrowly permitted
`cleanup_assisted_exit`, and `cleanup_failure`. The guard persists its complete
canonical input and evaluation. The parent passes that same input through the
same evaluator and rejects any missing or contradictory persisted result; it
does not independently upgrade a guard result from final residual zero.

`cleanup_assisted_exit` accepts at most one exact attempt-owned
`omni.telemetry.transmitter.exe` under the known Omniverse telemetry extension
store. PID, creation time, absolute path, extension identity, parent chain,
attempt ownership, first/last observation, termination time, killed-PID list,
cleanup suppression, and post-cleanup psutil/Win32 absence must all agree.
Any other helper, unknown identity, mismatch, or incomplete evidence is
`cleanup_failure`.

## Offline fixture

The no-Kit producer-to-consumer fixture at
`artifacts/phase6hq-lifecycle-preflight-20260815` passed 22/22. It covered
natural exit, one telemetry-assisted exit, natural grace exit, wrong binary or
path, external path, creation-time mismatch, PID reuse, wrong parent or
attempt ownership, two telemetry helpers, telemetry plus unknown child,
Kit/Flow/CDB residuals, post-cleanup survival, killed-PID mismatch, missing
operation marker, resource failure, and missing/duplicate/contradictory
evidence. Guard and parent classifications matched in every case. Focused unit
tests passed 4/4. Kit launch count was zero and Phase 6HP artifact hashes were
unchanged.

## Fresh app-ready smoke

One process was launched at
`artifacts/phase6hq-app-ready-smoke-20260815`, with no retry or replacement.
Kit reached app-ready, resolved both required extensions, acquired the
extension manager, imported `campfire` and `campfire.app`, and passed the
junction-aware module gate. Durable `operation_complete` and
`shutdown_complete` markers exist and Kit itself exited with code 0.

The canonical cleanup evidence found three exact attempt-owned survivors:

- `omni.telemetry.transmitter.exe`, PID 10608, directly parented by Kit;
- `nvngx_update.exe`, PID 9544, directly parented by Kit;
- `conhost.exe`, PID 23364, parented by that `nvngx_update.exe`.

Exact identity cleanup stopped those three identities and confirmed all absent;
final residual is zero. Nevertheless, the user-authorized assisted class allows
only the single telemetry transmitter. The guard and parent therefore both
classified the smoke as `cleanup_failure` with reason
`only_zero_or_one_telemetry_residual_allowed`. This is not
`cleanup_assisted_exit` or `natural_clean_exit`.

## Proxy boundary and safety result

The one-proxy root was not created. No stage, production hierarchy,
`FlowCollisionProxy`, viewport update, public Flow-interface call, or NanoVDB
readback occurred. Production-hierarchy/proxy coexistence remains unmeasured.

Smoke peak Private Bytes were runner 97,116,160, Kit 7,129,280,512,
diagnostic 17,084,416, child 61,546,496, and unique tree 7,574,065,152
bytes. Kit and tree headroom were 10,050,588,672 and 10,679,545,856 bytes.
Minimum available physical memory was 86,075,592,704 bytes and minimum commit
headroom was 105,805,922,304 bytes. Fatal/native exception, dump, automatic
upload, device loss, and TDR counts were zero.

Production app, production scene, wood authority, V3, and latest-demo hashes
are unchanged. Release build passed in 7.90 seconds, the standard suite passed
8/8 processes and 78/78 tests, Python compilation and static devlog validation
passed. Phase 0 RTX and Phase 3 were not run because production sources, USD
generation, rendering, wood authority, and Flow inputs are unchanged and no
proxy stage was launched.

## Qualified and pending boundaries

The canonical lifecycle evaluator and its guard-to-parent evidence contract are
qualified. The fresh smoke is a fail-closed sample, so neither app-ready smoke
acceptance nor the one-proxy coexistence boundary is qualified in Phase 6HQ.
Any future work requires separate approval. It must use a fresh root and may
decide whether the assisted policy should remain telemetry-only or whether the
observed NGX helper tree warrants a separate, predeclared diagnostic policy;
Phase 6HQ itself must not be retried or reclassified. Dynamic transforms,
occlusion, PhysX sharing, 20-log performance, Point policy, production
integration, and NanoVDB work remain out of scope.
