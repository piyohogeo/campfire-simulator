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
