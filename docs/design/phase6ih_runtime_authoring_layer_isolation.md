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
