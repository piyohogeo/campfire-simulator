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

