# Acquisition schema v0.1.0 to v0.2.0

Status: additive M1-03B.1 contract. `schemas/acquisition/v0.1.0/` is retained
byte-for-byte and remains the M1-03A design snapshot.

## Why the version changed

Acquisition v0.1.0 describes the reviewed dry-run plan, in-memory attempt/failure
receipts, a proposed authorization shape, and typed operational-ledger events. It
does not model the production authorization ceremony, one-shot storage identity,
hash-chained persistence, or restart reconciliation needed before a live comparison.

Version 0.2.0 adds six strict contracts:

- `NetworkAuthorizationArtifactV2`: exact plan/target/limit fingerprints, the
  post-M1-03B.1 protected-source receipt, reviewed execution commit/tree, exact
  installed dependency `RECORD` pins, reports and hosts, compare-only capabilities,
  redirect policy, storage marker, data-root/host identity, owner/time, and one-shot
  same-run resume policy;
- `AuthorizationRegistryV2`: sorted, unique exact-raw-artifact and semantic grants
  used by the independently pinned production registry (empty in M1-03B.1);
- `ExecutionTreeManifestV2`: sorted exact runtime inputs with byte counts, file
  hashes, and a deterministic tree hash;
- `StorageNamespaceMarkerV2`: canonical inert bytes identifying the authorized
  manifest namespace;
- `DurableLedgerRecordV2`: hash-chained run, attempt, landing, byte, comparison,
  cleanup, temp-recovery, source-rehash, issue, and terminal records; and
- `UseIndexRecordV2`: a global hash-chained authorization claim, ledger creation,
  per-record high-water anchor, and terminal anchor.

Durable attempts reserve request/byte budget before transport use. A body becomes a
successful durable outcome only after engine-level validation, not merely EOF.
Selected safe HTTP headers and explicit redirect/retry continuation links are
retained. Run/use-index identity binds the exact authorization artifact bytes,
execution tree, host, data root, marker, plan, and deterministic run. Completion is
valid only for the exact clean ordered ten-report comparison graph; scientific
ambiguity/collision requires `stop_for_review`, while operational failure may be
`abandoned` only with classified evidence.

The final v0.2 contract distinguishes durable observation of an unaccepted complete
temporary object from its later deletion and from acceptance of a complete object
for resume. A complete crash-window object is fingerprinted before deletion.
Unfinished attempt claims become ordinary v0.2 `attempt_finished` records with
`outcome = crash_outcome_unknown` and `accepted_bytes = null`, retain their full
reservation, and create `MISSING_EVIDENCE`; zero is never fabricated and a later
transport cannot silently continue under that authorization.

The authorization registry stores the exact raw artifact SHA-256 plus a semantic
core hash over every authorization field, including `execution_git_commit` and the
dependency pins. Registry bytes are separately pinned. Runtime binds the execution
tree to public protected-main evidence fetched directly from GitHub with no
credentials or proxy inheritance; local remote-tracking refs are not authority.
These are strict v0.2 loader and governance semantics, not a relaxation or in-place
change to v0.1.

## Migration rule

Changing `schema_version` is not a migration. No M1-03A v0.1 record may be relabeled
as v0.2. The dry-run made no operational ledger, so there are no production v0.1
records to transform. A future M1-03B.2 run must begin with a separately reviewed
v0.2 authorization and an empty-or-exact v0.2 namespace. Historical M1-03A receipts
retain their original schema and evidentiary meaning.

The immutable pilot v1/v2 plans remain acquisition-plan schema v0.1.0 and retain
`authorization_status: not_authorized`; v0.2 does not mutate or reinterpret them.

## Retention and drift

The drift check renders the expected bytes in memory and compares them with both
version directories; it does not rewrite either snapshot. A pinned tree-digest test
independently proves v0.1.0 remains unchanged. The v0.2.0 directory is separately
pinned after generation. Scientific and discovery schema exporters and snapshots are
unaffected.
