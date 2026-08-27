# M1-01/M1-02.2 review report

Status: M1-01 and the corrected M1-02 reconnaissance are complete for pull
request review. M1-03, M1-04, and M2 remain unauthorized and unexecuted. This
report does not assert corpus completeness.

## Scope and outcome

M1-01 defines the official-source discovery protocol, authority and path policy,
pagination/stopping rules, URL normalization, robots/rate-limit receipt,
provisional discovery contract, alternate-version semantics, three-layer
manifest boundary, and redistribution-rights gate.

M1-02.1 established entry-scoped extraction, realistic historical structures,
pagination, strict per-attempt receipts, an HTML-before-body MIME gate, and
discovery schema `v0.3.0`. The owner audit then demonstrated five source-visible
misses. M1-02.2 corrected those variants, added an exact reviewed landing-page
mechanism for report 175, hardened credential boundaries, and reconciled one
additional split-identity structure found during final inventory audit.

No PDF or ZIP body, workbook, OCR output, conflict-content extraction, raw
manifest, canonical table, or acquisition artifact was requested or created.
Dropbox remained read-only.

## Reportable HTML-only evidence bundle

The exact commands, run identities, byte counts, and SHA-256 values are in
`docs/m1_02_1_inventory_receipt.md`. The bundle contains:

1. one complete bounded traversal of all four ordinary official surfaces plus
   the pinned report-175 landing page; and
2. one two-page final-parser supplement for the thematic page and report-175
   landing after report 117's split entry was documented.

The complete traversal was not repeated while debugging. Its results were:

| Measure | Observed |
|---|---:|
| Request-attempt receipts | 166 |
| HTTP 200 / non-200 | 166 / 0 |
| HTML / robots requests | 165 / 1 |
| Start/pagination pages visited | 141 |
| Provisional records | 746 |
| Catalogue / search / thematic / landing records | 237 / 231 / 248 / 30 |
| Distinct landing URLs represented | 129 |
| Ordinary landing pages fetched / skipped | 24 / 104 |
| Distinct direct-file URLs represented but not requested | 251 |
| PDF/ZIP/binary requests | 0 |
| Dropbox writes | 0 |

The final-parser supplement made three more successful attempts: one robots and
two HTML requests. Both runs stayed on approved HTTPS URLs, retained complete
body byte counts and SHA-256 values, and had zero retries, redirects, errors,
credential/cookie retention, or unapproved successful MIME types.

## Traversal status and coverage

The reports catalogue traversed 120 pages to its independently verified no-next
terminal. The two official searches traversed 10 and 9 pages to verified
terminals. The Paz Social thematic and reviewed report-175 landing surfaces used
their declared single-page contracts. The ordinary 24-page landing cap was
reached. Local traversal termination does not establish corpus completeness;
`corpus_completeness_status` remains `not_assessed`.

The reportable evidence bundle directly observes:

- every report number from 23 through 269, for 247 distinct numbered candidates;
- every month from `2006-01` through `2026-07`, for 247 distinct month
  candidates; and
- no competing report-to-month or month-to-report mapping in that observed range.

Those counts are consequences of the current official HTML observation, not
expected constants or manufactured sequence rows. Reports 1-22 remain
unobserved. The official 2004 and 2005 entries remain unnumbered bundle/document
leads, and no monthly decomposition is inferred.

## Reconciled source-visible structures

The parser preserves the exact published text and applies only narrow,
deterministic tolerance:

- `Reporte Mensual de Conflcitos Sociales N° 122 – abril 2014`;
- `Reporte Mensual de Conflcitos Sociales N° 125 – julio 2014`;
- `Reporte mensual de conflictos N° 136 – junio 2015`;
- report 172's qualified heading plus same-number local
  `Reporte Mensual N° 172 – junio 2018`;
- report 175's reviewed landing-page label
  `Conflictos Sociales N° 175 - Septiembre 2018`; and
- report 117's bounded numbered heading plus independently series-qualified
  description
  `Reporte mensual de conflictos sociales – noviembre 2013.`.

The final rule never concatenates month/year tokens across visible nodes. A
secondary span with another explicit report number is rejected. A numberless
span may supply a month only inside an already numbered entry when that one span
independently names the complete conflict-report series. Publication dates,
generic monthly reports, conflict-adjacent institutional publications,
unqualified numberless months, and unsupported singular forms remain negative.

Visible links naming another report remain page-level discovery links but are
not attached to the current record as `appears_same_report` relations.

## Targeted landing and authority boundary

`config/official_sources.yaml` is source-policy configuration version 3. It
retains only `defensoria.gob.pe` and `www.defensoria.gob.pe` as authoritative
hosts and pins one reviewed target:
`report_175_reference_period` at the exact official HTTPS landing URL.

The CLI accepts only the reviewed identifier, never an arbitrary target URL.
Explicit targets are single-page starts, do not raise or consume the ordinary
landing cap, and are removed from the discovered queue to prevent duplicate
requests. They use the same robots, serial two-second spacing, retry, redirect,
MIME, body-size, hashing, receipt, and repository-cache boundaries as ordinary
HTML discovery.

## Discovery contract and schema preservation

Discovery `v0.3.0` already supports the required records and receipts; M1-02.2
does not change that schema. Scientific schemas `v0.1.0` and `v0.2.0`, and
discovery schemas `v0.1.0`, `v0.2.0`, and `v0.3.0`, remain byte-identical.
The source-policy YAML advances independently from version 2 to 3 because its
reviewed target registry changed.

Scientific `v0.2.0` remains the approved M1 working baseline, not the final M2
gold schema. M2-01 must still review Demand nullability; source-reported
case-level dialogue/mechanism and cumulative violence; a source-level
case/problem description; longitudinal mediation identity/observation semantics;
and any additional fields evidenced across reports 260-269.

## Ambiguities and source discrepancies retained

Overlapping source observations are not collapsed, and identical URLs are not
treated as identical bytes without authorized retrieval. Reports 69, 153, and
169 retain multiple direct-file links because each official card includes a
plausibly matching URL and a mismatched visible filename. Report 252 retains a
landing-slug/title-month inconsistency. Reports 261 and 263 retain opaque
`10.pdf.pdf` and `10.pdf` associations.

The stale embedded PDF title `RCS N° 126` remains unusable as sole identity
evidence. The report-269 58-versus-34 alert totals and the case
`1514-0726` reporting August 2026 entry inside the July 2026 report remain M2
source-inconsistency candidates. M1 does not open or correct those PDF contents.

## Credential and repository security

`AGENTS.md` and `SECURITY.md` now unconditionally prohibit agents from
invoking `git credential fill` or querying credential helpers, keychains,
password managers, environment secrets, stored tokens, or equivalent stores.
They separately prohibit extracting user secrets into process variables or
constructing Authorization headers to bypass connector permissions.

Authorized normal Git operations through preconfigured authentication remain
allowed because credentials are not exposed to the agent. A connector denial may
fall back to authenticated browser UI only after explicit user confirmation;
otherwise the agent stops and asks. Independent safe current/all-ref scans found
no high-confidence secret, private-key, token, or manual-authorization material.

## Manifest, rights, and M1-03 boundary

The full mutable discovery inventory remains ignored under repository `.cache`.
Dropbox `01_raw/manifests/` remains the future mutable acquisition ledger after
write authorization; Git contains schemas, code, rules, tests, and the reviewed
small pilot recipe; canonical `reports_manifest` remains a later reproducible
Parquet/DuckDB output. No public Git source index is created.

Public accessibility is not a redistribution license. Rights to redistribute
Defensoría PDFs, `Base15-26.xlsx`, or source-derived releases remain unresolved
and separately gated.

The reports-260–269 pilot remains
`config/acquisition_pilots/m1_03_reports_260_269_v1.yaml`, exactly 10 reports
and 20 logical public URLs, concurrency 1, minimum two-second spacing, retry cap
2, bounded attempts/bytes, validation before body acceptance, hash-before-
promote, no duplicate byte objects, multiple URL observations, and
`STOP FOR REVIEW` on bytes differing from an existing raw hash. Its
`authorization_status` remains `not_authorized`. No acquisition entry point,
dry run, network request, or raw promotion was implemented or executed.

## Quality and independent review

Independent read-only reviewers repeatedly probed false positives/negatives,
entry/link pairing, the pinned target, MIME/body boundaries, schema preservation,
and credential policy. Review-found defects were captured through failing tests
before correction. No Critical or Important finding remains.

The current local suite contains 270 tests. The final commit candidate must also
pass frozen sync, Ruff format/lint, strict Pyright, scientific and discovery
schema drift, repository data policy including staged blobs, pre-commit, Git
diff checks, source-integrity verification, and both protected PR checks. The
exact final results and source hashes are recorded in the M1-02.2 integrity
receipt and PR metadata, not by rerunning live discovery.

## Stop condition

PR #2 must remain open and unmerged. Do not begin M1-03, retrieve PDF/ZIP bodies,
write `01_raw/manifests/`, alter raw files, begin M1-04, run OCR, parse conflict
content, or begin M2 until Jorge audits and explicitly authorizes the next stage.
