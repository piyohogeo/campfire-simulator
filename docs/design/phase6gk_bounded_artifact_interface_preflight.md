# Phase 6GK bounded artifact interface preflight

Phase 6GJ remains a frozen nonreplaceable artifact safe stop. Its runtime
operation, normal Kit exit, exact cleanup, artifact root, and parent
`artifact_failure` classification are historical evidence only; this Phase
does not edit, reuse as a population sample, or reclassify them. Phase 6GK
freezes contract SHA-256
`849D5F778073977EF105DC2A1D63BADA96E56BC06A76820D1F17F458BF12E42E`
before runtime and authorizes only an artifact-interface correction followed by
one fresh corrected-four S93 public-channel preflight in a new root.

## Property audit and canonical boundary

The producer and consumer audit found two names for the same bounded-output
fact:

- `field_body_json_npz_or_openvdb_written` is emitted by the Phase 6GI/6GJ
  bounded channel observation. It states that no field body was written as
  JSON, NPZ, or OpenVDB.
- `full_field_json_or_npz_written` is emitted by the older Phase 6GD metadata
  result, consumed by the shared PowerShell runner, and read by the Phase 6GH
  diagnostic summarizer. It expresses the same prohibition but omits OpenVDB
  from its name.

Phase 6GK therefore makes
`field_body_json_npz_or_openvdb_written` canonical. New runtime artifacts emit
only that property. The parent runner evaluates only a canonical normalized
object and never uses a missing-property exception as classification. The
normalization boundary accepts a boolean legacy-only value while recording
`legacy_normalized`; equal dual values become one canonical value while
recording `dual_equal_normalized`. Conflicting dual values, absence, null,
strings, numbers, and other nonbooleans fail closed. A canonical true value is
an explicit `field_body_write_detected` failure.

The pre-Kit end-to-end fixture invokes the actual shared PowerShell child with
the same JSON object shape used by the runtime. It covers canonical false and
true, missing, legacy-only, equal and conflicting dual properties, null,
string, number, wrapper-to-parent exit-code propagation, and a read-only round
trip of the frozen Phase 6GJ raw artifact. All inputs, normalized objects,
normalization reports, wrapper reports, and child exit codes are bounded files.
The fixture must pass before Kit may start.

## Preserved preflight and safety boundary

Phase 6GK reuses the Phase 6GJ state-aware alias contract. Handles 0--5 must be
nonempty same-object aliases with shared memory and exact schema metadata.
Disabled RGBA handle 6 must be the same object, zero elements and bytes, create
no material copy, and leave no weak-reference residual; shared-memory overlap
is not required for an empty array. The runtime performs exactly one public
readback at frame 180 with divergence on and RGBA/RGB off, releases all seven
handles in order, and writes only bounded metadata. NumPy conversion, material
copy, field-body JSON/NPZ/OpenVDB, spatial aggregation, flux, deep velocity,
image, and video are forbidden.

The normal 16/17 GiB Kit/tree limits, 512 MiB runner and diagnostic limits,
8 GiB physical and commit floors, release-after-close, progress-aware
stack-first CDB, durable markers, exact attempt-tree cleanup, and startup-only
limited replacement policy remain unchanged. Operation, schema, resource,
pointer, artifact, lifecycle, identity, or cleanup failure is nonreplaceable.
Formal S93/S100/OFF, production, defaults, Point placement, V3, P4, dynamic
geometry, and latest demo remain outside this Phase.

## Pre-runtime fixture result

The explicit shared-runner fixture passed 10/10, including all negative cases,
exit-code propagation, and the frozen Phase 6GJ raw-artifact round trip (SHA-256
`6CFA176358215331B42A15057CAD27DC095E4B22B39940F8436EF70B1257D3DB`).
The Phase 6GJ artifact was read only. Runtime preflight remains gated on the
state-aware alias/schema fixture and startup replacement fixture as well.

## Runtime result

All pre-Kit gates passed: state-aware schema/alias 22/22, bounded artifact
interface 10/10, and startup replacement 12/12. One fresh process was launched;
it was representative from frame 1, needed no replacement, and reported active
blocks 688/1,118/1,329 at frames 60/120/180. The single frame-180 public
readback returned the exact seven-handle order. Handles 0--5 were nonempty
same-object aliases with required shared memory and schema metadata. Disabled
RGBA was the same zero-element, zero-byte object, created no copy, and correctly
did not require shared-memory overlap. Ordered release left zero weak-reference
or ownership-container residual.

Both runtime bounded artifacts use only the canonical property with value
false. The shared runner recorded normalization mode `canonical_only`, no
compatibility conversion, and explicit interface pass. There were zero
`np.asarray` calls, material copies, or JSON/NPZ/OpenVDB field-body writes.
The versioned schema
`flow110.0.0-kit110.2-public-readback-rgba7-v1` is therefore formally
public-channel-preflight-qualified for this fixed S93 condition.

Kit/tree peaks were 15,106,207,744 / 15,271,022,592 bytes, leaving
2,073,661,440 / 2,982,588,416 bytes below 16/17 GiB. Runner/diagnostic peaks
were 129,908,736 / 16,207,872 bytes. Minimum physical and commit headroom were
83,184,029,696 / 102,789,419,008 bytes. Stage close took 3.052436 seconds;
functional pass, lifecycle `normal_exit`, OS exit 0, `shutdown_complete`, exact
cleanup, and residual zero all held. CDB was not invoked and fatal, dump,
upload, device-lost, and TDR counts were zero.

Release build, Phase 0 RTX, Phase 3 with zero dry/wet mass-balance error and
wood-owned Flow input (active blocks final/peak 239/353), focused Phase 6F
212/212, focused Phase 6G 58/58, and standard 78/78 passed. Production and
latest-demo hashes are unchanged. Devlog validation passed 488 references, 291
unique IDs, 243 JSON files, 177 SVG files, and two ZIP files. Formal
S93/S100/OFF, flux, deep velocity, video, production, defaults, Point
placement, V3, P4, and dynamic geometry were not started. Resuming them
requires a separate explicit authorization and a new artifact root.
