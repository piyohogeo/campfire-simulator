# Phase 6IN minimal post-shutdown monitor

## Frozen scope and contract

Phase 6IL remains frozen at `3da784d` as
`safe_stop_post_shutdown_harness_failure`; its contract, artifacts, dump audit,
monitor, and classification were not changed or reused. Phase 6IN started from
the Phase 6IM result commit `54a027f`, used contract SHA-256
`84F1CD39D383702A424944BD7FC1887810E4314E82BFA86494DC180511C31656`,
and used the fresh roots
`artifacts/phase6in_post_shutdown_preflight_20260816` and
`artifacts/phase6in_post_shutdown_monitor_20260816`.

The unchanged Phase 6IM helper SHA-256 is
`E25CDA2BC189B6740A10E4330E78D5579740EFF4B3EB8C1F95D3E1421DE01F4A`.
It remained the sole authority for PID, FILETIME creation ticks, and resolved
executable path. The Phase 6IN parent retained the launched process handle for
passive zero-time wait and exit-code observation. No Stage, Layer, timeline,
Flow, renderer, camera, capture, NanoVDB, CDB, or dump analysis was started.

The schedule was fixed before runtime at 0, 0.25, 0.5, 1, 2, 5, 10, 15, and
30 seconds after `shutdown_complete`; 15 seconds separated normal from delayed
exit. CDB was deliberately disabled because adding an attach operation to this
short passive boundary would introduce a second variable.

## No-Kit qualification

The actual helper producer, atomic writer, PowerShell monitor, bounded reader,
and validators passed 26/26 cases with zero Kit launches. Four real child
processes covered immediate exit 0, delayed exit 0, bounded timeout plus exact
cleanup, and nonzero exit. Negative coverage included missing, duplicate, and
out-of-order markers; PID/creation/path mismatch and PID reuse; corrupt and
oversize JSON; incomplete operation evidence; and helper-contract conflict.
The fixture kept stdout/stderr file-backed and left residual zero in every
case. Focused Phase 6IN and Phase 6IM unit tests passed 3/3 and 4/4.

## Sole actual Kit attempt

One fresh Stage-free app-ready Kit process was launched without retry or
replacement. The Phase 6IM helper completed two identity captures, both with:

- PID `524`;
- creation FILETIME ticks `134313180179568390`;
- resolved executable path
  `c:\packman-repo\chk\kit-kernel\110.2.0+feature.windows-x86_64.release\kit.exe`;
- 64-bit handle evidence with open/close counts 2/2 and zero helper residual.

Child evidence reached `kit_app_ready`, `operation_complete`,
`shutdown_requested`, and `shutdown_complete`. The operation axis therefore is
`complete`.

The parent launch record used the lexical build deployment path
`c:\users\junic\src\campfire-simulator\_build\windows-x86_64\release\kit\kit.exe`.
PID and creation ticks matched the helper exactly, but the parent compared this
lexical spelling directly with the helper's resolved Packman target. It raised
`phase6in_launch_helper_identity_mismatch` before
`post_shutdown_monitor_started`. This is a deterministic harness path-
normalization mismatch, not PID reuse and not a Kit lifecycle observation.

The durable timeline was:

| Boundary | UTC epoch |
| --- | ---: |
| runner started | 1786844417.835 |
| Kit launched | 1786844417.989 |
| Kit app-ready | 1786844424.432821 |
| operation complete | 1786844424.465361 |
| shutdown requested | 1786844424.490885 |
| shutdown complete | 1786844424.526459 |
| exact cleanup started | 1786844425.008524 |
| exact cleanup complete / residual zero | 1786844425.965184 |

There are no post-shutdown samples. Cleanup began about 0.482 seconds after
`shutdown_complete`, before the planned monitor could start. The exact guard
stopped the still-live attempt-owned Kit and four descendants, then proved all
nine observed identities absent. Therefore natural exit, delayed exit,
post-shutdown exception, and timeout are all unobserved; the lifecycle axis is
`unknown`, not `post_shutdown_timeout`. Cleanup is `failure` for lifecycle
acceptance because intervention included the main Kit process, although the
safety cleanup itself completed and final residual was zero.

No fatal line, access violation, dump, crash reporter, CDB, device loss, TDR,
or automatic upload attempt was observed before cleanup. Because no monitor
sample exists, this attempt neither matches nor contradicts the Phase 6IK
post-shutdown `0xC0000005`; comparison is indeterminate.

## Resource, regression, and classification

Kit/tree peaks were 3,735,592,960 and 3,925,696,512 bytes, leaving
13,444,276,224 and 14,327,914,496 bytes under the fixed 16/17 GiB limits.
Runner/diagnostic peaks were 96,264,192 and 17,145,856 bytes. Minimum available
physical memory and commit headroom were 83,558,760,448 and 103,481,876,480
bytes. The resource axis is `qualified`.

The final classification is
`safe_stop_post_shutdown_monitor_harness_failure` with axes:

- `monitor=incomplete`;
- `operation=complete`;
- `lifecycle=unknown`;
- `cleanup=failure` for acceptance, with exact residual zero;
- `resource=qualified`.

Release build passed in 7.72 seconds. The standard eight-process suite passed
78/78 in 333.5 seconds. Python compilation, PowerShell parsing, focused tests,
and static devlog validation passed. Phase 0 RTX and Phase 3 were omitted
because production source, USD generation, rendering, wood authority, physics,
and Flow input were unchanged; the sole Phase operation was Stage-free.

Production, defaults, Point policy, wood authority, V3, public scene, and latest
demo hashes are unchanged. A/B/C is not ready. A separate approval may create a
new Phase that normalizes the parent's lexical launch path through the same
canonical boundary as Phase 6IM, requalifies that producer-to-consumer path,
and then runs one new monitor process. Phase 6IN itself must not be retried.
