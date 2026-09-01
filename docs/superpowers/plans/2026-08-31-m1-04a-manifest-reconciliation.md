# M1-04A Corpus Manifest Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a strict deterministic M1-04A reconciliation layer and candidate package from the frozen M1-02 discovery evidence and completed M1-03B.2 ledger.

**Architecture:** Strict manifest `v0.1.0` models define six research record families plus the materialization receipt. A read-only evidence loader validates frozen artifact bytes and operational hash chains; pure reconciliation functions build records; one canonical writer produces the ignored candidate package through a thin CLI.

**Tech Stack:** Python 3.12–3.13, Pydantic v2, repository canonical JSON/SHA utilities, pytest, Ruff, Pyright.

**Spec:** `docs/superpowers/specs/2026-08-31-m1-04a-manifest-reconciliation-design.md`

## Global Constraints

- No Defensoría request, discovery rerun, live comparison, raw write, or canonical Dropbox write.
- Do not alter scientific, discovery, or acquisition schema snapshots or authorization anchors.
- Preserve discovery capture multiplicity and source-original text exactly.
- Report rows require observed qualifying number/month evidence; never infer reports 1–22 or historical monthly reports.
- Candidate outputs exist only under `.cache/m1-04a/` and remain untracked.
- Use only existing Pydantic/PyYAML dependencies.

---

### Task 1: Strict manifest contract and schema export

**Files:**
- Create: `src/peru_conflicts/manifest/__init__.py`
- Create: `src/peru_conflicts/manifest/models.py`
- Create: `src/peru_conflicts/manifest/schema_export.py`
- Create: `tests/unit/test_manifest_models.py`
- Create: `tests/unit/test_manifest_schema_export.py`
- Modify: `scripts/export_schemas.py`
- Create: `schemas/manifest/v0.1.0/*.schema.json`

**Interfaces:**
- Produces: `CorpusReportManifestEntry`, `SourceObservationRecord`, `ByteVersionRecord`, `VersionSourceRelationshipEdge`, `GapRegisterEntry`, `CoverageReport`, `MaterializationReceipt`; `export_manifest_schemas()` and `manifest_schemas_are_current()`.

- [ ] **Step 1: Write strict-model tests** for unknown-field rejection, contradictory mappings, edge evidence requirements, report/gap separation, opaque-association preservation, and candidate-only coverage status.
- [ ] **Step 2: Run the focused tests and record RED** caused by the missing manifest package.
- [ ] **Step 3: Implement the minimum strict models and validators** required by those behaviors.
- [ ] **Step 4: Run focused tests and record GREEN.**
- [ ] **Step 5: Add schema-export tests, record RED, register deterministic rendering, export `manifest/v0.1.0`, and record GREEN** while proving all existing schema trees remain unchanged.

### Task 2: Frozen evidence loader

**Files:**
- Create: `src/peru_conflicts/manifest/evidence.py`
- Create: `tests/unit/test_manifest_evidence.py`

**Interfaces:**
- Produces: `DiscoveryRunInput`, `DiscoveryOccurrence`, `AcquisitionClosure`, `load_discovery_runs()`, and `load_acquisition_closure()`.
- Consumes: discovery `v0.3.0` models, acquisition `v0.2.0` adapters and graph validation, `DataPaths`, canonical hashes.

- [ ] **Step 1: Write failing tests** for exact artifact fingerprints, run-ID mismatches, input-order normalization, cross-run repeated record preservation, invalid ledger chains, terminal mismatch, unexpected raw files, and ten-file hash closure.
- [ ] **Step 2: Run and record RED** because evidence loaders do not exist.
- [ ] **Step 3: Implement read-only loaders** with reviewed fingerprints and no transport imports.
- [ ] **Step 4: Run and record GREEN.**

### Task 3: Identity and source-observation reconciliation

**Files:**
- Create: `src/peru_conflicts/manifest/reconcile.py`
- Create: `tests/unit/test_manifest_reconciliation.py`

**Interfaces:**
- Produces: `reconcile_manifest(discovery, acquisition, context) -> CandidatePackage`.
- Consumes: validated occurrences and closure from Task 2.

- [ ] **Step 1: Write failing tests** showing one-to-one observed mapping, both contradiction directions, no sequence-filled rows, no numberless monthly identity, separate expected months, preserved run/record/URL observation multiplicity, source-original text, and distinct apex/`www` URLs.
- [ ] **Step 2: Run and record RED.**
- [ ] **Step 3: Implement paired-evidence mapping and source observations** with run-qualified stable IDs and deterministic title policy.
- [ ] **Step 4: Run and record GREEN.**

### Task 4: Byte versions, graph, gaps, and coverage

**Files:**
- Modify: `src/peru_conflicts/manifest/reconcile.py`
- Modify: `tests/unit/test_manifest_reconciliation.py`

**Interfaces:**
- Extends `CandidatePackage` with byte versions, relationship edges, gaps, and coverage.

- [ ] **Step 1: Write failing tests** for exact-SHA byte identity, multiple-URL non-equivalence, alternate bytes, ten-report ledger closure, 261/263 opacity, stale embedded-title non-authority, 22 report-number gaps, 21 historical-month gaps, unnumbered 2004/2005 leads, and candidate-only coverage.
- [ ] **Step 2: Run and record RED.**
- [ ] **Step 3: Implement the minimum reconciliation logic** without inferred byte or report identities.
- [ ] **Step 4: Run and record GREEN.**

### Task 5: Canonical materializer and CLI

**Files:**
- Create: `src/peru_conflicts/manifest/materialize.py`
- Create: `scripts/reconcile_corpus_manifest.py`
- Create: `tests/unit/test_manifest_materialization.py`

**Interfaces:**
- Produces: `materialize_candidate_package()` and `python scripts/reconcile_corpus_manifest.py --discovery-run ... --output ...`.

- [ ] **Step 1: Write failing tests** for canonical JSONL, byte-identical reruns in separate directories, input-order invariance, output reread/roundtrip, existing-output rejection, and all prohibited output roots.
- [ ] **Step 2: Run and record RED.**
- [ ] **Step 3: Implement one canonical writer and thin argument parser.**
- [ ] **Step 4: Run and record GREEN.**

### Task 6: Closure and M1-04 documentation

**Files:**
- Create: `docs/m1_03b2_completion_report.md`
- Modify: `docs/execution_plan.md`
- Retain: this plan and its paired design specification.

**Interfaces:**
- Documents the immutable completed run and candidate/noncanonical review boundary.

- [ ] **Step 1: Write the bounded M1-03B.2 completion report** from ledger evidence without absolute user paths.
- [ ] **Step 2: Update only current execution-status text** to mark M1-03 complete, M1-04A active, and M2 unstarted.
- [ ] **Step 3: Check documentation for accidental final-completeness language or private paths.**

### Task 7: Verification, committed implementation, and candidate materialization

**Files:**
- Generate ignored: `.cache/m1-04a/*`

**Interfaces:**
- Produces the seven candidate files and a one-commit PR branch.

- [ ] **Step 1: Run targeted tests, Ruff, strict Pyright for Windows/Linux, schema drift, full pytest once, and repository data policy.**
- [ ] **Step 2: Inspect the complete tracked diff and explicit staged paths; verify authorization anchors, scientific schemas, Dropbox, and operational ledger remain unchanged.**
- [ ] **Step 3: Commit once with `Implement M1-04A corpus manifest reconciliation`.**
- [ ] **Step 4: Materialize `.cache/m1-04a/` from the committed implementation SHA and audit every count/hash/linkage invariant.**
- [ ] **Step 5: Obtain one narrow independent review of identity fidelity, gaps, byte/version semantics, completeness language, and provenance closure.**
- [ ] **Step 6: Push normally and create the implementation PR without waiting for CI or merging.**
