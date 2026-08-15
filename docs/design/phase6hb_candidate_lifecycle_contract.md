# Phase 6HB Candidate lifecycle isolation contract

Status: frozen before runtime. Base commit: `f147be1`. Contract SHA-256:
`4DC0D578D333C8485FC3BFD06EE7AFFFDD3E1549376EDCCE3B0081276D25DD37`.

Phase 6GZ and Phase 6HA remain immutable safe stops. Their artifacts are
read-only historical evidence and are not members of this Phase.

## Read-only difference audit

| Boundary | Phase 6GS Control | Phase 6GZ/6HA Candidate common path | Phase 6HB treatment |
|---|---|---|---|
| Stage and exports | Phase 6GN exact wrapper; corrected-four S93; six exports ON, RGBA/RGB OFF | Identical exact wrapper and values | No redundant stage-only condition |
| Point payload | 1,344/1,440, `allow_self_center`, offset -0.0125 m, support 0.05 m | Identical | Frozen |
| Startup | connect; 60 viewport frames; Flow acquired before updates; reset; 12 stopped updates; play | Identical | Frozen |
| Frames | samples 60/120/180/240; operation 180 | Same temperature-front frame set and operation frame | Frozen |
| Readback | one list of seven | one list of seven | A performs only this and release |
| Array metadata | slot 0 only | all seven slots | B adds all-seven bounded metadata |
| Schema prefix | temperature conversion and six public accessors only; no file | six nonempty slots each converted, inspected, temporarily saved, and typed-read | C adds the exact helper for slots 1--5 only; temperature and empty RGBA are excluded |
| Velocity | none | one save/sample/profile plus four collector captures | D adds save/sample/profile without collector; E adds collector use |
| Collector objects | four created before timeline play | Same four objects | Creation-only condition omitted |
| Temperature entry | slot 0 selected | slot 0 selected after velocity; GZ stops before conversion; HA converts once | F adds alias hold/release only; all temperature native work prohibited |
| Ownership | stage, viewport, capture provider alias, Flow, volume provider, emitter, collectors | Same shared container | Ownership-only condition omitted |
| Shutdown | stop; 8 updates; close; detach; 4 updates; release; app close; `shutdown_complete`; quit | Identical shared implementation | Release-order condition omitted |

The Candidate schema prefix normally includes temperature native work. The
user explicitly prohibited that work here, so Phase 6HB can isolate every
non-temperature addition but cannot eliminate interactions involving that
prohibited prefix. If all conditions exit normally, this remains the smallest
unseparated boundary rather than being inferred as safe.

## Fixed ladder

1. A: readback count/type and ordered release only.
2. B: A plus bounded Python-array metadata for all seven slots.
3. C: B plus Candidate schema volume/metadata/save/typed-read for slots 1--5.
4. D: C plus one velocity save/sample/profile, with no collector argument.
5. E: D plus the already-created four spatial collectors.
6. F: E plus slot-0 temperature alias hold/release, with no content access.

Each condition uses a new stage, process, and attempt directory. There are no
retries or replacements. A non-normal operation, incomplete reference release,
stage-close failure, missing `shutdown_complete`, post-shutdown OS-exit
failure, resource failure, cleanup failure, or nonzero residual stops all later
conditions. Operation and lifecycle outcomes remain separate axes.

## Safety and exclusions

Kit Private Bytes stay below 16 GiB, the unique tree stays below 17 GiB,
runner/diagnostic children stay below 512 MiB, and available physical memory
and commit headroom stay at or above 8 GiB. Only one Kit process may exist.
Temporary NanoVDB cleanup is restricted to the attempt root and the six frozen
names. Unknown files are not deleted and cause cleanup failure.

Temperature conversion, temperature metadata, temperature save/typed-read,
temperature sampling/collector work, formal S93/S100/OFF comparison, video,
production, defaults, Point policy, V3, and P4 are excluded.
