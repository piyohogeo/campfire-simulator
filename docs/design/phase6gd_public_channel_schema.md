# Phase 6GD public NanoVDB channel schema

Phase 6GC remains frozen at its seven-handle, pre-indexing safe stop. Phase 6GD
changes only the public readback schema boundary. Its discovery contract is
`campfire.phase6gd.public-channel-schema-discovery-contract.v1`, SHA-256
`FFD0D34F35A645B433334900F745C91D861BCAD5FE15703279409E64480A55A2`.
The Phase 6GC geometry, Point payload, payload-native source contract, Flow,
RTX, sampling frame, resource limits, release-after-close lifecycle, durable
commit, CDB, identity, cleanup, and replacement rules are unchanged.

The discovery process performs one S93 public readback at frame 180 and labels
the result only as `handle[0]` through `handle[n-1]`. It records direct Python
array metadata without `numpy.asarray`, then passes one handle at a time through
public `buffer_to_volume` / `omni.volume` metadata. A temporary uncompressed
NanoVDB is limited to 256 MiB per handle and 512 MiB total, is read only for
bounded grid metadata, and is deleted before the next lifecycle stage. No full
field JSON/NPZ, semantic value sampling, private API, forced GC, or formal
S93/S100/OFF run is allowed by the discovery contract.

Evidence priority is fixed before runtime: formal public grid/channel name,
bundled Flow 110.0.0 public definition, unique grid class/value type, a later
single-variable control probe if necessary, then scalar/vector distinction.
Value range or visual plausibility is not mapping evidence. Unavailable public
metadata is recorded as unavailable. If the seventh handle remains ambiguous,
the Phase stops without producing a versioned operational schema or restarting
the comparison.

The bundled Flow 110.0.0 `FlowNanoVdbReadback` OGN definition is read-only
reference evidence and exposes six named outputs: temperature, fuel, burn,
smoke, velocity, and divergence. It does not explain the Python binding's seven
returned objects, so its six-output order must not be mechanically extended.

The first completed baseline artifact is
`artifacts/phase6gd-channel-schema-discovery-2`. It returned seven objects. The
first four were nonempty scalar-like public volume buffers, the fifth was a
nonempty vector-like public volume buffer, and the final two were empty. All
seven supported weak references and none remained alive after sequential
release. Public metadata exposed the grid name `Flow`, but no semantic channel
name, so this evidence does not yet distinguish the two empty slots. The Kit
process exited normally and exact cleanup found no residual process.

A separate control contract,
`campfire.phase6gd.public-channel-schema-control-contract.v1`, freezes three
one-variable probes in the order divergence, RGBA, RGB. Each probe changes only
the corresponding public `FlowSparseNanoVdbExportParams` enable attribute on
the completed offline stage. A control may identify an index only when its
schema change is unique and repeatable relative to the frozen baseline. An
ambiguous result remains a safe stop; value range and visual appearance remain
inadmissible mapping evidence.

## Runtime outcome and safe stop

The divergence control completed its metadata operation and changed only
`handle[5]` from an empty array to a nonempty scalar public-volume buffer
(8,289,664 logical bytes).
The metadata SHA-256 values for handles 0--4 and 6 were unchanged. This is
direct one-variable evidence that index 5 is divergence. Stage close took about
2.66 seconds, but Kit did not exit within the frozen grace period. Bounded CDB
captured all-thread native stacks and modules and completed explicit detach.
The diagnostic stack fingerprint contained all five accepted NGX tokens, while
the frozen outer classifier still recorded `known_signature_matched=false` and
the final outcome remained `functional_status=fail`,
`lifecycle_status=unknown_shutdown_failure`, with no normal-exit sample. This
Phase does not reclassify that result. Kit/tree peaks were
15,737,917,440/15,850,504,192 bytes and exact outer cleanup found no residual
process.

The Phase 6GD parent metadata runner originally accepted raw
`shutdown_complete` plus its own guard exit and did not propagate the final
functional/lifecycle/OS-exit axes. That harness defect allowed the RGBA control
to start. It is now corrected fail-closed: later controls require functional
pass, lifecycle `normal_exit`, accepted normal-exit sample, and process exit
code zero. The divergence and RGBA artifacts remain frozen and neither Kit
condition was rerun.

The next frozen control enabled only `rgbaEnabled`. It reached the unchanged
16 GiB Kit hard limit at startup frame 100, before the frame-180 readback and
before any schema metadata call. The guard observed a Kit peak of
17,541,881,856 bytes, 362,012,672 bytes above the limit, stopped the exact
attempt tree, and confirmed all observed processes absent. The last durable
marker retained a live timeline, 991 active blocks, the expected 1,344 active
Points, revision 1, and exact payload hashes/source sums. No RGB control was
started after this nonreplaceable resource failure.

Consequently `handle[6]` remains unknown. The native Flow export structure
contains public enable attributes for both RGBA and RGB, but neither field name
may be assigned to the Python binding's seventh slot by structural guesswork.
There is no operational seven-channel schema ID and no schema fixture yet;
those are conditional on an unambiguous mapping. The S93 channel preflight,
formal 9-process S93/S100/OFF population, scalar/flux evaluation, and video all
remain unstarted. Phase 6GC is not reclassified and production is unchanged.

Final verification passed the Release build (7.06 seconds), Phase 0 RTX,
Phase 3 with dry/wet mass-balance error zero and wood-owned Flow input, focused
Phase 6F 212/212, focused Phase 6G 22/22, and the standard 8-process 78/78
suite (348.2 seconds). Devlog validation reported 479 references, 286 unique
IDs, 238 JSON, 177 SVG and 2 ZIP artifacts. Production app SHA-256 remained
`94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`;
the latest-demo manifest remained
`1C6FB249EAE8DF09E804680C7D0459BA8631D4ECFF4903944FFA4701E94E6285`.
No dump or partial dump was created, automatic upload remained disabled, and
the final Kit/CDB/GPU-helper residual count was zero.
