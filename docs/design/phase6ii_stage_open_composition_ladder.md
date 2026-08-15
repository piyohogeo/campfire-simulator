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
