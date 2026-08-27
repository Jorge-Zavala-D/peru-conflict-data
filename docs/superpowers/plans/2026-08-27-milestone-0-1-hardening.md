# Milestone 0.1 Hardening Implementation Plan

> Execute on `codex/milestone-0-foundation`. Keep `schemas/v0.1.0/` and all Dropbox
> external/raw bytes immutable. Do not start M1 or write to `01_raw`.

## Goal

Supersede the incomplete M0 schema with a source-evidenced, versioned `v0.2.0`
contract, strengthen the manifest and M1 safety documentation, run all quality and
source-integrity gates, and obtain remote pull-request CI without merging.

## Design

Pydantic models remain the source of generated JSON Schemas. v0.1.0 is retained byte for
byte; v0.2.0 adds nullable source fields and process-level mediation, separates agreement
follow-up, represents intervention hierarchy, and makes monthly indicator origin explicit.
The operational acquisition ledger stays in Dropbox; Git contains only its recipe and
reviewed small metadata.

## Tasks (test first)

### 1. Freeze baselines and record the design

- Verify branch, remote SHAs, clean starting tree, `schemas/v0.1.0` per-file/tree hashes,
  all 11 source hashes, license hash, and zero files under `02_extracted`–`07_releases`.
- Add this design and plan before implementation.
- Acceptance: baseline values are available for the final receipt and no source path is
  passed to a writer.

### 2. Add failing v0.2 model tests

- Test demand category separation and null semantics.
- Test process-level mediation and event/process linkage without requiring one event per
  process.
- Test agreement text/progress/responsibility/deadline separation.
- Test intervention category/subtype/hierarchy, alert source dimensions, structured
  original geography, protest date precision, and violence type/date precision.
- Test source-reported and derived indicator invariants, including required derivation
  metadata and non-substitution semantics.
- Test schema version `0.2.0`, registry additions, and open historical strings.
- Acceptance: new tests fail against the v0.1 implementation for the intended reasons.

### 3. Implement the v0.2 domain contract

- Set the current model/schema version to `0.2.0` without editing v0.1 files.
- Add the source-preserving fields and `MediationProcess` model; retain `DialogueEvent`.
- Add indicator-basis validation and conditional derivation metadata.
- Export new models through the registry and public package surface.
- Acceptance: focused model tests pass, strict/immutable/null semantics remain intact,
  and no closed historical taxonomy is introduced.

### 4. Regenerate schemas and prove migration/version retention

- Generate `schemas/v0.2.0/` and update the schema README/current-model references.
- Add tests that v0.1 bytes remain unchanged, v0.2 export is deterministic, registry and
  schema sets agree, and v0.1 payloads require an explicit migration boundary.
- Add `docs/schema_migrations/v0.1.0_to_v0.2.0.md` describing additive mappings and
  records that require review rather than inference.
- Acceptance: schema drift check passes and v0.1 tree digest remains the frozen baseline.

### 5. Expand documentation and M1 safeguards

- Replace the overview-only data dictionary with a field-level dictionary for every
  current v0.2 entity and field: meaning, representation/unit, original/normalized
  status, null semantics, multiplicity, provenance, relationships, and source-reported
  versus derived status.
- Update canonical-model, storage, manifest, benchmark, discrepancy, roadmap, decision,
  and open-question documents to reflect v0.2, the operational manifest boundary, stale
  PDF title rule, and the two report-269 discrepancy notes.
- Add a distinct M1-03 acquisition checkpoint specification covering command/design,
  atomic downloads, hash-before-promote, collisions, retries/idempotency, rate limits,
  and bounded dry run.
- Acceptance: docs contain no instruction to acquire or discover during M0.1 and remain
  synchronized with generated schemas.

### 6. Run complete local gates

- Run frozen dependency sync, Ruff format/lint, strict Pyright, complete tests, schema
  drift, repository data policy, pre-commit, `git diff --check`, and source-integrity
  verification.
- Confirm all 11 hashes/counts/sizes and zero files in derived layers; confirm LICENSE is
  unchanged; record exact command outputs and test count.
- Acceptance: every gate exits zero, or the completion report records the precise blocker
  rather than claiming success.

### 7. Review, commit, push, and remote CI

- Request an independent code review of the v0.2 diff; fix all critical/important issues.
- Commit the hardening pass on the dedicated branch and push it.
- Open a pull request to `main`; do not merge. Wait for the repository quality workflow
  and record check names, run URL/status, commit SHA, and any failures.
- Propose (do not apply) branch protection/ruleset requiring a pull request, at least one
  approving review, code-owner review if later configured, and the required quality
  checks on `main`.
- Acceptance: PR exists, remote CI result is recorded, and no M1 action has started.

## Verification checklist

- [ ] `schemas/v0.1.0` unchanged byte-for-byte.
- [ ] `schemas/v0.2.0` generated and current.
- [ ] No raw/external source modified; all 11 hashes match.
- [ ] No files added under `02_extracted`–`07_releases`.
- [ ] Frozen sync, Ruff, Pyright, pytest, schema drift, data policy, pre-commit pass.
- [ ] PR is open, remote Actions result recorded, branch is not merged.
- [ ] M1-01, M1-02, and M1-03 remain unauthorized/not started.
