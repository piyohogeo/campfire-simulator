# Phase 6GW startup-classifier safe stop

Phase 6GW is a fresh-root successor to the Phase 6GV pre-Kit harness safe
stop. It qualified output-root ownership and bounded pre-Kit classification,
then completed the frozen 48-slot ABBA launch schedule in 4,689.64 seconds.

Every process reached a representative Flow startup (frame-60 active blocks
were recorded), but every process stopped before readback. The runtime producer
uses `sample_perf_counter_ns`; `phase6fc_startup_contract.classify_startup`
still indexed `perf_counter_ns` and raised `KeyError`. A and B each had 23 such
operation failures and one stage-close timeout on the exception shutdown path.
No run is a valid observation of the Phase 6GN post-readback boundary.

The maximum Kit/tree peaks were 13,910,691,840 / 14,063,038,464 bytes. There
were no resource-limit or cleanup failures and all 48 residual counts were
zero. The next independent Phase must exercise the exact startup producer
record through the actual startup classifier before Kit launch. Physics,
post-readback operations, order, thresholds, and production remain unchanged.
