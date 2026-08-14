# Phase 6FZ deterministic import and three-axis memory qualification

## Frozen history and scope

Phase 6FY remains the formal operation-harness safe stop at commit `aa02635`:
its twenty fixtures passed, but attempt01 stopped immediately after Kit app-ready
because the `--exec` wrapper used a bare import and the scripts directory was not
in Kit's module search path. It contributed zero memory-valid samples. Phase 6FZ
does not overwrite that root, reuse that sample, or reinterpret the failure as a
Flow, memory, or lifecycle result.

Phase 6FZ changes only diagnostic and harness code. The production app, S93/S100
physics, 1,344/1,440 Point payload, Flow settings, corrected four-log geometry,
V3, release-after-close order, and all resource ceilings remain unchanged.

## Deterministic Kit import boundary

The executing wrapper resolves its own directory, adds that single absolute
directory to the current diagnostic Kit process' `sys.path`, and uses an
`importlib` file spec for the exact sibling
`scripts/probe_phase6fo_supply_comparison.py`. The loader rejects a missing file,
an origin different from the expected file, or missing `_run` and
`_append_resource_marker` entry points. It writes the pre/post `sys.path`, target,
expected path, resolved `__file__`, wrapper path, working directory, and entry
points to a bounded, fsync'd JSON artifact. It does not edit persistent Python
configuration or the production application search path.

Before any formal process, three app-ready `kit.exe --exec` smoke fixtures must
pass: the correct module, a missing module, and a decoy at the wrong path. The
negative cases are successful only when they fail closed for their declared
reason. A unit-Python import alone is not sufficient.

## CDB progress-aware timeout contract

The timeout values are frozen before runtime from the Phase 6FY observation that
the stack log was still growing when the previous fixed 30-second cutoff fired:

- no-progress timeout: 20 seconds;
- all-thread stack absolute timeout: 80 seconds;
- auxiliary module pass absolute timeout: 30 seconds;
- explicit detach absolute timeout: 10 seconds;
- worst-case aggregate bound: 120 seconds.

Progress means a change in stdout/stderr or an explicitly monitored diagnostic
artifact's length or modification time. Process liveness alone is not progress.
The absolute bound never extends. Each pass streams to bounded files and records
`no_progress` versus `absolute`, output changes, peak Private Bytes, and process
absence. Stack evidence is separately classified `complete`, `partial`, or
`none`; module evidence is independent. Partial files are retained, timeout is
never success, and explicit detach plus exact cleanup remain mandatory. The local
symbol cache remains Git-ignored; Microsoft symbol server waits, full dumps,
automatic upload, and system-wide debugger registration remain disabled.

Pre-runtime fixtures cover continued progress, silence, absolute cutoff despite
progress, preserved partial stack text, descendant cleanup, a real bounded CDB
stack capture, and an injected detach timeout. All must finish with no CDB child.

## Formal population

Only after the import, CDB, cleanup, and existing twenty policy fixtures pass may
the new empty Phase 6FZ root launch process 1. The frozen balanced order and all
nine basic conditions are identical to Phase 6FY: M0/M1/M2, three runs each,
readback zero, capture zero. The Phase 6FU guard, Phase 6FW PID-reuse policy,
durable pre-close commit, memory-valid/lifecycle/diagnostic-cleanup axes, limited
stage-close-timeout replacement, Kit 16 GiB, unique tree 17 GiB, runner 512 MiB,
diagnostic 512 MiB, and 8 GiB physical/commit floors are unchanged.

Every formal process must also prove that its shared probe resolved to the exact
expected file. Operation, resource, artifact, identity, or cleanup failure is not
replaceable. Stage-close timeout remains lifecycle failure evidence separate from
an already committed valid memory sample under the frozen policy.

Phase 6FZ does not start Phase 6FO. Only a completed population may determine
whether 16/17 GiB is qualified and whether a separately approved fresh Phase 6FO
root may be started.

