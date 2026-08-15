# Phase 6HK — production-hierarchy FlowCollisionProxy boundary

Phase 6HJ remains frozen as `parked / diagnostic-only lifecycle`; its Phase 6HH/6HJ artifacts, contracts, thresholds, parent-allowlist failure, L0 `0xC0000005`, and inconclusive sampling-result-lifetime comparison are not changed or reused. Natural recurrence in a normal, non-readback path is monitored with the existing bounded lifecycle markers, but this Phase does not restart its diagnostic ladder.

## Roadmap return audit

The repository, qualification records, and living roadmap were compared before implementation. The current classifications are:

| Candidate | Classification | Dependency / evidence |
|---|---|---|
| CollisionProxy in the actual wood-transform hierarchy | partial | The current root/analytic `Collider`/`RenderSurface` hierarchy is qualified and production-default; the closed low-detail Flow Mesh is qualified only in separate static diagnostic stages. Their combination is not qualified. |
| RenderSurface and CollisionProxy coexistence | partial | The two roles were authored together offline in Phase 6DU, but the current production hierarchy plus the qualified decomposition proxy has no accepted runtime boundary. |
| Shared Flow/PhysX Mesh | unstarted | Production PhysX still uses the analytic Cylinder; a shared Mesh would require separate physics and performance qualification. |
| Dynamic Flow CollisionProxy transform | unstarted / blocked | Static pose-set qualification exists; runtime moving collision geometry remains outside that evidence. |
| Corrected four-log production-equivalent layout | partial | Geometry and Point/Collision diagnostic layouts exist; P3 S93/S100 adoption remains blocked by its readback-dependent formal comparison. |
| 20-log performance | partial | V3/PhysX/Flow baseline costs are measured, but 20 low-detail FlowCollisionProxy instances are not. |
| V3 GPU transport production candidate | blocked | Default-off GPU probes lack a public producer-consumed fence/pointer-lifetime contract. CPU-source transport remains production. |
| V3 teardown stability | qualified for current CPU-source; partial for GPU | Current production CPU-source lifecycle is qualified. GPU probe teardown samples exist, but the public lifetime contract is unresolved. |
| V3 default ON | qualified / stale roadmap entry | Phase V3T-P made the hierarchy and CPU-source V3 path production defaults. |
| Fire lighting minimal probe | unstarted | No minimal implementation is qualified; it is lower priority than the first missing collision boundary. |
| Flow→wood GPU heat-feedback public API feasibility | blocked | The audited public Flow 110 interface exposes readback/export operations but no documented direct GPU consumer/fence/lifetime boundary. |

## Frozen contract

Phase 6HK selects only the first missing collision boundary: one diagnostic-only, invisible, 12-segment closed Mesh child at `/World/Logs/Log_00/FlowCollisionProxy` in the existing production Phase 2 wood render hierarchy. The one changed variable is the presence of that Prim. The Mesh uses the already-qualified `26 / 36 / 120` topology, `PhysicsCollisionAPI`, `PhysicsMeshCollisionAPI`, and `convexDecomposition`.

The timeline stays stopped. The Phase qualifies only offline authoring identity, unchanged existing Prim digest, shared world transform, stage connection, 30 renderer frames, public Flow-interface availability, release-after-close teardown, normal OS exit, resource ceilings, and exact cleanup. It does not claim Flow occlusion, dynamic-transform consumption, PhysX Mesh sharing, Point policy, 20-log cost, or production readiness. NanoVDB readback, conversion, file save/reload, and ROI sampling are absent. The machine contract is `scripts/phase6hk_flow_proxy_boundary_contract.json`; its SHA-256 is frozen in the fresh artifact root before Kit starts.

## Result

Pending the single fresh guarded process. Success or failure stops this turn before any next boundary.
