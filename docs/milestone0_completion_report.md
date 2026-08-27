# Milestone 0 completion report

> Historical receipt for the pre-hardening M0 commit. The owner-approved M0.1 pass
> supersedes its provisional schema/manifest recommendations; see
> `docs/milestone0.1_completion_report.md` and the v0.1.0-to-v0.2.0 migration note.

Completion date: 2026-08-27 (Europe/Berlin)

Branch: `codex/milestone-0-foundation`

Status: **Milestone 0 foundation complete and verified; stopped before Milestone 1.** No commit, push, pull request, merge, release, corpus crawl, benchmark annotation, parser, OCR, model extraction, historical linkage, taxonomy harmonization, or geocoding was performed.

## Outcome

The live repository has been expanded from `README.md` plus the preserved MIT `LICENSE` into an executable research-data engineering foundation. It uses a validated external data root, strict source-preserving models, retained versioned JSON Schemas, deterministic hashes and IDs, collision-safe run fingerprints, standards-compliant structured logs, data/secret/large-file guards, a real uv lock, CI/pre-commit quality controls, current Codex examples, project documentation, ADRs, and an approval-gated Milestone 1-12 execution plan.

Independent read-only reviewers audited live resources/capabilities, the archive seed, Dropbox sources, schema/domain design, reproducibility controls, and full M0 alignment. Their blocking findings were reproduced before repair. The final foundation rejects the demonstrated coercion, path-alias, staged-blob, provenance-bypass, evidence-free-link, impossible-month, negative-casualty, config-hash-collision, and invalid-JSON-log cases.

## Required deliverables

| # | Deliverable | Result |
|---:|---|---|
| 1 | `docs/codex_capability_inventory.md` | Complete; distinguishes installed/configured/callable/authenticated/used states |
| 2 | `docs/live_resource_inventory.md` | Complete; GitHub, full Dropbox hierarchy, workbook, and reports 260-269 |
| 3 | `docs/bootstrap_audit.md` | Complete; archive integrity, live differences, current Codex syntax, and adaptations |
| 4 | Adapted repository foundation | Complete; 141 Git candidate files after this report, no source/data artifacts |
| 5 | Finalized `AGENTS.md` | Complete; M0 gate and research contract enforced |
| 6 | `pyproject.toml` plus real `uv.lock` | Complete; 26-package lock, frozen sync verified |
| 7 | Safe config/path foundation plus tests | Complete; two-way repo/data-root separation, logical/resolved write-zone checks, synthetic roots |
| 8 | Domain/schema foundation plus tests | Complete; 23 canonical entity schemas at `schemas/v0.1.0/` |
| 9 | Run metadata/logging | Complete; Git/config/schema/lock/input/environment/model identity and valid JSON Lines |
| 10 | CI/pre-commit | Complete; frozen dependencies, format, lint, typing, tests, schema drift, data/secret guard |
| 11 | ADRs | Ten accepted M0 ADRs |
| 12 | `docs/execution_plan.md` | Complete; detailed M1-M4 work packages and M5-M12 roadmap |
| 13 | Completion report | This document |
| 14 | Decisions requiring Jorge approval | Listed below |
| 15 | Git diff/commit summary | Listed below; no commit exists |
| 16 | No raw source modified | Verified by all eleven hashes and unchanged Dropbox aggregate inventory |

## Implemented technical foundation

### Data-root safety

- Resolves an explicit root or `CONFLICT_DATA_ROOT`.
- Requires all nine expected storage zones.
- Rejects the repository as the root, a root inside the repository, or a repository inside the data root.
- Treats `00_external`, `01_raw`, and `99_archive` as routine read-only zones.
- Checks both logical and resolved paths, preventing a protected-zone symlink/reparse alias from becoming writable.
- Allows tests to construct complete synthetic roots without touching Dropbox.

This is an application-level safety boundary, not an operating-system ACL. Exceptional acquisition into raw storage remains a separate, explicitly authorized future workflow.

### Models and schemas

- Strict Pydantic validation forbids extra fields, type coercion, non-finite numbers, impossible months, negative counts, and blank identifiers.
- Open source-original plus normalized text is retained for conflict types, status, phase, transitions, names, actors, demands, geography, and relationships.
- Transitions are open evidence records rather than hard-coded historical flags.
- Conflict cases, protest events, and violence events are distinct; links require provenance.
- Unknown casualty totals/components remain null; components use typed nonnegative records.
- Pipeline extraction methods are controlled. `probabilistic_model` requires full model/prompt/schema/span/output identity in Pydantic and JSON Schema; aliases cannot bypass it.
- Discrepancies require rationale, parser version, and type-appropriate evidence while preserving `PARSER_ERROR` and `SOURCE_INCONSISTENCY` as distinct classes.
- Manual review uses immutable JSON documents, evidence, timezone-aware timestamps, explicit decision actions, supersession, and consistent second-review pairs.
- Generated schemas are retained under actual version directories. Python validation remains authoritative for documented semantic cross-field invariants that JSON Schema does not express.
- Stable ID scheme `1` has a pinned UUID5 golden vector before canonical rows exist.

### Reproducibility and repository protection

- Run metadata hashes every config without same-basename collapse, all versioned schemas recursively, `uv.lock`, and every declared input.
- Environment metadata records Python/platform/packages and caller-supplied system-binary versions.
- JSON logging emits one standards-compliant object per line; non-finite diagnostic floats become explicit strings rather than invalid JSON tokens.
- The repository guard checks tracked and untracked candidates, prohibited source/data/log formats, credential-like names, selected secret/link content patterns, file size, and—during pre-commit—the actual index blobs rather than replaceable worktree bytes.
- `.gitignore`, `.gitattributes`, pre-commit, and CI reinforce the same boundary.

## Verification receipt

Fresh final verification on Python 3.12.13:

| Check | Result |
|---|---|
| `uv lock --check` | Passed; 26 packages resolved |
| `uv sync --frozen --group dev` | Passed; 26 packages checked |
| `uv run ruff format --check .` | Passed; 95 files formatted |
| `uv run ruff check .` | Passed |
| `uv run pyright` | Passed; 0 errors, 0 warnings |
| `uv run pytest` | Passed; 76 tests, 0 failures, 0 skips |
| `uv run python scripts/export_schemas.py --check` | Passed; 23 current schemas |
| `uv run python scripts/check_git_data_policy.py` | Passed |
| `git diff --check` | Passed |
| Eight project skill structural validations | Passed |
| JSON/TOML/YAML syntax audit | Passed |

No gold benchmark exists yet, so no benchmark accuracy test or parser guarantee was fabricated. The >=99% targets remain future acceptance gates.

## Source-integrity verification

The eleven allowed M0 inputs were hashed again after implementation. Every SHA-256 exactly matched the pre-implementation baseline in `docs/live_resource_inventory.md`:

- `Base15-26.xlsx`: match.
- Reports 260, 261, 262, 263, 264, 265, 266, 267, 268, and 269: ten matches.
- Aggregate Dropbox inventory: 82 directories, 110 files, 33,453,193 bytes before and after.
- `LICENSE`: unchanged SHA-256 `7838bc30d3402b894dc236cc3cc9a62933f3dd6ec71ff21f02f1044f38b5edff`.

Therefore no raw PDF, workbook, archive seed, or other Dropbox file was modified by M0.

## Git diff and commit summary

- Base/default-branch commit: `14b913f390056a74b598de08742be1120515dda6`.
- Current branch: `codex/milestone-0-foundation`.
- Existing tracked change: expanded `README.md`.
- New untracked foundation: root governance/build files; `.agents`, `.codex`, `.github`; six configs; 49 documentation files including ten ADRs; 24 schema files including the schema README; package/scripts; fixtures/notebook/test directory markers; and the real `uv.lock`.
- Expected final candidate total after this report: 141 files (the two original tracked files plus 139 new files), all below 1 MiB.
- Commits created: none.
- Remote writes, branch publication, pull requests, merges, tags, and releases: none.

## Decisions requiring Jorge's approval before M1

Recommended defaults are stated for a concise review.

1. **Authorize M1 start.** Recommended: approve M1-01 and M1-02 for protocol design and read-only official-source reconnaissance only.
2. **Choose the M1 acquisition checkpoint.** Recommended: require a second explicit approval before M1-03 writes newly downloaded official bytes into `01_raw`; discovery records alone do not authorize acquisition.
3. **Approve the M0 schema/config contract as the M1 baseline.** Recommended: accept `schema_version=0.1.0`, ID scheme `1`, extraction-method vocabulary, and the Git/Dropbox boundary; later changes require migrations and retained prior schemas.
4. **Confirm manifest publication boundary.** Recommended: keep URLs, hashes, report metadata, and coverage receipts in Git, while official PDFs/workbooks and any restricted row-level evidence stay in Dropbox. Public redistribution rights remain unresolved until a later legal/source-terms review.

No benchmark-gate revision, licensing change, significant paid service, or new external dependency is proposed. M1 must not begin until item 1 is explicitly approved; M1-03 must not begin until item 2 is explicitly approved.

## Deferred by design

Java, Tesseract/Spanish data, qpdf, Ghostscript, DuckDB/PyArrow, PDF parsing libraries, OCR, geospatial, linkage, and model SDKs remain absent from the project dependency set. They are not M0 defects. Additions require a specific authorized package, measured need, system/license/security review, and tests. Poppler native-text/page inspection and the bundled workbook reader were sufficient for the M0 integrity snapshot.
