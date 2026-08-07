# Flow 110 Point Emitter core qualification

Status: Phase 6CB public Point Emitter route qualified in a default-off technical phase. Production still uses the existing Sphere Emitter.

## Scope and construction rule

The qualification does not reference, sublayer, copy, or mutate NVIDIA's bundled `PointCloud/Native.usda` preset. Each run creates a fresh USDA stage containing `FlowSimulate`, `FlowOffscreen`, `FlowRender`, `FlowEmitterPoint`, and `UsdGeomPoints` before the stage is connected to the Kit USD context.

After connection, the script never deletes, defines, or changes a Prim, relationship, material, layer, or scalar Flow setting. Every publication changes only the pre-existing `pointPositions`, `pointFuels`, `pointTemperatures`, `pointSmokes`, and `campfire:residentRevision` attributes inside one `Sdf.ChangeBlock`. A `Usd.Notice.ObjectsChanged` listener rejects any relevant live resync.

The production extension, canonical scenes, dependency lock, physics, Wood JSON, Resident snapshot schema, lifecycle, rollback, and defaults are unchanged.

## Separately qualified boundaries

- Layer: Point Emitter, simulation, offscreen, and render use layer `0`.
- Relationship: every `FlowEmitterPoint.pointsPrim` targets exactly one pre-authored `UsdGeomPoints` Prim.
- Material: each Points source has an ordinary USD Preview Surface binding. This verifies source-material composition independently; Flow volume appearance is controlled by `FlowOffscreen` colormap and `FlowRender`, because `FlowEmitterPoint` has no material relationship in the 110.0.0 schema.
- Timeline: the fixed headless app reports a `PLAY` event followed by `STOP` at time code zero. `forceSimulate` drives the explicit Kit update loop; playing-phase active-block peak must exceed stopped warm-up allocation.
- Viewport: the active camera is `/World/Camera`, resolution is 1280×720, two real RTX captures are produced, and the final image hash differs from the pre-simulation image.
- Core and fields: active-block peak must be positive and temperature, fuel, burn, smoke, and velocity NanoVDB readback must be non-empty.
- Publication: all four arrays retain the requested point count, fuel/temperature/smoke sums match their generated values, all consumer revisions equal the final publication, and exactly one relevant notice is emitted per publication.

## Measured configurations

All runs use 30 warm-up plus 120 measured publications on Flow 110.0.0 and RTX 3090.

| Configuration | Points | Emitters | Active blocks peak | Source p95 | Python→Vt p95 | USD Set p95 | ChangeBlock exit p95 | Total publication p95 | Flow/render update p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Small qualification | 16 | 1 | 56 | 0.1435 ms | 0.1103 ms | 0.2112 ms | 0.9077 ms | 1.2621 ms | 10.4068 ms |
| Target single | 7,200 | 1 | 901 | 22.2409 ms | 1.3261 ms | 0.3317 ms | 0.9859 ms | 23.8944 ms | 7.5267 ms |
| Target four-way | 7,200 | 4 | 923 | 27.4073 ms | 1.6168 ms | 0.4227 ms | 0.9640 ms | 29.6119 ms | 7.4977 ms |

The target represents 20 logs × 360 surface samples from the Phase 6BV 24×12×4 grid, not one Prim per sample. Logical payload is 172,808 bytes per single-Emitter publication and 172,832 bytes for four Emitters. Each configuration passed 17/17 gates and emitted 150 relevant notices for 150 publications.

## Decision

Flow 110.0.0 now has a qualified public Point Emitter route through USD ingestion, rasterization, core simulation, sparse-field readback, and viewport fire/smoke rendering. The condition for investigating a newer Flow version is therefore not met; production dependencies remain fixed.

The single Point Emitter remains the first candidate. Four-way splitting is also functional but did not reduce total publication p95 and adds attributes and Prim ownership. Production adoption is deferred because the current technical source rebuilds 7,200 Python `Gf.Vec3f` values every publication, which dominates the target run. The next useful default-off experiment is a Resident-native surface-array producer and boundary-copy measurement feeding the already-qualified single Emitter. It must preserve the existing Wood authority, immutable revision contract, and current production Sphere path until separately adopted.

The standard regression suite passed 49/49 checks across eight processes in 313.3 s; collapse coverage completed in 184.6 s.

Reproduction:

```powershell
.\scripts\run_phase6cb_point_emitter_core.ps1 -Configuration all
.\scripts\run_phase6cb_point_emitter_core.ps1 -Configuration small-single
.\scripts\run_phase6cb_point_emitter_core.ps1 -Configuration target-single
.\scripts\run_phase6cb_point_emitter_core.ps1 -Configuration target-few
```
