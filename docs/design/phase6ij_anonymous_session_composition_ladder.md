# Phase 6IJ: bounded anonymous-session composition ladder

Date: 2026-08-16  
Baseline: `c57a6b2`  
Contract SHA-256: `6EDC39A8C0160A08C2263A89D57A3D81E80B639924CB887326EE9EC092BDE81E`

## Frozen history and scope

Phase 6II remains frozen as
`safe_stop_stage_open_native_failure_unlocalized`. Its A attempt, artifacts,
classification, and contract are not reused or changed. The recorded native
open and close returned; the observed stop was the old filename-suffix session
identifier contract rejecting Kit 110.2's `anon:<runtime-id>` form. Phase 6IJ
corrects only that contract and recreates A/B/C from empty attempt roots.

The protected diagnostic Layer, hashes, container and empty-runtime files,
Kit/Flow extension set, stopped timeline, open/close APIs, A→B→C order,
resource limits, lifecycle policy, and exact cleanup remain unchanged. There
is one fresh process per condition, no retry or replacement, and fail-fast at
the first non-normal condition. D remains identical to C and is not launched.

## Session identity contract

The only accepted syntax is `anon:<runtime-id>`, where the runtime ID is 1–32
ASCII hexadecimal characters. Normalization uppercases only that ID for
bounded comparison. Empty IDs, controls, path separators, URI/traversal text,
the former filename suffix, and any extra suffix are rejected.

Acceptance also requires exactly one anonymous, non-file-backed session Layer;
the Layer returned by `GetSessionLayer()`; identity distinct from root,
runtime, and protected Layers; and stable identifier and Layer identity from
open completion until close request. Runtime IDs may differ between processes
and are not compared across A/B/C. Root/sublayer order, EditTarget, protected
SHA-256, and C's empty runtime Layer remain strict.

## Evidence and classification

The operation report records the raw and normalized session identifier,
anonymous/file-backed facts, bounded Layer identity comparisons, session count,
root/sublayer/EditTarget identity, timings, calls, and lifecycle state. The
resource marker remains separate but its recorded root identity must agree
with the operation evidence.

Session, marker, artifact, or validator mismatches classify as
`safe_stop_stage_open_contract_failure`. A native exception, access violation,
fatal, or dump classifies as
`safe_stop_stage_open_native_failure_unlocalized`; one occurrence never proves
composition specificity. A B/C deterministic non-native mismatch in the
single newly added composition element, after every prior condition passed,
is the only route to
`safe_stop_stage_open_composition_specific_failure`.

The actual producer → atomic writer → bounded reader → validator fixture
qualified 30/30 with Kit launch count zero. All six exact dependencies matched.
Negative cases covered the legacy suffix, malformed IDs, file-backed and
non-anonymous Layers, identity collisions, multiple sessions, within-process
identity changes, missing/type-invalid evidence, marker conflict, nonfinite
content, and oversize content.

Runtime results are recorded only after this contract and implementation are
committed. Even a fully qualified ladder does not start the four-boundary Layer
audit, Flow, renderer updates, capture, or Collision OFF/ON comparison.

## Runtime result

Implementation was frozen at `a3f9f03`, then one new-root Condition A process
was launched. B and C were not launched after A's first non-normal boundary.
The corrected contract itself passed: the raw identifier was
`anon:000004B31A0C0180`; normalization preserved that bounded value; the Layer
was anonymous and non-file-backed; exactly one session Layer was present; it
was distinct from root/runtime/protected Layers; and its identifier and Layer
identity were stable through the close request.

The protected root opened in 0.251944 seconds with expected root, sublayers,
EditTarget, and SHA-256. Stage close returned in 0.491582 seconds; context empty,
reference release, operation complete, and `shutdown_complete` were durable.
The complete operation validator, marker sequence, and marker/Layer evidence
consistency all passed.

The parent PowerShell did not persist `runner_evidence.json` before the fixed
180-second outer guard boundary. Consequently the canonical lifecycle
evaluator reported `canonical_evidence_missing`, the natural-exit acceptance
contract was incomplete, and the condition is not qualified. Exact identity
cleanup left zero residual processes. There was no fatal, native exception,
device loss, TDR, dump, CDB evidence, or automatic upload. Kit/tree Private
Bytes peaked at 3,992,465,408 / 4,429,004,800 bytes, leaving
13,187,403,776 / 13,824,606,208 bytes to the fixed 16/17 GiB ceilings.

Phase 6IJ therefore stops as `safe_stop_stage_open_contract_failure` at the
post-`shutdown_complete` parent-evidence boundary. This is not a native
Stage-open failure and does not localize a composition-specific issue. There is
no fully qualified ladder condition. Phase 6II remains frozen and unchanged.
The next separately approved work must address or isolate the canonical parent
lifecycle-evidence completion before a fresh A/B/C population; four-boundary
validation and Collision OFF/ON remain stopped.

Regression completed with Python compilation, focused fixture 30/30, Release
build, the standard 8-process/78-test suite, and devlog static validation.
Phase 0 RTX and Phase 3 were omitted because the change is confined to
diagnostic session validation/runner code and documentation: production source,
generated production USD, rendering inputs, wood authority, Flow inputs,
defaults, Point policy, V3, public scene, and latest demo hashes are unchanged.
