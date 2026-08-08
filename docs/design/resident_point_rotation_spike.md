# Resident Point arbitrary-rotation and selective-publication spike

Status: Phase 6DI design-only contract. No production code, schema, default, or dependency is changed by this document.

## Goal and non-goals

The next default-off spike will test two independent changes to the existing Resident Point path:

1. represent each fixed log layout with a full rigid frame instead of the current cardinal X/Y axis code;
2. convert and author only numeric Point attributes whose immutable candidate bytes changed.

The spike does not activate Point in production, change the authoritative wood model, alter the published USD schema, or claim to solve the remaining Flow USD ingestion cost. A rotation changes `pointPositions`; even one `UsdAttribute.Set()` can still copy and ingest the complete array.

## Additive native layout ABI

The current `campfire_native_surface_layout` function remains unchanged. The spike adds a separate entry point that accepts, for every log, an origin and a right-handed orthonormal frame:

```text
world = origin + axial * axis_x + cross_a * axis_y + cross_b * axis_z
```

The frame is preferable to a quaternion at this boundary because its element order is explicit, it maps directly to the existing local cylinder coordinates, and it avoids quaternion component-order and sign-equivalence ambiguity across C++, `ctypes`, and NumPy.

The candidate ABI uses fixed-width scalar arrays and explicit counts. It does not expose C++ containers, NumPy-owned pointers, or packed structs. The caller retains every input/output buffer until the synchronous call returns. The native library neither stores nor frees those pointers.

The wrapper rejects non-finite components, zero-length axes, non-uniform scale, shear, and reflection. Unit length, pairwise orthogonality, and positive determinant are checked with a named spike tolerance. The implementation may normalize only small floating-point drift inside that tolerance; it must not silently turn a non-rigid transform into a supported layout.

## Owner-thread transform sample

One owner-thread provider samples each log's local-to-world transform once and derives origin plus the three transformed local basis vectors from that same matrix. This replaces the position-only provider in the spike; it does not introduce a second transform authority.

The provider returns one immutable layout candidate containing origins and frames. Structural topology stays fixed: no live Prim creation, deletion, relationship edit, material edit, or point-count change is permitted. A changed frame rebuilds the existing positions array and advances only `campfire:layoutRevision` after the positions Set succeeds.

## Immutable payload and recovery

The spike extends immutable in-process layout metadata with `layout_frames`. The legacy `layout_axes` representation remains available to the unchanged ABI, but a candidate must use exactly one representation. Origins, representation, frames or axes, and all numeric array bytes participate in the payload digest.

Commit, retry, rollback, stopped layout replacement, shared layout state, and stage recovery carry the same frame metadata. Native layout state is committed only after the USD transaction succeeds. An injected failure restores USD values, layout revision, native positions, origins, frames or axes, and the last committed immutable payload exactly.

`campfire:residentRevision` remains the final successful write for a wood snapshot. Revision continues to synchronize tick, immutable snapshot, retry, recovery, and consumers; it is not removed merely because an attribute value is unchanged.

## Changed-attribute publication

Before Vt conversion, the sidecar compares each immutable float32 candidate byte string with the last committed payload. The in-process payload records a changed-field mask for `positions`, `fuels`, `temperatures`, and `smokes`; this mask is not added to the USD or JSON schema.

- unchanged fields are neither converted nor passed to `UsdAttribute.Set()`;
- `campfire:layoutRevision` is written only when positions change;
- `campfire:residentRevision` is written last for every successfully published wood snapshot;
- rollback records and restores every attribute that the attempt may write;
- the first conservative prototype may retain old-value reads for all existing attributes, but the measurement must report that cost separately before narrowing the rollback journal.

This can reduce Python/C++ conversion work and Set-call count when channels remain byte-identical. It does not remove the cost of a changed large array, `Sdf.ChangeBlock` exit, USD notices, `omni.flowusd` ingestion, Flow rasterization, solver work, or rendering.

## Qualification matrix

The isolated prototype must pass all of the following before production adoption is considered:

- the legacy cardinal layouts and the new frame layout produce identical or explicitly bounded positions;
- 45-degree Z rotation and a non-cardinal 3D rigid rotation match an independent `Gf` or NumPy reference;
- scale, shear, reflection, non-finite values, and invalid buffer lengths fail closed without state change;
- unchanged candidates perform zero numeric channel Sets except the required resident revision publication;
- each single-field and multi-field change produces the exact expected Set collection;
- injected failures at every writable attribute restore USD and native state exactly;
- retry reuses the same immutable payload and digest;
- replacement-stage recovery receives the latest committed frame and revisions;
- source generation, boundary conversion/copy, USD Set calls, ChangeBlock exit, notices, Flow ingestion proxy, active blocks/readback, solver/render update, transferred bytes, and memory are reported separately;
- 720 points are checked first, followed by the existing 20-log x 360-surface-point target of 7,200 points.

Rotation jitter thresholds are not a production constant yet. The spike first records stationary transform noise, then reports sensitivity at multiple explicit angular thresholds. No value is adopted without the measurement.

## Adoption boundary

The prototype stays behind a new default-off diagnostic setting and an additive native symbol. Production keeps Sphere as the default emitter, Point stays default-off, Flow remains 110.0.0, and the physical equations, JSON schema, serialization, USD save behavior, revision, rollback, and immutable snapshot contracts remain unchanged.

Adoption requires both correctness and a repeatable reduction in total update cost. If selective Sets save only Python-side work while Flow ingestion remains dominant, the change may still be useful but is not evidence that USD is a scalable high-frequency bulk-data path.

## Phase 6DJ isolated-kernel result

The first implementation is deliberately separate from the production Phase 6AU library. The isolated MSVC `/O2 /fp:strict` DLL passed 10/10 gates with two logs and 720 surface points. Identity-X output is byte-identical to the legacy kernel. A 45-degree Z rotation and an arbitrary 3D rigid rotation both matched the independent float32 reference with zero observed maximum error.

The test also exposed a compatibility constraint that the design must not hide. The legacy Y-axis path swaps world X and Y while leaving Z unchanged, which has determinant `-1`; it is a reflection, not a rigid rotation. A proper right-handed 90-degree frame produces the same geometric point set after sorting with zero observed error, but the same-index positions differ by as much as `0.1774888635 m`. Because fuel, temperature, and smoke are ordered by surface-cell index, geometric set equivalence is not channel equivalence.

Scale, shear, reflection, non-finite frames, and insufficient capacity returned explicit errors without modifying the output buffer or count. The isolated 720-point p95 was `0.0240 ms` for the legacy function and `0.0266 ms` for the frame function. These are kernel-only values and say nothing about Vt conversion, USD authoring, notices, Flow ingestion, rasterization, solver, or rendering.

The frame kernel is therefore correctness-qualified in isolation, but production integration is not qualified. The next spike must derive frames from real USD transforms and validate every emitted position together with the fuel, temperature, and smoke value from the same stable surface-cell identity. No frame metadata is added to the Resident payload until that mapping is demonstrated.
