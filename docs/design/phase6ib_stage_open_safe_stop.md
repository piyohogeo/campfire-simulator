# Phase 6IB registered-schema stage-open safe stop

## Frozen history and scope

Phase 6IA remains frozen at `cfc4fd2` as
`safe_stop_runtime_stage_parse_harness_failure`. Phase 6IB used a new contract,
new preflight roots, and one new runtime root. No Phase 6IA artifact or runtime
sample was reused or reclassified. The frozen single-log geometry, 26/36/120
proxy topology, 0.06 m source gap, 1.6 m end clearance, Emitter, camera, ROI,
temporal window, image gates, and OFF-then-ON contract were unchanged.

The Phase 6IB contract SHA-256 is
`A32560472007EEC87B28D35B6A11575CADB766261ACBDFBBA8B929071C4A9A32`.
The implementation/contract commit is `b12c34c`.

## Confirmed Phase 6IA parser cause

The frozen Phase 6IA artifact placed each nested
`FlowAdvectionChannelParams` prim and its property spec on one line. Line 118
was:

`def FlowAdvectionChannelParams "temperature" { float secondOrderBlendFactor = 0.9 }`

The repository's known-good `assets/scenes/phase1_flow.usda` uses the same prim
type, name, nesting, property type, and property value, but terminates the
property spec with a newline before the closing brace. Phase 6IA also used
semicolon-separated property specs on the multi-property channels. Kit's USD
text parser stopped at the first same-line closing brace, so the confirmed
problem is the hand-written inline property-spec layout, not the Flow schema,
namespace, or numeric value.

Phase 6IB therefore removed hand-written positive USDA from the diagnostic
builder. Its positive path uses `pxr.Usd.Stage.CreateNew`, registered Flow prim
types, registered attribute lookup/type checking, and `UsdPhysics` APIs. The
old inline declaration remains only as an expected-rejection negative fixture.
Production stage generation was not changed.

## Preflight

The second empty no-Kit preflight root qualified all required fixtures with
zero Kit launches:

- Phase 6IB canonical stage/marker fixture: 23/23
- frozen Phase 6HZ exact-loader regression: 12/12
- canonical Point-policy producer/consumer: 13/13
- atomic report producer/writer/reader/consumer: 15/15

The first no-Kit preflight root recorded a 22/23 fixture-development failure
because a source-text assertion also matched the intentionally retained
negative recognizer. It did not launch Kit. The assertion was scoped to the
actual positive `author_stage()` function before the contract-authorized
runtime root was created. Both preflight roots remain immutable evidence.

## Actual Kit smoke and first failure

Exactly one fresh Kit process was launched. Kit reached app-ready and began the
exact wrapper, but exact-loading `phase6ib_stage_authoring.py` failed because
that module imported the repository-local `phase6hw_stage_builder` through the
ordinary module search path. The actual Kit `--exec` environment did not expose
that path:

`ModuleNotFoundError: No module named 'phase6hw_stage_builder'`

This occurred before the wrapper could persist `kit_launch` or
`kit_app_ready`, before stage generation, and before any OpenUSD parse/open
call. There is no generated Phase 6IB stage, stage hash, parser fixture result,
required-Prim result, stage-close marker, shutdown marker, Flow simulation,
Flow-interface call, readback, capture, image, or OFF/ON evidence. The bounded
180-second guard stopped the attempt; there was no retry, replacement, or root
reuse. Phase 6IB is therefore
`safe_stop_kit_stage_authoring_import_harness_failure`, not a stage-open
qualification and not a recurrence of the Phase 6IA parser error.

## Resources, lifecycle, and cleanup

Kit/tree Private Bytes peaked at 9,083,842,560 / 9,266,745,344 bytes, leaving
8,096,026,624 / 8,986,865,664 bytes below the 16/17 GiB limits. Runner and
diagnostic peaks were 94,130,176 / 16,941,056 bytes. Minimum available physical
memory and commit headroom were 84,198,518,784 / 104,160,718,848 bytes.

No canonical lifecycle evidence was produced, so the parent correctly rejected
the sample (`canonical_evidence_missing`; safe stop). Kit did not provide a
natural exit code before the guard boundary. Exact PID/creation-time/path
cleanup confirmed every observed attempt identity absent and final residual
process count zero. There was no fatal, native exception, dump, automatic
upload attempt, or CDB invocation.

## Verification and next boundary

Python compilation, the focused Phase 6IB tests (3/3), Release build, the
standard eight-process/78-test suite, and static devlog validation passed.
Phase 0 RTX and Phase 3 were omitted because production code, production USD
generation, rendering, wood authority, and Flow inputs were unchanged.

Phase 6IB does not authorize a fresh OFF/ON comparison. A separately approved
Phase must first make every repository-local dependency of the exact-loaded
authoring module deterministic in the actual Kit environment, then qualify one
new stage-generate/parse/open/close smoke from a new contract and empty root.
Only after that independent success may the unchanged single-log OFF/ON probe
be considered. Production, defaults, Point policy/payload/revision/ordering,
wood authority, V3, public scenes, and latest demo remain unchanged.
