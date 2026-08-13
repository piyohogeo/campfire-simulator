# Phase 6FR stack-first CDB and stage-close order qualification

Phase 6FQ is frozen at commit `778623c`. Its first six readback-free conditions exited normally; attempt 07 then reached `stage_close_timeout` after 180.023808 seconds in the ordinary capture-none, eight-drain, release-before-close control. The Kit and tree memory limits were not exceeded, no fatal/dump/upload occurred, and exact cleanup left zero residual processes. The CDB module pass timed out before the all-thread pass, so module, owner, and wait boundary were not established. None of that evidence is reclassified here, and Phase 6FO remains stopped.

## Pre-runtime contract

The frozen machine-readable contract is `scripts/phase6fr_stage_close_native_lifecycle_contract.json`. Its SHA-256 sidecar is authoritative. Phase 6FR changes only diagnostic and probe shutdown ordering; production, S93/S100 physics, Point payload, Flow, CollisionProxy, V3, physical thresholds, and the existing 14/16 GiB safety limits do not change.

The CDB path is now:

1. verify PID, creation time, and absolute executable path;
2. capture `~* kPn 16` first with a local-only symbol cache and bounded direct-to-file output;
3. attempt `lm` in a separate auxiliary CDB process;
4. perform an independent explicit `qd` attach/detach pass;
5. verify every CDB child is absent.

Module enumeration is not a prerequisite for an already complete native stack. A module timeout therefore produces explicit partial module evidence while preserving the stack. Empty/partial stacks remain non-qualifying, and the known NGX classification still requires all five accepted stack tokens. Microsoft symbol-server waits, postmortem debugger registration, full dumps, and automatic upload are excluded.

The stoppable fixture must pass before Kit starts. It covers a waiting target, module timeout after a complete stack, forced stack timeout and cleanup, a locked-log end-to-end diagnostic, and a target that exits before attach. It requires bounded files and memory, target survival after non-invasive detach, exact fixture cleanup, and zero CDB remainder.

## Minimal Kit comparison

Only two readback-free/capture-free conditions are allowed, in the frozen order `A B / B A / A B`:

- A: timeline stop → eight renderer updates → release owned Flow/provider/collector/viewport references → `close_stage_async()`.
- B: timeline stop → eight renderer updates → retain references → `close_stage_async()` → USD detach → four post-close updates → release the same references.

Each condition has at most three successful independent runs. Startup-prerequisite failure alone may consume the one frozen replacement; a stage-close timeout, ceiling violation, fatal/dump/device-lost/TDR, diagnostic or cleanup failure, residual process, or marker/order defect stops the population without retry. The phase records memory but does not qualify 14 or 16 GiB.

Three normal B runs with an A timeout make release-after-close only a candidate for a separate qualification. Timeouts in both conditions reject reference order as the sufficient explanation. Three normal runs for both conditions do not prove an order; they classify the failure as low-frequency/nondeterministic and retain the stack-first path for natural recurrence. Phase 6FO is not restarted in this phase.
