# Phase 6IH: runtime render/camera Layer isolation

Date: 2026-08-16  
Baseline: `ea7217d`  
Contract SHA-256: `DE98DCEA6854BA95DEE63C3310D41CCDC80623EE238FA1249C449F6A10D1D4FA`

## Frozen history and scope

Phase 6IG remains `safe_stop_camera_opinion_unresolved`; it is not rerun,
reclassified, or reused as a runtime sample. Phase 6IH tests Layer ownership,
not a camera-attribute allowlist. Timeline play, Flow update/interface,
NanoVDB readback, capture, OFF/ON, and production changes are excluded.

## Layer design fixed before runtime

The diagnostic stage is authored into `protected_diagnostic.usda`. A new
`container.usda` is opened by Kit and sublayers, strongest to weakest,
`runtime_opinions.usda` and the protected diagnostic Layer. Kit's anonymous
session Layer and the container root are the runtime side. The protected Layer
contains Flow, Emitter, CollisionProxy, source/advection, diagnostic camera,
and all frozen physical inputs. The default EditTarget is the container root.

The protected file hash is fixed to the existing deterministic authoring
result `D5668572...E99C`; fixed empty-runtime and container hashes are
`28F84F70...E2D1` and `C556894E...6250`. The only accepted stack is session,
container, runtime, protected. The protected Layer must remain clean, its file
and in-memory exports must match, and its composed semantic digest must remain
constant at all four boundaries.

Runtime Prim paths/types are bounded to the 14 already observed Camera,
Render, Hydra, and Flow-render helpers, maximum depth five. Runtime properties
must be registered by the composed Prim definition or be one of four exact
custom exceptions. Three known false-valued nonsemantic Flow defaults may be
opinions in the runtime container but may not modify the protected Layer or
the protected semantic inputs. Runtime creation timing is deliberately not a
gate.

## No-Kit preflight

The actual producer/writer/reader/validator path passed 14/14 cases, including
both live-open and stopped-update creation timing. Protected-layer injection,
semantic change, unknown Layer/path/type/property, role exchange, disk hash,
dirty state, duplicate, missing, oversize, and hash/content contradictions
failed closed. The complete marker fixture passed 19/19 and all seven exact
dependencies matched. Kit launch count was zero.

The separately authorized one-process result is recorded below after runtime.

## Actual Kit result

One fresh Kit process was launched from
`artifacts/phase6ih_runtime_authoring_isolation_20260816_01`; no prior Phase
6IG artifact or runtime sample was reused. The generated boundary produced the
required session/container/runtime/protected stack with the container as the
EditTarget. The protected Layer was clean and its file and in-memory SHA-256
both remained `D5668572...E99C`. Its protected semantic digest was
`AA895FB6...4EBD`, and the generated runtime record population was empty.

The process then ended with Windows status `0xC0000005` while
`open_stage_async` was pending. The last durable marker is
`isolation_snapshot_complete` for the generated boundary; there is no
`stage_open_complete`, live-open snapshot, stopped-update snapshot, pre-close
snapshot, stage-close marker, or shutdown marker. Consequently, no runtime
camera/render opinion was observed in the separated configuration and the
required four-boundary evidence is incomplete. The result is
`safe_stop_runtime_authoring_isolation_failure`, not a Layer-isolation
qualification. The evidence establishes the generated Layer topology only; it
does not establish that the topology caused the native exception.

Kit and unique-tree Private Bytes peaked at 7,408,095,232 and 7,831,797,760
bytes, leaving 9,771,773,952 and 10,421,813,248 bytes below the fixed 16/17 GiB
limits. A single bounded 1,719,306-byte dump was preserved with SHA-256
`5AAE1EAD...1CC5`; automatic upload was not attempted. Exact identity cleanup
left zero residual processes. Timeline play, stopped update, Flow interface,
readback, capture, and OFF/ON remained at zero.

## Verification and next boundary

Focused producer-to-consumer tests passed, Python compilation passed, the
Release build succeeded, and the standard suite passed all eight processes and
78 tests. Devlog static validation passed after the result was recorded.
Phase 0 RTX and Phase 3 were not run because production code, published USD,
renderer configuration, wood authority, and Flow input are unchanged.

Phase 6IG remains frozen as `safe_stop_camera_opinion_unresolved`. A separate
approval is required for the smallest stage-open/lifecycle isolation of the
container composition before any live-stage policy validation. Production
policy application and the single-log OFF/ON comparison must not start from
this result.
