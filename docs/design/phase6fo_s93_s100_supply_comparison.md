# Phase 6FO S93 / S100 Point supply comparison

Status: pre-runtime contract. Phase 6FN is frozen as the qualification boundary for three public NanoVDB readbacks and three fuel zero-copy aliases in one process. Phase 6FO does not extend that count, connect production, or reinterpret Phase 6EP–6ES.

## Question

The corrected production-like four-log diagnostic fixture has 1,440 immutable surface Points. At offset `-0.0125 m`, every Point center is inside its owner proxy and outside every other proxy. Ninety-six Points have only the assumed `0.05 m` support sphere intersecting another log.

- `S93_support_clear` uses `allow_self_center`: self center/support overlap is allowed, but those 96 other-log support intersections are disabled. It supplies 1,344/1,440 Points (93.33%).
- `S100_center_clear` uses `allow_other_support`: the same 96 support-only intersections are allowed, while an actual Point center inside another log remains forbidden. It supplies 1,440/1,440 Points (100%).

The 0.05 m sphere is an engineering assumption equal to one velocity voxel. Flow 110.0.0 exposes no public exact Point support radius. The comparison therefore decides between two authoring policies; it does not reverse-engineer Flow's support kernel.

## Frozen fixture and offline evidence

The stage uses the Phase 6ER corrected four-log placement: lower log axes are world X and separated in Y, upper axes are world Y and separated in X. Each proxy remains the same closed 26-vertex, 36-face, 120-index Mesh. Offline exact authored-Mesh sampling requires zero other-log Point centers and zero sampled volume-overlap pairs.

Before Kit runtime, `prepare_phase6fo_supply_comparison.py` writes a bounded JSONL record for every Point under both policies. Each record contains world coordinates, owner log, enabled state and reason, self/other signed distances, center/support classification, and channel strengths. It also writes the stage-blueprint hash. Runtime preserves each generated USDA SHA separately; policy-specific source arrays make byte-identical stage files neither expected nor claimed.

Geometry, transforms, Point order, per-Point channel values, Flow settings, voxel sizes, renderer, camera, lighting, timeline, readback frames, startup, and shutdown stay fixed. Only the Point enable policy differs.

## Public channel preflight

Phase 6FN formally qualified fuel aliasing, not spatial use of velocity, temperature, or smoke. Before the six comparison processes, an evidence-only S93 process performs one public readback at frame 180 and samples one representative upper collider.

For velocity, temperature, smoke, and fuel, the preflight requires the declared public channel index, a direct NumPy `uint32` buffer, shape/stride/logical-byte metadata, a positive public data pointer, no `np.asarray`, no requested material copy, deletion of the temporary NanoVDB file, ordered alias release, and zero weak-reference residual. Any pointer, resource, lifecycle, or release failure stops Phase 6FO before the formal comparison. The preflight is not a formal S93 run.

Formal processes use exactly three public readbacks at frames 180, 360, and 540. Returned channel arrays are consumed directly. After one channel's near-Mesh NPZ and bounded aggregates are durable, its list slot and local alias are cleared before the next channel. Raw public buffers do not survive the operation scope. The collector disables its historical explicit `gc.collect()` path, so forced GC cannot make the lifetime result look better.

## Spatial regions and transport proxy

Flow exposes no public collision occupancy mask. All inside/deep/boundary labels are computed against the authored proxy Mesh and must not be called Flow occupancy.

- deep interior: signed distance less than minus one channel-specific voxel;
- boundary band: inside the Mesh and within one channel-specific voxel of the surface;
- opposite/top, side, and end control faces: the closed local control volume expanded by 0.05 m;
- global gap, flame-rise, opposite-above, and side-control regions: fixed world AABBs in the frozen contract.

Every stored near-Mesh record retains voxel center, local/world coordinates, signed distance, face class, and channel value through the existing compact NPZ schema. Boundary values are always reported and are excluded only from the deep hard gate.

For each control face, the directional proxy is

`max(dot(velocity, outward_normal), 0) * scalar * voxel_face_area`.

The same normals, face areas, frames, and trapezoidal time integration are used for S93 and S100. With velocity in m/s, the result is scalar-value times m³/s; public channel semantics do not justify a strict conservation or source-ownership claim. Temperature comparison uses `max(raw - 1.0, 0)` because prior calibration observed the ambient reference at 1.0. Raw temperature remains reported.

Flame height is a numerical profile proxy: maximum Z of fuel above 0.001 and temperature above 1.01 in the fixed scene region. Startup/rise is the first representative-ingestion frame. These accompany, not replace, the video review.

## Population and predeclared decision

The balanced formal order is `S93/S100`, `S100/S93`, `S93/S100`, for three independent processes per policy. Only a startup prerequisite failure before the first readback may replace a slot, with a total budget of two. Physical, channel, marker, resource, native lifecycle, or cleanup failures are never retried.

Hard conditions include three readbacks exactly, weak residual zero, source sums and Point counts matching the offline plan, deep velocity at most `1e-4 m/s`, absolute resource/lifecycle safety, and normal OS exit. S100 must retain at least 1.07 times S93 weighted supply. A 25% S100/S93 increase in deep temperature-excess, smoke, fuel, opposite-face transport, or floored deep velocity is predeclared as material worsening. This is deliberately larger than the 7.142857% relative supply increase: a leakage increase more than 3.5 times the supply gain is disproportionate. Cross-run relative range for decision metrics is at most 35%.

Small internal nonzero values alone do not reject S100. If numeric gates pass, the same-camera 15-second RTX comparison must show no new clearly visible direct passage through an upper or adjacent log. If both policies are materially equivalent, the simpler S100 policy is preferred because it avoids a 6.67% Point loss. If S100 materially worsens deep/opposite transport or visible penetration, S93 remains the candidate. Thresholds are frozen before runtime and are not adjusted after seeing results.

## Safety and scope

Kit remains capped at 14 GiB and the unique tree at 16 GiB; runner and diagnostic child remain capped at 512 MiB, and physical/commit headroom floors remain 8 GiB. Stage close is bounded at 180 seconds. Fatal, access violation, dump, automatic upload, residual process, weak residual, or missing lifecycle marker is a nonreplaceable stop. The narrow Phase 6FN margin is not used to justify raising any ceiling.

This Phase does not qualify a fourth readback, per-frame or long-duration readback, production Point policy, production defaults, V3, PhysX sharing, dynamic transform, 20-log performance, wood shape change, or fire lighting. Production adoption and roadmap P4 require a new explicit approval after this comparison.
