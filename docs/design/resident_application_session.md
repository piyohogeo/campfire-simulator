# Persistent Resident application session

Status: Phase 6CA owner contract qualified as a production module. Runtime activation, frame scheduling, checkpoint UI, and replacement of the existing validation path remain deferred.

## Responsibility

`ResidentApplicationSession` is the single owner-thread boundary around an already constructed `ResidentNativeBackend` and `UsdResidentSnapshotAdapter`. It serializes:

- start and stop of consumer publication;
- native step followed by immutable-snapshot publication;
- retention and explicit retry of a snapshot after downstream failure;
- clean or explicitly forced close;
- observable lifecycle counters and component status.

The class does not create a stage, choose logs, locate the native library, schedule frames, write checkpoints, or present UI. Those policies remain outside the owner so they can be introduced and tested independently.

## States

The explicit states are `ready`, `running`, `stopped`, and `closed`.

- A new session is `ready` and cannot step until `start()` succeeds.
- `running` accepts a new monotonically increasing tick only when no snapshot is pending.
- `stop()` moves `running` to `stopped`; repeated stop is idempotent.
- `start()` may resume from `stopped`, including when a pending snapshot must be retried.
- `closed` is terminal; repeated close returns an idempotent result.

All public lifecycle operations require the construction thread. The wrapped backend and adapter retain their own checks as defense in depth.

## Pending publication contract

Native stepping commits the authoritative Resident revision before downstream USD publication. If publication fails after USD rollback/replay, the session retains the complete `ResidentNativeStep`, including its immutable snapshot, as `pending_revision`.

While pending:

- no new native step is allowed;
- normal close is rejected;
- stop/start is allowed so timeline or application state can recover;
- `retry_pending()` publishes exactly the retained snapshot;
- a failed retry leaves the same snapshot pending.

Once retry succeeds, the pending value is cleared and the next native tick may proceed. This prevents an application-level scheduler from skipping the consumer-visible revision even though the native authority has already advanced.

## Close policy

Normal close requires no pending snapshot, stops publication, exports and closes the native backend, then closes the adapter. `close(discard_pending=True)` is the only way to abandon an unpublished revision, and the result records `pending_discarded: true`. That path is intended only for explicit emergency cleanup, never normal save or restart.

If backend close/export raises, the session is not marked closed. The caller may report the failure and retry cleanup.

## Phase 6CA evidence and activation gate

The pure lifecycle test covers state transitions, pending retry, owner-thread rejection, counters, and idempotent close. The real Kit/MSVC benchmark injects a lightweight revision-last USD failure at revision 2. USD and adapter return to revision 1 while the backend remains at revision 2; the session blocks revision 3 and normal close, survives stop/start, retries revision 2 to all three consumers, and then commits revision 3. A separate failure case proves that only explicit `discard_pending=True` closes with a pending snapshot. All 15 real-object gates pass.

Activation remains blocked until a default-off frame scheduler owns tick delivery, stage replacement invalidates or reconstructs the session safely, and UI commands are queued on the same owner thread. The existing Phase 3 validation implementation and all default settings remain unchanged.
