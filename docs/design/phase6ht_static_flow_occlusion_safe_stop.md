# Phase 6HT static production-hierarchy Flow occlusion safe stop

Phase 6HS (`fbbac6f`) remains the frozen qualified baseline. Phase 6HT used a
new contract and root; no Phase 6HS runtime sample was reused or reclassified.
The machine contract SHA-256 is
`AC5571BBFF59456285B745226137DE5055159A3628F46083BA47DC32C43E73A2`.

The pre-Kit fixture first exposed a test-only module-search-path defect and
stopped with zero Kit launches. That artifact was preserved. After changing
only the fixture import path, the new preflight root passed 8/8. The formal
order remained ON then OFF, one process each, no retry or replacement.

Only Collision ON launched. The exact Phase 6HS 26/36/120 closed outward Mesh
and Log_00 world transform were preserved, as were the known-good Flow/camera
authoring helpers. The process made one public Flow-interface acquisition,
zero NanoVDB readbacks, one timeline play, 240 updates, and two bounded image
captures. Active blocks at frames 60/120/180/240 were 46/46/40/49, below the
predeclared 128 representative-field minimum. Visual review of the ON-only
final capture found no clearly discernible Flow field, so sensitivity was not
established.

The last operation marker was `operation_complete`; the last lifecycle marker
was `timeline_stop_complete`. A subsequent atomic raw-report replacement
failed with `WinError 5`, so stage close and `shutdown_complete` were not
measured. Kit exited 1 and the canonical producer correctly did not run. OFF
was therefore not launched. This is a fail-closed harness/lifecycle result and
a failed Flow prerequisite, not an occlusion result.

Resource limits and system floors passed. Kit/tree peaks were
11,370,786,816/11,694,043,136 bytes; exact cleanup left no residual process.
Fatal, device-loss, TDR, dump, automatic upload, CDB, and readback counts were
zero. Production code, defaults, wood authority, Point policy, V3, public
scenes, and latest demo are unchanged. Static occlusion, timeline-playing
qualification, dynamic transform, PhysX sharing, Point coexistence, and 4/20
log performance remain unqualified.

Focused fixtures passed 8/8, Python compilation passed, Release build
completed in 7.50 seconds, the standard suite passed all eight processes and
78/78 tests, and static devlog validation passed with 553 references and no
missing asset. Phase 0 RTX and Phase 3 were omitted because production code,
published USD generation, render defaults, wood authority, and production
Flow input are byte-for-byte unchanged; the only runtime was a default-off
diagnostic stage and it stopped before an occlusion comparison. Source and
built app hashes remain
`94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`;
latest demo remains
`1C6FB249EAE8DF09E804680C7D0459BA8631D4ECFF4903944FFA4701E94E6285`.
