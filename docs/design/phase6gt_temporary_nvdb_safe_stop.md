# Phase 6GT temporary NanoVDB save safe stop

Phase 6GN through Phase 6GS remain frozen. Phase 6GT used the pre-runtime
contract SHA-256
`0C2B2832F9AEE4F8B4D3853B7086F31742DB392AB120B2D2C13153417AB1AF01`
and a new empty artifact root. It authorized one corrected-four S93 process,
one frame-180 public readback, one slot-0 temperature conversion, the six
Phase 6GS public accessors, and exactly one temporary uncompressed NanoVDB save.
No prior runtime sample was reused.

## Pre-runtime gates

The pure Python no-Kit fixture passed 23/23. It covered the fixed artifact-local
path, pre-existing-file rejection, boolean save-return semantics, nonempty and
256 MiB bounds, empty-file timeout, oversize rejection, exact deletion, path
escape rejection, neighbor preservation, one-call static scope, and the absence
of content reads, hashes, reloads, NumPy conversion, sampling, collectors, and
flux. The shared PowerShell exact-cleanup end-to-end fixture passed 5/5 and
confirmed that only the contracted file is removed. Release build passed before
runtime.

## Runtime boundary

The one allowed process reached frame 180 with 1,329 active blocks. It completed
one seven-slot readback, selected the qualified 47,641,344-byte temperature
source, converted it once to `omni.volume._volume.GridData`, and completed every
bounded metadata accessor once. The results matched Phase 6GS: grid count/type/
name/class were `1/1/Flow/2`, the index box was
`[[-96,-96,-16],[127,111,639]]`, and the world box was approximately
`[[-2.4,-2.4,-0.4],[2.4,2.4,15.6]]`.

The next operation checked that the exact temporary path did not exist and set
the bounded report field accordingly. Its durable resource marker then passed a
payload property named `path` to `_append_resource_marker()`, whose first
argument is also named `path`. Python raised
`TypeError: _append_resource_marker() got multiple values for argument 'path'`.
The last completed normal operation marker was
`phase6gt_bounded_metadata_complete`; the final marker was
`phase6gt_operation_failure`.

`SaveVolumeParameters` was not constructed, `save_volume()` was called zero
times, and no NanoVDB file was created. File size, poll time, save return, and
reference-release weak evidence are therefore unavailable. Content reads,
file hashes, reloads, typed metadata, NumPy conversion, sampling, collectors,
flux, other channels, images, videos, and the formal population all remained
zero or unstarted. This result is a diagnostic harness failure before the save
API, not evidence that `save_volume()` failed.

## Lifecycle and safety

The common shutdown path stopped the timeline, completed stage close in
2.369910 seconds, and durably reached `shutdown_complete`. Kit exited without a
Windows exception but returned code 1 because of the probe exception, so the
contractual lifecycle axis is failure rather than natural exit 0. Fatal, dump,
automatic upload, CDB, and residual-process counts were zero. Exact parent
cleanup found no temporary NanoVDB file and left zero temporary file.

Kit/tree peaks were 14,911,668,224 / 15,075,356,672 bytes, leaving
2,268,200,960 bytes (2.112 GiB) / 3,178,254,336 bytes (2.960 GiB) below the
16/17 GiB ceilings. Runner/diagnostic peaks were 95,997,952 / 16,846,848 bytes;
physical and commit minima remained above their 8 GiB floors. Production and
latest-demo hashes were unchanged.

## Continuation boundary

Phase 6GT is a safe stop and does not qualify temporary NanoVDB saving. It must
not be retried, replaced, or reclassified. The smallest future Phase would fix
and fixture the marker key at the actual resource-marker boundary (for example,
use an unambiguous `temporary_file_path` field), freeze a new contract/root, and
then decide whether one new save-only process is authorized. Typed metadata
reload, any content access, another channel, sampling, collectors, flux, and the
formal S93/S100/OFF population remain blocked.

Final verification passed the Release build, Phase 0 RTX, Phase 3 with zero
dry/wet mass-balance error and wood-owned Flow input (active blocks final/peak
312/350), Phase 6GT Python/end-to-end fixtures (23/23 and 5/5), Phase
6GS/6GR/6GQ focused fixtures (14/14, 26/26, 19/19), the standard suite (8/8
processes, 78 tests), and devlog validation.
