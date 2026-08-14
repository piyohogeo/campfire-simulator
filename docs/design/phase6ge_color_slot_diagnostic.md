# Phase 6GE public color-export slot diagnostic

## Phase 6GH result: startup-gated identification

Phase 6GG remains frozen at its C0 small-field safe stop and is not reused or
reclassified. The independent Phase 6GH contract adds a short representative
startup gate to every C0/C1/C2 process. The gate requires at least 128 active
blocks, fresh timeline/update telemetry, an enabled Emitter, exact 1,344/1,440
Point identity, and exact float32 source sums before the single metadata
readback. An all-24 120-frame startup may consume one of only two predeclared
population-wide replacement slots; no operation, resource, lifecycle, cleanup,
identity, or post-readback failure is replaceable. Offline replacement-policy
fixtures passed 12/12 before Kit was launched.

The fresh root `artifacts/phase6gh-color-slot-diagnostic-1` completed C0, C1,
and C2 in three launches with no replacement. Each process was representative
at frame 1 with 269 active blocks, reached 1,124 blocks during the 120-frame
startup gate, retained payload SHA-256
`0D3B074B7BE3E482E8702A126A11619D87F587C4848C80D4A3162A11B876C389`,
and recorded fuel/temperature/smoke source sums
`1075.2000160217285 / 2688.0 / 107.51999759674072`. All three completed one
frame-180 bounded metadata readback, release-after-close, normal OS exit, exact
cleanup, and residual zero. CDB was not invoked.
Stage-close times were 2.673884 / 14.961279 / 4.014062 seconds for C0/C1/C2;
the explicit ownership container retained four observable referents at close,
then reached zero slots after release. Three of four weak referents remained
alive through external Kit/USD ownership at the immediate in-process check, so
they are not described as Python leaks; direct Flow/provider/emitter references
were absent by `shutdown_complete`, OS exit was normal, and exact process
cleanup found no residual.

C0 (RGBA OFF/RGB OFF) left handle 6 empty. C1 changed only
`rgbaEnabled`; only handle 6 changed, becoming a 179,184,672-byte `uint32`
public buffer containing one `Flow` grid with grid class 0, value type 17,
index bounds `[-96,-96,-16]..[127,111,639]`, and world bounds approximately
`[-2.4,-2.4,-0.4]..[2.4,2.4,15.6]`. Its metadata SHA-256 changed from
`4A57F039...` to `9609E73B...`; handles 0--5 remained metadata-identical. C2
changed only `rgbEnabled` and all seven metadata hashes remained identical to
C0. Thus handle 6 is the RGBA export slot under Flow 110.0.0 / Kit 110.2. RGB
does not share this slot and no separate returned RGB slot was observed. This
conclusion uses only one-variable metadata change, not values or appearance.

The versioned candidate schema is
`flow110.0.0-kit110.2-public-readback-rgba7-v1`, SHA-256
`06BAF639E07E7585CB6ED79FFBA6229EA118F450A34BAD1F3EC1228EA59DD8B9`.
It records the existing temperature/fuel/burn/smoke/velocity/divergence order
and the newly identified RGBA slot. Its 12/12 offline fixtures accept RGBA
enabled/disabled forms and reject missing/added/reordered/duplicate handles,
class or value-type mismatch, unknown handles/versions, required empty fields,
and the legacy six-handle schema. Unknown future schemas are never corrected.

Kit peaks for C0/C1/C2 were 14,977,552,384 / 17,744,617,472 /
17,760,870,400 bytes, leaving 6,497,284,096 / 3,730,219,008 /
3,713,966,080 bytes below the diagnostic 20 GiB ceiling. Tree peaks were
15,141,261,312 / 17,907,589,120 / 17,924,362,240 bytes, leaving
7,407,316,992 / 4,640,989,184 / 4,624,216,064 bytes below 21 GiB. Runner and
diagnostic children stayed below 512 MiB and physical/commit minima stayed
above 32 GiB. These ceilings remain diagnostic-only; the normal/formal 16/17
GiB contract is unchanged.

This Phase stops at schema identification. The candidate has not passed a fresh
S93 channel preflight, and the formal S93/S100/OFF comparison, directional
flux, deep velocity, image/video work, Point adoption, production integration,
defaults, V3, P4, and dynamic geometry were not started. The next gate requires
explicit approval for a new preflight/root under the normal 16/17 GiB limits.

Final regression passed the Release build (8.59 seconds), Phase 0 RTX, Phase 3,
focused Phase 6F 212/212 and Phase 6G 42/42, and the standard eight-process
78/78 suite (339.6 seconds). Phase 3 retained zero dry/wet mass-balance error,
wood-owned Flow input, active blocks final/peak 263/346, and peak fuel 1.0.
Devlog validation reported 482 references, 288 unique IDs, 240 JSON, 177 SVG,
and two ZIP files. Production and latest-demo hashes remained unchanged; no
Kit, CDB, nvidia-smi, or NGX helper process remained.

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
