# Phase V3M-B stable wood render Mesh

## Decision

The legacy analytic `UsdGeom.Cylinder` path remains the production default. The new representation is selected only by the default-off setting `/exts/campfire.app/woodRenderHierarchyEnabled` for Phase 2 or Phase 3:

```text
/World/Logs/Log_00                 Xform (identity, transform, RigidBody, Mass)
├── Collider                       UsdGeom.Cylinder (Collision, physics material, invisible)
└── RenderSurface                  UsdGeom.Mesh (render material, no Physics API)
```

V0 and V1 are mutually exclusive with this representation and fail closed. The physical collider remains an analytic local-X Cylinder; the Mesh is never a collider. The flag does not change Flow, Point payloads, wood JSON, checkpoint v1, rollback, revision, or immutable snapshot contracts.

## 360-state mapping

The authoritative grid is 24 axial × 12 circumferential × 4 radial cells. V2 packs exposed cells by ascending native local-cell index, producing 360 stable identities per log.

- Side: 24 × 12 = 288 quads. Each face references the outer-radial state at its axial/circumferential location.
- End caps: each end has 4 × 12 = 48 faces, for 96 cap faces total. The innermost ring uses triangles; three outer rings use quads.
- The 24 outer-ring cap faces overlap the two side-end rings. Those faces reuse the same state identity instead of creating duplicate state.
- Consequently the Mesh has 384 render faces but exactly 360 unique surface-state identities.
- The angular seam has duplicated geometry vertices. Geometry vertex identity is deliberately separate from surface-cell identity.

The static `primvars:surfaceIndex` is uniform per face. The authored `primvars:st` is face-varying and assigns every vertex of a face to the centre of that face's state texel. This produces piecewise-cell display and avoids interpolation within one physical cell.

## Fixed atlas

One atlas reserves 20 logs × 360 cells. Log slots are fixed before stage connection.

- Atlas: 480 × 240 pixels.
- Log layout: 5 × 4 tiles.
- One log tile: 24 × 15 state cells.
- One state cell: 4 × 4 pixels with a one-pixel gutter and a 2 × 2 interior.
- One authored UV samples the interior centre.

The stage and asset path remain fixed during runtime. Phase V3M-B only proves the topology and lookup; Phase V3M-C owns dynamic state upload and revision semantics.

## Compatibility helpers

Callers resolve representation differences through `get_log_root`, `get_log_collider`, `get_log_render_surface`, `get_log_dimensions`, `get_log_physics_transform`, and `get_log_material_target`. Identity, model attributes, diagnostic attributes, revision, RigidBody, Mass, velocity, and damping remain on the root. Collision and physics material resolve to the collider. Display color and future render material resolve to the render surface.

The Resident snapshot adapter writes derived display color to the resolved render surface while keeping diagnostic fields and revision on the stable root. Resident Point layout uses the resolved analytic dimensions and root transform, so OFF and ON return the same layout descriptor.

## Measured equivalence

The acceptance tolerances were fixed before the final comparison:

- final position: 0.02 m;
- final orientation: 0.05 rad;
- contact-report/contact-point/Flow active-block counts: 10% relative.

Phase 2 OFF/ON produced a 0.010646 m final-position difference and a 0.042244 rad final-orientation difference. Both paths dropped, contacted and settled inside the stone ring. Contact-report events were 1,063 / 1,018 and contact points were 1,061 / 1,017. Flow peak active blocks were 224 / 215 and emitter-follow error remained zero.

Resident-native Phase 3 produced exact OFF/ON authoritative SHA-256 values for dry and wet logs, revision 1,200, ignition times 66.2 s / 166.4 s, zero mass-balance error, equal fuel input, and equal support ratios. The checker probe passed 10/10 gates; the combined V3M-B report passed 13/13 gates.

## Limits and next gate

The Mesh is faceted at 12 circumferential segments and its points are immutable. It does not shrink, crack, char geometrically, or track mass-dependent collision. The ID checker is a diagnostic, not a combustion trajectory. Phase V3M-C may connect V2 state bytes to the fixed dynamic atlas only because V3M-B passed; it must remain default-off and best-effort, and it must not alter wood authority or roll back Flow on visual failure.
