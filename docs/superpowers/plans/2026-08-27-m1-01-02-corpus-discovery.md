# M1-01/M1-02 Corpus Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and execute a source-safe, versioned, HTML-only discovery protocol for official Defensoría social-conflict reports from April 2004 onward, then stop before acquisition.

**Architecture:** A separate versioned discovery contract (current `discovery/v0.2.0`, with `v0.1.0` retained) models paired identity evidence, source page metadata, and URL roles without changing scientific schema `v0.2.0`. Pure URL/pagination/HTML functions are isolated from a serial, robots-aware standard-library client; the thin CLI writes only to Git-ignored temporary output. The live M1-02 run produces a review report, not a public Git source index or Dropbox ledger.

**Tech Stack:** Python 3.12-3.13, Pydantic 2, PyYAML, urllib/HTMLParser, pytest, Ruff, strict Pyright, pre-commit.

**Spec:** `docs/superpowers/specs/2026-08-27-m1-01-02-corpus-discovery-design.md`

## Global Constraints

- M1-01 and M1-02 are authorized; M1-03 and every raw write remain prohibited.
- Initial authoritative hosts are exactly `defensoria.gob.pe` and `www.defensoria.gob.pe`.
- Retrieve official HTML/robots/headers only; never retrieve discovered PDF bodies.
- Use serial concurrency 1, a live-run delay of at least 2.0 seconds, and at most two retries.
- `schemas/v0.1.0/` and `schemas/v0.2.0/` must remain byte-identical to the approved merge.
- No Dropbox writes and no files under active derived layers `02_extracted` through `07_releases`.
- No public Git source index; full provisional records live only in Git-ignored `.cache/`.
- Tests precede production behavior, and every test must fail for the intended missing behavior before implementation.
- No PDF parsing, OCR, gold annotation, extraction, entity resolution, geocoding, LLM calls, or canonical materialization.

---

### Task 1: Governance transition and configuration

**Files:**
- Modify: `AGENTS.md`
- Modify: `config/project.yaml`
- Create: `config/official_sources.yaml`
- Modify: `docs/29_open_questions.md`
- Modify: `docs/execution_plan.md`
- Modify: `docs/github_branch_protection_proposal.md`

**Interfaces:**
- Consumes: the approved M1 boundary and live ruleset receipt.
- Produces: the durable authorization gate and exact source/retrieval configuration used by later tasks.

- [x] **Step 1: Add the approved M1 gate and deferred M2 questions**

  Update the documents so `v0.2.0` is explicitly an M1-only working baseline, M2-01 owns the five named ontology questions, and M1-03 remains separately prohibited.

- [x] **Step 2: Add the official-source configuration**

  Define the two approved hosts, starting surface URLs, serial concurrency `1`, delay `2.0`, retry cap `2`, HTML content types, and binary/PDF rejection policy in `config/official_sources.yaml`.

- [x] **Step 3: Validate configuration syntax**

  Run: `uv run python -c "from pathlib import Path; import yaml; yaml.safe_load(Path('config/official_sources.yaml').read_text(encoding='utf-8'))"`

  Expected: exit `0` with no output.

### Task 2: Versioned provisional discovery schema

**Files:**
- Create: `src/peru_conflicts/discovery/__init__.py`
- Create: `src/peru_conflicts/discovery/models.py`
- Create: `src/peru_conflicts/discovery/schema_export.py`
- Create: `tests/unit/test_discovery_models.py`
- Create: `tests/unit/test_discovery_schema_export.py`
- Create: `schemas/discovery/v0.2.0/provisional_discovery_record.schema.json`; retain the
  generated `schemas/discovery/v0.1.0/` snapshot unchanged
- Modify: `scripts/export_schemas.py`
- Modify: `schemas/README.md`

**Interfaces:**
- Consumes: `StrictModel`, identifier/reference-period validation conventions, and the M1 evidence design.
- Produces: `IdentityEvidence`, `UrlObservation`, `RedirectHop`, `CandidateSourceRelation`, `CoverageExpectation`, and `ProvisionalDiscoveryRecord`; `export_discovery_schemas()` and `discovery_schemas_are_current()`.

- [x] **Step 1: Write failing model tests**

  Tests must show that report-number/reference-period values require paired evidence, embedded-title/filename evidence cannot be the sole identity basis, landing/download/redirect roles remain distinct, null candidates are valid, source contradictions are preserved, and candidate source relations do not claim byte identity.

- [x] **Step 2: Run tests and verify the intended failure**

  Run: `uv run pytest tests/unit/test_discovery_models.py -q`

  Expected: collection/import failure because the discovery models do not exist.

- [x] **Step 3: Implement the minimal strict models**

  Use a frozen strict technical discovery schema, non-empty identifiers, source-original page
  metadata, and model validators enforcing evidence pairing and identity-source sufficiency;
  bump the discovery version when adding fields and retain prior generated directories.

- [x] **Step 4: Run model tests to green**

  Run: `uv run pytest tests/unit/test_discovery_models.py -q`

  Expected: all model tests pass.

- [x] **Step 5: Write failing schema-export tests**

  Require deterministic export under the current `schemas/discovery/v0.2.0/`, preservation of
  prior discovery and scientific schema directories, and drift detection through the existing
  `scripts/export_schemas.py --check` gate.

- [x] **Step 6: Implement export and regenerate the schema**

  Run: `uv run python scripts/export_schemas.py`

  Expected: scientific schemas are unchanged and the discovery schema is written deterministically.

- [x] **Step 7: Run schema tests**

  Run: `uv run pytest tests/unit/test_discovery_models.py tests/unit/test_discovery_schema_export.py -q`

  Expected: all tests pass.

### Task 3: URL authority, normalization, coverage, and pagination

**Files:**
- Create: `src/peru_conflicts/discovery/policy.py`
- Create: `tests/unit/test_discovery_policy.py`

**Interfaces:**
- Consumes: source configuration and discovery URL/evidence models.
- Produces: `normalize_url()`, `classify_host()`, `build_coverage_grid()`, and `PaginationTracker` with explicit stop reasons.

- [x] **Step 1: Write failing behavior tests**

  Cover scheme/host normalization, tracking-query removal without damaging meaningful search parameters, fragment removal, relative URL resolution, rejection of credentials/non-HTTP schemes, exact-host allowlisting, pending classification for other subdomains/shorteners, April-2004 coverage-grid semantics, repeated-page termination, visible-next termination, and safety-cap termination.

- [x] **Step 2: Run tests and verify failure**

  Run: `uv run pytest tests/unit/test_discovery_policy.py -q`

  Expected: import failure because `policy.py` is absent.

- [x] **Step 3: Implement pure policy functions**

  Keep URL normalization loss-minimizing: preserve path case and meaningful query values; never rewrite an unapproved host into an approved one.

- [x] **Step 4: Run tests to green**

  Run: `uv run pytest tests/unit/test_discovery_policy.py -q`

  Expected: all tests pass.

### Task 4: Safe HTML-only reconnaissance engine and CLI

**Files:**
- Create: `src/peru_conflicts/discovery/html.py`
- Create: `src/peru_conflicts/discovery/client.py`
- Create: `src/peru_conflicts/discovery/reconnaissance.py`
- Create: `scripts/discover_official_sources.py`
- Create: `tests/fixtures/discovery/catalogue_page_1.html`
- Create: `tests/fixtures/discovery/catalogue_page_2.html`
- Create: `tests/unit/test_discovery_html.py`
- Create: `tests/integration/test_discovery_reconnaissance.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: the policy functions, models, and `config/official_sources.yaml`.
- Produces: `parse_discovery_page()`, a robots-aware `HtmlClient`, `run_reconnaissance()`, and a CLI whose output directory must be outside the protected data root.

- [x] **Step 1: Write failing HTML parser tests**

  Fixtures must exercise report title/publication date/file URL extraction, candidate number/month parsing from visible official metadata, visible next-page discovery, duplicate links, and non-conflict report exclusion without using PDF text.

- [x] **Step 2: Run parser tests and verify failure**

  Run: `uv run pytest tests/unit/test_discovery_html.py -q`

  Expected: import failure because the parser is absent.

- [x] **Step 3: Implement the deterministic HTML parser**

  Use `html.parser.HTMLParser`; keep Spanish source strings intact and create paired official-metadata evidence.

- [x] **Step 4: Write failing client/integration tests**

  Use an injected fake transport to prove serial traversal, delay invocation, retry limits, `Retry-After` handling, robots rejection, PDF/body rejection, redirect evidence, output-path refusal for `CONFLICT_DATA_ROOT`, temporary JSON/JSONL output, idempotent reruns, and explicit incomplete stop reasons.

- [x] **Step 5: Run integration tests and verify failure**

  Run: `uv run pytest tests/integration/test_discovery_reconnaissance.py -q`

  Expected: import or assertion failure for missing client behavior.

- [x] **Step 6: Implement the minimal client, runner, and CLI**

  The live mode must use concurrency `1`, delay `>=2.0`, retries `<=2`, and never call GET on a discovered `.pdf` or a response advertised as PDF/binary.

- [x] **Step 7: Run Task 4 tests to green**

  Run: `uv run pytest tests/unit/test_discovery_html.py tests/integration/test_discovery_reconnaissance.py -q`

  Expected: all tests pass without network or Dropbox access.

### Task 5: Live read-only M1-02 run, receipts, and milestone report

**Files:**
- Create: `docs/m1_official_source_discovery_protocol.md`
- Create: `docs/m1_robots_rate_limit_terms_receipt.md`
- Create: `docs/m1_01_02_review_report.md`
- Modify: `docs/m1_acquisition_checkpoint.md`
- Modify: `README.md`
- Temporary only: `.cache/m1-discovery-2026-08-27/`

**Interfaces:**
- Consumes: the complete tested discovery command and approved official surfaces.
- Produces: a provisional temporary inventory, durable methodological receipts and coverage summary, and the exact bounded M1-03 proposal without acquiring anything.

- [x] **Step 1: Record pre-run source integrity and derived-layer state**

  Recompute the 11 approved hashes and count files under `02_extracted` through `07_releases`; retain the receipt in the review report.

- [x] **Step 2: Run official HTML-only reconnaissance**

  Run the CLI against the reports catalogue, thematic page, official search/pagination, and discovered official document surfaces with output under `.cache/m1-discovery-2026-08-27/`. Do not request PDF bodies.

- [x] **Step 3: Review the provisional inventory**

  Summarize observed candidate coverage from April 2004, gaps, duplicate/ambiguous identities, suspected alternate source URLs, redirects/new hosts, and every stop reason. Do not assert completeness.

- [x] **Step 4: Write protocol, robots/rate-limit/terms receipt, and review report**

  Include exact URLs, timestamps, page/request counts, response-header evidence, unresolved redistribution rights, schema changes, and the exact proposed first acquisition set.

- [x] **Step 5: Run the complete quality gate**

  Run: `uv sync --frozen --group dev`; `uv run ruff format --check .`; `uv run ruff check .`; `uv run pyright`; `uv run pytest`; `uv run python scripts/export_schemas.py --check`; `uv run python scripts/check_git_data_policy.py`; `uv run pre-commit run --all-files`; `git diff --check`.

  Expected: every command exits `0`.

- [x] **Step 6: Reverify source integrity and M1 boundary**

  Confirm all 11 source hashes are unchanged, no file was added to Dropbox layers `02`-`07`, no file was added to `01_raw`, and no PDF/workbook/data artifact is tracked by Git.

- [x] **Step 7: Freeze the branch and stop before M1-03**

  Commit and push the focused branch only after verification. Present the acquisition command/dry-run proposal with exact maximum report/URL count, concurrency, delay, retry cap, temporary location, hash-before-promote, collision/version handling, idempotency, and rollback/abandon behavior. Do not execute it.
