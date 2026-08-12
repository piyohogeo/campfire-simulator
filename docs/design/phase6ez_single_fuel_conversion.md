# Phase 6EZ single fuel-channel conversion boundary

Phase 6EY remains frozen at commit `6dd497c`: R0 is qualified 3/3 and the single R1 acquire/discard boundary is qualified 1/1. None of those samples enter the Phase 6EZ formal population.

Phase 6EZ changes diagnostic observation only. It runs two independent processes from a new empty artifact root: C0 calls public `get_latest_nanovdb_readback()` once and explicitly drops all returned aliases; C1 makes the same call, selects only `CHANNELS[1]` (`fuel`), calls the existing `numpy.asarray()` conversion exactly once, then drops the source tuple/aliases, retains only the converted object, drops that object, advances one renderer frame, and performs the unchanged Phase 6EY finite dynamic-stationarity observation. C1 starts only after C0 passes.

The current public return boundary is a Python list whose elements were NumPy arrays in Phase 6EY. The existing fuel conversion is `np.asarray(source)`, not an explicit copy API. Therefore the contract records identity, ownership, base identity, `np.shares_memory`, shape, dtype, element count, and logical bytes. If the returned fuel object and converted object are identical, “converted buffer only held” means only that alias remains; it does not claim a distinct allocation. The code makes no claim about provider-internal CPU/GPU copies. Synchronous marker values are Kit Private Bytes/Working Set; GPU dedicated memory comes from the nearest bounded, isolated `nvidia-smi` sample and is labelled with its time offset.

The frozen contract is `scripts/phase6ez_fuel_conversion_contract.json`. It preserves the Phase 6EY dynamic-stationarity predicates and all 14 GiB Kit, 16 GiB unique-tree, 512 MiB runner/diagnostic, and 8 GiB system-headroom limits. It allows no other channel conversion, aggregation, field JSON/JSONL/NPZ persistence, repeated readback, forced GC, private release API, production integration, or ceiling increase. A single successful C1 qualifies only this fixed one-conversion lifetime boundary; repeated conversion remains a later Phase.

Runtime results have not yet been collected at contract declaration time.
