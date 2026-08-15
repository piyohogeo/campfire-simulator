# Phase 6II: minimal Stage-open composition ladder

Date: 2026-08-16  
Baseline: `2df5df9`  
Contract SHA-256: `F567B60DF29D262426DD52B37D1E1C297A90144CD8339692378084820506CC58`

## Frozen history and purpose

Phase 6IH remains `safe_stop_runtime_authoring_isolation_failure`. Its
contract, artifacts, dump, and classification are neither reused nor changed.
Phase 6II localizes only the minimal `open_stage_async`/close boundary. It does
not audit runtime properties, create a camera allowlist, advance Flow, or run
the Collision OFF/ON comparison.

## Actual one-variable ladder

Kit's USD Context supplies an anonymous session Layer for every opened root;
there is no real session-free condition in the current API path. Phase 6II
therefore keeps that behavior constant rather than synthesizing a false
control. Phase 6IH's complete composition is already container + empty runtime
+ protected, so requested condition D is identical to C and is not duplicated.

| Condition | Opened root | Sublayers, strongest first | Single addition |
|---|---|---|---|
| A | `protected_diagnostic.usda` | none | direct-open baseline |
| B | `container.usda` | protected | file-backed container root |
| C | `container.usda` | empty runtime, protected | empty runtime sublayer |

Every condition regenerates the same frozen protected diagnostic Layer and
requires SHA-256 `D5668572...E99C`. It uses the same app-ready sequence,
extensions, stopped timeline, context open/close API, process guard, timeouts,
dump policy, and exact cleanup. Conditions run A then B then C in separate
processes, once each, stopping on the first non-normal result.

## Bounded evidence and classification

Only process/condition identity, opened path/hash, root and sublayer
identifiers, anonymous session identity, EditTarget, open/close elapsed times,
exit/resource/crash facts, and cleanup are retained. No complete property,
camera, or semantic snapshot is made. Required fsync markers cover process
start, app-ready, open request/completion, identity, close request/completion,
empty context, and shutdown request/completion.

A native exception in any single attempt is classified
`safe_stop_stage_open_native_failure_unlocalized`, even after an earlier
condition passes; one occurrence is not evidence of composition specificity.
Only a deterministic non-native identity/composition failure introduced by B
or C after all prior conditions pass may use
`safe_stop_stage_open_composition_specific_failure`. Pre-open harness evidence
failures use `safe_stop_stage_open_harness_failure`. All three fully normal
attempts are required for `stage_open_composition_ladder_qualified`.

The runtime result is appended only after the no-Kit producer-to-consumer gate
and the separately committed implementation are complete.

## Runtime result

The no-Kit fixture passed 20/20 and all five exact dependencies matched. One
fresh Condition A process was launched; B and C were not launched after A's
fail-fast boundary. The protected Layer SHA matched the contract.

`open_stage_async` returned normally in 0.167172 seconds. The root had no
sublayers, the EditTarget was the protected root, and the context did create an
anonymous session Layer. Its actual identifier was the bounded form
`anon:<runtime-id>`, not the predeclared filename-suffixed
`anon:<runtime-id>:protected_diagnostic-session.usda`. The exact identity gate
therefore stopped at `opened_stage_identity` with
`session_identifier_mismatch`. This is an identity-contract mismatch after a
successful native open, not a recurrence of Phase 6IH's access violation.

The error cleanup used the same close API. Stage close completed in 0.121282
seconds, context-empty and shutdown markers were durable, Kit exited 1, and
exact cleanup left residual zero. No fatal, access violation, device loss,
TDR, dump, CDB action, or upload occurred. Kit/tree Private Bytes peaked at
7,290,847,232/7,745,839,104 bytes, within the fixed 16/17 GiB limits.

The frozen A-failure rule yields
`safe_stop_stage_open_native_failure_unlocalized`; the label does not assert a
native crash. There is no fully qualified ladder condition. The evidence does
establish that direct protected-root open/close can return normally in this
one process, but it does not test container or runtime sublayers and cannot
localize Phase 6IH's native exception.

The next separately approved Phase must correct and fixture only the anonymous
session-identity contract, then run a new-root A/B/C ladder. It must not reuse
this attempt, proceed to four-boundary Layer audit, or start OFF/ON.
