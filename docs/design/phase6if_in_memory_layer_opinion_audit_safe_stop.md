# Phase 6IF in-memory layer/opinion audit safe stop

Date: 2026-08-16  
Baseline: `88dcb99`  
Implementation: `174c3c6`  
Contract SHA-256: `887BE9A2B717534FA71E01A3FBEAD5ED8EB277038152153D1CED7E1E100CA5E0`

## Scope and frozen history

Phase 6IE remains frozen as `safe_stop_runtime_prim_policy_and_lifecycle_failure`.
No Phase 6IE artifact, dump, classification, threshold, or runtime sample was
modified or admitted to Phase 6IF. Phase 6IF was audit-only: it did not relax
the runtime-Prim policy, play the timeline, advance Flow simulation, obtain a
Flow interface, perform readback, or create a capture.

The predeclared evidence boundaries were generated stage, immediate live open,
one stopped Kit update, and pre-close. Each boundary records bounded composed
Prim/property data plus root/session Sdf specs and fields. Full in-memory layer
exports are stored separately with size and SHA-256 evidence.

## No-Kit qualification

The actual producer, atomic writer, bounded reader, normalizer, and validator
passed 24/24 layer/opinion cases. Observational positives covered root-file vs
in-memory divergence, dirty state, runtime properties and relationships,
property order, schema application, root/session opinions, and an authored
record change with protected semantics unchanged. File/protected input changes,
unknown layers, oversize/nonfinite data, missing/duplicate/swapped paths,
hash/content contradictions, and layer identity mismatches failed closed. The
complete marker-payload fixture passed 34/34. All inherited fixtures passed.

## Actual one-process audit

The single permitted Kit process opened a newly generated Collision-OFF stage.

| boundary | root dirty | root bytes | root Prim/property specs | session dirty | session bytes | session Prim/property specs |
|---|---:|---:|---:|---:|---:|---:|
| generated | false | 8,254 | 25 / 101 | false | 11 | 0 / 0 |
| live open | true | 11,054 | 38 / 121 | true | 3,476 | 8 / 37 |
| one stopped update | true | 12,904 | 39 / 147 | true | 3,476 | 8 / 37 |

The file-backed root SHA-256 remained
`D5668572776AC0B48E9C8AF193FF517631865D9203864DBBFA1B52EFB8B8E99C`.
Its in-memory export changed to `DC0817...C99E` at live open and
`0EF89F...D197` after the stopped update. The session export changed from
`BA1EAA...D49` to `CAB9A9...2BA` at live open, then remained unchanged. The
25-path protected semantic-input digest stayed exactly
`8D8B471515ACF54767DDC863D66EBEBEAE3F9F91D1EF1D4F87A8027DEC52ECF9`.

### Exact target opinions

All ten requested runtime paths had root-layer Prim specs. Four also had
session-layer specs: `/Render`, `/Render/OmniverseKit`,
`/Render/OmniverseKit/HydraTextures`, and the viewport RenderProduct. The other
six were root-only: global RenderSettings, `/Render/Vars`, `LdrColor`, Flow
`debugVolume`, ray-march `cloud`, and Flow `renderSettings`.

The viewport product grew from 15 to 38 composed authored properties during
the stopped update. It was the only one of the twelve fixed target records to
change between live-open and post-update snapshots. Exact spec fields,
properties, relationships, stacks, and children remain in the JSON evidence.

The two existing authored Prims gained root-layer custom `bool` properties,
all `false` with a property stack pointing at the in-memory file-backed root:

- `/World/Flow/Simulate`: `enableHighPrecisionDensity`,
  `enableHighPrecisionVelocity`
- `/World/Flow/Simulate/nanoVdbExport`: `interopEnabled`

These are runtime/default augmentations, not changes to frozen collision,
emitter, advection, proxy geometry/transform, camera, source gap, or OFF/ON
common inputs. No explicit Sdf `propertyOrder` field was authored.

## Safe-stop boundary

After the stopped update, the unchanged Phase 6IE validator reported 14
runtime Prims, unknown count zero, protected-conflict count zero, and the two
expected authored-record changes. Its rejected set contained the ten
predeclared targets **plus** `/OmniverseKit_Persp`, which failed the same
`runtime_layer_mismatch` rule. Phase 6IF therefore stopped with
`runtime_unaccepted_path_set_changed` before pre-close and operation complete.
The audit does not infer when or which subsystem authored the extra camera
opinion because the live-open fixed target set did not include that path.

Cleanup still ran. Stage close completed in 0.572481 seconds, the context was
empty, neither layer remained in the layer registry after close, and
`shutdown_complete` was durable. Kit exited 1 because the operation failed.
Exact cleanup removed one known telemetry helper and ended at residual zero.
There was no fatal, native exception, device loss, TDR, CDB, dump, or upload;
the Phase 6IE RTX/device-loss lifecycle failure did not reproduce.

Kit/tree peaks were 7,555,067,904 / 7,992,868,864 bytes, leaving
9,624,801,280 / 10,260,742,144 bytes below the 16/17 GiB limits. Runner and
diagnostic peaks were 101,261,312 / 16,900,096 bytes. Minimum available
physical memory and estimated commit headroom were 80,460,148,736 and
100,465,414,144 bytes.

## Classification and next boundary

Phase 6IF is `safe_stop_audit_operation_incomplete`. Completed snapshots are
valid partial audit evidence, but the pre-close boundary is absent and the
live-stage policy remains unqualified. This does not qualify OFF/ON and does
not justify an allowlist change.

A separate approval is required to audit the perspective-camera opinion at all
four boundaries or isolate runtime render authoring from the diagnostic root.
No retry, OFF/ON run, production integration, or visual work starts
automatically.

## Regression

- Python compilation: pass
- Focused Phase 6IF tests: 2/2; underlying layer/marker cases 24/24 and 34/34
- Release build: pass, 7.24 seconds
- Standard suite: 8/8 processes, 78/78 tests, 330.6 seconds
- Static devlog validation: pass, 582 references, 335 IDs, 288 JSON, 177 SVG,
  and 2 ZIP files
- Phase 0 RTX and Phase 3: not rerun because production source, generated
  production USD, rendering, wood authority, Flow input, defaults, and the
  latest demo were unchanged; the only runtime work was a default-off audit
  stage with no timeline play or Flow update

## Evidence

- [Machine summary](../../artifacts/phase6if_layer_opinion_20260816_01/summary.json)
- [Generated-to-live diff](../../artifacts/phase6if_layer_opinion_20260816_01/attempt01/generated_to_live_open_diff.json)
- [Live-to-update diff](../../artifacts/phase6if_layer_opinion_20260816_01/attempt01/live_open_to_post_stopped_update_diff.json)
- [Post-update snapshot](../../artifacts/phase6if_layer_opinion_20260816_01/attempt01/post_stopped_update_layer_snapshot.json)
- [No-Kit preflight](../../artifacts/phase6if_preflight_20260816_01/preflight_report.json)
