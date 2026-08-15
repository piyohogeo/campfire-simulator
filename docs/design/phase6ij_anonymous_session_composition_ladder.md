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
