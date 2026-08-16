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

## Fresh runtime result

The producer-to-consumer preflight qualified 25/25 with zero Kit launches.
The one permitted fresh minimal Kit launch then produced this durable sequence
(UTC):

| Boundary | UTC | Actor elapsed |
|---|---:|---:|
| outer guard wait start | 00:17:49.285 | 0.000 s |
| child wait start | 00:17:49.821 | 0.116 s |
| Kit app-ready | 00:17:55.041 | 0.000 s |
| operation complete | 00:17:55.052 | 0.016 s |
| shutdown complete | 00:17:55.061 | 0.016 s |
| outer guard result received | 00:20:49.533 | 180.234 s |
| canonical evaluation started | 00:20:49.535 | 180.250 s |

`child_process_exit`, `child_wait_completed`, both runner-evidence write
markers, and `parent_return` were absent. The outer guard therefore fired
before PowerShell returned. It then confirmed exact cleanup with residual zero.
Canonical evaluation started but correctly failed closed because the absent
PowerShell completion also meant `runner_evidence.json` did not exist.

The Kit crash reporter emitted one 1,906,509-byte dump ZIP plus three bounded
support files after the shutdown marker; no automatic upload was observed.
This Phase does not inspect or attribute the dump. It establishes only that a
natural child exit and parent wait completion were not evidenced before the
fixed outer boundary. The first incomplete boundary is `child_process_exit`,
so the result is `safe_stop_parent_lifecycle_boundary_localized`; it is not a
Stage, Layer composition, Flow, or CollisionProxy result.

Kit and unique-tree peaks were 6,206,468,096 and 6,350,667,776 bytes, leaving
10,973,401,088 and 11,902,943,232 bytes to their 16/17 GiB limits. Runner and
diagnostic peaks were 98,283,520 and 16,863,232 bytes. Minimum available
physical memory and commit headroom were 81,556,672,512 and 101,564,051,456
bytes. Production, defaults, Point policy, V3, public scenes, and latest demo
hashes were unchanged.

Dedicated Phase 0 RTX and Phase 3 were omitted because this lifecycle-only
change did not modify production code, USD generation, rendering, wood
authority, or Flow input, and the formal probe was contractually forbidden
from creating a Stage. The Release build, focused Phase 6IK tests, standard
eight-process 78/78 suite, Python compilation, and static devlog validation
passed.

The next approval boundary is a separately contracted minimal test of the
post-shutdown child-exit/poll behavior. The 180-second limit was not changed,
and neither the A/B/C ladder nor the four-boundary Layer audit may resume from
this result automatically.
