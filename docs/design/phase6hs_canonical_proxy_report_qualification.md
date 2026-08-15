# Phase 6HS canonical proxy report and one-proxy qualification

Phase 6HR remains frozen at `f3bca01` with its original partial functional
evidence and formal `cleanup_failure`. No Phase 6HR runtime sample was reused
or reclassified. Phase 6HS used contract
`8DA32B5CCCA6AD4539EC60494F52988BEA3D06D5E7D9E93DF35EB097B7F6CA93`
and a new empty artifact root.

## Canonical report qualification

The versioned schema
`campfire.phase6hs.proxy-operation-report.v1` has digest
`5664B84A498D81FF2A53B793AF246F853F8C9912030DB7A1086959317DD7A393`.
Durable attempt-bound JSONL markers are the source of truth. The runtime
producer validated exactly one ordered `operation_complete`,
`stage_close_complete`, and final `shutdown_complete`, then generated atomic
top-level booleans after Kit exited. Nested lifecycle data was accepted only as
an exact optional mirror.

The no-Kit fixture qualified 42/42 operation cases and 5/5 lifecycle cases.
It exercised the real producer, JSON writer, persisted file, bounded reader,
validator, guard report construction, and parent consumer. Natural,
telemetry-assisted, and NGX-assisted positives passed. Missing, false,
mistyped, duplicate, reordered, post-shutdown, cross-attempt, legacy-schema,
digest-mismatch, truncated, transformed, and contradictory evidence failed
closed with fixed reasons. Guard and parent used the same validation object.
The frozen Phase 6HR artifact hashes were unchanged and Kit launch count was
zero.

## Fresh one-proxy measurement

The fresh root was
`artifacts/phase6hs-flow-proxy-boundary-20260815`; exactly one process was
launched, with no retry or replacement. It preserved the production log
hierarchy and added only
`/World/Logs/Log_00/FlowCollisionProxy`. The proxy remained the qualified
invisible, default-off, closed outward Mesh: 26 vertices, 36 faces, 120
indices, zero degenerate faces, and the expected world transform. Excluding
that one Prim reproduced the production baseline digest. No Point Prim,
revision property, rigid body, production source, default, or published scene
was changed.

The timeline stayed stopped, renderer update count was exactly 30, the public
Flow interface was acquired exactly once, and NanoVDB readback count was zero.
Operation, stage close, and shutdown markers each occurred once and in order;
the top-level booleans were all true, `last_marker` was
`shutdown_complete`, and Kit exit code was zero. Stage close took 0.514881
seconds. The canonical report and marker digests were respectively
`185B1C491B2E489B3A2B4CFCE47EF689A9B8622B69EEB886C8104BA9811A5652`
and
`22507DF85E3C8BE6300A9AD271A143F7DB42204D87B6366A590FB09FC76547AD`.

Lifecycle classification was `cleanup_assisted_telemetry_exit`, explicitly not
natural exit. One exact attempt-owned telemetry transmitter (PID 15296) was
removed; both identity sources subsequently confirmed absence. No NGX helper,
CDB, fatal/native exception, dump, automatic upload, device loss, or TDR was
present. Exact cleanup ended with residual zero.

Kit and unique-tree peaks were 10,036,449,280 and 10,430,550,016 bytes,
leaving 7,143,419,904 and 7,823,060,992 bytes to the frozen 16/17 GiB limits.
Runner and diagnostic peaks were 95,580,160 and 16,891,904 bytes. Minimum
available physical memory and commit headroom were 85,067,730,944 and
104,803,434,496 bytes.

## Regression and boundary

The Phase 6HS focused tests passed 5/5 and the frozen Phase 6HR focused tests
passed 5/5. Python compilation, Release build, the standard suite (8/8
processes, 78/78 tests), and static devlog validation passed. Phase 0 RTX and
Phase 3 were omitted because production code, USD publication, renderer
configuration, wood authority, and Flow input were byte-for-byte unchanged;
the operation was a default-off diagnostic stage only. Source and built
production app hashes both remain
`94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`.
Scene, wood authority, V3, and latest-demo hashes also remain unchanged.

The qualified scope is now only the present production log hierarchy plus one
default-off low-detail proxy, stopped timeline, 30 renderer updates, one public
Flow-interface acquisition, zero readbacks, and the measured lifecycle,
resource, and cleanup behavior. Flow occlusion, timeline play, dynamic
transforms, PhysX mesh sharing, Point Emitter coexistence, four-/twenty-log
performance, production integration, default-on policy, V3 changes, and visual
media remain unqualified and require separate approval.
