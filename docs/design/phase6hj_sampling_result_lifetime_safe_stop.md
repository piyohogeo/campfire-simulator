# Phase 6HJ sampling-result lifetime comparison safe stop

Phase 6HF remains frozen at `c27267f`. Its artifacts, contract, classification,
thresholds, and samples were neither changed nor reused as new measurement.
Phase 6HH's contract/harness implementation is `5f483a9`; it stopped before Kit
launch because the no-Kit exact-command fixture reused a fixed temporary
directory. Phase 6HJ fixed only that fixture isolation in `7b989f8`, froze
contract SHA-256
`48F7BC9A1939D518CF9112647049082E1BE92D2DD63459CEA6D09A346C4F0047`, and used
the fresh root `artifacts/phase6hj-sampling-result-lifetime-20260815`.

## Read-only ownership audit

The Phase 6HF R1 `_sample_grid()` result is a `builtins.dict` with seven scalar
leaves: `available`, `voxel_count`, `nonzero_voxel_count`, `mean`, `sum`,
`p95`, and `maximum`. It contains no NumPy object, NanoVDB/native wrapper,
grid, volume, or readback handle. A built-in dict is not weak-referenceable.
Phase 6HF stored the original dict in `velocity_result["rois"]["scene"]` and
then placed that same velocity-result object in the operation report. Clearing
the local variable did not release the report-owned object. Handle weak
residual zero did not cover that dict. The bounded audit was durably saved
before runtime without reading or copying a field body.

## Pre-runtime safe stops

The Phase 6HH formal preflight stopped before Kit launch because its exact
command fixture found the fixed `%TEMP%/phase6hh-command/runner-logs` left by
the implementation fixture. Phase 6HJ placed the unchanged 51-case fixture
under a unique `TemporaryDirectory`; 51/51 passed. The runtime probe,
L0/L1/L2 meanings, safety gates, and original-result lifetime behavior were
unchanged.

The Phase 6HJ parent contract accidentally omitted the temporary-file
allowlist required by the shared post-process classifier. This caused a parent
`KeyError` after the first child process ended and prevented the normal parent
summary from being written. It did not cause or hide a successful child: the
durable child evidence independently records a non-normal L0 result. The
missing parent field is retained as a harness/reporting failure and is not
repaired or retried in this phase.

## L0 result and comparison decision

Only L0 launched. The startup telemetry was fresh and representative through
frame 138, with 1,190 active blocks, the expected 1,344/1,440 Points, revision
1, and the frozen payload hash. Kit then exited with code `0xC0000005` before
frame 180 readback. The operation report remained `running`, all counters were
zero, and no readback, schema prefix, volume path, sampling, result retention,
reference release, stage close, or `shutdown_complete` marker occurred.

| Axis | L0 result |
|---|---|
| functional | failure before readback; operation incomplete |
| lifecycle | stage close and `shutdown_complete` not reached |
| OS exit | abnormal `0xC0000005` |
| resource | within all ceilings and floors |
| cleanup | exact attempt-tree cleanup passed; residual zero |

Kit/tree peaks were 15,525,724,160 / 15,678,468,096 bytes, leaving
1,654,145,024 / 2,575,142,912 bytes below 16/17 GiB. Runner/diagnostic peaks
were 96,456,704 / 17,014,784 bytes. Minimum available physical memory and
estimated commit headroom were 82,787,434,496 / 102,438,232,064 bytes. There
was one bounded crash artifact, no automatic upload, no residual NanoVDB, and
no Kit/CDB/GPU-helper residual. A stage-close timeout did not occur because the
process exited before shutdown; CDB was not started for the already-exited
target.

L0 is non-normal, so the retention comparison is invalid. L1 immediate-clear
and L2 retained-result conditions were not launched. No statement about
sampling-result lifetime can be made from this population, and Phase 6HF is
not retrospectively changed. The observed L0 failure is before sampling and is
not interpreted as a sampling or retention root cause.

Given the repeated low-frequency native lifecycle outcomes and the inability
of this bounded ladder to establish a normal control, NanoVDB readback shutdown
work is parked as `diagnostic-only lifecycle`. Natural future recurrence keeps
the detailed markers; no automatic fix, replacement, long repetition,
temperature/collector/profile work, formal comparison, or production change
is authorized.

## Verification

Release build passed in 7.72 seconds. The Phase 6HJ fixture passed 51/51;
frozen Phase 6HF and Phase 6HE focused fixtures passed 62/62 and 63/63. The
frozen Phase 6HH fixture still produces its expected pre-Kit safe-stop exit and
is not reclassified. Python compilation and the static devlog validator passed
(533 references, 313 IDs, 266 JSON, 177 SVG, 2 ZIP). The standard suite passed
78/78 across eight processes in 336.3 seconds. Phase 0 RTX and Phase 3 were not
rerun because this phase changes no production, USD generation, rendering,
physics, or Flow input. Production app SHA-256 remains
`94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`;
the latest-demo manifest and video remain unchanged.
