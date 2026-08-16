# Phase 6IK parent lifecycle evidence boundary

## Frozen predecessor

Phase 6IJ remains frozen at `b32411c` as
`safe_stop_stage_open_contract_failure`. Its contract, Condition A attempt,
artifacts, classification, and unlaunched B/C conditions are neither reused nor
reclassified by this phase.

## Actual process boundary

The implementation audit established that the conceptual evidence order must
be adapted to the real process topology. The PowerShell case runner owns the
Kit child and must wait for it, persist `runner_evidence.json`, and return.
Only then can the outer Python resource guard receive its raw result and run
the Phase 6HR canonical evaluator. Consequently the frozen Phase 6IK order is:

1. outer guard wait start;
2. PowerShell child wait start;
3. Kit app-ready, operation complete, and shutdown complete;
4. Kit process exit and PowerShell wait completion;
5. atomic runner-evidence write start and completion;
6. PowerShell parent return;
7. outer guard result receipt;
8. canonical evaluation start and completion;
9. outer guard return.

Each row is a bounded, flushed and fsynced JSONL record containing the attempt
ID, actor PID and creation time, UTC time, actor-monotonic elapsed time, and
step ID. Stdout and stderr go directly to bounded files rather than being held
in PowerShell memory. Runner evidence uses the qualified Phase 6HU atomic
writer; the outer evaluation uses the actual Phase 6HR evidence producer and
consumer.

Phase 6IJ used 180 seconds for both the inner child shutdown monitor and the
outer resource guard. That makes an outer-guard race structurally possible if
the inner boundary consumes its full allowance. Phase 6IK does not raise that
limit; it records the intervening boundaries so a future limit proposal can be
evidence-based.

## Frozen operation scope

The sole permitted runtime is one app-ready Kit process followed immediately
by `operation_complete`, `shutdown_complete`, natural Kit exit, parent
evaluation, and exact cleanup. USD Stage creation/open/close, timeline play,
Flow, renderer updates, camera/Layer inspection, capture, NanoVDB, and the A/B/C
composition ladder are forbidden and have explicit zero call counts.

Safety remains runner/diagnostic 512 MiB, Kit 16 GiB, unique tree 17 GiB, and
physical/commit headroom floors of 8 GiB. There is one launch, no retry, and no
replacement. The contract digest is stored in
`scripts/phase6ik_parent_lifecycle_contract.sha256`.

## Pre-runtime qualification

The no-Kit producer-to-consumer fixture covers normal and delayed child exits,
non-exit, exit 1, premature wait completion, guard and evaluator boundaries,
atomic lock/replace failures, missing/duplicate/conflicting evidence,
attempt/PID/creation-time identity failures, PID reuse, outer-guard conflict,
cleanup residual, oversize, non-finite values, corrupt JSON, and the completely
consistent path. It invokes the real marker producer, Phase 6HU atomic writer,
Phase 6HR canonical evaluator/consumer, and a bounded PowerShell child-wait
process path. Kit launch count is required to remain zero.

Runtime results are intentionally recorded in a later independent commit.
