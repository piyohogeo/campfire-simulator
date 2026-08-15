# Phase 6IA single-log Collision OFF/ON safe stop

## Frozen history and scope

Phase 6HV, Phase 6HW, Phase 6HX, Phase 6HY, and Phase 6HZ remain frozen with
their original artifacts and classifications. Phase 6IA used a new contract
and empty runtime root. No earlier runtime sample was reused or reclassified.
The frozen Phase 6HW/HX geometry, source, camera, ROI, temporal window, image
gates, and OFF-then-ON ordering were not changed.

The orchestration contract SHA-256 is
`24A46129E99627AF44CA5CB9BCB152C494C4083E19C4702B7AADB6CA9380DFD6`.
The implementation commit is `2ecd177`.

## Preflight

The no-Kit preflight passed 62/62 cases with zero Kit launches:

- Phase 6HZ exact import loader: 12/12
- reserved-key-safe marker producer/helper: 11/11
- canonical Point-policy producer/consumer: 13/13
- atomic report producer/writer/reader/consumer: 15/15
- generated OFF/ON stage contract: 11/11

The generated stages had the frozen 26/36/120 closed proxy topology, a 0.06 m
source-to-proxy gap, 1.6 m end clearance, identical common stage/settings
digests, and only `physicsCollisionEnabled` as the declared OFF/ON difference.
Resource, lifecycle, cleanup, and exact-import dependencies were all present.

## Formal runtime and first failure

The first and only formal launch was Collision OFF. Kit reached the probe
operation, but the frozen generated USDA was rejected by Kit's USD text parser
before the stage opened. The first parser error was:

`candidate.usda:118:64: Expected } at 'float secondOrderBlendFactor = 0.9 }'`

The affected declaration was the single-line nested
`FlowAdvectionChannelParams` block under
`/World/Flow/Simulate/advection/temperature`. The operation report therefore
ended with `RuntimeError: Phase 6HX stage did not open`. This is classified as
`safe_stop_runtime_stage_parse_harness_failure`; it is not Flow occlusion,
CollisionProxy behavior, visual ambiguity, or a resource failure.

Fail-fast held. Collision ON was not launched, and there was no retry,
replacement, or root reuse. No simulation frame, active-block sample, ROI
occupancy value, capture, difference image, or comparison video exists, so
neither the numeric gate nor human visual gate was evaluated.

## Lifecycle, resources, and cleanup

The error path persisted `stage_close_complete` and `shutdown_complete`, then
Kit exited with code 1. The canonical operation report was absent, so the
guard correctly rejected the attempt and the parent classified it as a failed
sample. Exact identity cleanup left zero residual processes.

Peak Private Bytes were 7,344,545,792 for Kit and 7,799,668,736 for the unique
tree, leaving 9,835,323,392 and 10,453,942,272 bytes below the 16/17 GiB
limits. Runner and diagnostic peaks were 96,362,496 and 16,896,000 bytes.
Minimum available physical memory and commit headroom were 84,981,919,744 and
104,944,119,808 bytes. There was no native exception, fatal marker, dump,
automatic upload attempt, timeout, or CDB invocation.

## Verification and boundary

Python compilation, focused regression 14/14, Release build, the standard
eight-process/78-test suite, and static devlog validation passed. Phase 0 RTX
and Phase 3 were omitted because no production, USD-generation, render,
wood-authority, or Flow-input source changed. Production source, defaults,
canonical Point policy, Point payload/revision/ordering, wood authority, V3,
public scenes, and latest demo remain unchanged.

Phase 6IA does not qualify the single-log visual occlusion signature and does
not satisfy the condition for returning to the production log placement. A
future separately approved Phase must first make the frozen diagnostic stage
authoring Kit-parseable and exercise an actual Kit stage-open boundary from a
new contract/root. It must not reclassify Phase 6IA, loosen the frozen visual
gates, or automatically proceed to production integration.
