# M1-01 official-source discovery protocol

Status: M1-01 is approved and this protocol is hardened through the corrective
M1-02.2 review, 2026-08-28. It is read-only. It does not authorize M1-03
acquisition, writes to Dropbox, PDF or binary retrieval, OCR, content extraction,
or a corpus-completeness claim.

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

One source-policy configuration version 3 target is separately pinned for
reviewed gap verification: the exact official report-175 landing page. The CLI
selects it only by its reviewed identifier and exposes no arbitrary target-URL
option. It is a single-page start, excluded from the discovered landing queue,
and does not raise or consume the ordinary landing cap.

The bare host and `www` host are not interchangeable in practice: the read-only
audit found a Zimbra login at the bare-host root. The public WordPress discovery
surfaces therefore use `www.defensoria.gob.pe`; the bare host remains allowlisted
only so its behavior can be recorded rather than silently rewritten.

## Evidence and provisional records

The current technical discovery contract is `schemas/discovery/v0.3.0/`;
`schemas/discovery/v0.1.0/` and `schemas/discovery/v0.2.0/` are immutable reviewed
snapshots. Discovery versioning is separate from scientific content schema
`v0.2.0`, which remains unchanged. A `ProvisionalDiscoveryRecord` may contain
null candidate number/month values. Each non-null candidate value requires a
paired `IdentityEvidence` record for the exact subject/value, a source observation
ID, source URL, capture time, observed source value, and optional excerpt. Only
`document_visible` or `official_metadata` evidence can qualify an identity claim.
Filenames, URL slugs, direct-file paths, and embedded PDF titles are retained only
as weak or conflicting evidence and never establish identity alone.

Each record separates nullable source-original containing-page metadata from the
bounded entry/card metadata: `source_page_title_original`,
`entry_title_original`, `entry_publication_date_original`, and
`entry_description_original`. Search or thematic page metadata is never copied
across its entries. A landing page may use its own page-level publication metadata
because that page is scoped to one source entry. Dates remain unnormalized until
later evidence review.

Malformed source HTML can nest later Bootstrap cards inside an earlier card.
Candidate text, dates, and links therefore stop at nested peer card, article, or
list-item boundaries. Historical reference-period parsing preserves the exact
visible span, accepts only evidenced Spanish month forms and separators, and
rejects forward/reverse calendar dates and compact identifiers. A day-like token
is exempted from date rejection only when its exact span is a recognized report
number, which protects reports 23-31.

Identity values are parsed from exact individual visible nodes, never from text
concatenated across nodes. A local span with an explicit report number must match
the entry's established number. A numberless period span is eligible only inside
an already numbered bounded entry when that one span independently names the
complete conflict-report series. This preserves report 117's split heading and
description without admitting generic months, mismatched reports, or publication
dates. Visible links naming another report remain page-level discoveries but are
not attached as same-report relations.

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

Each configured surface declares either `numeric_or_rel_next` or `single_page`.
For paginated surfaces, follow only visible navigation evidence inside pagination
or navigation containers: scoped `rel=next`, accessible next labels/titles/classes,
or the next numeric page after the visible current page. Article-level `rel=next`
and page chrome do not qualify. Stop with a machine-readable reason: no next link,
single-page completion, repeated URL, non-authoritative next URL, page cap, or
error. `reached_local_terminal` describes traversal only. `pagination_exhausted`
requires both a verified pagination contract and a no-next terminal; neither field
claims corpus completeness. `corpus_completeness_status` remains `not_assessed`.

The reports catalogue's observed pagination container is WP-PageNavi
(`wp-pagenavi`) with a current-page span, numeric shortcuts, `rel=next`, and a
last-page link. Immediate `rel=next`/current+1 evidence takes precedence over
distant numeric or `Last` links. Official search uses a different pagination
structure and is tested separately. `NO_NEXT_LINK` is meaningful only for a
surface whose pagination contract has been verified; `REPEATED_URL` is a safety
stop, never evidence of corpus completeness.

## URL normalization

Before comparison, preserve the observed URL verbatim in the evidence record, then
normalize only transport details: HTTP(S) scheme and host lowercase, default-port
removal, fragment removal, empty-path `/`, and removal of known `utm_*` tracking
parameters. Preserve path case and meaningful query parameters such as `s=`. Resolve
relative links against the observed page. Reject credentials, malformed URLs,
non-HTTP schemes, and protocol-relative URLs without a trusted base. Never rewrite
an apex host to `www` or promote a new host through normalization.

## Responsible retrieval

M1-02 uses the standard-library client and a stable identifying user agent.
Requests are serial (`concurrency=1`) with at least 2.0 seconds between requests
and at most two retries after the initial attempt. Ordinary CLI inputs cannot
lower the delay or raise retry, page, or landing limits beyond the reviewed
configuration. `Retry-After` is honored for transient 429/5xx responses.
`robots.txt` is fetched separately as `text/plain`; ordinary page bodies accept
only `text/html` or `application/xhtml+xml`. The transport checks status,
Content-Type, and a declared oversize Content-Length before a body read. PDF, ZIP,
workbook, unfamiliar binary MIME types, binary signatures, and oversized bodies
are rejected without interpretation. Redirects to binary or unapproved hosts are
rejected and recorded.

Every actual attempt receives independent UTC request/completion timestamps and
an outcome. Safe response evidence retains status, response URL, original
Content-Type, Content-Length, ETag, Last-Modified, Retry-After, Location, recognized
rate-limit headers, and a normalized redirect target when available. A permitted
body retains exact byte count and SHA-256; partial oversize reads are marked
incomplete. Cookies, authorization headers, and credentials are never retained.

The full provisional inventory is temporary and Git-ignored under the repository's
`.cache/`; the ordinary CLI rejects output anywhere else, including Dropbox.
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
