# Phase 6GE public color-export slot diagnostic

Phase 6GD remains frozen: its divergence operation established direct evidence
for `handle[5]`, its final lifecycle outcome remains
`unknown_shutdown_failure`, and its RGBA control remains a pre-readback 16 GiB
resource safe stop. Phase 6GE neither retries nor reclassifies those artifacts.

The only purpose of Phase 6GE is to compare three fresh S93 processes at the
first frame-180 public readback: C0 has RGBA/RGB disabled, C1 enables only
`FlowSparseNanoVdbExportParams.rgbaEnabled`, and C2 enables only
`FlowSparseNanoVdbExportParams.rgbEnabled`. Geometry, 1,344/1,440 Point
payload, payload-native source hashes, Flow/RTX settings, transform, timeline,
and readback frame are unchanged. Each process owns a fresh stage, Flow state,
and artifact directory. Metadata is collected sequentially from `handle[0]`
through `handle[6]`; no `numpy.asarray`, full-field JSON/NPZ, spatial metric,
flux, deep-velocity, capture, or video is allowed. After the first metadata is
durable the process closes without the former post-readback stability window.

The frozen contract is
`campfire.phase6ge.color-slot-diagnostic-contract.v1`, SHA-256
`7F4F06F7F68250F0C7D857A3A6462269D357548AB3500A8500CBC61B18F3BB29`.
Only these three identification processes receive the temporary diagnostic
ceilings: Kit 20 GiB, unique tree 21 GiB, runner/diagnostic 512 MiB each, and
physical/commit floors 32 GiB each. These values cannot replace the qualified
16/17 GiB Phase 6FZ/formal limits and cannot be raised after runtime. Any
ceiling or floor violation is a nonreplaceable safe stop.

Mapping requires one changed index, unchanged metadata at every other index,
one-to-one correspondence with the enabled attribute, and identical geometry,
payload, active Point, and source hashes. Value ranges and appearance are not
evidence. If both controls change handle 6 with distinct public types it may be
recorded as a setting-dependent color-export slot; ambiguous or multiple-index
changes keep it unknown.

The parent runner correction is part of the preflight. Every next condition
requires functional pass, lifecycle `normal_exit`, accepted normal-exit sample,
process exit code zero, exact cleanup, and residual zero. Eight fixture cases
accept only the fully normal result and reject functional failure, unknown
lifecycle, rejected/missing OS exit, missing process exit, residual, and
incomplete cleanup. Metadata committed before a later lifecycle failure remains
partial schema evidence, but the failing process is not a normal sample and no
later condition starts.

If mapping is unambiguous, this Phase may emit a Flow 110.0.0 / Kit 110.2
candidate schema plus offline count/order/type fixture. It must stop before the
formal S93 channel preflight, S93/S100/OFF population, directional metrics,
video, S100 adoption, production integration, defaults, V3, P4, or dynamic
geometry.

## Phase 6GE pre-Kit safe stop and Phase 6GF correction

The first Phase 6GE root stopped before Kit because the reused case runner's
`ReportPhase` `ValidateSet` ended at `phase6gd`. Resource telemetry recorded Kit
peak zero, the intended 20/21 GiB and 32 GiB limits, and exact cleanup with no
residual. C1 and C2 were not started. This is a parameter-binding harness defect,
not schema, Flow, resource, or lifecycle evidence, and the root is frozen.

Phase 6GF changes only that boundary by adding the explicit diagnostic report
token and exercising the real case runner with `-ValidateArgumentsOnly` before
Kit. It uses a new contract and empty runtime root; no Phase 6GE artifact is
reused and all diagnostic, physical, mapping, and next-condition gates remain
identical.

Phase 6GF C0 then completed all child-process gates: seven-handle metadata was
durable, Kit exited normally with code zero, exact cleanup passed, and residual
was zero. The outer orchestrator nevertheless recorded a safe stop because its
PowerShell `Start-Process` object exposed a null `ExitCode` after completion.
C1/C2 were not started. Phase 6GG freezes that root and launches a new complete
population; it changes only exit-code propagation to the external command's
deterministic `$LASTEXITCODE` while retaining direct stdout/stderr files.

## Phase 6GG startup safe stop

The direct `$LASTEXITCODE` fixture passed, but the fresh Phase 6GG C0 process
failed the already-frozen representative-startup prerequisite before any public
readback. All 120 fresh samples reported 24 active blocks. Timeline telemetry
was fresh, the emitter was enabled, the exact 1,344/1,440 Point payload and its
canonical SHA matched, and all float32 source sums matched exactly; nevertheless
the classification was `small_field_ingestion`, so readback was not permitted.

This is functional/startup evidence, not handle metadata and not a resource
failure. The process completed release-after-close and `shutdown_complete`, was
observed exiting during the normal grace interval, and exact cleanup found no
residual. Its deliberate probe error produced exit code 1, so the frozen
three-axis outcome is not a normal accepted sample. Kit/tree peaks were
11,609,899,008 / 11,773,349,888 bytes, leaving 9,864,937,472 /
10,775,228,416 bytes below the temporary 20/21 GiB diagnostic limits. CDB was
not invoked; fatal, dump, upload, and residual counts were zero.

The next-condition contract therefore stopped the population. C1 RGBA-only and
C2 RGB-only were not started, `handle[6]` remains unknown, no candidate schema
or schema fixture exists, and formal channel preflight remains blocked. This
root is frozen and must not be retried or reclassified. The ordinary 16/17 GiB
contract remains unchanged; the 20/21 GiB limits remain diagnostic-only.

Release build, Phase 0 RTX, Phase 3 with zero dry/wet mass-balance error,
focused Phase 6F 212/212, focused Phase 6G 32/32, standard 78/78, and devlog
validation passed. The production app and latest-demo manifest hashes remained
unchanged, and final Kit/CDB/GPU-helper residual counts were zero.
