# Phase 6GX repetition evidence safe stop

The Phase 6GX startup producer/consumer fixture passed 6/6 and the fixed runner
fixture passed 17/17 before runtime. The six-hour boundary admitted 46 fixed
ABBA launches: 23 Control A and 23 Candidate B.

Control supplied 22 representative normal exits. One additional A launch had
a 24-block startup prerequisite failure and then a stage-close timeout.
Candidate supplied 20 representative launches; every one completed the first
seven-handle readback and stopped with `phase6gl_readback_after` /
`timeline_playing`, without a normal exit. Three further B launches were
startup-prerequisite failures. This is deterministic-like partial evidence for
the Phase 6GN candidate boundary, while the low-frequency A shutdown event
remains separately visible.

The population is not qualified. Each B timeout left one 41-byte partial
`p3_f0180_temperature.nvdb` under its own attempt. Although no process residual,
resource limit, or process cleanup failure occurred, the runner failed the
contract requiring temporary-file residual zero before the next launch. The
authoritative conclusion is `inconclusive due to harness or safety stop`.
