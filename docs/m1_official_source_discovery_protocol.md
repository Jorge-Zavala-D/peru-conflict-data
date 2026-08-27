# M1-01 official-source discovery protocol

Status: approved working protocol for M1-01/M1-02, 2026-08-27. This protocol is
read-only. It does not authorize M1-03 acquisition, writes to Dropbox, PDF or
binary retrieval, OCR, content extraction, or a completeness claim.

## Authority boundary

The initial authoritative host allowlist is exactly:

- `defensoria.gob.pe`
- `www.defensoria.gob.pe`

The starting surfaces are the official [reports catalogue](https://www.defensoria.gob.pe/categorias_de_documentos/reportes/),
the official [search query for Reporte conflictos](https://www.defensoria.gob.pe/?s=Reporte+conflictos),
the distinct [search query for Reporte Mensual de Conflictos Sociales](https://www.defensoria.gob.pe/?s=Reporte+Mensual+de+Conflictos+Sociales),
and the [Paz Social / Prevención de Conflictos thematic page](https://www.defensoria.gob.pe/areas_tematicas/paz-social-y-prevencion-de-conflictos/).
Individual `/documentos/` landing pages and Defensoría-hosted file links are
discovered from those surfaces. A different subdomain, redirect destination,
shortener, mirror, or third-party host is recorded as pending review and is not
automatically authoritative. Internet Archive is fallback evidence only after an
official-source gap is demonstrated.

The bare host and `www` host are not interchangeable in practice: the read-only
audit found a Zimbra login at the bare-host root. The public WordPress discovery
surfaces therefore use `www.defensoria.gob.pe`; the bare host remains allowlisted
only so its behavior can be recorded rather than silently rewritten.

## Evidence and provisional records

The technical discovery contract is `schemas/discovery/v0.2.0/`; `schemas/discovery/v0.1.0/`
is retained as the first discovery snapshot. It is separate from scientific content schema
`v0.2.0`. A `ProvisionalDiscoveryRecord` may contain
null candidate number/month values. Each non-null candidate value requires a
paired `IdentityEvidence` record for the exact subject/value, a source observation
ID, source URL, capture time, observed source value, and optional excerpt. Only
`document_visible` or `official_metadata` evidence can qualify an identity claim.
Filenames, URL slugs, direct-file paths, and embedded PDF titles are retained only
as weak or conflicting evidence and never establish identity alone.

Each record also retains nullable source-original page title and publication-date text when
the page exposes them. This prevents landing-page metadata from being lost while keeping
publication dates unnormalized until a later evidence review.

URL roles are separate structured observations: `catalogue_page`,
`search_result_page`, `thematic_page`, `landing_page`, and `direct_download`.
Redirect hops are structured edges; a chain must be contiguous and terminate at
the observed URL. Candidate source relations may say that URLs appear to concern
the same report, but cannot assert byte identity or an alternate byte version
until an authorized M1-03 hash receipt exists. Source contradictions are retained
as `SOURCE_INCONSISTENCY` discovery issues; no parser correction is made.

## Coverage and pagination

The research coverage grid begins at April 2004. An **expected month** is a
research-scope hypothesis (`YYYY-MM`) used to ask whether an official source has
been observed; it is not an assertion that a report was published. An **expected
report** is a provisional hypothesis pairing a report number and/or reference
month from the approved project coverage specification, never a row manufactured
from a filename, sequence, or missing month. An **observed source** is a concrete
HTML observation with URL, visible metadata, capture time, and paired evidence.
Only observed source evidence can populate a provisional candidate report or
month. Missing or unobserved months/reports remain unknown or unresolved; they are
never coded as zero or silently treated as absent.

For each surface, traverse only visible, normalized next links. Stop with an
explicit reason: no next link (terminal traversal), repeated URL, non-authoritative
next URL, page cap, or error. A page cap or error is incomplete. The reports
catalogue was observed through the site's linked `/page/120/`; this is a navigation
receipt, not proof that report numbering or historical coverage is complete.
Search and thematic pagination is recorded independently for each query/surface.

## URL normalization

Before comparison, preserve the observed URL verbatim in the evidence record, then
normalize only transport details: HTTP(S) scheme and host lowercase, default-port
removal, fragment removal, empty-path `/`, and removal of known `utm_*` tracking
parameters. Preserve path case and meaningful query parameters such as `s=`. Resolve
relative links against the observed page. Reject credentials, malformed URLs,
non-HTTP schemes, and protocol-relative URLs without a trusted base. Never rewrite
an apex host to `www` or promote a new host through normalization.

## Responsible retrieval

M1-02 uses the standard-library client and a stable identifying user agent. Requests
are serial (`concurrency=1`) with at least 2.0 seconds between requests and at
most two retries after the initial attempt. `Retry-After` is honored for transient
429/5xx responses. `robots.txt` is fetched separately as `text/plain`; ordinary
page bodies accept only `text/html` or `application/xhtml+xml`. PDF, ZIP, workbook,
and other binary URLs or response content types are rejected before body
interpretation. Redirects to binary or unapproved hosts are rejected and recorded.

The full provisional inventory is temporary and Git-ignored under `.cache/`.
Dropbox `01_raw/manifests/` is the future mutable operational acquisition ledger;
Git stores the protocol, schema, code, allowlist, tests, and reviewed aggregate
receipts. No public Git source index is created in M1. The future canonical
`reports_manifest` is reproducibly materialized in Parquet/DuckDB.

Public accessibility does not establish redistribution rights. Internal research
acquisition into private Dropbox may be proposed at M1-03; public redistribution of
Defensoría PDFs, `Base15-26.xlsx`, and source-derived releases remains separately
gated.

## M2 handoff

M1 does not resolve the five owner-deferred M2-01 questions in `docs/29_open_questions.md`:
whether `Demand.text_original` is nullable for structured demand rows; source-reported
case-level dialogue/mechanism and cumulative-violence fields; a source-level
case/problem description distinct from monthly facts; longitudinal mediation-process
identity/observation semantics; and any additional fields evidenced across reports
260-269.
