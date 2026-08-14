# Phase 6GS bounded public volume-metadata qualification

Phase 6GR remains frozen as a harness-failure safe stop. Phase 6GS used a new
contract (SHA-256
`DCCE22B554ED778644CDDBBF03F9F3F0E5EAEFE18C28E381F0AF22142169E930`),
a new empty artifact root, and one fresh corrected-four S93 process. No Phase
6GR runtime sample was retried, replaced, reclassified, or reused.

## Harness corrections

The source marker now receives one canonical dictionary through
`marker(name, **canonical_payload)`. The canonical channel authority is
`temperature`; a duplicate input carrying the same value is normalized to one
key, while a conflicting value fails before Kit starts. The PowerShell parent
now normalizes optional string properties through a shared helper: a valid
nonempty string is retained, explicit null, absence, and an empty or
whitespace-only string become null, and any other type fails closed. The raw
evidence is committed before parent normalization, and every safe stop writes
a terminal incremental state instead of leaving `running`.

The child fixture passed 14/14 and the actual child-JSON-to-parent-PowerShell
end-to-end fixture passed 13/13 without starting Kit. It covered the exact
47,641,344-byte temperature source payload, duplicate/equal and conflicting
channels, valid/null/missing/empty/invalid optional values, zero/partial/full
accessor summaries, terminal safe-stop state, and preservation of raw evidence
across a parent reporting failure.

## One-process result

The fresh process reached frame 180 with 1,329 active blocks. One public
readback returned the qualified slot-0 temperature source:

- Python type `numpy.ndarray`
- shape `[11910336]`, dtype `uint32`
- 11,910,336 elements and 47,641,344 logical bytes

`buffer_to_volume()` was called exactly once and returned
`omni.volume._volume.GridData`. The bounded accessor helper then called each
approved public accessor exactly once, in the frozen order:

| accessor | result |
| --- | --- |
| `get_num_grids()` | `1` |
| `get_grid_type(..., 0)` | `1` |
| `get_short_grid_name(..., 0)` | `Flow` |
| `get_grid_class(..., 0)` | `2` |
| `get_index_bounding_box(..., 0)` | `[[-96, -96, -16], [127, 111, 639]]` |
| `get_world_bounding_box(..., 0)` | `[[-2.400000095, -2.400000095, -0.400000006], [2.400000095, 2.400000095, 15.600000381]]` |

The incremental artifact was durable after every accessor. The last successful
accessor was `get_world_bounding_box`. Volume then source/list references were
released in order; both weak references were dead and total residual was zero.
There were no calls to the broad `_volume_metadata()` helper, `save_volume()`,
`numpy.asarray()`, sampling, collector, flux, another channel, a repeated
readback, or a repeated conversion.

The operation axis passed. The lifecycle axis also passed: release-after-close
completed stage close in 5.732096 seconds, reached `shutdown_complete`, and Kit
exited naturally with code 0. Exact cleanup found zero residual process. Kit
and unique-tree peaks were 14,877,048,832 and 15,041,200,128 bytes, leaving
2,302,820,352 bytes (2.144 GiB) and 3,212,410,880 bytes (2.992 GiB) below the
16/17 GiB limits. Runner/diagnostic peaks were 128,081,920 / 16,887,808 bytes;
physical and commit minima remained above 8 GiB.

## Qualification boundary

Phase 6GS qualifies only the fixed S93, slot-0 temperature, single-conversion,
bounded public volume-metadata boundary. It does not qualify temporary NVDB,
typed metadata, another channel, volume values, sampling, near-Mesh collection,
directional flux, repeated readback/conversion, or the formal S93/S100/OFF
population. Those remain separate approval boundaries. Production, defaults,
Point policy, V3, P4, and the latest demo are unchanged.

Final verification passed the Release build, Phase 0 RTX, Phase 3 with zero
dry/wet mass-balance error and wood-owned Flow input (active blocks final/peak
278/301), the Phase 6GS child/end-to-end fixtures (14/14 and 13/13), the
6GR/6GQ/6GP/6GO/6GN/6GL focused fixtures (26/26, 19/19, 19/19, 18/18, 5/5,
3/3), the standard suite (8/8 processes, 78 tests), and devlog validation.
