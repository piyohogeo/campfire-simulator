# Phase 6HM: Phase 6FZ process-tree reuse for one Flow proxy boundary

## Frozen input

Phase 6HL remains `safe_stop_resource_role_harness_failure` at `f1f5578`. Its
artifact, classification, contract, limits, and one failed launch are not
changed or reused as a Phase 6HM runtime sample.

The Phase 6HL failure was a harness topology error: Kit was the resource
guard's root PID. The frozen classifier therefore correctly called it
`runner`; Kit private bytes reached 1,845,035,008 while the `kit` role remained
zero, and the 512 MiB runner gate stopped the process before the probe.

## Read-only Phase 6FZ audit

The qualified Phase 6FZ launch topology was:

```text
C:\Python38\python.exe phase6fu_resource_guard.py
  -> powershell.exe run_phase6fz_memory_case.ps1       (runner)
       -> kit.exe                                      (kit)
```

All nine frozen Phase 6FZ attempts record a PowerShell guarded root, a direct
Kit child in the `kit` role, a separate diagnostic role, and no duplicate
`(pid, create_time_utc_epoch)` row in a sample. Kit exits through the case
runner; the case runner owns Kit lifecycle handling, while the Phase 6FU guard
owns bounded resource enforcement and exact cleanup of its observed tree.
Child stdout/stderr and GPU telemetry are streamed to files. The detailed
audit is emitted by Phase 6HM as bounded JSON and does not alter Phase 6FZ.

## Contract

Phase 6HM changes one variable only: it restores the Phase 6FZ topology. The
legacy role classifier is not redesigned. The guarded root is a small
PowerShell case runner and the case runner starts Kit as its child. The exact
Kit path is an explicit parameter, and a direct-Kit guarded root fails before
Kit launch.

Before the formal launch, a no-Kit process-role fixture must prove:

- `C:\Python38\python.exe` launches the unchanged Phase 6FU guard;
- the actual guarded root is PowerShell and is accounted as `runner`;
- child exit status propagates through PowerShell;
- stdout/stderr go directly to bounded files;
- Kit, diagnostic, unknown-child, and root-runner role decisions remain those
  of the frozen classifier;
- PID/creation-time deduplication and PID-reuse protection remain active;
- direct Kit root, path mismatch, missing summary, and unknown role are
  distinct fail-closed cases;
- guard, runner, and mock child leave no residual process.

Only after that fixture passes may one fresh Kit process run the unchanged
Phase 6HK/6HL one-proxy boundary. It adds only
`/World/Logs/Log_00/FlowCollisionProxy`, keeps the timeline stopped, advances
30 viewport frames, obtains the public Flow interface, performs no readback,
and uses release-after-close shutdown.

## Safety and scope

The frozen ceilings remain runner 512 MiB, Kit 16 GiB, diagnostic 512 MiB,
unique tree 17 GiB, and 8 GiB physical/commit floors. The tree sum includes
each PID/creation identity once. The first preflight, operation, resource,
lifecycle, identity, cleanup, or artifact failure stops the phase. There is no
retry or replacement and no limit is changed after seeing results.

Flow occlusion, dynamic transforms, PhysX Mesh sharing, Point Emitter
coexistence, 20-log performance, production/default integration, V3, P4, P5,
video, and all NanoVDB operations remain out of scope.
