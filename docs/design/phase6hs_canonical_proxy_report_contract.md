# Phase 6HS canonical proxy operation report contract

Phase 6HR (`f3bca01`) remains a frozen safe stop. Its operation artifact,
partial functional evidence, `cleanup_failure` classification, contract, and
artifact root are not edited, reclassified, or admitted to the Phase 6HS
runtime population.

## Boundary

Phase 6HS changes only the diagnostic operation-evidence interface. The
default-off one-proxy geometry, stopped timeline, 30 renderer updates, one
public Flow-interface acquisition, zero NanoVDB readbacks, release-after-close
sequence, lifecycle policy, and resource ceilings remain those of Phase 6HR.
There is one fresh runtime launch, with no retry or replacement, and it is
allowed only after the no-Kit preflight qualifies.

The canonical operation-report schema is
`campfire.phase6hs.proxy-operation-report.v1`. Its frozen schema digest is
`5664B84A498D81FF2A53B793AF246F853F8C9912030DB7A1086959317DD7A393`.
The frozen runtime contract digest is
`8DA32B5CCCA6AD4539EC60494F52988BEA3D06D5E7D9E93DF35EB097B7F6CA93`.

## Evidence flow

The durable, fsync-completed marker JSONL is the completion source of truth.
Exactly one `operation_complete`, `stage_close_complete`, and
`shutdown_complete` marker must occur in that order, must belong to the same
attempt, and `shutdown_complete` must be the final marker. Only then does the
shared runtime producer create top-level completion booleans. It writes the
report atomically after Kit has exited with code zero. A nested `lifecycle`
object is optional; when present it is a strict mirror and cannot override the
top-level values.

The same bounded validator is imported by the resource guard and the parent.
The guard persists its exact validation object and the parent requires exact
equality before applying the shared Phase 6HR lifecycle classifier. A missing,
false, mistyped, duplicated, reordered, cross-attempt, legacy-schema, or
digest-inconsistent item fails closed with a specific reason. `status` alone
is never completion evidence.

## Preflight

The no-Kit producer-to-consumer fixture qualified 42 operation cases and five
lifecycle cases. It covered nested and non-nested positive reports, natural,
telemetry-assisted, and exact NGX-assisted exits, plus the frozen negative
matrix. The actual producer output was persisted, read without transformation,
validated, passed through guard report construction, and consumed again by
the parent. The frozen Phase 6HR report was rejected as a legacy/incomplete
schema and the Phase 6HR artifact tree hashes were unchanged. Kit launch count
was zero.

## Runtime gates and stop boundary

The fresh process must create only
`/World/Logs/Log_00/FlowCollisionProxy`, preserve the production hierarchy
digest after proxy exclusion, retain the qualified 26/36/120 closed outward
mesh and world transform, keep the timeline stopped, perform exactly 30
renderer updates, acquire Flow once, and perform zero readbacks. Canonical
completion fields, marker order, Kit exit, lifecycle classification, resource
limits, exact cleanup, and final residual zero are all hard gates.

Only `natural_clean_exit`, `cleanup_assisted_telemetry_exit`, and
`cleanup_assisted_ngx_exit` are accepted, with assisted exits recorded
separately from natural exit. The phase stops after this one boundary even if
qualified. Occlusion, timeline play, dynamic transforms, PhysX sharing, Point
Emitter coexistence, multi-log performance, production integration, defaults,
V3, images, videos, and all NanoVDB work remain out of scope.
