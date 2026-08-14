# Phase 6GP metadata-only R1 qualification

Phase 6GN and Phase 6GO remain frozen. Phase 6GO R0 is still a lifecycle safe
stop: its public readback and ordered release completed, but Kit did not exit
naturally. Phase 6GP neither reuses that sample nor changes its classification.
It uses a fresh root and one independent S93 process.

The pre-runtime contract SHA-256 is
`8019F720DF4E32B797EAF546BE39B7AEE91247CEBBD5E55558BC9CA76C735111`.
The only allowed operation is one frame-180 public readback followed by the
constant-size Python metadata fields `slot`, `python_type`, `ndim`, `shape`,
`dtype`, `size`, `nbytes`, and `empty`. Element access, `np.asarray()`, material
copy, volume conversion, field save, schema-content inspection, sampling,
collectors, flux, image, video, R2, and the formal nine-process population are
excluded.

Operation and lifecycle are independent result axes. Completed metadata and
ordered release may be retained as partial operation evidence when lifecycle
fails, but metadata-boundary qualification requires a natural exit as well.
The shutdown-time low-level diagnostic path is disabled for this Phase; an
exit timeout preserves the bounded artifacts and uses exact identity cleanup
only.

## Result

The fresh root `artifacts/phase6gp-metadata-r1-1` launched exactly one process.
The public call returned seven `numpy.ndarray` slots. Slots 0--3 each reported
shape `[11910336]`, dtype `uint32`, and 47,641,344 logical bytes. Slot 4 reported
`[5415112]` and 21,660,448 bytes; slot 5 reported `[2072416]` and 8,289,664
bytes; disabled RGBA slot 6 reported `[0]`, zero elements, and zero bytes. No
array element or field body was read.

All slot metadata completed, ordered release reached
`phase6gp_reference_release_after`, and weak-reference residual was zero.
Timeline stop, release-after-close, stage close, and `shutdown_complete` were
durable. Stage close took 125.816074 seconds, below the frozen 180-second
limit. Kit exited naturally with code 0 and no outer-runner termination.

Kit/tree peaks were 14,940,184,576 / 15,103,287,296 bytes, leaving
2,239,684,608 / 3,150,323,712 bytes below the 16/17 GiB limits. Fatal, dump,
automatic upload, low-level diagnostic, and final residual counts were zero.
The result is therefore `operation=pass`, `lifecycle=normal_exit`, and Phase
6GP R1 metadata-boundary qualified.

## Continuation boundary

This result does not qualify volume conversion or any repeated readback.
The next smallest possible operation is one separately approved process that
converts only one preselected handle to a volume, with a new contract and empty
artifact root. R2 and the S93/S100/OFF population were not started. Production,
defaults, Point policy, V3, and P4 remain unchanged.

Release build, Phase 0 RTX, Phase 3, Phase 6GP/6GO/6GN/6GL focused fixtures,
the standard suite, and the devlog static check passed. Production app and
latest-demo SHA-256 values remained unchanged, and the final Kit/CDB/GPU-helper
residual count was zero.
