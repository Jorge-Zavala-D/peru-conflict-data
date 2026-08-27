# M1-01/M1-02 official-corpus discovery design

## Status and boundary

Jorge authorized M1-01 and M1-02 on 2026-08-27 after squash-merging pull
request #1. M1-03 remains prohibited. This design permits read-only requests for
official HTML, robots, headers, and metadata. It prohibits downloading or promoting
new PDFs, writing to Dropbox `01_raw`, parsing conflict content, OCR, gold annotation,
entity resolution, geocoding, model extraction, and canonical data materialization.

Schema `v0.2.0` is the working M1 content baseline, not the final M2 gold schema.
`schemas/v0.1.0/` remains immutable. M2-01 must review all ten benchmark reports before
resolving content-model questions recorded in `docs/29_open_questions.md`.

## Architecture

M1 discovery has a separate technical schema version from the scientific content
schema. The current `discovery/v0.2.0` contract (with `discovery/v0.1.0` retained as the
first snapshot) pairs every candidate identity value with its evidence and provenance,
preserves source-original page metadata, and distinguishes catalogue/search/thematic/landing/download/redirect URL roles,
and preserves uncertainty. It does not mutate either scientific schema directory.

The read-only reconnaissance command uses the Python standard library plus the existing
Pydantic and YAML runtime. It retrieves HTML only, follows robots, stays serial, delays
requests, caps retries and pages, records redirect and response metadata, and refuses PDF
or other binary response bodies. Working records are written only to a caller-selected
Git-ignored temporary directory outside `CONFLICT_DATA_ROOT`; they are not a public source
index or the future mutable acquisition ledger.

## Approved sources and authority

Initial authoritative hosts are exactly `defensoria.gob.pe` and
`www.defensoria.gob.pe`. Approved starting surfaces are the official reports catalogue,
the official site search and pagination, the Paz Social / Prevención de Conflictos
thematic page, individual Defensoría document records where exposed, and Defensoría-hosted
file links. Other subdomains, redirect destinations, shorteners, or mirrors are recorded
as pending review and never promoted to authoritative automatically. Internet Archive is
fallback evidence only after an official-source gap is demonstrated.

## Identity and coverage semantics

An observed source is one URL or metadata record actually encountered at a stated time.
An expected month is a research coverage-grid hypothesis beginning in April 2004; it does
not assert that Defensoría published a report for that month. A candidate report number or
reference period remains provisional until paired evidence supports it. Filenames and
embedded PDF titles may be retained as weak evidence but cannot establish identity alone.

Every identity evidence record contains the subject, source classification, observed
value, source URL, captured time, and optional source excerpt. Report number and reference
period therefore do not use parallel arrays. Landing-page, direct file, and redirect-chain
evidence are separate structured URL observations.

Multiple official URLs that appear to describe the same report are candidate source
relations during M1-02. They do not become alternate byte versions until an authorized
M1-03 acquisition computes hashes. Same-name/different-byte collision handling remains an
acquisition concern.

## Responsible retrieval contract

- Serial concurrency: one request.
- Inter-request delay: at least 2.0 seconds for the M1-02 live run.
- Retry cap: two retries after the initial attempt, limited to transient HTTP/network
  failures and honoring `Retry-After` when present.
- HTML-only body retrieval; do not request a discovered PDF body.
- Per-surface page cap and repeated-URL detection are safety stops, not completeness
  claims.
- Record robots response, response headers relevant to caching/rate limits, absence of
  explicit rate-limit headers, and the terms/license search outcome.
- Public accessibility does not imply permission to redistribute PDFs, the administrative
  workbook, or source-derived releases.

## Durable and temporary outputs

Git stores the discovery schema, code, allowlist, tests, protocol, methodological receipts,
and M1 review report. The full provisional working inventory remains under `.cache/` and
is Git-ignored. No public compact source index is created in M1-01/M1-02. The future
operational ledger belongs in Dropbox `01_raw/manifests/` only after M1-03 authorization;
the later canonical manifest is reproducibly materialized in Parquet/DuckDB.

## Acceptance and stop condition

M1-01 is accepted when the protocol, policy, schema, and tests are reproducible without a
raw write. M1-02 is accepted when official surfaces have been enumerated read-only, the
provisional coverage/gap/duplicate evidence is reported without a premature completeness
claim, the full repository quality gate passes, and source integrity is reverified. Work
then stops with a bounded M1-03 dry-run proposal; no acquisition is executed.
