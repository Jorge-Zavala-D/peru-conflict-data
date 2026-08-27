# M1-02.1 definitive inventory receipt

Status: reviewed read-only reconnaissance evidence for the M1-02.1 pull request.
This is not a corpus-completeness claim, a public source index, an acquisition
ledger, or authorization for M1-03.

## Definitive run

The final reviewed parser snapshot was run from
`codex/m1-01-02-corpus-discovery` on 2026-08-27. The command was:

```powershell
uv run python scripts/discover_official_sources.py `
  --output .cache/m1-discovery-2026-08-27-m1-02-1-final-reviewed `
  --page-cap 120 `
  --max-landing-pages 24 `
  --delay-seconds 2.0 `
  --retry-cap 2
```

Run ID: `reconnaissance-aeadfcf0e96c1654`. Start:
`2026-08-27T21:18:56.748687Z`. Completion:
`2026-08-27T21:25:09.375267Z`. Schema: discovery `v0.3.0`.

The full mutable files remain Git-ignored in the repository `.cache/`. Their
durable audit identifiers are:

| Artifact | Bytes | Records | SHA-256 |
|---|---:|---:|---|
| `records.jsonl` | 1,992,166 | 739 | `712136ef2010fcd93e5e113c0be7cd9ee0a8a4247ff00898fd451a261feefd3b` |
| `requests.jsonl` | 162,928 | 165 | `3a76412dd10ecd19e0c9de5e634c00fe34bcc564772dfbfa1d14d612cb982991` |
| `summary.json` | 14,036 | 1 | `b2302f441a0d53609283e8e934e966a9929c96e2cbab347d296e5787cdb6ee39` |

These hashes identify this exact live observation. A later run may differ because
the official site is mutable; that would be a new observation, not a replacement
for this receipt.

## Request and traversal audit

- 165 actual attempts: 164 HTML requests and one exact-host robots request.
- All 165 returned HTTP 200 on `https://www.defensoria.gob.pe`.
- Successful MIME types were `text/html; charset=UTF-8` and
  `text/plain; charset=UTF-8` for robots.
- Every permitted body is complete and has a byte count and SHA-256.
- Zero retries, redirect hops, non-HTTPS URLs, off-allowlist hosts, PDF/direct-file
  requests, binary requests, unapproved successful MIME types, cookies, or
  authorization fields occurred.
- The reports catalogue traversed pages 1-120 and stopped at its verified
  no-next terminal. The two official searches traversed 10 and 9 pages and also
  stopped at verified no-next terminals. The thematic page used its declared
  single-page contract.
- Twenty-four of 129 discovered landing URLs were fetched under the approved cap;
  105 were intentionally skipped. Reaching local pagination terminals does not
  establish corpus completeness, which remains `not_assessed`.

## Observed source coverage

The run produced 739 provisional records: 234 catalogue, 231 search-result, 245
thematic, and 29 landing-page or unresolved landing-download records. It observed
244 distinct candidate report numbers from 23 through 269. Numbers 122, 125, and
136 were not observed on the traversed surfaces. It observed 242 distinct
candidate reference months from 2006-01 through 2026-07; the unobserved month
positions inside that interval are 2014-04, 2014-07, 2015-06, 2018-06, and
2018-09. These are discovery gaps, not evidence that a report did not exist.

The site independently exposes unnumbered 2004 and 2005 conflict-report entries.
They remain bundle/document leads with null candidate reference month. No report
numbers 1-22 and no monthly rows for 2004/2005 were inferred. Reports 172 and 175
are visible by number but their scoped HTML entries do not visibly state a
reference month, so those month values remain null.

The only candidate groups exposing more than one distinct direct-file URL are
reports 69, 153, and 169. In each case the official thematic card includes one
plausibly matching URL and one URL whose visible filename refers to another report.
Both links are preserved as source-page ambiguity; no byte-version relationship
is asserted because no linked body was retrieved.

## Retention boundary and superseded attempts

Earlier bounded attempts in `.cache/` exposed the live WP-PageNavi catalogue
structure, malformed nested catalogue cards, and historical month spelling. Their
findings became regression tests, but those provisional outputs are superseded and
are not the reportable inventory. Only the final reviewed artifact hashes above
are carried into durable documentation.

The operational acquisition ledger still belongs in Dropbox
`01_raw/manifests/` only after a write-capable milestone is authorized. No full
inventory is committed to Git, and no Dropbox path was used as an output target.
