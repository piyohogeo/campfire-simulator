# Phase 6HP: junction-aware app-ready qualification and pre-proxy safe stop

## Frozen history and contract

Phase 6HO remains frozen at `de224b3`. Its contract, artifact, false-negative
classification, thresholds, and unmeasured proxy boundary were not edited,
reclassified, or reused as new runtime evidence. Phase 6HP uses new artifact
roots and contract
`campfire.phase6hp.junction-aware-app-ready-and-proxy-contract.v1`, SHA-256
`BEE59EA12B8AAA074D863F2ABB8AA28FA21718682637734E89A8CFEF0A8E15B0`.

The only intended change is the module-path gate. Kit/app launch spelling,
extension layout, Phase 6FU/FW process topology, resource limits, one-proxy
scope, and production invariants remain unchanged. The existing junction,
extension cache, and ACLs were inspected read-only and were not created,
removed, or modified.

## Junction-aware gate

The gate starts from extension manager identity
`campfire.app-0.1.0` and its lexical build root
`_build/windows-x86_64/release/exts/campfire.app`. It accepts only the declared
`campfire` child when all of the following agree:

- the extension ID, name, version, and lexical root;
- one reparse point with Windows mount-point/junction tag `0xA0000003`;
- the fixed resolved target
  `source/extensions/campfire.app/campfire` inside this repository;
- exactly one junction boundary and zero further reparse points in the target
  path;
- imported package/module names `campfire` and `campfire.app`;
- the imported module file's lexical and resolved locations under either the
  declared junction spelling or the fixed resolved target.

Arbitrary external targets, another extension target, wrong root/name/ID or
version, broken/non-junction paths, path traversal, junction chains, module
escape, and missing/duplicate/unknown/contradictory evidence fail closed.

## No-Kit fixture result

The fresh root `artifacts/phase6hp-junction-preflight-20260815` passed 23/23
cases with zero Kit launches. Both the source-spelled and lexical-junction
module paths passed the same runtime validator. All requested negative classes
were rejected. The exact PowerShell command and Phase 6FU guard binding were
also checked without starting a child process. The actual junction evidence
records tag `2684354563`, the fixed target, chain depth one, and target reparse
count zero.

## Fresh app-ready smoke

One process was launched from
`artifacts/phase6hp-app-ready-smoke-20260815`; there was no retry or
replacement. Kit reached app-ready, dependency solving succeeded,
`omni.anim.curve.core-1.6.0` loaded from build `extscache`, and
`campfire.app-0.1.0` loaded from build `exts`. The extension manager was
acquired, both imports succeeded, and the new junction gate passed. Durable
`operation_complete` and `shutdown_complete` markers exist. The Kit process
exited naturally with code 0.

The bounded parent summary classifies the smoke as `qualified`, with resource,
role, invariant, and final cleanup checks passing. However, the underlying
Phase 6FU guard document itself has `status=failed` and
`stop_reason=observed_descendant_residual`. It recorded child exit code 0 and
later exact cleanup reported `process_absent=true` and
`all_observed_absent=true`; the final machine residual is zero. Thus the raw
evidence contains an acceptance conflict: a transient observed descendant is a
guard failure but the parent treats the later all-absent cleanup as a pass.

Phase 6HP does not rewrite either artifact or decide after runtime that one
axis overrides the other. Because the instruction allowed the proxy only after
an unambiguous complete smoke pass, the conflict is fail-closed.

## Proxy boundary was not launched

No proxy artifact root was created and no proxy Kit process was launched. No
stage, production hierarchy, `FlowCollisionProxy`, viewport update, or public
Flow-interface call was measured. NanoVDB readback count remains zero. This is
a pre-proxy diagnostic/cleanup-classification safe stop, not evidence for or
against production-hierarchy proxy coexistence.

## Resource, lifecycle, and invariants

Smoke peak Private Bytes were runner 95,444,992, Kit 6,971,183,104,
diagnostic 17,219,584, and other child 62,386,176 bytes; unique-tree peak was
7,432,355,840 bytes. Minimum available physical memory was 86,633,455,616
bytes and minimum commit headroom was 106,314,379,264 bytes. The 512 MiB,
16 GiB, 512 MiB, 17 GiB, and 8 GiB floor limits all passed.

There was no native exception, dump, automatic upload, device loss/TDR, or CDB
attach. Final Kit/CDB/GPU-helper residual count is zero. Production app/source
app, scene, wood authority, V3, and latest demo hashes are unchanged. No visual
operation occurred, so no video was generated.

## Regression and next approval boundary

Focused tests passed 8/8, Python compilation passed, Release build passed in
6.56 seconds, the standard suite passed 8/8 processes and 78/78 tests in 306.4
seconds, and static devlog validation passed. Phase 0 RTX and Phase 3 were not
run because production source, USD generation, renderer configuration, wood
authority, and Flow input are unchanged and the proxy stage was never launched.

The junction-aware gate itself is qualified. The exact smoke is functionally
and lifecycle-complete but not accepted as an unambiguous overall prerequisite
because the guard/parent cleanup classifications conflict. A future separately
approved Phase must first define one canonical rule for transient descendants
that subsequently pass exact identity cleanup, verify that rule offline against
both pass/fail cases, then use a fresh smoke root. Only an unambiguously accepted
smoke may start the unchanged one-proxy boundary. Dynamic transforms,
occlusion, PhysX sharing, 20-log performance, Point policy, production
integration, and NanoVDB work remain unqualified and out of scope.
