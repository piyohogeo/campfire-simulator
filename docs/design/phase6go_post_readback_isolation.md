# Phase 6GO post-readback native-operation isolation

Phase 6GN remains frozen as a nonreplaceable native-operation safe stop. Its
first S93 process returned seven public NanoVDB handles and durably wrote
`phase6gl_readback_after`, then exited with `0xC0000005` before the first
per-handle volume-metadata result was durable. No Phase 6GN sample is reused.

Phase 6GO is a diagnostic-only, one-condition-per-process ladder. It retains
the corrected S93 stage, 1,344/1,440 Point payload, qualified seven-channel
schema/export state, frame 180 readback, 16/17 GiB limits, release-after-close,
and exact identity cleanup. R0 releases unused handles, R1 reads Python object
metadata only, R2 tests one channel per process through `buffer_to_volume()` and
public volume metadata, and R3–R7 add temporary NVDB, selected schema checking,
sampling, near-Mesh collection, and directional transport in that order.

Every native boundary has paired, fsync-backed markers. The first abnormal
exit, dump, resource breach, missing marker, lifecycle failure, or cleanup
failure stops the entire ladder; there is no retry or replacement. Full-field
NumPy copies, forced GC, unbounded JSON/stdout, formal S93/S100/OFF comparison,
video, and production changes are outside this phase.

The Phase 6GN dump package is preserved byte-for-byte. Local-symbol CDB/WinDbg
analysis is supplementary: a quick-shutdown frame or incomplete-symbol stack
cannot identify the crashing API without agreement from the operation markers.

The machine contract is
`scripts/phase6go_post_readback_isolation_contract.json`; its SHA-256 is pinned
in the adjacent `.sha256` file before runtime.
