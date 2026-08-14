# Phase 6GI S93 public-channel preflight

Phase 6GH remains frozen as candidate identification and contributes no runtime
sample to this Phase. Phase 6GI froze contract SHA-256
`5A6A943B84CA0A2D987BEA22585F287026529AB7A2600050898599DA1A467784`
before runtime. It requires one fresh corrected-four S93 process, divergence
enabled, RGBA/RGB disabled, one public readback at frame 180, the ordinary
16/17 GiB resource limits, release-after-close, and at most two replacements
for the exact startup-prerequisite failure only. Operation, schema, resource,
pointer, lifecycle, artifact, identity, and cleanup failures are nonreplaceable.

The offline versioned-schema fixture passed 20/20 and the inherited startup
replacement fixture passed 12/12. Attempt 01 had representative ingestion from
frame 1, reached 1,329 active blocks at frame 180, and exactly matched the
1,344/1,440 Point payload, revision, canonical SHA, and payload-native float32
fuel/temperature/smoke sums. The one public readback returned seven handles.
The raw schema passed before semantic mapping: temperature, fuel, burn, smoke,
velocity, and enabled divergence were nonempty with the expected grid classes,
value types, shapes, logical sizes, and positive pointers; disabled RGBA was an
empty uint32 array. Every returned-list slot was cleared sequentially and all
seven Python weak references were dead without forced GC. No `np.asarray`,
material copy, field-body JSON/NPZ/OpenVDB output, spatial aggregation, flux, or
deep-velocity work occurred.

The formal preflight then failed on `alias_contract_mismatch`. All six nonempty
channels were same-object aliases and `numpy.shares_memory` returned true.
Empty handle 6 was also the same Python object, had zero elements/bytes, and
was released without a weak-reference residual, but NumPy correctly returned
false for `shares_memory(empty, empty)` because no element can overlap. The
Phase 6GI implementation had incorrectly required a true sharing predicate for
every handle instead of treating same-object/zero-byte/no-copy as the empty
alias contract. This is a harness operation failure, not evidence of a schema,
Flow, Point, resource, or native lifecycle failure. It is not eligible for the
startup-only replacement policy, so no second launch occurred and Phase 6GI is
frozen as a safe stop rather than retrospectively corrected.

Kit/tree peaks were 15,099,490,304 / 15,263,600,640 bytes, leaving
2,080,378,880 / 2,990,010,368 bytes below the unchanged 16/17 GiB limits.
Stage close completed in 62.417672 seconds, `shutdown_complete` was durable,
and exact cleanup found no Kit/CDB/GPU-helper residual. The deliberate
operation error produced exit code 1, so it is not an accepted normal-exit
sample; CDB was not invoked and fatal/dump/upload counts were zero.

The candidate schema is therefore not yet formally preflight-qualified.
Formal S93/S100/OFF, directional flux, deep velocity, comparison video,
production adoption, defaults, Point integration, V3, P4, and dynamic geometry
remain unstarted. A future explicitly approved Phase must freeze an empty-array
alias rule before runtime and use a new artifact root; Phase 6GI may not be
retried or reclassified.

Final regression passed the Release build, Phase 0 RTX, Phase 3 with zero
dry/wet mass-balance error and wood-owned Flow input (active blocks final/peak
303/323, peak fuel 1.0), focused Phase 6F 212/212, focused Phase 6G 46/46, and
the standard eight-process 78/78 suite in 348.6 seconds. Devlog validation
passed 484 references, 289 unique IDs, 241 JSON, 177 SVG, and two ZIP files.
Production app SHA-256 stayed
`94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`;
the latest-demo manifest stayed
`1C6FB249EAE8DF09E804680C7D0459BA8631D4ECFF4903944FFA4701E94E6285`.
