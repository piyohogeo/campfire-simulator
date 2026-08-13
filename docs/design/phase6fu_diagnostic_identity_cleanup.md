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

## Qualification result

The final implementation was qualified in the new, Git-ignored root
`artifacts/phase6fu-diagnostic-cleanup-4`.  Root 1 is preserved as the
pre-policy-import harness failure, root 2 exercised the first implementation,
and root 3 is preserved as an adapter-report schema failure.  None was
overwritten or promoted.  Root 4 is authoritative for the final adapter.

- Contract SHA-256:
  `745522077F7481C41A121EC732188FF6BDF0706FB2CE3313AD7288E4B6328132`.
- Stack-first CDB completed a non-empty all-thread native stack, an independent
  module pass, and explicit detach while leaving the target alive.  A forced
  module timeout retained the already complete stack and still detached.  A
  forced stack timeout was classified as incomplete evidence and still
  detached and cleaned up.  Locked-log and target-exited-before-attach cases
  also completed their bounded reports.
- The seven identity/cleanup fixture groups passed: normal exit, transient
  query failure, identity mismatch protection, parent exit with a live child,
  diagnostic/cleanup race, suppression deadline, and unknown-not-absent.
- The real outer-guard adapter observed four attempt identities.  Its root had
  already exited, so exact cleanup stopped only the two still-matching fixture
  identities; no mismatch or unknown identity was stopped.  psutil and native
  Win32 both confirmed all four exited before the summary was committed.
- Cleanup suppression was observed and released before exact cleanup.  Final
  CDB/fixture residual count was zero.  Peak runner Private Bytes was
  9,482,240 bytes and peak guarded diagnostic Private Bytes was 94,515,200
  bytes, both below 512 MiB.
- No Kit population, Phase 6FO condition, memory nine-process population,
  full dump, automatic upload, production change, or ceiling change occurred.

The shared `phase6eg_resource_guard.py` was restored byte-for-byte to its
frozen SHA-256
`A16FA82606A4265093E88816540A0E293205AADC9A15FA11B7CA09C6B32CC45E`.
Phase 6FU behavior is isolated in `phase6fu_resource_guard.py`, so Phase 6FM,
6FN, and other historical runtime-hash contracts remain valid.

## Decision

The diagnostic/identity/cleanup boundary is qualified for a future explicitly
authorized memory-ceiling population.  This does not qualify 16/17 GiB, does
not repair or reclassify Phase 6FT attempt09, and does not authorize Phase 6FO.
The next population must use a new artifact root and explicit user approval.
If a real timeout occurs, unknown identity evidence remains fail-closed and a
missing/partial CDB result remains a lifecycle diagnostic failure rather than a
known NGX classification.

Final regression passed the Release build in 6.30 seconds, Phase 0 RTX, and
Phase 3.  Phase 3 retained dry/wet mass-balance error zero, authority SHA-256
`0dec57f324fadbdb0c7f5908ac16fe9437d81726cfec047fda5c88f52e84be10`
and `148585f8ea43ddda826db198be6a6c03c151ce2c857009e171a9c93cfd2b20c9`,
wood-owned Flow input, active blocks final/peak 260/332, and peak fuel 1.0.
Focused Phase 6F contracts passed 168/168, the dedicated Phase 6FU/6FR/6EA
set passed 28/28, and the standard eight-process suite passed 78/78 in 294.3
seconds.  Static devlog validation passed 461 references, 277 IDs, 229 JSON,
177 SVG, and two ZIP files.  Production app SHA-256 remained
`94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`.
