# Resident checkpoint session ownership policy

Status: Phase 6BZ isolated prototype qualified. Production session ownership, UI, automatic save, and automatic resume remain deferred.

## Current ownership gap

The application currently creates `ResidentNativeBackend` as a local object inside the finite Phase 3 validation scenario. The extension retains only the USD adapter for shutdown cleanup; it does not own a persistent interactive backend, models, scheduler, or checkpoint destination. Consequently, adding a Save button now would imply a product lifecycle that does not exist.

Production checkpoint integration must first introduce one persistent Resident session owner. That owner—not UI code, the Flow emitter, or individual consumers—must serialize native stepping, USD publication, save barriers, close, and resume on the Kit owner thread.

## Qualified explicit save barrier

The isolated controller uses this synchronous sequence at a fully committed revision:

1. Verify backend revision, adapter revision, and every consumer revision agree.
2. Stop adapter publication and reject concurrent/non-owner operations.
3. Export Resident SoA values to the existing Python model mirrors without closing the backend.
4. Clone the live USD stage in memory.
5. Write the existing versioned Wood JSON only into the clone.
6. Atomically publish the Phase 6BY checkpoint package.
7. Resume adapter publication in `finally`, whether save succeeds or fails.

The live stage is never used as a persistence scratchpad. A failed or partial model-state write affects only the anonymous clone. Save does not increment revision, does not close native storage, and does not become a simulation tick.

## Resume policy

Resume remains explicit and creates a new session. It validates the package, model hashes, native ABI, log order, scheduler values, and all consumer revisions before constructing the backend/adapter pair with the saved revision and tick. The first post-resume step must be byte/value-equivalent to the same next step in the uninterrupted session.

Version 1 does not merge a checkpoint into an already running session. It does not silently fall back to a fresh run after validation failure. The caller must present the failure and keep the current session or start a deliberate new one.

## Failure and concurrency rules

- One Kit owner thread owns step, publish, save, resume, and close.
- Save is allowed only in `running` state at a committed consumer boundary.
- A save request cannot overlap a step or another save; future UI commands must queue at the session boundary.
- Failure before atomic replace preserves the previous package and resumes the same running session.
- Close is idempotent; save and step after close fail closed.
- Autosave cadence, retention, cancellation, disk-full UX, and concurrent writers are not defined by this spike.

## Phase 6BZ evidence and decision

The real Kit/MSVC sequence passed all 12 gates. Two successful saves and one injected failure paused/resumed the adapter three times. SoA export took 2.0541 and 2.1952 ms. The injected failure preserved the previous package, left the session at revision 2, and allowed it to commit revision 3. A second session restored from revision 2 and produced exactly the same revision 3 step result and immutable snapshot as uninterrupted execution. Non-owner save, save after close, and repeated close followed the fail-closed contract.

The boundary is technically qualified but remains outside production. Reconsider integration only after the application has a persistent default-off Resident session owner and an explicit user policy for destination selection, overwrite confirmation, retention, compatibility errors, and new-run versus resume choice.
