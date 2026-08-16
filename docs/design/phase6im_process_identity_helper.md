# Phase 6IM Kit-compatible process identity helper

## Frozen boundary and scope

Phase 6IL remains frozen at `3da784d` as
`safe_stop_post_shutdown_harness_failure`. Its contract, artifact root, attempt,
dump audit, classification, and post-shutdown schedule were not changed or
reused. Phase 6IM used contract SHA-256
`CCC603326EC355EE54390952D85816214DBB52DA061ECABB2DA025E306CD12ED` and
the new artifact root `artifacts/phase6im-process-identity-20260816`.

The only runtime operation was two identity captures in one Stage-free
app-ready Kit process. Stage/Layer calls, timeline play, Flow, renderer update,
readback, camera, capture, CDB attach, dump analysis, and Phase 6IL
post-shutdown sampling all remained zero. A/B/C was not started.

## Exact Windows signatures

The helper declares the Windows SDK-compatible `ctypes` signatures before any
call:

| API | Arguments | Return |
| --- | --- | --- |
| `OpenProcess` | `DWORD, BOOL, DWORD` | `HANDLE` |
| `GetProcessTimes` | `HANDLE, LPFILETIME, LPFILETIME, LPFILETIME, LPFILETIME` | `BOOL` |
| `CloseHandle` | `HANDLE` | `BOOL` |
| `GetCurrentProcess` | none | `HANDLE` |
| `GetCurrentProcessId` | none | `DWORD` |
| `GetExitCodeProcess` | `HANDLE, LPDWORD` | `BOOL` |
| `WaitForSingleObject` | `HANDLE, DWORD` | `DWORD` |
| `QueryFullProcessImageNameW` | `HANDLE, DWORD, LPWSTR, LPDWORD` | `BOOL` |

The measured x64 ABI is pointer 8 bytes, `HANDLE` 8, `DWORD`/`BOOL` 4, and
`FILETIME` 8. `OpenProcess` requests only
`PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE`. A positive bounded DWORD
PID is required. The helper verifies a live zero-time wait and `STILL_ACTIVE`,
combines FILETIME high/low components without truncation, obtains the exact
normalized executable path, and treats exit races and identity mismatches as
fail-closed. Every opened handle is closed in `finally`; close failure remains
explicit evidence.

## No-Kit qualification

The actual producer, atomic writer, bounded reader, marker reader, and validator
passed 24/24 cases with zero Kit launches. At least two real Windows processes
were exercised: the fixture process and a short-lived child. Coverage included
repeated identity stability, before/after child exit, invalid PID/zero/negative/
DWORD overflow, invalid and closed handles, forced `GetProcessTimes` and
`CloseHandle` failures, synthetic 64-bit handle preservation, FILETIME
combination, exact-path and creation-time mismatches, PID reuse, marker
missing/duplicate/conflict, corrupt/oversize JSON, and an unmodified
producer-to-consumer round trip. Focused unit tests passed 4/4.

## Sole actual Kit smoke

One fresh app-ready Kit process was launched, without retry or replacement.
Both identity calls returned:

- PID `54552`;
- FILETIME creation ticks `134313166752306621`;
- UTC epoch `1786843075.2306633`;
- executable
  `c:\packman-repo\chk\kit-kernel\110.2.0+feature.windows-x86_64.release\kit.exe`;
- 64-bit handle evidence `0x00000000000021CC` for each sequential open;
- alive wait state and exit code `STILL_ACTIVE` during capture.

The two identities matched exactly. Open/close counts were 2/2, close failures
were zero, and helper-owned handle residual was zero. Durable markers reached
`kit_app_ready`, `process_started`, `identity_helper_complete`,
`operation_complete`, and `shutdown_complete` in order. The helper axis is
`qualified`.

Kit then exited naturally with code 0 inside the 30-second shutdown grace, so
the lifecycle axis is `normal_exit`. The outer resource guard returned 2 only
because it observed auxiliary `nvngx_update.exe`/telemetry descendants after
the Kit process exit. Existing exact identity cleanup removed only observed
attempt identities and finished with residual zero. This cleanup-assisted
auxiliary result is recorded separately and does not alter the Kit natural-exit
axis or the helper evidence.

Kit/tree peaks were 7,362,031,616 and 7,847,092,224 bytes, leaving
9,817,837,568 and 10,406,518,784 bytes below the fixed 16/17 GiB limits.
Minimum physical-memory and commit headroom were 80,215,314,432 and
100,137,283,584 bytes. No fatal, native exception, dump, CDB, device loss, TDR,
or automatic upload was observed.

The final classification is `kit_process_identity_helper_qualified` with
`helper=qualified` and `lifecycle=normal_exit`.

## Regression and next boundary

Python compilation and PowerShell parsing passed, Release build passed in 7.22
seconds, and the standard eight-process suite passed 78/78 in 333.1 seconds.
Static devlog validation passed. Phase 0 RTX and Phase 3 were omitted because
production, USD generation, rendering, physics, wood authority, and Flow input
were unchanged and the smoke made no Stage or simulation call.

Production, defaults, Point policy, wood authority, V3, public scene, and
latest demo are unchanged. The qualified scope is only the pointer-sized
process identity helper. A separately approved new Phase may use it in one
fresh minimal post-shutdown monitor. Phase 6IL itself, A/B/C, Layer auditing,
Flow, and Collision comparison must not start automatically.

