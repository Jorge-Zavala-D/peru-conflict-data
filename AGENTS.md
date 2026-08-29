# Project instructions

## Mission

Build a reproducible, auditable, versioned historical reconstruction of the Defensoría del Pueblo Social Conflicts Monitoring System in Peru, April 2004-present.

## Non-negotiable research contract

1. Official Defensoría PDFs are the authoritative published primary source. `Base15-26.xlsx` is complementary administrative evidence, not the canonical universe.
2. Raw files are immutable and hashed. Preserve alternate official byte versions; never silently replace them.
3. Preserve source contradictions. Classify `SOURCE_INCONSISTENCY` separately from `PARSER_ERROR`; never repair published values in place.
4. Missing or unreported is null, never zero. Preserve original Spanish strings/classifications beside normalized derivatives.
5. Separate stock status from transitions and conflict cases from protest events. Link distinct entities only with evidence.
6. Model violence at event level; unknown casualty totals and components remain null.
7. Identity priority is official code, deterministic multi-field linkage, probabilistic candidate, then manual adjudication. Model continuation, rename, merge, split, reactivation, and related cases explicitly.
8. Scientifically material fields retain report/hash/page/section provenance plus bbox/span where feasible, source evidence, and extractor/parser/schema/model/prompt versions as applicable.
9. Manual corrections are append-only, versioned adjudication records. Never edit canonical Parquet or DuckDB directly.
10. Deterministic/native/layout/table extraction precedes segmented, structured, cached, benchmarked model use. Unsupported fields may be null.
11. Canonical tables are Parquet and DuckDB. CSV, XLSX, Stata, and R files are exports.
12. Do not scale beyond a parser regime until its benchmark gates pass or Jorge explicitly approves a documented revision.

## Storage and security

- Git stores the reproducible recipe. `CONFLICT_DATA_ROOT` stores external/raw/derived data.
- Routine code treats `00_external`, `01_raw`, and `99_archive` as non-writable.
- The mutable acquisition ledger belongs in Dropbox `01_raw/manifests/`; Git stores its schema, code, rules, and reviewed small indexes only.
- Never commit PDFs, workbooks, database/data files, OCR/renders, logs, credentials, cookies, or temporary download links.
- Do not install or enable paid/external services without Jorge's approval. Prefer the smallest trusted capability set.
- Start Dropbox/archive inspection read-only. A filesystem ACL is not an immutability guarantee.

### Credential and integration boundary

- Agents must never invoke `git credential fill` or otherwise query or inspect OS
  credential helpers, keychains, password managers, environment secrets, stored
  OAuth/API tokens, or similar credential stores. Agents must never extract a user
  secret into a process variable or manually
  construct an Authorization header to bypass the selected integration's permissions.
- Normal `git push` and `git fetch` through preconfigured Git authentication are
  allowed when the repository action itself is authorized because Git handles the
  credential without exposing it to the agent.
- If an app or connector cannot perform an explicitly authorized GitHub action,
  use the authenticated browser UI only after explicit user confirmation when that
  route is available; otherwise stop and ask the user. Respect least privilege and
  the permission boundary of the selected integration.

## Development discipline

- Python 3.12-3.13, `uv`, Pydantic, pytest, Ruff, Pyright, and pre-commit.
- Production logic belongs in `src/peru_conflicts/`; scripts are thin entry points; notebooks are diagnostics.
- Add behavior through failing tests first. Schema changes require tests, documentation, regenerated JSON Schemas, and reviewable diffs.
- Use `uv sync --frozen --group dev`, then run `make quality` or the equivalent individual commands.
- Work on focused branches. Never autonomously merge to `main`; do not commit or push unless Jorge authorizes it.

## Current milestone gate

M1-01/M1-02.2 and M1-03A are merged. M1-03B.1 is authorized only on
`codex/m1-03b1-live-comparison-readiness`: production transport, byte-pinned
authorization, compare-only orchestration, and operational-ledger behavior may be
implemented and tested solely with synthetic/local temporary evidence. The
production authorization registry must remain empty. `dry-run` remains
zero-network/zero-Dropbox; `live-compare` must fail before side effects because no
reviewed M1-03B.2 authorization exists. Any future supported live invocation must
use the dedicated `.venv-live` interpreter via `.venv-live\Scripts\python.exe -I
-S -B scripts\acquire_official_sources.py` on Windows; `uv run` and direct application imports are
not reviewed production invocations. The dedicated environment must be created in
a separate reviewed preparation step from the frozen lock with copy-mode installs,
no development group, and no project install. That bootstrap must obtain
protected-`main` identity from
credential-free verified public GitHub evidence, not a locally writable remote ref,
and verify the authorization-pinned dependency `RECORD` files before adding
site-packages after the standard library. External Defensoría PDF/ZIP requests,
real `01_raw/manifests/` writes, raw staging/promotion, M1-03B.2, M1-04, and M2 are
prohibited pending separate owner approval. Schema `v0.2.0` remains the M1-only
working content baseline, not the final M2 gold schema; scientific `v0.1.0` and all
prior discovery/acquisition snapshots remain immutable. M2-01 owns the five
deferred ontology questions in `docs/29_open_questions.md`.

The M1-03B.1 live-comparison cleanup claim is Windows-only. POSIX offline tests are
supported, but POSIX live authorization is prohibited: exact retained-handle unlink
is unavailable, so the implementation preserves a durably synced delete quarantine
and leaves cleanup pending rather than using a raceable pathname unlink.
