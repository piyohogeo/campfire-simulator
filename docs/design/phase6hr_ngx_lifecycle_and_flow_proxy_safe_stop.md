# Phase 6HR exact NGX lifecycle and one-proxy safe stop

## Frozen history

Phase 6HQ remains frozen at `faa7903`. Its raw artifacts, contract,
guard/parent `cleanup_failure`, and absence of a proxy run were not rewritten
or reclassified. Phase 6HR uses contract
`campfire.phase6hr.ngx-cleanup-assisted-proxy-contract.v1`, SHA-256
`5BBBA68CCCFB15B5FED787F4ED82E230B27B0145E5ECD20F80FFC4463109BD2C`,
and fresh roots throughout.

## Canonical lifecycle fixture

The actual evidence producer, atomic JSON persistence, bounded reader, and the
same guard/parent consumer passed 32/32 no-Kit cases. Natural exit, one exact
telemetry helper, one exact NGX updater/conhost tree, telemetry plus that tree,
grace exit, and exact cleanup were accepted. Incomplete/duplicated trees,
wrong parent/path/basename/creation time, PID reuse, pre-attempt identity,
missing chain, unknown or critical residuals, surviving cleanup targets,
killed-PID mismatch, missing/duplicate/contradictory evidence, missing
operation/shutdown marker, and resource failure failed closed. Guard and
parent matched classification, reason, allowed helper set, and killed PID set
for all 32 cases. Focused tests passed 5/5.

## Fresh app-ready smoke

The one fresh smoke at `artifacts/phase6hr-app-ready-smoke-20260815` is
qualified as `cleanup_assisted_ngx_exit`, explicitly not natural exit. Kit
completed app-ready, operation, shutdown, and exit code 0. Exact cleanup was
limited to telemetry PID 4652, NGX updater PID 43592 directly under Kit, and
System32 conhost PID 38296 directly under that updater. Both identity query
sources confirmed absence afterwards; final residual is zero.

Smoke peaks were runner 96,624,640, Kit 7,300,018,176, diagnostic 16,924,672,
child 61,345,792, and unique tree 7,753,838,592 bytes. Minimum available
physical memory was 85,572,374,528 bytes and minimum commit headroom was
105,302,704,128 bytes. There was no readback, fatal/native exception, dump,
automatic upload, device loss, or TDR.

## Fresh one-proxy boundary

The accepted smoke authorized one fresh process at
`artifacts/phase6hr-flow-proxy-boundary-20260815`; there was no retry or
replacement. The diagnostic operation itself constructed the current
production log hierarchy and added only
`/World/Logs/Log_00/FlowCollisionProxy`. The proxy is the qualified closed,
outward low-detail Mesh (26 vertices, 36 faces, 120 indices), shares the
expected transform with the log hierarchy, is invisible and default-off, and
adds no Point Prim or revision attribute. The stopped timeline remained
stopped, 30 renderer updates completed, the public Flow interface was acquired
once, and NanoVDB readback count was zero.

The operation then completed release-after-close: stage close took 0.899246
seconds, four post-close updates ran, references were released,
`shutdown_complete` was durable, and Kit exited with code 0. A single exact
telemetry helper was removed and final residual was zero. Kit/tree peaks were
10,123,976,704 / 10,471,964,672 bytes, leaving 7,055,892,480 /
7,781,646,336 bytes to the frozen ceilings. Physical/commit minima were
84,124,553,216 / 103,859,863,552 bytes. No CDB, fatal, dump, upload, device
loss, or TDR occurred.

Nevertheless, the Phase 6HR parent contract required top-level booleans
`operation_complete` and `shutdown_complete` in the bounded operation report.
The reused proxy report stores lifecycle completion under `lifecycle` while
its fsynced JSONL contains the exact `operation_complete` and
`shutdown_complete` names. The canonical producer therefore returned
`operation_complete_failed` and `shutdown_complete_failed`, and both consumers
classified the run as `cleanup_failure`. This is a bounded artifact-interface
harness failure, not a Flow, proxy, resource, stage-close, or Kit-exit failure.
The functional coexistence is retained only as partial evidence; the formal
production-hierarchy plus one-proxy boundary is not qualified and the run is
not reclassified.

## Regression and current boundary

Release build passed, focused tests passed 5/5, the canonical fixture passed
32/32, Python compilation passed, and the standard suite passed 8/8 processes
and 78/78 tests. Static devlog validation passed. Phase 0 RTX and Phase 3 were
omitted because production sources, published USD generation, renderer
settings, wood authority, and Flow inputs were unchanged; only a default-off
diagnostic stage was exercised. Production app, scene, wood authority, V3,
and latest-demo hashes remain unchanged.

The exact NGX-assisted lifecycle classification and fresh app-ready smoke are
qualified. The one-proxy functional operation was observed but its formal
boundary remains unqualified due solely to the canonical report-interface
mismatch. A separately approved Phase may unify the proxy operation report
with the canonical evidence schema in a no-Kit fixture, then run a fresh
one-proxy process. Dynamic transforms, occlusion, PhysX sharing, 20-log
performance, Point policy, and production integration remain unqualified.
