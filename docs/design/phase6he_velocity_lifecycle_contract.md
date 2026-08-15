# Phase 6HE velocity sub-boundary lifecycle contract

Phase 6HD remains frozen as a Candidate lifecycle safe stop. No Phase 6HD
artifact, classification, or runtime sample is changed, upgraded, or reused.
Phase 6HE starts from fresh stages and processes under contract SHA-256
`C611A4805D91C544006BAB6E1232EC973444142659CCA6A270DCE37D07D051B1`.

## Audited Phase 6HD D path

The actual helper used by D is imported by the shared probe from
`probe_phase6dt_flow_collision_reference._save_and_sample`. For velocity it
executes, in order: `buffer_to_volume`, `SaveVolumeParameters` with
`kNanoVDBCodecNone`, `save_volume`, a bounded file-durability poll,
`nanovdb.io.readGrid`, `vec3fGrid`, `voxelSize` and `activeVoxelCount`, five
calls to `_sample_grid` in the existing ROI order (`scene`, `inter_log_gap`,
`flame_rise`, `opposite_above`, `side_control`), `_profile_grid` for `scene` at
threshold `0.01`, temporary-file unlink, function-local release, and caller
ordered alias/handle release. Local ROI and spatial collector branches were
disabled in D.

Condition C had already processed slots 1--5, including velocity, through a
separate schema conversion, volume metadata, temporary save, and typed read.
Phase 6HE therefore isolates the *second*, spatial-analysis velocity path; it
does not test the first-ever use of these APIs.

The diagnostic-only optional stop and observer parameters were added to the
existing helper with defaults of `None`. Existing callers keep the same
selected native call order. The no-Kit fixture compares that order against the
exact helper source frozen at `cefa061`, verifies that no existing caller opts
into the stop mechanism, and confirms that V7 reaches the final applicable
profile step with the same velocity channel, path format, ROIs, threshold, and
collector-disabled arguments as Phase 6HD D.

## One-shot ladder

Every condition rebuilds Phase 6HD C as a common prefix in a new process.

| Condition | Sole new boundary after the preceding condition |
|---|---|
| V0 | none; fresh Condition C control |
| V1 | velocity alias selection and bounded metadata |
| V2 | second `buffer_to_volume`, then immediate function-scope release |
| V3 | parameters, `save_volume`, durability check, and allowlisted deletion |
| V4 | `nanovdb.io.readGrid`, then handle-scope release |
| V5 | `vec3fGrid`, voxel size, and active voxel count |
| V6 | the five existing `_sample_grid` calls; no profile |
| V7 | the existing `_profile_grid` call |

V3 necessarily groups parameter construction, save, and durability because a
durable file cannot be checked without those preceding operations; this is the
smallest useful public-API boundary. V5 similarly groups the vector-grid view
with its two bounded basic accessors. V8 is not scheduled: V7 uses the actual
helper through its final applicable step, while disabled local/collector
branches add no call. The offline equivalence fixture makes an extra identical
native process unnecessary.

Each condition runs once with no retry or replacement. V0 must pass canonical
operation evidence, release, weak residual, stage close, `shutdown_complete`,
natural exit code 0, resource gates, exact cleanup, and final residual zero
before V1 starts; the same rule applies sequentially. The first non-normal
condition stops the Phase.

## Canonical counters and safety

`phase6he_operation_schema.py` is the sole counter owner. It retains all 15
Phase 6HD counters and adds `velocity_alias_metadata`,
`velocity_second_conversion`, `velocity_file_save`,
`velocity_file_durability_check`, `velocity_file_read`,
`velocity_vector_grid_access`, `velocity_basic_metadata`,
`velocity_roi_sampling`, `velocity_profile`, and
`velocity_temporary_file_deletion`. The shared factory emits every key as an
exact integer zero. Runtime producer, bounded writer, reader, normalizer,
validator, and fixture all import this same schema. Missing, forbidden
nonzero, invalid-type, and unknown keys have distinct fail-closed reasons.

Kit/tree limits remain 16/17 GiB, runner/diagnostic limits 512 MiB, physical
and commit floors 8 GiB, stage close 180 seconds, and simultaneous Kit count
one. Temporary deletion is restricted to the five schema files and the exact
`p3_f0180_velocity.nvdb` attempt file. Unknown files are not deleted and fail
cleanup. Spatial collector use, every temperature native operation, other new
channel work, formal comparison, video, and production/default/Point/V3/P4
changes are prohibited.
