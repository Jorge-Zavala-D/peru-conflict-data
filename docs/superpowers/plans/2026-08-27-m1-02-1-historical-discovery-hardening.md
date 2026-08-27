# M1-02.1 Historical Discovery Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the parser-limited historical discovery inventory, strengthen the HTML-only safety/receipt contract, and produce a durable reviewed M1-03 pilot recipe without retrieving a PDF or writing Dropbox.

**Architecture:** Discovery contract `v0.3.0` separates containing-page metadata from bounded entry metadata and adds strict request-attempt and pilot-plan records while retaining prior schema versions. A source-order entry parser and verified WordPress pagination extractor feed a serial client whose transport gates MIME before body reads; the runner reports local traversal termination independently from corpus completeness.

**Tech Stack:** Python 3.12-3.13, Pydantic 2, PyYAML, `urllib`, `html.parser`, pytest, Ruff, strict Pyright, pre-commit.

**Spec:** `docs/superpowers/specs/2026-08-27-m1-02-1-historical-discovery-hardening-design.md`

## Global Constraints

- Continue only on `codex/m1-01-02-corpus-discovery`; never merge this branch.
- M1-03, M1-04, M2, PDF retrieval, OCR, parsing, extraction, entity resolution, and raw/canonical writes remain prohibited.
- Dropbox is read-only; `01_raw/manifests/` and layers `02_extracted` through `07_releases` receive zero writes.
- Scientific `schemas/v0.1.0/` and `schemas/v0.2.0/`, and discovery `v0.1.0`/`v0.2.0`, remain byte-identical.
- Live requests are serial, HTML/XHTML or exact-host robots text only, delayed at least 2.0 seconds, with at most two retries.
- The full live traversal runs once, after offline tests, targeted verification, and independent review.
- The main agent is the only writer for schemas, fixtures, configuration, inventories, pilot plan, and final integration.

---

### Task 1: Forward-version the discovery evidence contract

**Files:**
- Modify: `src/peru_conflicts/discovery/models.py`
- Create: `src/peru_conflicts/discovery/receipts.py`
- Modify: `src/peru_conflicts/discovery/__init__.py`
- Modify: `src/peru_conflicts/discovery/schema_export.py`
- Modify: `tests/unit/test_discovery_models.py`
- Create: `tests/unit/test_discovery_receipts.py`
- Modify: `tests/unit/test_discovery_schema_export.py`
- Modify: `tests/unit/test_schema_versioning.py`
- Create: `schemas/discovery/v0.3.0/*.schema.json`
- Create: `docs/schema_migrations/discovery_v0.2.0_to_v0.3.0.md`
- Modify: `schemas/README.md`

**Interfaces:**
- Produces: `ProvisionalDiscoveryRecord` fields `source_page_title_original`, `entry_title_original`, `entry_publication_date_original`, and `entry_description_original`.
- Produces: strict `RequestAttemptReceipt`, selected-header evidence,
  `SurfaceTraversalReceipt`, and `ReconnaissanceSummary` models.
- Preserves: tree digests for scientific `v0.1.0`/`v0.2.0` and discovery `v0.1.0`/`v0.2.0`.

- [x] **Step 1: Write failing discovery-v0.3 model tests**

  Add literal assertions proving page and entry titles/dates are independent. In
  `test_discovery_receipts.py`, prove body hashes require a read byte count,
  rejected/transport-error attempts cannot claim a body hash, and only selected
  headers are representable. Pilot invariants are exercised through the plan
  consumer test in Task 5.

- [x] **Step 2: Verify the intended RED state**

  Run: `uv run pytest tests/unit/test_discovery_models.py tests/unit/test_discovery_receipts.py tests/unit/test_discovery_schema_export.py tests/unit/test_schema_versioning.py -q`

  Expected: failures because `v0.3.0` fields/models/schemas do not exist and current version is `0.2.0`.

- [x] **Step 3: Implement the minimal strict models**

  Use these public shapes:

  ```python
  class ProvisionalDiscoveryRecord(StrictModel):
      schema_version: Literal["0.3.0"] = "0.3.0"
      source_page_title_original: str | None = None
      entry_title_original: str | None = None
      entry_publication_date_original: str | None = None
      entry_description_original: str | None = None


  class RequestAttemptReceipt(StrictModel):
      schema_version: Literal["0.3.0"] = "0.3.0"
      receipt_id: Identifier
      observation_id: Identifier | None = None
      request_kind: RequestKind
      attempt_number: int = Field(ge=1)
      redirect_index: int = Field(ge=0)
      requested_url: Identifier
      requested_at: AwareDatetime
      completed_at: AwareDatetime
      outcome: RequestOutcome
      status_code: int | None = Field(default=None, ge=100, le=599)
      selected_headers: SelectedHttpHeaders
      body_read: bool
      body_byte_count: int | None = Field(default=None, ge=0)
      body_sha256: str | None = None
  ```

  Keep semantic cross-field checks in Pydantic. Put transport receipts in
  `receipts.py` and the declarative pilot contract/loader in `pilot.py`; generate
  the provisional-record, request-attempt, and reconnaissance-summary schemas deterministically
  under `schemas/discovery/v0.3.0/`.

- [x] **Step 4: Generate only discovery `v0.3.0` and run focused tests**

  Run: `uv run python scripts/export_schemas.py`

  Run: `uv run pytest tests/unit/test_discovery_models.py tests/unit/test_discovery_receipts.py tests/unit/test_discovery_schema_export.py tests/unit/test_schema_versioning.py -q`

  Expected: all focused tests pass; prior four schema-tree digests are unchanged.

### Task 2: Parse bounded historical source entries and real pagination markup

**Files:**
- Modify: `src/peru_conflicts/discovery/html.py`
- Modify: `tests/unit/test_discovery_html.py`
- Create: `tests/fixtures/discovery/thematic_historical_bundles.html`
- Create: `tests/fixtures/discovery/thematic_historical_numbered_2006.html`
- Create: `tests/fixtures/discovery/search_page_1_live_pagination.html`
- Create: `tests/fixtures/discovery/search_result_item_dates.html`
- Create: `tests/fixtures/discovery/thematic_page_chrome.html`

**Interfaces:**
- Produces: entry-scoped candidate records from `h1`-`h6`, article/card scopes, source order, and entry-local links/date/description.
- Produces: `ParsedDiscoveryPage.next_url` from observed WordPress next/numeric pagination without treating generic page content as report metadata.

- [x] **Step 1: Add realistic Spanish fixtures and failing parser tests**

  The fixtures reproduce thematic `.card > .card-body` records and search-result
  `<li>` records. They contain independent 2004/2005 ZIP-linked entries, reports
  23-34, generic `Conflictos Sociales` headings, `h6` dates, unrelated
  informes/notas, nested heading spans, multiple entry-local downloads, and the
  `.pagination` page-2/`-›`/`Último »` markup. Assert that report 23 is observed,
  reports 1-22 are not invented, 2004/2005 months remain null, each date stays
  with its entry, page 2 wins over page 9, and unrelated links never cross blocks.

- [x] **Step 2: Verify parser tests fail for the audited bugs**

  Run: `uv run pytest tests/unit/test_discovery_html.py -q`

  Expected: failures showing missing lower-heading/block extraction, date leakage, and unrecognized pagination.

- [x] **Step 3: Implement entry blocks and pagination extraction**

  Build candidate inputs as `(entry_title, entry_description, entry_date,
  scoped_links)` rather than page-global candidate strings. Select thematic
  `.card`, search `<li>`, catalogue article/card, and landing-page scopes. Parse
  identity only from the title/description pair; exclude the publication date
  from reference-period inference. Recognize PDF/ZIP links as direct-file
  observations but never fetch them. Resolve the next numeric page inside
  `.pagination` and never confuse `Último »` with the immediate next page.

- [x] **Step 4: Run parser tests to green and mutation-check scoping**

  Run: `uv run pytest tests/unit/test_discovery_html.py -q`

  Expected: all parser tests pass; moving one fixture date/download into another block makes at least one scoping assertion fail.

### Task 3: Enforce bounded CLI policy and honest traversal semantics

**Files:**
- Create: `src/peru_conflicts/discovery/config.py`
- Modify: `src/peru_conflicts/discovery/policy.py`
- Modify: `src/peru_conflicts/discovery/reconnaissance.py`
- Modify: `scripts/discover_official_sources.py`
- Modify: `config/official_sources.yaml`
- Modify: `tests/unit/test_discovery_policy.py`
- Create: `tests/unit/test_discovery_config.py`
- Modify: `tests/integration/test_discovery_reconnaissance.py`

**Interfaces:**
- Produces: `load_discovery_config()` and `resolve_runtime_limits()`; CLI flags may only make the approved run more conservative.
- Produces: stop receipts with `local_traversal_terminated`, `pagination_contract_verified`, `pagination_exhausted`, and `corpus_completeness: not_assessed`.

- [x] **Step 1: Write failing policy/config/runner tests**

  Assert rejection of delay `1.99`, retries `3`, page cap `121`, and landing cap `25`; acceptance of delay `2.0`, retries `0`, page cap `1`, and landing cap `0`; no bypass flag; `NO_NEXT_LINK` is local termination but only verified contracts can be pagination exhaustion; `REPEATED_URL` is never exhaustion or completeness.

- [x] **Step 2: Verify the intended RED state**

  Run: `uv run pytest tests/unit/test_discovery_config.py tests/unit/test_discovery_policy.py tests/integration/test_discovery_reconnaissance.py -q`

  Expected: failures because hard bounds and renamed summary fields are absent.

- [x] **Step 3: Implement config-owned bounds and renamed semantics**

  Add configured maxima/minima (`2.0`, `2`, `120`, `24`) and optional repeatable `--surface-id` selection for bounded targeted verification. Remove machine `complete` fields; never emit a corpus-complete boolean from M1.

- [x] **Step 4: Run focused tests to green**

  Run: `uv run pytest tests/unit/test_discovery_config.py tests/unit/test_discovery_policy.py tests/integration/test_discovery_reconnaissance.py -q`

  Expected: all focused tests pass without network access.

### Task 4: Preserve per-attempt HTTP evidence and reject MIME before reading

**Files:**
- Modify: `src/peru_conflicts/discovery/client.py`
- Modify: `tests/integration/test_discovery_reconnaissance.py`

**Interfaces:**
- `HttpTransport.request(..., allowed_content_types: frozenset[str]) -> HttpResponse` inspects headers before body reads.
- `HtmlClient.request_receipts` contains one `RequestAttemptReceipt` per actual attempt, including transient and transport-error attempts.

- [x] **Step 1: Write failing transport/receipt tests**

  Use a fake urllib response whose `read()` raises if invoked for
  `application/x-unlisted-binary`; assert rejection occurs without that call. Add a
  `503, 200` sequence with deterministic UTC clock values and assert two distinct
  attempts, timestamps, `Retry-After`, selected cache/rate headers, HTML byte count,
  and literal SHA-256.

- [x] **Step 2: Verify the intended RED state**

  Run: `uv run pytest tests/integration/test_discovery_reconnaissance.py -q`

  Expected: failures because the current transport reads unlisted MIME and receipts collapse retries.

- [x] **Step 3: Implement header-first body gating and attempt receipts**

  Pass the exact allowed MIME set into the transport. Read only successful approved bodies. Record each attempt in a `finally`-safe path and retain only the allowlisted header fields; never serialize request headers, cookies, or credentials.

- [x] **Step 4: Run integration and schema tests to green**

  Run: `uv run pytest tests/integration/test_discovery_reconnaissance.py tests/unit/test_discovery_models.py -q`

  Expected: all tests pass and the unlisted response object's `read()` call count remains zero.

### Task 5: Create the durable pilot recipe and revise M1 governance documents

**Files:**
- Create: `src/peru_conflicts/discovery/pilot.py`
- Create: `config/acquisition_pilots/m1_03_reports_260_269_v1.yaml`
- Create: `tests/unit/test_discovery_pilot.py`
- Modify: `docs/m1_official_source_discovery_protocol.md`
- Modify: `docs/m1_acquisition_checkpoint.md`
- Modify: `docs/m1_robots_rate_limit_terms_receipt.md`
- Modify: `docs/m1_01_02_review_report.md`
- Modify: `docs/execution_plan.md`
- Modify: `README.md`

**Interfaces:**
- Produces: strict `PilotAcquisitionPlan`/`PilotReportCandidate` loading and a
  fourth deterministic `discovery/v0.3.0` schema.
- Consumes: the ten existing benchmark hashes.
- Produces: a Git-safe recipe capped at 10 reports/20 URLs and a future command based on that reviewed plan, not `.cache/records.jsonl`.

- [x] **Step 1: Write the failing pilot-plan consumer test**

  Load the YAML through the strict model and assert reports 260-269 occur once,
  every landing/direct URL is on an approved host, all ten existing logical raw
  paths/local baseline sizes and hashes are present, every remote expected hash is
  null, and opaque report-261/report-263 URLs carry both unresolved-association and
  opaque-filename uncertainty.

- [x] **Step 2: Verify RED and create the minimal reviewed plan**

  Run: `uv run pytest tests/unit/test_discovery_pilot.py -q`

  Expected: failure because the plan does not exist.

  Create the plan with `max_reports: 10`, `max_urls: 20`, concurrency `1`, delay
  `2.0`, retries `2`, 30-second timeout, a hard total-attempt cap including robots,
  redirects, and retries, a 1 KiB-50 MB per-PDF and 500 MB total envelope, and
  `different_hash: stop_before_promotion`.

- [x] **Step 3: Update the checkpoint and protocol**

  Replace the ignored-cache input with
  `config/acquisition_pilots/m1_03_reports_260_269_v1.yaml`. Require approved host/robots/status,
  `application/pdf`, size, `%PDF-`, and SHA-256 before any future promotion;
  identical bytes deduplicate while multiple URL observations remain. State that
  the future dry run performs zero network and zero Dropbox writes, and that any
  authorized network preflight is a distinct later mode.

- [x] **Step 4: Run the pilot/config/document-focused tests**

  Run: `uv run pytest tests/unit/test_discovery_pilot.py tests/unit/test_discovery_settings.py -q`

  Expected: all focused tests pass; no acquisition script exists or runs.

### Task 6: Offline gate, targeted live check, independent review, one final run, and PR

**Files:**
- Modify: `docs/m1_01_02_review_report.md`
- Modify: `docs/m1_robots_rate_limit_terms_receipt.md`
- Create: `docs/m1_02_1_inventory_receipt.md`
- Modify: `docs/source_integrity_receipt_m1_02.md` only if a new append-only M1-02.1 section is warranted; otherwise create a separate receipt.
- Temporary only: `.cache/m1-discovery-2026-08-27-m1-02-1-targeted/`
- Temporary only: `.cache/m1-discovery-2026-08-27-m1-02-1-final-reviewed/`

**Interfaces:**
- Produces: the final ignored inventory, durable three-file hashes/bytes and findings, an exact source-integrity receipt, and an open unmerged PR with two required checks.

- [x] **Step 1: Run the complete offline test/quality gate before network use**

  Run: `uv sync --frozen --group dev`; `uv run ruff format --check .`; `uv run ruff check .`; `uv run pyright`; `uv run pytest -q`; `uv run python scripts/export_schemas.py --check`; `uv run python scripts/check_git_data_policy.py`; `uv run pre-commit run --all-files`; `git diff --check`.

  Expected: every command exits `0`.

- [x] **Step 2: Perform one small targeted official HTML-only verification**

  Run the CLI for only the thematic and official-search surface IDs with page cap
  `2`, landing cap `0`, delay `2.0`, and retry cap `2`. Verify request receipts
  contain only approved HTML/XHTML and exact `/robots.txt` text requests and that
  the output represents the 2004/2005 leads plus report 23.

- [x] **Step 3: Obtain independent integrated review before the final crawl**

  Give the reviewer the spec, plan, full diff, focused test outputs, and targeted
  receipt. Fix every critical/important finding with a new failing regression
  test and rerun the offline gate. Do not begin the full crawl until review passes.

- [x] **Step 4: Execute exactly one final bounded complete HTML-only reconnaissance**

  Use all configured starting surfaces, page cap `120`, landing cap `24`, delay
  `2.0`, retry cap `2`, and ignored output
  `.cache/m1-discovery-2026-08-27-m1-02-1-final-reviewed/`. Earlier complete
  attempts that expose a material live-structure defect become superseded
  diagnostic evidence, never the reportable inventory. Do not retry a reviewed
  run merely to change prose; preserve and report any bounded failure honestly.

- [x] **Step 5: Audit and document final evidence**

  Record exact byte counts and SHA-256 for `records.jsonl`, `requests.jsonl`, and
  `summary.json`; observed historical entries, traversal state, gaps,
  ambiguities/duplicates, suspected alternate versions, and the exact proposed
  260-269 acquisition URLs. Explicitly state corpus completeness is not assessed.

- [x] **Step 6: Reverify the final tree and Dropbox boundary**

  Rerun the full quality gate on the exact commit candidate. Recompute all eleven
  source hashes and confirm the exact Dropbox root counts plus zero files in
  layers `02_extracted` through `07_releases`. Verify Git tracks no PDF, workbook,
  JSONL inventory, secret, or large data object.

- [ ] **Step 7: Commit, push, open the PR, and await exact-head CI**

  Push `codex/m1-01-02-corpus-discovery`, open a PR to protected `main`, do not
  merge, and wait for `quality (3.12)` and `quality (3.13)` on the exact PR head.
  Report the PR URL, head SHA, local test count, CI run/check results, inventory
  hashes, source-integrity receipt, schema transition, and remaining decisions.
  Stop before M1-03.
