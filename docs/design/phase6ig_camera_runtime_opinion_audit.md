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

## Single-process result

The sole authorized process stopped at the `live_open` camera snapshot with
`camera_property_set_unknown_or_incomplete`. The generated snapshot was
complete and confirmed that the camera was absent, the file-backed root was
clean, and the generated root/file SHA-256 was
`D5668572776AC0B48E9C8AF193FF517631865D9203864DBBFA1B52EFB8B8E99C`.

The live-open layer exports are durable bounded partial evidence. The session
layer contained the expected Camera definition and eight camera/xform
properties. Unlike the frozen Phase 6IF observation, however, the in-memory
root already contained `exposure:fStop`, `exposure:responsivity`, and
`exposure:time` before the one stopped update. The contract expected those
root opinions only after that update, so the first changed-time boundary was
not accepted. This is evidence that opinion timing was not stable across the
two observations; it is not evidence for a broader allowlist.

The root file on disk remained 8,254 bytes with the same SHA. The live
in-memory root export was 12,853 bytes (`60821BAB...A7FF`), and the live
session export was 3,476 bytes (`2BDFE38E...482F`). Because the live snapshot
failed before its canonical document commit, no claim is made that the
protected-semantic digest was validated at all four requested boundaries.

Cleanup remained independent of the operation failure. Stage close completed
in 0.344443 seconds, `shutdown_complete` was durable, Kit exited 1 by the
fail-closed path, and exact cleanup ended at residual zero. No fatal, native
exception, device loss, TDR, CDB, dump, or upload occurred. Kit/tree peaks
were 7,467,442,176 / 7,954,870,272 bytes, leaving 9,712,427,008 /
10,298,740,736 bytes below the 16/17 GiB ceilings.

Final classification: `safe_stop_camera_opinion_unresolved`. Phase 6IF is not
reclassified. The next separately approved boundary is to isolate runtime
render/camera authoring from the diagnostic root; applying any camera
allowlist or restarting Collision OFF/ON is not justified by this result.

## Regression

- Focused no-Kit tests: 2/2; camera cases 8/8; complete marker payloads pass
- Python compilation: pass
- Release build: pass, 7.95 seconds
- Standard suite: 8/8 processes, 78/78 tests, 331.9 seconds
- Static devlog validation: pass
- Phase 0 RTX / Phase 3: omitted because production source, production USD
  generation, rendering code/settings, wood authority, Flow inputs, defaults,
  Point policy, V3, and latest demo were unchanged. The only actual stage was
  a stopped-timeline, no-Flow-update, no-capture diagnostic audit.

## Evidence

- [Machine summary](../../artifacts/phase6ig_camera_opinion_20260816_01/summary.json)
- [Generated camera snapshot](../../artifacts/phase6ig_camera_opinion_20260816_01/attempt01/generated_camera_snapshot.json)
- [Live root export](../../artifacts/phase6ig_camera_opinion_20260816_01/attempt01/layer-exports/live_open_root.usda.txt)
- [Live session export](../../artifacts/phase6ig_camera_opinion_20260816_01/attempt01/layer-exports/live_open_session.usda.txt)
- [No-Kit preflight](../../artifacts/phase6ig_camera_opinion_preflight_20260816_01/summary.json)
