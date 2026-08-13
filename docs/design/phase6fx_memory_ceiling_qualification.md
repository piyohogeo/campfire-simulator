# Phase 6FX memory-ceiling qualification

## Frozen boundary

Phase 6FT and Phase 6FV remain historical safe stops. Phase 6FX does not
reclassify either result and does not copy any prior runtime sample into the
formal population. Phase 6FW commit `39de323` is the safe starting point.

The pre-runtime contract is
`scripts/phase6fx_memory_ceiling_qualification_contract.json`, schema
`campfire.phase6fx.memory-ceiling-qualification-contract.v1`. Its SHA-256 is
`A32F9FB6CB94E733DC1B0B3A4133A1434B35CB4706B62EB2CCE7152993B0D0D6`.

## Fixed population

The formal population is nine fresh processes: M0 baseline at frame 96, M1
Phase-6FO-equivalent diagnostic state at frame 96, and M2 immediately before
the planned first readback at frame 179. Each condition runs three times in
the frozen balanced order `M0/M1/M2`, `M1/M2/M0`, `M2/M0/M1`. No readback,
capture, video, S93/S100 comparison, or production integration occurs. The
shared physical probe keeps its frozen `phase6fv` report label; the new outer
contract, attempt metadata, identity decisions, and final report are owned by
Phase 6FX. This avoids modifying the hash-pinned physical runner.

All processes use the corrected four-log fixture, S93 `allow_self_center`,
1,344/1,440 active Points, payload SHA-256
`0D3B074B7BE3E482E8702A126A11619D87F587C4848C80D4A3162A11B876C389`,
and the Phase 6FS diagnostic-only `release-after-close` order. Only a frozen
startup prerequisite failure can consume the single replacement allowance.
Resource, lifecycle, marker, diagnostic, identity, or cleanup failure stops
the whole population without retry.

## Safety and decision gates

The old 14 GiB Kit value is telemetry-only during qualification. Kit 16 GiB,
unique process tree 17 GiB, runner 512 MiB, diagnostic child 512 MiB, physical
memory floor 8 GiB, commit-headroom floor 8 GiB, and stage-close timeout 180
seconds are absolute gates. Candidate qualification additionally requires a
normal maximum Kit peak no greater than 15.5 GiB, providing at least 512 MiB
fixed headroom to the 16 GiB stop.

Short slopes remain telemetry. The only waveform failure is the frozen large,
non-decreasing, occupancy-unexplained terminal pattern. All nine processes
must close the stage, shut down, exit normally, and leave no attempt-owned or
unknown identity.

Phase 6FU continues to own process observation and exact cleanup. Phase 6FW
is the final classifier: a PID reuse is non-residual only with complete current
identity evidence, clear time or path difference, no stop request for the new
identity, ordered cleanup markers, dual-source evidence, and no rediscovery.
Access denied alone never proves reuse. The original Phase 6FU states and stop
authority are unchanged.

## Scope after qualification

If all gates pass, Phase 6FX may retire 14 GiB as the four-log anomaly ceiling,
qualify 16 GiB Kit and 17 GiB unique-tree candidates, and report that a later,
explicitly approved fresh-root Phase 6FO restart is ready. Phase 6FX itself
does not start Phase 6FO or change production shutdown order or defaults.

## Runtime result: lifecycle safe stop

The fresh root launched six processes and stopped without retry at attempt06,
the second M0 baseline. Attempts01--05 passed operation, resource, lifecycle,
normal OS exit, Phase 6FU cleanup, and Phase 6FW final identity gates. Their
Kit peaks were 14,534,746,112--14,967,640,064 bytes (median
14,869,356,544; range 432,893,952), and their stage-close times were
3.038--14.023 seconds (median 7.168). M1 did not show a fixed increase over
M0. Both completed M2 runs had 1,322 terminal blocks and lower peaks than the
frame-96 controls. This is partial evidence, not a complete distribution.

Attempt06 used the same payload and had 948 frame-96 blocks. Its Kit and tree
peaks were 14,851,428,352 and 15,014,383,616 bytes. It reached
`stage_close_request_before` after timeline stop, eight renderer updates, and
explicit ownership retention, then emitted `stage_close_timeout` after
180.016801 seconds. It never emitted close, post-close, release, extension
shutdown, or normal-exit markers. Attempts07--09 were not launched.

The timeout interval averaged 0.749% Kit CPU on the all-logical-CPU scale and
peaked at 3.181%, consistent with a low-CPU wait rather than a spin. This is
an inference only: stack-first CDB timed out after 30.354 seconds before an
attach/native frame was observed, the module pass also timed out, and only
explicit detach completed. No module, offset, owner thread, or wait object can
be asserted. The accepted NGX five-token signature did not match.

Phase 6FU cleanup and Phase 6FW classification completed for all six attempts:
236 identities absent, protected reuse 0, attempt-owned residual 0, unknown 0,
mismatch stop 0, and dual-source absence 6. Final Kit/CDB/GPU-helper residual
is zero. No full dump or upload occurred.

The largest representative normal peak left only 64,745,472 bytes below the
old 14 GiB value, so 14 GiB remains too close to normal high-water to be a
useful anomaly ceiling. Because only 5/9 normal exits completed, this Phase
does not adopt a replacement: Kit 16 GiB and tree 17 GiB remain unqualified,
and Phase 6FO remains blocked. The recurrent release-after-close failure and
CDB attach limitation must be addressed before another population.

Release build, Phase 0 RTX, Phase 3 authority/mass-balance/Flow input, 191/191
focused Phase 6F contracts, and the standard 8-process 78/78 suite passed.
Production app SHA-256 remained
`94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`.
Production, defaults, video, and latest demo were unchanged.
