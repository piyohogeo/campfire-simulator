# Phase 6IO canonical Kit path and minimal post-shutdown monitor

Phase 6IN remains frozen at `3c323b6` as
`safe_stop_post_shutdown_monitor_harness_failure`. Its root, process, report,
and classification were not reused. Phase 6IO used contract SHA-256
`7AB85991A84F6815D2A9F19437F0E90FF6FBDD6449CF84421D57D08DB0B97C94`
and fresh preflight/runtime roots.

## Canonical path boundary

The Phase 6IM module and hash remain unchanged. It is still the only authority
for the running process PID, creation FILETIME, and executable path. Phase 6IO
adds a file-identity comparison for the parent's predeclared launch path:

1. validate and normalize the lexical build path;
2. open both the lexical path and the Phase 6IM process path with `CreateFileW`;
3. obtain the final DOS path with `GetFinalPathNameByHandleW`;
4. obtain volume serial and 64-bit file index with
   `GetFileInformationByHandle`;
5. compare final path, volume serial, file index, file size, and SHA-256; and
6. close both pointer-sized handles and require zero helper residual.

This is not a Packman string substitution. The contract binds the allowed
lexical path and current file identity, so another junction, broken link,
same-name file, or Packman version fails closed. Case, separators, and the
valid `\\?\` prefix normalize before the same handle boundary.

The actual no-Kit producer, atomic writer, bounded reader, and validator passed
26/26. The build junction and direct Packman target resolved to
`c:\packman-repo\chk\kit-kernel\110.2.0+feature.windows-x86_64.release\kit.exe`,
volume serial `1261293552`, file index `1688849864660117`, size `752224`, and
SHA-256 `5FE8AD14C77328DBE4A11361D1FDB45F8581D2595E7607AFAB0221379D4650EF`.
The API opened and closed 2/2 handles with zero residual.

## One-process monitor result

One fresh Stage-free and Flow-free Kit process was launched: PID `9100`,
creation FILETIME `134313194397193539`. PID, creation time, and canonical file
identity matched, so the monitor started. The child had already persisted
`operation_complete` and `shutdown_complete`.

| scheduled seconds | observed seconds | state | Private Bytes | CPU delta |
|---:|---:|---|---:|---:|
| 0 | 0.0045 | alive | 3,764,785,152 | 3.21875 s |
| 0.25 | 0.2796 | alive | 3,773,194,240 | 0.21875 s |
| 0.5 | 0.5118 | alive | 3,803,885,568 | 0.234375 s |
| 1 | 1.0093 | alive | 3,850,903,552 | 0.3125 s |
| 2 | 2.0185 | alive | 3,908,726,784 | 0.96875 s |
| 5 | 5.0269 | alive | 5,190,729,728 | 24.125 s |
| 10 | 9.8968 | exited | n/a | n/a |

The exact process exited with unsigned code `2147483651` (`0x80000003`). Kit's
log recorded its crash boundary and the attempt-local dump directory contained
four bounded crash-report files by the terminal sample, including one
1,631,923-byte dump archive. No crash-reporter child was observed, no CDB was
started, and no automatic-upload line was found. Dumps were preserved but not
opened or analyzed in this Phase.

The monitor, operation, path identity, resource, and evidence boundaries are
qualified. Lifecycle is independently `post_shutdown_exception`, not a natural
production exit. Phase 6IK recorded `0xC0000005`; Phase 6IO recorded
`0x80000003`, so the exit codes do not match. A single process cannot determine
whether the two post-shutdown events share an underlying mechanism.

Kit/tree peaks were 6,009,487,360 and 6,158,381,056 bytes, leaving
11,170,381,824 and 12,095,229,952 bytes below the fixed limits. No cleanup
termination was needed; all observed identities were already absent and final
Kit/CDB/helper residual was zero.

## Boundary held

A/B/C is not restart-ready because natural exit 0 was not established. No
Stage, Layer, Flow, renderer update, readback, camera, capture, CDB, or dump
analysis ran. Production, defaults, Point policy, wood authority, V3, public
scene, and latest demo hashes remained unchanged. A separately approved next
Phase must decide whether to repeat a minimal post-shutdown observation or to
address the observed post-shutdown exception before A/B/C; neither starts
automatically.

Release build passed in 6.86 seconds. Focused path tests passed 26/26, the
Phase 6IO unit tests passed 2/2, inherited monitor tests passed 3/3, Python and
PowerShell parsing passed, the standard suite passed 78/78 across eight
processes in 292.6 seconds, and static devlog validation passed. Phase 0 RTX
and Phase 3 were omitted because no production source, USD authoring, renderer,
wood-authority, Flow input, or physical parameter changed.
