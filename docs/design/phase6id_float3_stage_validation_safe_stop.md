# Phase 6ID canonical float3 comparison and live-stage safe stop

Phase 6IC remains frozen at commit `832fd81` as
`safe_stop_stage_attribute_validation_failure`. Phase 6ID used a new contract,
preflight root, and runtime root. No Phase 6IC artifact or runtime sample was
reused or reclassified.

## Frozen contract and comparison semantics

The contract SHA-256 is
`218EDD32D73C71B6EDE2E9E9EBDD1D24288162F4ACEEA3A13174A3ACEEE98A30`.
Implementation commit `8b71d9f` adds a canonical comparison for declared USD
`float3` attributes. It requires an exact three-component, finite numeric
vector; rejects booleans, strings, nested values, non-finite values, wrong
lengths, and wrong declared types; quantizes the expected components to IEEE
754 binary32; and compares component bits with a predeclared zero-ULP budget.
Positive and negative evidence is bounded and includes the attribute path,
declared USD type, original and quantized expected values, actual Python type,
component bits, absolute differences, ULP distances, budget, and decision.
Signed zero is explicitly equivalent. The scalar `1e-6` comparison remains
limited to scalar attributes and was not generalized to vectors.

The no-Kit producer-to-consumer preflight passed its float3 cases 22/22. The
inherited deterministic authoring-dependency gate passed 18/18, exact-loader
gate 12/12, Point-policy invariant 13/13, and atomic-report gate 15/15. Python
compilation and focused tests passed before the sole runtime launch.

## One actual Kit attempt

Exactly one fresh Kit process was launched; retry and replacement counts are
zero. The registered OFF and ON stages were generated and parser-validated.
For `/World/Flow/Emitter.position`, the original expected value
`[0.0, 0.0, 0.48]` quantized to
`[0.0, 0.0, 0.47999998927116394]`. The actual `pxr.Gf.Vec3f` had the same
components and bits (`0x00000000`, `0x00000000`, `0x3EF5C28F`), so all
absolute differences and ULP distances were zero. The canonical float3
boundary is therefore qualified in the actual Kit/OpenUSD environment.

The live stage opened successfully. Its subsequent whole-stage validator
stopped fail-closed before required-attribute completion because Kit had added
runtime camera, render, Hydra texture, and Flow render/debug prims that were
not in the generated-stage exact prim set. The first failure was
`stage_prim_set_mismatch`; no float3 mismatch occurred at this boundary. This
Phase does not reinterpret those runtime prims or relax the prim-set contract.

The last durable marker was `shutdown_complete`. Stage close and shutdown
completed, Kit returned exit code 1, and exact cleanup left residual process
count zero. The canonical parent classification was `cleanup_failure` because
`operation_complete` was not reached. Kit/tree Private Bytes peaked at
7,390,875,648 / 7,884,918,784 bytes, leaving 9,788,993,536 / 10,368,692,224
bytes below the 16/17 GiB limits. Runner/diagnostic peaks were 97,308,672 /
16,941,056 bytes. Available physical memory and estimated commit headroom
minima were 81,574,780,928 and 101,536,980,992 bytes. No fatal, native
exception, dump, CDB invocation, automatic upload, device loss, or TDR was
recorded.

## Scope and next boundary

Phase 6ID is `safe_stop_live_stage_prim_set_validation_failure`. It qualifies
the canonical registered-`float3` comparison only; the complete live-stage
required-attribute gate and the single-log OFF/ON comparison remain
unqualified. No timeline play, Flow simulation, public Flow interface,
NanoVDB readback, capture, ROI, image, or video work ran.

Production source, production USD publication, defaults, Point policy/payload/
revision/ordering, wood authority, V3, public scene, and latest demo hashes are
unchanged. A new approval, contract, and empty root are required to define a
bounded policy for expected Kit-authored runtime prims and repeat only the
stage-open/validation boundary. The OFF/ON comparison must not restart until
that separate prerequisite qualifies.

Post-stop verification passed the Release build in 8.75 seconds, focused tests
7/7, Python compilation, the standard eight-process suite with 78/78 tests in
345.3 seconds. Static devlog validation is recorded with the result commit.
Phase 0 RTX and Phase 3 were not repeated because production, USD publication,
rendering, wood authority, physics inputs, and Flow inputs did not change.
