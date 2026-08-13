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
