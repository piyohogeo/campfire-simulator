# Phase 6HB Candidate lifecycle isolation safe stop

Phase 6GZ and Phase 6HA remain frozen. Phase 6HB used contract SHA-256
`4DC0D578D333C8485FC3BFD06EE7AFFFDD3E1549376EDCCE3B0081276D25DD37`
and the new root `artifacts/phase6hb-candidate-lifecycle-20260815`.

## Outcome

The 28-case no-Kit fixture passed. Only condition A was launched. The operation
report proves one seven-handle readback, list/count validation, ordered release,
weak-reference residual zero, and durable `phase6hb_operation_complete` in the
bounded report. Shared lifecycle evidence proves stage close in 4.1460752
seconds, durable `shutdown_complete`, natural process exit code 0, accepted
normal-exit sample, and exact cleanup with process/NanoVDB residual zero.

The parent classification nevertheless returned `operation_failure`. Its
frozen operation gate looked for `phase6hb_operation_complete` in the resource
JSONL, while the probe called `checkpoint()` for that final event and therefore
persisted it only in `post_readback_isolation.json`. This is a Phase 6HB harness
evidence-channel mismatch, not an operation, Flow, resource, stage-close, or OS
exit failure. The frozen aggregate is not rewritten or upgraded: the first
non-normal classification stopped the ladder exactly as contracted.

| Condition | Unique addition | Operation report | Stage close | `shutdown_complete` | Natural exit | Formal result |
|---|---|---|---:|---|---|---|
| A | none; readback/release base | complete, weak residual 0 | 4.1460752 s | yes | code 0 | harness safe stop |
| B | all-slot bounded metadata | not launched | -- | -- | -- | blocked |
| C | non-temperature schema prefix | not launched | -- | -- | -- | blocked |
| D | velocity sampling without collector | not launched | -- | -- | -- | blocked |
| E | collector use | not launched | -- | -- | -- | blocked |
| F | temperature alias hold/release | not launched | -- | -- | -- | blocked |

Kit/tree peaks were 15,133,282,304 / 15,296,561,152 bytes, leaving
2,046,586,880 / 2,957,049,856 bytes below the 16/17 GiB ceilings. Runner and
diagnostic peaks were 130,080,768 / 17,084,416 bytes. Minimum available physical
memory and commit headroom were 80,184,422,400 / 99,829,948,417 bytes.

## Interpretation and continuation

There is no last-qualified ladder condition and no first Candidate-added
element under test. The next smallest work, if separately approved, is an
offline end-to-end correction that normalizes the operation-complete event from
the bounded report or writes the same event to the expected durable resource
channel before any fresh process. Phase 6HB itself must not be retried or
reclassified. Temperature conversion did not run and is not interpreted as the
failure. Production, defaults, Point policy, V3, P4, formal comparison, and
video remain unchanged/unstarted.

Release build, the focused 28/28 fixture, Python compilation, and static devlog
validation passed. The production app SHA-256 remained
`94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`
across the runtime process, latest-demo content is unchanged, and the final OS
audit found zero matching Kit/CDB/PowerShell residuals.
