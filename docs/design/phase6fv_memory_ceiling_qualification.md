# Phase 6FV — post-6FU memory-ceiling qualification

## Frozen boundary

Phase 6FT remains frozen at commit `146ded9` as an 8/9 lifecycle safe stop.
Its samples, artifact, thresholds, and decision are not reused or reclassified.
Phase 6FU qualified the stack-first diagnostic, seven-state identity model,
cleanup suppression, exact attempt-tree cleanup, and dual-source absence
confirmation at commit `13516f8`.  Phase 6FV is a new population with a new
empty artifact root.  It does not start Phase 6FO.

The authoritative pre-runtime contract is
`scripts/phase6fv_memory_ceiling_qualification_contract.json`, schema
`campfire.phase6fv.memory-ceiling-qualification-contract.v1`, SHA-256
`C917FE4463E3BCA600714A51EFEDF64E9E505F19F082647CCF5683269071AF0C`.
It pins the qualified Phase 6FU adapter and identity implementation, the frozen
legacy guard hash, shutdown policy, shared case runner, and shared probe.

## Population

The population has nine new independent processes in the predeclared balanced
order `M0/M1/M2`, `M1/M2/M0`, `M2/M0/M1`:

- M0: Phase 6FN-equivalent baseline through frame 96;
- M1: Phase 6FO-equivalent diagnostic state through frame 96;
- M2: the same diagnostic state through frame 179, immediately before the
  planned Phase 6FO readback at frame 180.

All processes use the corrected four-log fixture, S93 `allow_self_center`,
1,344/1,440 active Points, payload SHA-256
`0D3B074B7BE3E482E8702A126A11619D87F587C4848C80D4A3162A11B876C389`,
the same source sums, readback zero, capture zero, and no video.  Only a frozen
startup-prerequisite failure may consume the single replacement budget.  Any
resource, lifecycle, marker, diagnostic, identity, cleanup, or residual failure
stops the population without replacement.

## Lifecycle and diagnostic ownership

The runtime directly reuses `run_phase6fo_supply_case.ps1`; no lifecycle body is
duplicated.  The fixed diagnostic-only order is timeline stop, eight renderer
updates, retention of stage/viewport/Flow/provider/Emitter/collector
references, `close_stage_async()`, USD-context detach, four post-close updates,
ordered reference release, extension shutdown, Kit shutdown, and normal OS
exit.  Production shutdown order is unchanged.

The outer runner uses `phase6fu_resource_guard.py`, not the shared legacy guard.
Every observed identity records PID, creation time, absolute path, parent PID,
observation time, role, and attempt ID.  A normal result requires the Phase 6FU
exact-cleanup schema, no unknown or mismatch, released cleanup suppression,
cleanup marker completion, and absence confirmation from both psutil and native
Win32.  A timeout uses identity recheck, cleanup-suppression ownership,
stack-first CDB, bounded all-thread stack, independent module pass, explicit
detach, full or partial diagnostic JSON, exact matching cleanup, and dual-source
absence confirmation.  Empty stack, incomplete detach, unresolved identity, or
inconsistent summary is a qualification failure.  Full dump, upload, symbol
server wait, postmortem registration, and broad name/PID-only termination are
forbidden.

## Resource and decision contract

The old 14 GiB Kit value is a soft evaluation threshold, not a stop.  Kit 16
GiB and unique tree 17 GiB are absolute stops.  Runner and diagnostic remain
512 MiB each, physical and commit floors remain 8 GiB, and stage close remains
180 seconds.  The 16 GiB candidate requires a normal maximum no greater than
15.5 GiB, giving at least 512 MiB fixed headroom.  The corresponding tree
candidate must remain below 17 GiB.  Public field shape and logical bytes are
unavailable with readback zero and are not estimated.

Short slopes are telemetry only.  The only waveform failure is the inherited
predeclared terminal pattern: ten nondecreasing Kit samples rising at least 512
MiB without active-block growth.  Condition medians/ranges, peak recovery,
active-block relation, cache activity, GPU memory, and stage-close correlation
are recorded for interpretation.

The old 14 GiB threshold is too strict if at least two normal runs cross it or
the largest normal peak leaves less than 256 MiB below it.  Kit 16 GiB and tree
17 GiB qualify only with 9/9 representative normal exits, all separated
resource gates and floors, no unexplained persistent accumulation, complete
lifecycle markers, Phase 6FU identity/cleanup evidence, and zero residual.
Success only establishes that a later explicitly approved Phase 6FO may start
from another new root; Phase 6FV itself performs no readback, supply comparison,
video, P4, production change, or production adoption.

Runtime results are appended only after the contract, implementation, focused
tests, and Release build are committed and pass.
