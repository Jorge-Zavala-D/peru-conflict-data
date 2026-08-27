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
- Never commit PDFs, workbooks, database/data files, OCR/renders, logs, credentials, cookies, or temporary download links.
- Do not install or enable paid/external services without Jorge's approval. Prefer the smallest trusted capability set.
- Start Dropbox/archive inspection read-only. A filesystem ACL is not an immutability guarantee.

## Development discipline

- Python 3.12-3.13, `uv`, Pydantic, pytest, Ruff, Pyright, and pre-commit.
- Production logic belongs in `src/peru_conflicts/`; scripts are thin entry points; notebooks are diagnostics.
- Add behavior through failing tests first. Schema changes require tests, documentation, regenerated JSON Schemas, and reviewable diffs.
- Use `uv sync --frozen --group dev`, then run `make quality` or the equivalent individual commands.
- Work on focused branches. Never autonomously merge to `main`; do not commit or push unless Jorge authorizes it.

## Current milestone gate

Milestone 0 only unless Jorge explicitly authorizes Milestone 1. During M0, inventorying reports 260-269 and workbook metadata is allowed; gold annotation, parser development, full discovery, OCR, historical taxonomy work, and entity resolution are not.
