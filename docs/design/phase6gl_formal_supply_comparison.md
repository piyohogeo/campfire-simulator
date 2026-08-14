# Phase 6GL formal supply comparison

## Frozen boundary

Phase 6GL is a new formal population. Phase 6FO and Phase 6GA through 6GK stay
unchanged, and none of their process samples is admitted. The Phase 6GK schema
qualification is a hash-pinned interface prerequisite, not a formal S93 sample.
The machine contract is `scripts/phase6gl_supply_comparison_contract.json`
(SHA-256 `21BC3156D77CCB758514EB58D8B8BE7B83DE43B05705DDA934DEE3014A7ACF9C`).

The accepted population contains three independent processes for each of S93,
S100, and Collision OFF. Its balanced order and maximum two startup-only
replacements are fixed before runtime. Any other failure is nonreplaceable.

## Readback interface

At frames 180, 360, and 540 the public Flow readback must return exactly:

1. temperature
2. fuel
3. burn
4. smoke
5. velocity
6. divergence
7. rgba

The raw count, order, grid class, value type, enabled/empty state, and version
are validated before those names are applied. Six enabled fields must satisfy
the same-object/shared-memory alias rule; disabled RGBA remains a same-object,
zero-element, zero-byte handle for which `shares_memory == true` is not required.
No forced garbage collection or full-field JSON/NPZ/OpenVDB write is permitted.
The existing near-Mesh NPZ is bounded diagnostic evidence and contains only the
samples required to reproduce authored-Mesh signed-distance and transport
statistics.

## Physical and safety gates

The Phase 6GC corrected-four geometry, float32 payload-native source contract,
Point policies, offsets, Flow settings, frames, deep/boundary definitions, and
directional transport proxy are unchanged. The absolute/relative gates are
copied verbatim into the machine contract. Run-to-run relative range applies to
the per-condition deep-velocity metrics and every paired decision metric.

Kit remains limited to 16 GiB and the unique process tree to 17 GiB. Runner and
diagnostic helpers remain at 512 MiB; physical and commit floors remain 8 GiB.
The qualified release-after-close order, durable pre-close commit,
progress-aware stack-first CDB, exact cleanup, and PID-reuse policy remain
mandatory. Numerical 9/9 qualification is the sole authorization for a later
same-camera comparison capture within this Phase.

## Frozen result: safe stop at attempt01

The fresh population launched only sequence 01 position 01 (S93). Startup and
payload-native source validation passed, with active blocks 688 at frame 60 and
1,118 at frame 120. The first frame-180 public call returned seven handles, but
raw schema validation stopped before channel semantics and near-Mesh sampling.

Phase 6GK authored divergence export ON. Phase 6GL accidentally reused the
Phase 6GC stage builder without that explicit attribute; its generated USD has
no `divergenceEnabled` authoring. The required divergence handle was therefore
empty, producing `required_handle_empty`, `grid_count_mismatch`,
`grid_name_mismatch`, `grid_class_mismatch`, and `value_type_mismatch`. This is
a confirmed harness/schema-operation mismatch. It is not evidence about S93 or
S100 collision, directional transport, deep velocity, or visible penetration.

The failure is nonreplaceable under the frozen contract. Attempt02 through 09,
paired gates, cross-run repeatability, and video were not started. Stage close
completed in 139.028518 seconds (below 180 seconds), followed by
`shutdown_complete`; the process correctly exited nonzero because the operation
failed. Kit/tree peaks were 15,135,453,184 / 15,298,633,728 bytes, leaving
2,044,416,000 / 2,954,977,280 bytes below their limits. CDB was not needed and
exact cleanup recorded zero residual.

Post-stop verification passed Release build, Phase 0 RTX, Phase 3 (zero dry
and wet mass-balance error; wood-owned Flow input), focused Phase 6G 61/61,
standard suite 78/78 across eight processes, and devlog static validation.
The broad all-Phase-6 discovery was 503/505 because two older tests still assert
superseded Phase 6EB/6EJ shutdown-policy text; neither failure touches Phase 6GL
code. Production and latest-demo hashes stayed unchanged.
