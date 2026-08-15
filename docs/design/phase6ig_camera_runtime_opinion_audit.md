# Phase 6IG: `/OmniverseKit_Persp` in-memory opinion audit

Date: 2026-08-16  
Baseline: `d1e660f`  
Runtime population: one Collision-OFF process, no retry or replacement

## Frozen history

Phase 6IF remains `safe_stop_audit_operation_incomplete`. Its artifact,
contract, thresholds, and classification are not changed or reused as a new
runtime sample. Its preserved layer exports are used only as read-only design
evidence: the camera was absent in the generated stage, appeared in the
session layer at live open, and received three exposure opinions in the root
layer after one stopped Kit update.

## Contract fixed before runtime

The audit target is exactly `/OmniverseKit_Persp`. Four ordered snapshots are
required: `generated`, `live_open`, `post_stopped_update`, and `preclose`.
The only accepted layer stack is the generated root layer plus its anonymous
session layer. The accepted property set is limited to the eight session
camera/xform properties and the three root exposure properties recorded in
the frozen Phase 6IF evidence. Unknown paths, layers, attributes, metadata,
relationships, children, schema applications, protected-semantic changes,
disk root changes, hash contradictions, and oversized evidence fail closed.

The subsystem attribution is deliberately an inference: exact path, Camera
type, session-layer creation at live open, and exposure opinions after one
stopped Kit update are consistent with Kit viewport/camera augmentation. No
public owner API is claimed.

No timeline play, Flow update/interface, NanoVDB readback, capture, production
allowlist, Collision OFF/ON comparison, or production/default mutation is in
scope. Resource limits remain Kit 16 GiB and unique tree 17 GiB.

## Preflight

Contract SHA-256:
`551ED00172EF246A3D6B720783C61B3295896B6B10CA35D4E0C016A580E94244`.

The no-Kit camera fixture passed 8/8 cases: the exact harmless augmentation
and fail-closed protected change, unknown layer, missing property, duplicate
property, hash contradiction, unknown metadata, and oversize cases. The full
marker fixture also passed. Seven exact-loaded dependencies matched their
frozen SHA-256 values. The preflight launched Kit zero times.

Runtime outcome is recorded separately after the single authorized process.
