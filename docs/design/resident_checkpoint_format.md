# Resident checkpoint package format

Status: Phase 6BY isolated spike. Format feasibility is qualified; production adoption and automatic resume remain deferred.

## Purpose and non-goals

The package persists one revision-consistent Resident boundary so an explicit later session can seed the existing native backend and USD adapter, then continue with the next revision. It does not alter the authoritative wood model, its JSON schema, the immutable snapshot schema, the USD publication transaction, rollback behavior, physics, or production defaults.

This work does not define autosave frequency, retention, UI, crash recovery policy, cross-machine compatibility, or a product-supported resume command.

## Version 1 container

The file suffix is `.campfire-checkpoint`. The container is a deterministic ZIP with exactly two entries in this order:

1. `manifest.json`: canonical UTF-8 JSON with sorted keys and no insignificant whitespace.
2. `stage.usda`: UTF-8 USDA exported after native shutdown state is written through the existing versioned `WoodThermalModel.to_dict()` representation.

The USDA is the sole model payload. The manifest records hashes of the canonical model states but does not duplicate their JSON, avoiding two independently editable authorities.

The manifest records:

- checkpoint kind and schema version;
- stage entry name, byte count, and SHA-256;
- committed revision and tick;
- ordered log identifiers and per-log canonical model-state SHA-256;
- the two log consumer revisions plus Flow-emitter consumer revision;
- initial dry mass per log;
- scheduler time step and heat flux;
- native ABI version.

Readers reject unknown kind/version, noncanonical or oversized entries, malformed hashes, duplicate log IDs, invalid numeric values, consumer revisions that differ from the manifest revision, stage byte-count/hash mismatch, and model-state hash mismatch after model loading. Version 1 entries are bounded to 64 MiB each.

## Atomic write contract

One writer creates a sibling temporary file, closes the ZIP, flushes and `fsync`s the file, then uses `os.replace` to publish it. Failure before replace removes the candidate and preserves the prior checkpoint byte-for-byte. Concurrent writers are outside the version 1 contract and must be serialized by a future product owner.

SHA-256 supplies accidental-corruption detection, not authenticity. A malicious party able to rewrite both payload and manifest can recompute the hashes; signing or an authenticated storage boundary would be a separate requirement.

## Resume contract

A reader validates the complete package before constructing runtime objects. It loads existing model JSON from the stage, verifies its hashes and all three consumer revisions, then supplies the explicit saved revision/tick to the existing `ResidentNativeBackend` and saved revision to `UsdResidentSnapshotAdapter`. The first successful step and publish must be revision `saved + 1`; no component may infer a revision independently.

Rollback remains session-local and unchanged. A saved checkpoint is a last-known-good committed boundary, not a partial transaction journal.

## Phase 6BY result and adoption gate

The real Kit/MSVC spike saves revision 3, rejects an interrupted replacement, rejects stage tampering, rejects a validly hashed manifest whose revision disagrees with stage consumers, restores both canonical model states, and commits revision 4 across both log consumers and the Flow emitter.

Production adoption remains deferred until save ownership, explicit user operations, retention, compatibility/migration policy, and end-to-end application tests are defined. The default remains a fresh revision-zero Resident session.
