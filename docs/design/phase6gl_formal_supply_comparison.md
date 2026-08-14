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
