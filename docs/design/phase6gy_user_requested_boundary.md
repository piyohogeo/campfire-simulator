# Phase 6GY user-requested safe boundary

Phase 6GX remains frozen and is not reused. Phase 6GY froze contract SHA-256
`2F97017708DF3C01277E7BF669827ADDD363798906859EACF35FAFBF368723E5`,
passed the no-Kit repetition fixture 20/20 and startup-timestamp fixture 6/6,
and added exact attempt-local cleanup for the contract allowlist of NanoVDB
temporary files.

At the user's request, no launch was started after the condition already in
progress. The outer runner was suspended while launch 23 B completed under its
existing resource guard. After the guard had terminated Kit and confirmed the
observed attempt tree absent, the exact pre-close committer and outer runner
identities were terminated. The one allowlisted file
`case/p3_f0180_temperature.nvdb` (47,641,541 bytes) was deleted, deletion was
confirmed, and no other file was targeted. An offline finalizer appended launch
23 exactly once and made the heartbeat terminal with
`user_requested_safe_boundary`. No launch 24 exists.

The resulting population contains 23 launches. Control A has 11 launches: 10
representative runs, all 10 normal exits, plus one nonrepresentative 24-block
`startup_prerequisite_not_met`. Candidate B has 12 representative runs and no
normal exit. Eleven ended as `os_exit_timeout`; launch 23 ended with Windows
exit `0xC0000005`. All 12 B runs share the last durable operation marker
`phase6gl_readback_after`. Launch 23 performed one seven-handle readback and no
volume conversion, metadata accessor, save, or sampling call.

Because the population was intentionally truncated and B produced two distinct
terminal classifications, the frozen conclusion is
`inconclusive due to harness or safety stop`. This does not reclassify Phase
6GN or prove a deterministic native mechanism. It does establish a 12/12
observed Candidate failure rate in this bounded partial population, versus
0/10 representative Control failures. The 95% Wilson intervals are
75.7506%–100% for B and 0%–27.7533% for A; A's zero-failure rule-of-three upper
bound is 30%.

Maximum Kit/tree peaks were 15,608,578,048 / 15,772,295,168 bytes for B and
15,168,745,472 / 15,332,499,456 bytes for representative A. The remaining
margins to 16/17 GiB were 1,498.5 MiB and 2,366.367 MiB respectively. No
resource limit or cleanup failure occurred, final process and NanoVDB residuals
are zero, production/defaults/Point placement/V3/P4 are unchanged, and no
typed metadata, other channel, formal S93/S100/OFF comparison, or video was
started.

The next step requires explicit approval. It should use this terminal aggregate
as partial reproduction evidence and decide whether to isolate the mixed
Candidate terminal outcomes or revise the repetition scope; it must not resume
the remaining fixed slots automatically.

Post-stop verification passed the Release build (8.31 seconds), the Phase 6GY
runner fixture 20/20, the startup timestamp fixture 6/6, finalizer idempotence,
and static devlog validation (`refs=516`, `ids=305`, `json=257`, `svg=177`,
`zip=2`). The explicit stop request prevented launching the Phase 0, Phase 3,
or standard runtime suites after the boundary. The production app SHA-256 is
unchanged at
`94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`;
the latest-demo manifest remains
`1C6FB249EAE8DF09E804680C7D0459BA8631D4ECFF4903944FFA4701E94E6285`.
