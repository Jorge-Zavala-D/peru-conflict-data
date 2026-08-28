# M1-02.2 Source-Gap Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover five source-visible historical HTML identities with narrow deterministic parsing, add reviewed targeted landing verification, and prohibit credential-store bypass behavior before M1 discovery is merged.

**Architecture:** Keep discovery schema v0.3 unchanged. Extend only the source-recognition grammar and bounded-entry evidence selection, then expose report 175 through a configuration-pinned, identifier-selected landing surface that uses the existing HTML-only client without consuming or raising the general landing cap.

**Tech Stack:** Python 3.12-3.13, Pydantic 2, PyYAML, `html.parser`, `urllib`, pytest, Ruff, strict Pyright, pre-commit.

**Spec:** `docs/superpowers/specs/2026-08-28-m1-02-2-source-gap-reconciliation-design.md`

## Global Constraints

- Work only on `codex/m1-01-02-corpus-discovery`; update PR #2 and never merge it.
- The main agent is the sole writer for parser, fixtures, configuration, schemas, inventories, and integration.
- Subagents perform independent read-only audits/reviews only.
- Scientific `v0.1.0`/`v0.2.0` and discovery `v0.1.0`/`v0.2.0`/`v0.3.0` remain byte-identical.
- Dropbox and all PDF/ZIP bodies remain read-only and unfetched.
- M1-03, its acquisition script/dry run/network mode, M1-04, OCR, PDF parsing, and M2 remain prohibited.
- The M1-03 pilot v1 stays `authorization_status: not_authorized` and retains its current fingerprint.
- Do not encode 247 reports or 247 months as an expected result; report only observed corrected evidence.

---

### Task 1: Capture source-faithful parser regressions

**Files:**
- Create: `tests/fixtures/discovery/thematic_historical_gap_variants.html`
- Create: `tests/fixtures/discovery/landing_report_175_visible_label.html`
- Modify: `tests/unit/test_discovery_html.py`

**Interfaces:**
- Consumes: `parse_discovery_page(...)` with existing discovery v0.3 output.
- Produces: literal expected number/month/evidence assertions for 122, 125, 136, 172, and 175.

- [x] **Step 1: Add the exact source-original positive fixtures**

  Preserve `Conflcitos`, the missing `sociales`, report 172's two local spans,
  and report 175's linked visible label exactly. Put multiple independent records
  in the thematic fixture to exercise bounded scoping.

- [x] **Step 2: Add strong negative fixture cases and assertions**

  Include `Reporte mensual de actividades`, a generic institutional report,
  `conflictos ambientales`, a special prevention report, a standalone
  `Reporte Mensual N° 999 – septiembre 2018`, mismatched local report numbers,
  page-global month text, and publication dates. Assert none supplies a false
  social-conflict record or reference period.

- [x] **Step 3: Run RED against the unchanged parser**

  Run: `uv run pytest tests/unit/test_discovery_html.py -k "historical_gap or bounded_secondary or landing_visible_label" -vv`

  Expected: 122/125/136 are absent and 172/175 have null reference periods;
  negative controls remain excluded.

### Task 2: Implement the narrow recognition and local-evidence grammar

**Files:**
- Modify: `src/peru_conflicts/discovery/html.py`
- Modify: `tests/unit/test_discovery_html.py`

**Interfaces:**
- Produces: qualified entry recognition for the literal `conflcitos` spelling and numbered missing-`sociales` form.
- Produces: exact same-number local evidence selection after independent scope qualification.
- Preserves: page-global exclusion, publication-date exclusion, and existing entry boundaries.

- [x] **Step 1: Add the minimal source-recognition alternatives**

  Replace no words by fuzzy matching. Permit literal `conflcitos` only inside the
  otherwise qualified social-report phrase. Add a separate pattern requiring
  `Reporte mensual de conflictos`, an explicit `N`/ordinal marker, and digits.

- [x] **Step 2: Select bounded secondary identity evidence**

  After the primary qualified span yields report number `n`, consider local
  heading/paragraph/link nodes only when they repeat `n`, contain a valid
  month/year, and match either `Reporte Mensual N° n` or
  `Conflictos Sociales N° n`. Do not allow these abbreviated spans to create a
  scope. Use that exact node text as reference-period `source_excerpt`.

- [x] **Step 3: Run GREEN and mutation checks**

  Run: `uv run pytest tests/unit/test_discovery_html.py -vv`

  Expected: all HTML tests pass. Mutating `conflcitos`, removing the explicit
  number marker from the report-136 pattern, or changing a secondary number must
  make a corresponding positive/negative assertion fail.

### Task 3: Add reviewed targeted landing verification without widening caps

**Files:**
- Modify: `config/official_sources.yaml`
- Modify: `src/peru_conflicts/discovery/settings.py`
- Modify: `src/peru_conflicts/discovery/cli.py`
- Modify: `tests/unit/test_discovery_settings.py`
- Modify: `tests/integration/test_discovery_reconnaissance.py`

**Interfaces:**
- Produces: `ReviewedTargetedLanding` configuration and `select_targeted_landings(...)` by exact reviewed ID.
- Consumes: the existing `run_reconnaissance(...)` start-surface interface with `UrlRole.LANDING_PAGE` and `single_page` pagination.
- Preserves: `MAX_LANDING_PAGE_CAP = 24` for discovered general landing pages.

- [x] **Step 1: Write RED configuration and CLI tests**

  Assert that reviewed report-175 selection succeeds; an unknown ID, duplicate
  ID, arbitrary URL, non-HTTPS URL, off-host URL, or changed reviewed URL fails
  before client construction. Assert the selected target is added as a
  single-page landing start while general landing cap stays 24 or a safer value.

- [x] **Step 2: Verify RED**

  Run: `uv run pytest tests/unit/test_discovery_settings.py tests/integration/test_discovery_reconnaissance.py -k "targeted or reviewed_landing" -vv`

  Expected: failures because no targeted registry/selector exists.

- [x] **Step 3: Implement the exact registry and identifier-only selection**

  Advance the source-policy configuration contract to version 3 and pin
  `report_175_reference_period` to
  `https://www.defensoria.gob.pe/documentos/reporte-mensual-de-conflictos-sociales-n-175/`.
  Add repeatable `--targeted-landing-id`; expose no arbitrary-URL or authorization
  override flag. Combine it with selected normal surfaces as a landing-role,
  verified single-page start. Exclude explicit targets from the ordinary
  discovered-landing queue so a URL is fetched at most once.

- [x] **Step 4: Run focused settings/runner/CLI tests**

  Run: `uv run pytest tests/unit/test_discovery_settings.py tests/integration/test_discovery_reconnaissance.py -vv`

  Expected: all focused tests pass; PDF/body safety tests remain green.

### Task 4: Encode and verify the credential-permission boundary

**Files:**
- Modify: `AGENTS.md`
- Modify: `SECURITY.md`

**Interfaces:**
- Produces: durable instructions prohibiting credential-store inspection and manual authorization-header bypass.
- Preserves: normal Git-mediated `fetch`/`push` and explicit-confirmation browser fallback.

- [x] **Step 1: Add the least-privilege rules to both policy files**

  Prohibit `git credential fill`, OS credential helpers, keychains, password
  managers, environment secrets, stored OAuth/API tokens, extracting secrets to
  process variables, and hand-built authorization headers after integration
  denial. Allow normal preconfigured Git authentication. Require explicit user
  confirmation for browser UI fallback; otherwise stop and ask.

- [x] **Step 2: Run safe repository scans**

  Search tracked files and history for high-confidence token/private-key/header
  patterns without inspecting environment variables or credential stores. If a
  potential secret is found, report only file/ref/location and stop without
  printing its value. Do not rotate credentials.

### Task 5: Offline gate and targeted five-gap live verification

**Files:**
- Temporary only: `.cache/m1-discovery-2026-08-28-m1-02-2-targeted-gap-verification/`

**Interfaces:**
- Consumes: one thematic surface plus `report_175_reference_period`.
- Produces: ignored HTML/robots-only records, requests, and summary used to verify the five source spans.

- [x] **Step 1: Run the complete offline suite before network access**

  Run frozen sync, Ruff format/lint, strict Pyright, complete pytest, schema drift,
  repository data policy, pre-commit, and `git diff --check`. Expected: all exit
  zero and every protected schema directory remains unchanged.

- [x] **Step 2: Run one targeted HTML-only verification**

  Run:

  ```powershell
  uv run python scripts/discover_official_sources.py `
    --surface-id paz_social_conflict_prevention `
    --targeted-landing-id report_175_reference_period `
    --page-cap 1 `
    --max-landing-pages 0 `
    --delay-seconds 2.0 `
    --retry-cap 2 `
    --output .cache/m1-discovery-2026-08-28-m1-02-2-targeted-gap-verification
  ```

  Confirm only approved HTTPS thematic/landing HTML and exact-host robots text
  were requested. Confirm exact evidence for 122/2014-04, 125/2014-07,
  136/2015-06, 172/2018-06, and 175/2018-09. Preserve any unresolved result.

### Task 6: Independent review and one replacement definitive reconnaissance

**Files:**
- Temporary only: `.cache/m1-discovery-2026-08-28-m1-02-2-definitive/`
- Modify: `docs/m1_02_1_inventory_receipt.md`
- Modify: `docs/m1_01_02_review_report.md`
- Modify: any other tracked coverage summary found by `rg`.

**Interfaces:**
- Consumes: independently reviewed exact integrated parser/config/policy snapshot.
- Produces: one replacement reportable ignored inventory and durable hashes/coverage statements.

- [x] **Step 1: Obtain an independent exact-snapshot read-only review**

  Review false positives/negatives, exact evidence excerpts, targeted authority,
  unchanged schemas, and credential policy. Resolve every critical/important
  finding through a new RED/GREEN test before live regeneration.

- [x] **Step 2: Execute one replacement complete HTML-only reconnaissance**

  Use all four ordinary starting surfaces, the reviewed report-175 targeted
  landing, page cap 120, general landing cap 24, delay 2.0, and retry cap 2.
  Write only the ignored definitive directory above. Do not repeat the run to
  update prose.

- [x] **Step 3: Audit and supersede durable claims**

  Compute bytes, row counts, and SHA-256 for all three new artifacts. Retain the
  M1-02.1 hashes as historical evidence and state explicitly why owner audit
  superseded that inventory. Report observed coverage and ambiguities without a
  corpus-completeness claim or manufactured sequence.

- [x] **Step 4: Reconcile the report-117 split entry without a second broad crawl**

  Final traversal audit found a numbered heading and a separate numberless but
  fully series-qualified period span for report 117. Capture RED/GREEN and
  negative regressions, obtain independent review, and run only one targeted
  thematic/report-175 supplement. Preserve separate hashes for the complete
  traversal and supplement; do not synthesize a combined mutable ledger.

### Task 7: Final quality, source integrity, PR update, and exact-head CI

**Files:**
- Create: `docs/source_integrity_receipt_m1_02_2.md`
- Modify: `docs/execution_plan.md` only where stage status requires correction.

**Interfaces:**
- Produces: exact local/remote commit SHA, source-integrity receipt, and successful PR #2 checks.

- [ ] **Step 1: Run the full final local gate**

  Run `uv sync --frozen --group dev`, Ruff format/lint, strict Pyright, all
  pytest tests, schema drift, repository data policy including staged blobs,
  pre-commit, and Git diff checks. Rehash all eleven protected source files and
  verify zero files in `02_extracted` through `07_releases`.

- [ ] **Step 2: Verify the exact commit candidate**

  Confirm no PDFs, workbooks, JSONL inventories, secrets, cache artifacts, or
  protected-schema changes are staged. Confirm the pilot v1 digest and
  authorization state are unchanged.

- [ ] **Step 3: Commit, push, and wait on existing PR #2**

  Push the existing branch; do not create another PR and do not merge. Wait for
  `quality (3.12)` and `quality (3.13)` on the exact new head. Make no CI-receipt
  commit. Report the exact head, workflow run, local test count, new inventory
  hashes, source-integrity result, and remaining authorization decisions, then
  stop before M1-03.
