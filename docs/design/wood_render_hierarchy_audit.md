# Phase V3M-A: wood render hierarchy compatibility audit

Date: 2026-08-09

Baseline: `c9d127b` (`Record dynamic texture V3 feasibility boundary`)

Scope: audit and isolated Kit/RTX probe only; production scene integration is not part of this phase.

## Decision

The proposed hierarchy is viable in an isolated stage:

```text
/World/Logs/ProbeLog             Xform + RigidBodyAPI + MassAPI + damping
├── Collider                     Cylinder + CollisionAPI + physics material + invisible
└── RenderSurface                Mesh + face-varying primvars:st + render material
```

The isolated probe passed all 14 structural and RTX checks. Both children follow the root transform with a measured matrix error of `0.0`; the Mesh has no Physics/PhysX schemas; the analytic collider is invisible; a fixed `dynamic://` checker appears on the side and both caps; and stage reload preserves the exact topology SHA-256. Phase V3M-B may therefore begin, but this result does not qualify production integration or physical equivalence.

## Current Cylinder-root assumptions

The machine audit records 1,034 source/stage evidence lines in `hierarchy_audit.json`. Broad evidence is retained so future changes can be compared mechanically; the compatibility-critical boundaries are summarized below.

| Area | Current assumption | V3M-B treatment |
| --- | --- | --- |
| `wood.py:create_log` | Stable `/World/Logs/<id>` Prim is a `UsdGeom.Cylinder`; transform, identity metadata, collision, rigid body, mass, damping and both material roles share it. | Keep legacy path byte-for-byte when OFF. ON authors Xform root, Cylinder child and Mesh child before stage connection. |
| `wood.py:move_log` | Writes translate/orient and clears velocities on the root Cylinder. | Root remains the physics transform owner, so operation semantics can remain stable through a helper. |
| `wood.py:get_log_world_position` | Computes the root world transform. | Compatible with both forms; formalize as `get_log_physics_transform`. |
| `wood.py:list_log_ids` | Enumerates direct children carrying `campfire:logId`. | Compatible if identity stays on Xform root; reject children or malformed duplicates. |
| `scene.py` / Phase 0 | Four Cylinder children are created directly under `/World/Logs`, without stable metadata/rigid bodies. | OFF stays unchanged. A separate default-off hierarchy authoring path must not rewrite the canonical Phase 0 scene. |
| `flow_scene.py` | Applies `CollisionAPI` to every direct log child. | In hierarchy mode target `Collider`; never apply collision to `RenderSurface` or redundantly to the root. |
| `resident_point_scene.py` | Requires root `IsA(Cylinder)`, reads axis there and uses its world transform. | Axis/dimensions resolve from Collider; origin/axis transform resolves from root. Existing cardinal restriction remains unchanged. |
| `resident_snapshot_adapter.py` | Publishes visual/support/revision attributes directly to stable log paths. | Keep attributes on root so revision, rollback and cached handle contracts remain stable. |
| `wood_visual_v0.py` | Binds render material to the root Cylinder. | Helper returns root for legacy and RenderSurface for hierarchy. V0/V1/V3M modes must fail closed if combined. |
| `wood_visual_v1.py` | Requires a Cylinder source, copies its local transform, radius and height, then hides it. | V1 stays a separate fallback; do not combine its render-only band geometry with V3M. |
| `support.py` / Phase 5 | Prepared Cylinder segment roots receive direct radius updates and joint removal. | Leave the Phase 5 legacy segment path unchanged in the first hierarchy integration; no shrinking collider or V4 work. |
| Phase 2–5 scene builders | Save root Cylinder topology and bind physics material on each root. | Canonical `.usda` assets remain legacy. Dedicated ON probes build hierarchy offline. |
| checkpoint v1 | Stores authoritative model metadata plus exact stage text and addresses consumers by stable log IDs/revisions. It has no render-mode field. | Do not change schema v1. Recovery must reconstruct/use an already authored matching stage mode; no implicit live migration. |
| stage recovery | Rebuilds consumers after attaching the replacement stage, using stable log IDs and revision. | Validate hierarchy before consumer construction; retain owner thread, pending payload retry and revision contracts. |
| Flow source / Emitter | Reads stable log positions or attributes; some diagnostics count root CollisionAPI. | Preserve root path and source position; update validation to resolve Collider without changing emitter payload. |
| Resident Point layout | Uses root transform and Cylinder axis assumption; positions remain an independent payload. | Resolve dimensions/schema through helper only; Point arrays, sidecar and representation contract remain unchanged. |

The audit found Cylinder-root saved-stage evidence in `phase0.usda`, `phase1_flow.usda`, `phase2_rigid.usda`, `phase3_thermal.usda`, and `phase5_collapse.usda`. It also enumerated 14 checkpoint/recovery scripts or modules. Phase 4 is generated from Phase 2/wood authoring even though its saved file did not match the narrow log-name Cylinder pattern used by the audit; it remains in the manual compatibility scope.

## Proposed shared helper boundary

Type branching should be localized in `wood.py`, not repeated in consumers:

- `get_log_root(stage, log_id)`: stable direct child with matching `campfire:logId`.
- `get_log_collider(stage, log_id)`: legacy root Cylinder or hierarchy `Collider` Cylinder.
- `get_log_render_surface(stage, log_id)`: legacy root Cylinder or hierarchy `RenderSurface` Mesh.
- `get_log_dimensions(stage, log_id)`: finite positive radius/length and X axis, validated against root metadata.
- `get_log_physics_transform(stage, log_id)`: world transform of the stable root.
- `get_log_material_target(stage, log_id)`: render target only; never the hierarchy collider.

V3M-B should also expose one immutable representation token authored before stage connection. Missing, mixed or competing visual modes must fail before Physics/Flow consumers start.

## Isolated Mesh and UV probe

The A probe deliberately uses a coarse `6 axial × 12 circumferential` Mesh rather than the final 360-cell topology. Its purpose is hierarchy and UV feasibility only.

- 117 points, including duplicated side seam vertices.
- 72 side quads and 12 triangles per cap: 96 faces total.
- 360 face vertices and exactly 360 face-varying UV values.
- Fixed 384 × 128 RGBA8 atlas split into side, left-cap and right-cap regions.
- Nearest filtering and colored seam/orientation marks expose wrapping and inversion.
- Right-cap, 180-degree left-cap, moved/rotated, and reloaded captures are distinct real RTX frames.
- Root, Collider and RenderSurface world matrices match exactly after move/rotation.
- Prim path set and topology digest remain identical through live transform and reload.
- Texture URI remains `dynamic://campfire_phasev3ma_mesh_checker`.

The short video is a fixed checker diagnostic assembled from four measured states. It is not a combustion trajectory.

## Non-changes and next gate

Phase V3M-A changes no production module, app setting, scene asset, physical formula, schema, checkpoint, Flow/Point publication or default. V0 and V1 remain OFF fallbacks, V2 remains an independent immutable payload, V3 production integration remains absent, and Phase 6DM remains held at `57fe3bc`.

V3M-B may proceed only with a default-off hierarchy and exact OFF behavior. It must implement the final 24 × 12 side and two 4 × 12 cap mapping, then demonstrate physical/Flow/Resident equivalence. A failure in topology identity or physical equivalence stops work before dynamic texture integration.
