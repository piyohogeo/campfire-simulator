# Phase 6IL post-shutdown exit boundary

## Scope and frozen history

Phase 6IK remains frozen at commit `60d2b54` as
`safe_stop_parent_lifecycle_boundary_localized`. Phase 6IL did not rerun its
attempt, reuse its runtime sample, change its 180-second limit, or start the
A/B/C composition ladder. The new contract was limited to the process boundary
after `shutdown_complete` and used a fresh artifact root:
`artifacts/phase6il-post-shutdown-exit-20260816`.

The Phase 6IL contract SHA-256 is
`FBEA44FE97E1B0E60030309EC53C661B984A94768AF5F9268C1CDB5B6DF438D4`.
Its fixed post-shutdown samples are 0, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60,
120, and 175 seconds. The contract distinguishes the PowerShell process
object, OS enumeration, native process-handle wait/exit code, and the exact
PID/creation-time/path/parent process tree. CDB is bounded to one attempt at 60
seconds only while the exact Kit identity remains alive.

## Frozen Phase 6IK dump audit

The original Phase 6IK crash bundle was copied to the new read-only audit
directory before inspection. Original and copied sizes and SHA-256 values
match, and the original files had identical hashes before and after the audit.
Network symbols and automatic upload were disabled.

Confirmed facts from the user minidump are:

- exception `0xC0000005`, write access to `00000200656e6f4e`;
- exception address `omni_usd!omni::usd::UsdContext::addHydraEngine+0x288`;
- recorded crash time about 4.938714 seconds after the frozen
  `shutdown_complete` marker;
- the dump contains registers, stacks, and partial memory, not full memory;
- the bounded local-symbol CDB transcript is 301,682 bytes and no upload was
  performed.

This localizes the recorded exception but does not prove the root cause,
ownership race, or relationship to the parent wait. Most modules had only
deferred or export-level symbols. The audit therefore does not reclassify
Phase 6IK.

## No-Kit producer-to-consumer qualification

The first provisional fixture output is retained as failed evidence. After
correcting the pre-runtime validator, the formal no-Kit preflight used the
actual producer, PowerShell/native monitor, atomic writer, bounded reader, and
validator and passed 33/33 cases. Eight cases launched real fixture child
processes; Kit launch count was zero. Coverage included immediate and delayed
exit 0, non-exit, exit 1, an access-violation-equivalent exit status,
crash-reporter child exit/residual, growing dump, PID reuse, stale process
objects, unknown children, identity mismatch, malformed/oversize/nonfinite
artifacts, resource and cleanup failure, and final evidence consistency.

## Sole actual Kit attempt

Exactly one new minimal app-ready Kit process was launched, with no retry or
replacement. No Stage, Layer, timeline, renderer, Flow, camera, readback, or
A/B/C operation was requested.

The child failed before its first durable `process_started` marker. The new
process-creation-time helper called Windows `GetProcessTimes` through `ctypes`
without a Kit-compatible argument declaration, producing:

`ArgumentError: argument 1: OverflowError: int too long to convert`

The parent later persisted `child_wait_started`, then its evidence-write start
and completion, and `parent_return`. It classified the attempt as
`safe_stop_post_shutdown_harness_failure`; the operation report and fixed
post-shutdown samples are absent. This result does not evaluate whether Kit
naturally exits after `shutdown_complete`.

Resource gates passed: Kit/tree peaks were 7,313,997,824 and 7,446,261,760
bytes, leaving 9,865,871,360 and 10,807,349,248 bytes below the 16/17 GiB
limits. Minimum available physical memory was 79,744,315,392 bytes and minimum
commit headroom was 99,737,870,336 bytes. Exact cleanup passed with residual
zero; no new dump, fatal, CDB invocation, device-loss evidence, or automatic
upload was recorded.

## Verification and continuation boundary

Focused tests passed 4/4, the formal no-Kit fixture passed 33/33, Python and
PowerShell parsing passed, Release build passed, and the standard eight-process
suite passed 78/78. Phase 0 RTX and Phase 3 were omitted because production,
USD generation, rendering, physics, wood authority, and Flow inputs are
unchanged and the sole Kit attempt stopped before its first operation marker.

Production application, defaults, canonical Point-policy sources, wood
authority, V3, public scene, and latest-demo hashes are unchanged.

A separately approved new Phase must first qualify a Kit-compatible exact
process-identity marker helper in an app-ready smoke. Only then may one fresh
minimal post-shutdown monitor be attempted. The A/B/C ladder, Layer audit, Flow,
and Collision comparison remain blocked and must not start automatically.

