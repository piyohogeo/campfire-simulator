# Phase 6FY three-axis memory qualification

Status before runtime: frozen contract. Phase 6FT, 6FV, and 6FX remain
historical safe stops. Their artifacts, classifications, and memory samples are
read-only design input and are not reused in the Phase 6FY formal population.
Phase 6FO remains stopped.

## Why this contract is different

Phase 6FX completed the physical operation and memory observation for attempt
06 before `close_stage_async()` timed out. The former 9/9-normal-exit contract
combined three questions and discarded otherwise complete resource evidence.
Phase 6FY therefore records three independent axes:

1. whether the condition operation and bounded memory measurement completed;
2. whether stage close, extension shutdown, and normal OS exit completed;
3. whether bounded CDB degradation, exact cleanup, and final identity
   classification were safe.

`memory_valid_lifecycle_timeout` is explicitly a lifecycle failure. It is not a
normal exit or production lifecycle evidence. Its pre-close Kit/tree peak stays
in the formal memory distribution, while its stage-close duration is a
right-censored timeout at 180 seconds. No timeout artifact is deleted or
replaced. A replacement is a separate attempt used only to obtain an additional
normal-exit sample for the same condition.

## Durable pre-close boundary

The unchanged Phase 6FO physical probe still authors the fixture, drives Flow,
samples frames, and implements `release-after-close`. A Phase 6FY wrapper only
pauses at its existing `measurement_complete` marker. A bounded 128 MiB helper
streams the current raw report, resource JSONL, marker JSONL, metadata, contract,
and optional GPU CSV into an atomic measurement directory, flushes and fsyncs
them, records SHA-256 values, and then acknowledges the probe. Stage close is
not allowed to begin until that acknowledgement exists. Missing files, a hash
mismatch, insufficient resource roles, or a commit after
`stage_close_request_before` makes the memory sample invalid.

The shared physical probe and its release-after-close lifecycle are not copied
or modified. The Phase 6FY synchronization wrapper calls the existing probe's
`_run()` and intercepts only the existing measurement marker. Production and
the production shutdown order are unchanged.

## Frozen classes and replacement policy

The formal classes are:

- `memory_valid_lifecycle_normal`;
- `memory_valid_lifecycle_timeout`;
- `memory_invalid_operation_failure`;
- `memory_invalid_resource_failure`;
- `memory_invalid_diagnostic_cleanup_failure`;
- `memory_invalid_identity_failure`;
- `memory_invalid_lifecycle_failure` for a lifecycle outcome outside the two
  explicitly supported completed-measurement cases.

Only a completely classified `memory_valid_lifecycle_timeout` may create one
replacement slot. There are at most two replacement launches and eleven total
launches. The original remains in the memory and lifecycle summaries. A second
timeout for the same M0/M1/M2 condition, an invalid origin, an overwritten
attempt ID, resource/operation/artifact/identity/cleanup failure, or exceeding
either limit stops the population.

The CDB axis accepts a bounded complete diagnostic or a declared partial stack,
module, or pre-attach outcome only when its artifact is committed, all CDB
children are absent, detach succeeded or attach was proven not to have happened,
Phase 6FU exact cleanup completed, and Phase 6FW reports no residual or unknown.
Detach failure, unknown attach state, missing diagnostic artifact, CDB residual,
or cleanup conflict invalidates the sample and stops the population. Known NGX
still requires every established stack token.

## Fixture gate

Twenty pre-runtime fixtures cover normal and timeout measurements, timeout
before measurement or artifact commit, resource violation, complete/partial
CDB, residual CDB, detach and cleanup failure, unknown identity, protected PID
reuse, attempt residual, allowed replacement, second same-condition timeout,
launch-limit excess, attempted timeout exclusion or overwrite, prohibited
resource replacement, and a timeout holding the population's largest peak.
They include short-lived process cleanup evidence. All twenty must pass before
Kit starts.

## Runtime population and limits

The fresh basic population remains M0 frame 96, M1 frame 96, and M2 frame 179,
each three times in the balanced order `M0/M1/M2`, `M1/M2/M0`,
`M2/M0/M1`. Readback, capture, video, and Phase 6FO are zero. Phase 6FU guard,
Phase 6FW PID reuse policy, stack-first CDB, exact cleanup, and the
`release-after-close` diagnostic sequence remain in force.

Absolute limits remain Kit 16 GiB, unique tree 17 GiB, runner and diagnostic
512 MiB each, physical and commit headroom floors 8 GiB, and stage close 180
seconds. Qualification uses every `memory_valid_*` peak and requires at least
three samples per condition and nine total, maximum Kit peak at or below 15.5
GiB, at least 512 MiB to 16 GiB, all tree peaks below 17 GiB, no persistent
unexplained accumulation, operation/measurement integrity, 100% exact cleanup,
and zero owned residual, unknown, or mismatch stop.

Old 14 GiB is retired only if at least two memory-valid samples cross it or the
largest leaves less than 256 MiB. Even if memory qualifies, the native
stage-close issue remains unresolved. A later monitored Phase 6FO restart can
only be reported ready when there are at most two post-measurement timeouts, no
condition times out twice, each timeout has bounded diagnostic evidence, all
replacement limits are respected, and every cleanup/identity gate passes.
Phase 6FY itself never starts Phase 6FO.

## Runtime safe stop

The frozen contract SHA-256 was
`2FF8A1A6FC8BB5C453E4DEC5A29A148CB17EE17FC02A5A9892BD12D3919D997C`.
All twenty pre-runtime fixtures passed.  The fresh formal root was
`artifacts/phase6fy-three-axis-memory-1`, but its first basic slot
(`attempt01`, M0) failed before the physical probe entered its operation.

The confirmed boundary is the Kit `--exec` import at app-ready.  Kit logged
`ModuleNotFoundError: No module named 'probe_phase6fo_supply_comparison'` at
line 17 of `probe_phase6fy_three_axis_memory.py`.  Only the extension-startup
marker exists; `process_entry`, startup, fixed-frame, active-block,
`measurement_complete`, pre-close commit, and stage-close markers do not.
The external committer consequently ended with
`parent_stopped_before_measurement_commit`.  This is a Phase 6FY harness/module
search-path defect, not evidence of Flow operation, memory boundedness, or a
stage-close failure.

The outer 540-second absolute guard then initiated the bounded shutdown
diagnostic.  Its stack-first CDB child attached and wrote partial native frames
but timed out before the completion token; the module pass completed and
explicit detach/exact cleanup succeeded.  The diagnostic class is
`diagnostic_partial_stack_timeout`, not known NGX.  Phase 6FW classified 45
attempt identities absent, zero owned residual, zero unknown identity, and
zero mismatch stop.  Fatal, dump, upload, device-lost, and TDR counts were
zero.

Although the full resource trace observed a Kit peak of 9,535,336,448 bytes
and a unique-tree peak of 9,765,523,456 bytes, the pre-close artifact was never
committed and none of the operation gates passed.  The sample is therefore
`memory_invalid_operation_failure` and is excluded from the formal memory
distribution.  The population is 0 memory-valid / 1 memory-invalid; attempts
02 onward were not launched and no replacement was permitted.  Neither the
old 14 GiB decision nor the 16/17 GiB candidates can be qualified from this
root.

Phase 6FT, 6FV, and 6FX remain frozen.  Phase 6FO remains blocked.  A future
attempt must use a new phase/contract/root, explicitly make the shared probe
importable under Kit `--exec`, and add an app-ready import smoke fixture before
launching a formal population.  Phase 6FY is not retried or reclassified.

Post-stop verification passed the Release build in 7.20 seconds, Phase 0 RTX,
Phase 3 with zero dry/wet mass-balance error and wood-owned Flow input,
32/32 focused Phase 6F contracts, and the standard eight-process 78/78 suite
in 328.4 seconds.  Devlog validation found 821 references, 281 unique IDs, 233
JSON, 177 SVG, and 2 ZIP files with no missing reference or duplicate ID.
Production app SHA-256 and the latest-demo manifest remain unchanged.
