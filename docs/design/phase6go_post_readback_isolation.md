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

## R0 result and narrowed stop

R0 alone was launched in the fresh root
`artifacts/phase6go-post-readback-isolation-1`. The public call returned a
`builtins.list` of seven `numpy.ndarray` objects. No handle metadata, volume
conversion, sampling, collector, field file, image, or video operation ran.
Ordered slot clearing left zero weak-reference residual. The operation marker
ended at `phase6go_release_sequence_after`.

Timeline stop, renderer drain, `close_stage_async()`, USD detach, post-close
updates, and `shutdown_complete` all became durable; stage close took about
12.33 seconds. Kit nevertheless did not produce a normal OS exit within the
existing lifecycle contract. The run is therefore a lifecycle safe stop, not
an R0 qualification. Exact cleanup confirmed all 45 observed attempt identities absent,
and no crash dump, fatal, or automatic upload was produced. R1 was not started.
The later R2-R7 ladder is no longer authorized by the narrowed scope and needs
separate approval.

The pre-existing shutdown helper produced low-level diagnostic files before
the scope was narrowed. They are retained but are not interpreted here. No
additional debugger, dump, attachment, disassembly, or memory inspection is
part of this result.

Release build, Phase 0 RTX, Phase 3, the focused Phase 6GO/6GN/6GL tests, the
standard suite, and the devlog static check passed. The production app and
latest-demo hashes remained unchanged. No Kit, CDB, or GPU inventory helper
remained after verification.
