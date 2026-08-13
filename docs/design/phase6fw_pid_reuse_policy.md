# Phase 6FW PID reuse identity policy

## Scope and frozen history

Phase 6FV remains the frozen `445a1da` safe stop. Its third process completed
the Flow operation, stage close, shutdown, and OS exit, but the frozen analyzer
rejected one protected identity mismatch. Phase 6FW does not rewrite that
report, continue attempts 04–09, start Phase 6FO, or change production.

The Phase 6FU seven-state query and exact-cleanup implementation remains
byte-for-byte outside this change. Phase 6FW is a post-cleanup policy layer: it
can call a sufficiently proven reuse `protected_pid_reuse_non_residual`, but it
does not create stop authority over the process currently using the PID.

The frozen contract is
`scripts/phase6fw_pid_reuse_policy_contract.json`, schema
`campfire.phase6fw.pid-reuse-policy-contract.v1`, SHA-256
`4DA8B0C71F7AAF0A9BA437D0D7712674C87F80AF982F413148E317C4EF4CDBA0`.

## Confirmed Phase 6FV evidence

The recorded attempt identity was PID 43676, creation time
`1786657112.7231607` UTC Unix epoch seconds, and absolute path
`C:\Windows\System32\conhost.exe`. At final cleanup, psutil reported that the
same PID referred to creation time `1786657296.362193` and
`C:\Windows\System32\wbem\WmiPrvSE.exe`; native Win32 returned access denied.
The creation-time separation was about 183.639 seconds and the executable
basename differed. No stop request targeted PID 43676. Matching residual,
final unknown, and killed PID counts were zero; suppression was released; the
other attempt identities were confirmed absent. This is read-only evidence,
not a retrospective Phase 6FV pass.

## Identity comparison contract

Creation timestamps use UTC Unix epoch seconds. A finite absolute difference
greater than 1.0 second is a clear mismatch; a difference at or below 1.0
second is treated as the same creation-time component. This matches the Phase
6FU query tolerance and absorbs floating representation and independent query
rounding. Wall-clock order is not used to prove absence.

Paths must be absolute. Comparison removes only documented Windows namespace
prefixes, normalizes separators, dot components, and case, and resolves an
existing path when possible. Lexically different paths with the same basename
are ambiguous unless both can be resolved. This prevents 8.3 names,
symlink/junction aliases, namespace prefixes, or System32 redirection from
creating false reuse evidence. Different executable basenames are never
collapsed.

A reuse is accepted only when at least one trusted psutil or Win32 query gives
a complete current PID/creation-time/path identity, that identity clearly
differs from the attempt identity, no trusted query matches the attempt, and
complete sources do not conflict. One complete psutil mismatch plus a Win32
access-denied result is acceptable; access denied alone is not.

## Final policy layer

- exact match: attempt-owned residual and failure;
- sufficiently proven mismatch, with original identity displaced and all other
  cleanup evidence complete: protected PID reuse and non-residual;
- insufficient or conflicting mismatch: unresolved identity failure;
- confirmed exit: attempt identity absent;
- unknown: bounded Phase 6FU retry, then unresolved failure.

The protected classification additionally requires no stop request for the
new identity, no matching or unknown final identity, no rediscovery after the
summary, dual-source cleanup evidence, ordered suppression/start/complete
markers, released suppression, and zero final attempt-owned residual. A
mismatched process remains protected from termination in every case.

## Qualification boundary

Fifteen named cases run as separate, bounded child processes. They cover clear
time/path reuse, same-time/different-path, same-path/different-time, exact
identity, missing components, psutil plus native access denied, conflicting
sources, a live original identity, mixed clean children, forbidden mismatch
stop, post-summary rediscovery, ordinary exit, and parent exit followed by
child PID reuse. The Phase 6FV attempt03 evidence is also copied by hash into a
new offline comparison artifact. The original artifact is read-only.

Each child has a 10-second timeout and 512 MiB Private Bytes limit. The runner
also remains below 512 MiB. No CDB, Kit, dump, upload, Phase 6FO, or memory
population is invoked. Qualification requires every fixture and the offline
comparison to match the frozen expectation, with zero fixture/helper residual.

If qualified, the only next-step claim is that a separately authorized,
fresh-root nine-process memory-ceiling qualification may combine the unchanged
Phase 6FU cleanup with this final reuse policy. It would still use the
diagnostic-only release-after-close order, provisional 16/17 GiB stops, and
stack-first CDB. It is not started by Phase 6FW.
