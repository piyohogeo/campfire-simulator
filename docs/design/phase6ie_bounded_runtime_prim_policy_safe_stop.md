# Phase 6IE bounded runtime Prim policy safe stop

Phase 6ID remains frozen at commit `b761a4a` as
`safe_stop_live_stage_prim_set_validation_failure`. Phase 6IE used a new
contract, preflight root, and runtime root. No Phase 6ID artifact or runtime
sample was reused or reclassified.

## Contract and offline qualification

The Phase 6IE contract SHA-256 is
`F951BBD78B895404D8B9BE77700FD032BF186D916EA5017B9C4EC443AB71BDC2`.
Implementation commit `f78f786` replaces the exact whole-live-stage Prim-set
assumption with a bounded, exact-path policy. It snapshots all 25 generated
stage Prims and their types, specifiers, defining layer, applied schemas,
authored properties, relationships, authored children, protected
classification, opinion layers, and the root-layer file digest. The live-stage
projection then separates those authored Prims from Kit additions.

The runtime allowlist is not a prefix wildcard. It contains exactly the 14
paths observed by Phase 6ID, with exact type, parent, maximum depth, expected
session-layer ownership, category limits, and a total maximum of 14. The
categories are four Kit cameras, five render-core Prims, two Hydra texture
Prims, one Flow debug Prim, and two Flow render Prims. Unknown paths, lookalike
names, wrong types or parents, root/external opinions, protected-subtree
intersections, relationships targeting protected inputs, changed or missing
authored Prims, and root-file hash changes are rejected.

The actual producer-to-consumer policy fixture passed 26/26 cases, including a
canonicalized replay of all 14 Phase 6ID runtime paths. Marker payloads passed
8/8. Inherited gates passed float3 22/22, Phase 6ID exact dependencies 18/18,
exact loader 12/12, Point-policy 13/13, and atomic report 15/15. The new
five-module manifest was parsed exactly and its four no-Kit-safe modules were
loaded 4/4. No Kit process ran during preflight.

## One actual Kit attempt

Exactly one fresh Kit process was launched from implementation commit
`f78f786`; retry and replacement counts are zero. Both registered-schema
stages were generated and parsed. Their only intended semantic difference was
`/World/Flow/Simulate.physicsCollisionEnabled`. Parser-side float3 evidence
for OFF and ON remained bit-exact at zero ULP. The OFF stage opened in the
actual Kit USD context.

The live projection found the same 14 paths and category counts as Phase 6ID.
There were no unknown paths, no missing authored Prims, and no protected path
or relationship conflicts. The file-backed root-layer SHA-256 remained
`D5668572776AC0B48E9C8AF193FF517631865D9203864DBBFA1B52EFB8B8E99C`
before and after open.

The policy nevertheless rejected the stage. Ten render/Hydra/Flow runtime
entries did not satisfy the predeclared session-only layer rule: their Prim
stacks included an in-memory root-layer opinion, and several defining specs
were reported in the generated root layer. In addition, the complete authored
records for `/World/Flow/Simulate` and
`/World/Flow/Simulate/nanoVdbExport` changed. The bounded evidence identifies
the paths and record hashes; it does not infer that these changes are safe.
The first operation failure was therefore
`runtime_prim_policy_rejected:authored_prim_changed:/World/Flow/Simulate`.
`required_prims_validated` and `operation_complete` were not reached.

## Lifecycle and resources

Error cleanup stopped the timeline, completed stage close in approximately
0.413 seconds, and persisted `shutdown_complete`, which is the last durable
marker. Kit did not then produce a natural exit or the parent runner evidence.
The log recorded three RTX semaphore fatal lines, device loss, and crash
reporter activation. One 7,212,176-byte dump and one 37,444-byte NVIDIA GPU
dump were preserved; automatic upload was not observed. CDB was not invoked.
The outer guard stopped after 180.77 seconds and exact identity cleanup
confirmed residual zero. Operation, lifecycle, and cleanup are therefore
reported separately as failure, failure, and pass.

Kit/tree Private Bytes peaked at 4,431,814,656 / 4,577,067,008 bytes, leaving
12,748,054,528 / 13,676,544,000 bytes below the 16/17 GiB limits.
Runner/diagnostic peaks were 95,936,512 / 17,010,688 bytes. Available physical
memory and estimated commit headroom minima were 82,583,556,096 and
102,546,468,864 bytes. No resource gate failed.

## Verification and scope

The Release build passed in 9.17 seconds. The standard eight-process suite
passed 78/78 tests in 329.8 seconds. The relevant Phase 6IB, 6ID, and 6IE
focused tests passed 8/8, and Python compilation passed. The intentionally
frozen Phase 6IC direct-manifest test remains stale against the later
Phase 6ID authoring source and reports its expected SHA mismatch; the inherited
dependency regression used by this Phase passed 18/18 against the frozen
Phase 6ID manifest. Static devlog validation is recorded with the result.
Phase 0 RTX and Phase 3 were not repeated because production code, production
USD generation, rendering configuration, wood authority, physical inputs, and
Flow inputs did not change.

Phase 6IE is `safe_stop_runtime_prim_policy_and_lifecycle_failure`. It does
not qualify the live-stage policy, complete required-attribute validation, or
the single-log OFF/ON comparison. No timeline play, Flow update, public Flow
interface, NanoVDB readback, capture, image, or video operation ran.
Production, defaults, Point policy/payload/revision/ordering, wood authority,
V3, public scene, and latest demo remain unchanged. A separately approved
Phase must decide whether and how Kit's in-memory root opinions and the two
authored-record changes can be represented by a narrower evidence-backed
contract; Phase 6IE must not be retried or relaxed in place.
