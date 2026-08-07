# Resident Point production module

Status: Phase 6CG qualified the native surface producer, immutable Point payload, and transactional Point sidecar as production-shaped but unactivated modules. The production default remains the existing Sphere path.

## Extracted responsibilities

`resident_point_sidecar.py` removes three runtime types from benchmark-only ownership:

- `ResidentNativeSurfaceProducer` converts Resident native SoA state into persistent position, fuel, temperature, and smoke arrays.
- `ImmutableSurfacePayload` owns one revision's arrays as immutable `bytes` with an identity-independent SHA-256 digest.
- `ResidentPointSidecar` publishes one pre-authored `FlowEmitterPoint`, rolls back its last commit when the primary consumer fails, retains exact payload identity for retry, and rejects stage identity changes before writes.

`ResidentApplicationSession` remains the authority for pending work and consumer order. `ResidentStageRecoveryOrchestrator` remains the authority for the close/drain/attach/rebuild transition. The new module does not create a second scheduler, revision, rollback, or stage lifecycle.

## Fail-closed geometry and ABI boundary

The producer derives log count, cells per log, published field count, and exposed point count from the active backend rather than assuming 20 logs or 7,200 points. Before calling the audited native ABI, it requires:

- at least one exposed surface cell;
- one common axial/circumferential/radial cell geometry, radius, and length across all logs;
- origins shaped `(log_count, 3)` with finite `float64` values;
- axes shaped `(log_count,)`, stored as `uint32`, containing only 0 or 1;
- one common finite positive ambient temperature;
- persistent NumPy output pointers that do not change during channel generation.

The sidecar additionally requires an existing `FlowEmitterPoint` Prim, an authored non-empty `pointsPrim` relationship, all four existing array attributes, and the existing Resident revision attribute. It never deletes or redefines a live Prim. Layout replacement is same-shape, finite, monotonic, and remains restricted by the owning session to ready/stopped state with no pending snapshot.

Payload metadata must be non-boolean integers. Position and channel buffers must be exact immutable `bytes` of the expected length. This prevents a caller from mutating a retained retry payload behind the session's revision contract.

## Equivalence and real Flow result

The Phase 6CG real Kit scenario used Flow 110.0.0, 20 logs × 1,152 cells, 360 exposed cells per log, and one 7,200-point emitter. At revision 1 it ran the previous benchmark producer and the extracted production producer against the same Resident backend. Position, fuel, temperature, and smoke arrays matched byte-for-byte.

The scenario then repeated the qualified lifecycle: injected Point failure created pending revision 3; close plus four updates and attach plus four updates delivered the complete ordered Kit event sequence; an injected replacement consumer-factory failure retained the pending value and old consumers; retry rebuilt at committed revision 2 and reused the exact immutable payload; all consumers reached revision 3 and continued to revision 124.

All 21 gates passed. Flow reached 1,309 active blocks, every required sparse field readback was non-empty, and no relevant live structural resync occurred after recovery. Clean shutdown discarded no pending value. The 60-frame real RTX video has 59 unique frame hashes and is excluded from performance measurement.

The standard regression suite passed 52/52 checks across eight processes in 294.3 s; collapse coverage completed in 174.2 s.

## Adoption decision

The code ownership gap is closed, so the Point path is suitable for a default-off application integration spike. It is not yet the production default because the normal application scene does not pre-author the Point schema and the interactive runtime does not yet compose the backend, session, sidecar, and recovery orchestrator from one explicit setting.

The next boundary must pre-author the complete Point/UsdGeomPoints/Flow solver graph before stage connection, expose one default-off application setting, and prove startup, timeline ownership, clean shutdown, and fallback to the unchanged Sphere path. Only after that result should the default emitter choice be reconsidered.

Reproduction:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_phase6cg_resident_point_module.ps1
```
