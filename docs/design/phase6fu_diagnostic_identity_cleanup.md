# Phase 6FU — hang diagnostic identity and cleanup qualification

## Scope

Phase 6FT remains frozen at commit `146ded9`: eight of nine processes exited normally and attempt09 stopped at a 180.021-second stage-close timeout. Its eight normal samples are partial distribution evidence only. Phase 6FU does not restart Phase 6FO, the nine-process memory population, or an actual Kit hang. It changes diagnostic, identity, and cleanup code only.

The frozen Phase 6FU contract is `campfire.phase6fu.diagnostic-cleanup-contract.v1`. Its SHA-256 sidecar is checked before fixtures run. Production code, Flow, the S93/S100 physical comparison, Point payload, CollisionProxy, V3, thresholds, defaults, video, and P4 are outside this phase.

## Phase 6FT attempt09 audit

Confirmed evidence:

- Kit committed `stage_close_timeout` and `raw.json`; no later stage-close, USD-detach, reference-release, extension-shutdown, or OS-exit marker exists.
- No `sensitive-shutdown-diagnostics` result or marker file was committed.
- The outer resource guard later reported Kit alive before cleanup, `killed_pids=[]`, and `all_observed_absent=true`.
- Direct OS enumeration after that summary found the exact recorded runner, Kit, GPU helper, telemetry child, and console children alive. Exact manual cleanup produced zero residual.
- The guard used a two-valued helper: every `AccessDenied`, `NoSuchProcess`, zombie, or `OSError` became `None`; `None` was then treated exactly like absence. `psutil.wait_procs()` and another call to that helper could therefore produce an absence summary without preserving why a query failed.
- The outer guard had no diagnostic-ownership/suppression contract. It could finalize cleanup independently from the runner's bounded diagnostic path.

The narrowest confirmed implementation boundary is therefore between the last stage-close marker and diagnostic launch, followed by ambiguous guard identity queries during cleanup. The exact native reason why the runner failed to commit a diagnostic is not recoverable from the frozen artifact; CDB was either not launched or its output was lost before the first durable diagnostic marker. No stack or module inference is made.

## New state machine

Process state is no longer a boolean. Both PowerShell and the Python guard use:

- `alive_identity_match`
- `alive_identity_mismatch`
- `confirmed_exited`
- `query_failed_unknown`
- `access_denied_unknown`
- `creation_time_unavailable_unknown`
- `path_unavailable_unknown`

An identity stores PID, creation time, absolute executable path, parent PID, observation time, role, and root attempt ID. Cleanup authority belongs only to the exact identities observed for that attempt. Parentage is retained as evidence; an already observed child is not broadened to unrelated same-name processes after reparenting.

Absence requires agreement from two independent paths: psutil/Get-Process and native Win32/CIM. One exact live match proves the process is not absent. A mismatch protects the process from termination. An unknown state triggers bounded re-query and cannot become `confirmed_exited`.

The timeout path is fixed as: identity recheck, cleanup-suppression ownership, stack-first CDB, bounded stack/modules/detach, diagnostic or partial JSON commit, ownership release, attempt-identity re-enumeration, exact stops, dual-source absence confirmation, then cleanup summary. CDB output remains direct-to-file and bounded; no full dump, symbol-server wait, automatic upload, or machine-wide debugger registration is introduced.

## Qualification gate

The dedicated fixtures cover normal exit, attachable target, target survival through stack capture, stack timeout, module timeout, target exit before attach, transient query failure, identity mismatch, parent-exit/child-survival, auxiliary child, diagnostic/cleanup race, and summary-after-cleanup ordering. Runner and diagnostic child each retain a 512 MiB limit. Failure prevents all real-Kit population work.

Runtime results are appended only after the frozen fixtures complete.
