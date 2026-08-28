# M1 discovery inventory receipt

Status: the M1-02.1 inventory is preserved below as superseded historical
evidence. The current M1-02.2 reportable evidence consists of one complete
bounded HTML-only traversal plus one final-parser targeted supplement. This is
not a corpus-completeness claim, a public source index, an acquisition ledger, or
authorization for M1-03.

## Why M1-02.1 was superseded

The independent research-owner audit found official HTML entries that the
M1-02.1 parser had missed: reports 122, 125, and 136, plus visible reference
months for reports 172 and 175. The old artifact hashes remain valid for that
observation and are not rewritten:

| Superseded M1-02.1 artifact | Bytes | Lines | SHA-256 |
|---|---:|---:|---|
| `records.jsonl` | 1,992,166 | 739 | `712136ef2010fcd93e5e113c0be7cd9ee0a8a4247ff00898fd451a261feefd3b` |
| `requests.jsonl` | 162,928 | 165 | `3a76412dd10ecd19e0c9de5e634c00fe34bcc564772dfbfa1d14d612cb982991` |
| `summary.json` | 14,036 | 213 | `b2302f441a0d53609283e8e934e966a9929c96e2cbab347d296e5787cdb6ee39` |

That run observed 244 distinct report numbers and 242 distinct months. Those
coverage statements are superseded parser outputs, not official-source gaps.

## M1-02.2 complete bounded traversal

After source-faithful RED/GREEN tests and independent read-only review, the four
ordinary surfaces and the exact reviewed report-175 landing page were traversed
once:

```powershell
uv run python scripts/discover_official_sources.py `
  --targeted-landing-id report_175_reference_period `
  --page-cap 120 `
  --max-landing-pages 24 `
  --delay-seconds 2.0 `
  --retry-cap 2 `
  --output .cache/m1-discovery-2026-08-28-m1-02-2-definitive
```

Run ID: `reconnaissance-24df69cdc9ef9156`. Start:
`2026-08-27T22:52:57.279081Z`. Completion:
`2026-08-27T22:59:08.876287Z`. Schema: discovery `v0.3.0`.

| Complete-traversal artifact | Bytes | Lines | SHA-256 |
|---|---:|---:|---|
| `records.jsonl` | 1,970,685 | 746 | `dd3d4e71245e0d7e94459f7b318fa5245cb731b05cc57ad5f98cfa9ecf52d5de` |
| `requests.jsonl` | 163,939 | 166 | `9b5aab045a81808f462655b907c59f90f9b0d86ffb45ef73271f3b80b044772f` |
| `summary.json` | 14,597 | 226 | `27aebe5abbbc62c3f644c619c84c0914dc55497f89749da45337daa74b9dead1` |

The run made 165 HTML requests and one robots request. All returned HTTP 200
from the approved HTTPS host, all permitted bodies were complete and hashed, and
there were zero retries, redirect hops, errors, PDF/ZIP requests, other binary
requests, or Dropbox writes. It visited 141 start/pagination pages. Catalogue
pagination reached its verified no-next terminal after 120 pages; the two search
surfaces reached verified no-next terminals after 10 and 9 pages; the thematic
and targeted pages used single-page contracts. The ordinary landing queue
discovered 128 URLs, fetched 24, and deliberately skipped 104 at the reviewed
cap. The explicit report-175 target was fetched once outside that queue.

This traversal produced 746 records: 237 catalogue, 231 search, 248 thematic,
and 30 landing-page records. It observed 129 distinct landing URLs and 251
distinct direct-file URLs without requesting a linked file body.

## Final-parser targeted supplement

Audit of the complete traversal exposed one further bounded source structure:
the report-117 card separates `Reporte Nº 117` from
`Reporte mensual de conflictos sociales – noviembre 2013.`. The latter is a
single, independently series-qualified visible span; it is not a publication
date and contains no conflicting number. The final parser accepts this narrow
entry-scoped pairing while continuing to reject mismatched numbers, cross-node
month/year synthesis, and unqualified numberless month text.

The complete traversal was not repeated. After another offline gate and
independent parser review, a two-page HTML-only supplement re-observed the
thematic page and pinned report-175 landing:

```powershell
uv run python scripts/discover_official_sources.py `
  --surface-id paz_social_conflict_prevention `
  --targeted-landing-id report_175_reference_period `
  --page-cap 1 `
  --max-landing-pages 0 `
  --delay-seconds 2.0 `
  --retry-cap 2 `
  --output .cache/m1-discovery-2026-08-28-m1-02-2-targeted-gap-supplement
```

Run ID: `reconnaissance-155898df773d1808`. Start:
`2026-08-27T23:04:05.058851Z`. Completion:
`2026-08-27T23:04:13.312078Z`.

| Targeted-supplement artifact | Bytes | Lines | SHA-256 |
|---|---:|---:|---|
| `records.jsonl` | 692,970 | 249 | `c05afd73f85986a281c5fad1b38ac0ab00e7ea7da0d7836644bb89515484ac6e` |
| `requests.jsonl` | 2,964 | 3 | `e5a325c59f91fc6156bc7f5f64cd7bab938f0961a3fa00ba77258464843f370a` |
| `summary.json` | 1,758 | 51 | `22e2464616c67989881fbeec0d4a1975c13b65dec1b3e1cfba346b93e6024474` |

The supplement made one robots request and two HTML requests, all HTTP 200 and
fully hashed, with zero retries, redirects, errors, PDF/ZIP requests, binary
requests, or Dropbox writes. An earlier M1-02.2 targeted diagnostic at
`.cache/m1-discovery-2026-08-28-m1-02-2-targeted-gap-verification` is
superseded because it preceded the report-117 refinement; it is not part of the
reportable evidence bundle.

## Observed source evidence

The complete traversal plus final-parser supplement directly observe these
previously unresolved pairs:

| Report | Reference month | Exact visible supporting span | Official HTML source |
|---:|---|---|---|
| 117 | `2013-11` | `Reporte mensual de conflictos sociales – noviembre 2013.` | Paz Social thematic page |
| 122 | `2014-04` | `Reporte Mensual de Conflcitos Sociales N° 122 – abril 2014` | Catalogue and thematic page |
| 125 | `2014-07` | `Reporte Mensual de Conflcitos Sociales N° 125 – julio 2014` | Catalogue and thematic page |
| 136 | `2015-06` | `Reporte mensual de conflictos N° 136 – junio 2015` | Catalogue and thematic page |
| 172 | `2018-06` | `Reporte Mensual N° 172 – junio 2018` | Catalogue and thematic page |
| 175 | `2018-09` | `Conflictos Sociales N° 175 - Septiembre 2018` | Reviewed report-175 landing page |

As an observed consequence—not an encoded expected answer—the evidence bundle
contains 247 distinct candidate report numbers from 23 through 269 and 247
distinct candidate reference months from 2006-01 through 2026-07. There are no
internal number/month holes or competing report-month mappings in those observed
ranges. This does not establish corpus completeness, byte availability, or a
monthly structure before 2006.

The official site separately exposes unnumbered 2004 and 2005 bundle/document
leads. Reports 1-22 and any month-level decomposition of those bundles remain
unobserved and are not inferred.

## Ambiguities retained

Overlapping catalogue, search, thematic, and landing records remain separate
observations. Identical URLs are not treated as identical bytes. Reports 69, 153,
and 169 each retain two direct-file URLs because the official card includes one
plausible match and one visibly mismatched filename. No byte-version relationship
is asserted without authorized retrieval and hashing.

The stale embedded PDF title `RCS N° 126` remains unusable as sole identity
evidence. The report-269 alert 58-versus-34 totals and case `1514-0726` saying
it entered as new in August 2026 inside the July 2026 report remain M2
source-discrepancy candidates. No PDF body was opened or interpreted.

## Retention and manifest boundary

All reportable JSON/JSONL artifacts remain Git-ignored in repository `.cache`;
their exact byte counts and hashes above make the observation bundle auditable
across sessions. No mutable inventory is committed. The operational acquisition
ledger remains reserved for Dropbox `01_raw/manifests/` only after write
authorization. The reviewed reports-260–269 pilot remains a small public-URL
recipe in Git with `authorization_status: not_authorized`.
