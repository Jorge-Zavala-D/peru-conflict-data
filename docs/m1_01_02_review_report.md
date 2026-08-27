# M1-01/M1-02.1 review report

Status: M1-01 is approved. The M1-02.1 historical-discovery hardening pass is
complete for pull-request review. M1-03, M1-04, and M2 remain unauthorized and
unexecuted. This report does not claim a complete corpus.

## Scope and result

The corrective pass replaced page-global extraction with bounded source-entry
extraction, added the actual Defensoría historical heading/card and pagination
structures, hardened the CLI and HTTP body boundary, versioned the discovery
contract forward to `v0.3.0`, and created a non-executable reports 260-269 pilot
recipe. Scientific schemas `v0.1.0` and `v0.2.0` and discovery schemas `v0.1.0`
and `v0.2.0` remain immutable.

No PDF body, ZIP, workbook, OCR output, conflict-content extraction, raw manifest,
or canonical data artifact was requested or created. Dropbox was read-only.

## Definitive HTML-only reconnaissance

The exact command and three-file checksums are preserved in
`docs/m1_02_1_inventory_receipt.md`. The run used all four configured official
surfaces, page cap 120, landing cap 24, concurrency 1, delay 2.0 seconds, retry cap
2, and discovery schema `v0.3.0`.

| Measure | Observed |
|---|---:|
| HTML/robots request-attempt receipts | 165 |
| HTTP 200 / non-200 | 165 / 0 |
| Pages visited | 140 |
| Provisional records | 739 |
| Distinct candidate report numbers | 244 (23-269) |
| Distinct candidate reference months | 242 (2006-01 to 2026-07) |
| Distinct landing URLs observed | 129 |
| Landing pages fetched / deliberately skipped | 24 / 105 |
| Distinct direct-file URLs observed but not requested | 248 |
| Records retaining source-original publication dates | 734 |
| PDF/binary requests | 0 |
| Dropbox writes | 0 |

All 165 requests remained HTTPS on `www.defensoria.gob.pe`. They comprise 164
complete `text/html` bodies and one complete `text/plain` robots body. Every body
has a byte count and SHA-256. There were no redirects, retries, off-allowlist
hosts, unapproved successful MIME types, credentials, or cookie evidence.

## Traversal status is not corpus completeness

The reports catalogue traversed all 120 visible pages and stopped at its verified
WP-PageNavi no-next terminal. The official `Reporte conflictos` and `Reporte
Mensual de Conflictos Sociales` searches traversed 10 and 9 pages respectively
and stopped at their verified no-next terminals. The Paz Social thematic surface
used its declared single-page contract.

These are local traversal results only. The 24-page landing cap was reached, the
official site can change, and HTML discovery cannot establish byte availability.
`corpus_completeness_status` therefore remains `not_assessed`.

## Historical source evidence and coverage hypotheses

The corrected parser visibly observes report 23 as January 2006 and the numbered
series through report 269. It does not infer reports 1-22. Within 23-269, report
numbers 122, 125, and 136 were not observed on any traversed source surface.
Neighboring entries are visible, so these remain explicit source-discovery gaps,
not proof of nonpublication.

The 242 distinct source-visible reference months span 2006-01 through 2026-07.
Five month positions inside that interval lack a source-visible month candidate:
2014-04, 2014-07, 2015-06, 2018-06, and 2018-09. The first three correspond to
the same portions of the observed numbering sequence as missing reports 122, 125,
and 136, but no missing record is manufactured from that sequence. Reports 172
and 175 are visible by number while their scoped HTML entries state no reference
month; their month remains null.

The official catalogue, thematic page, and searches independently expose
`Reporte Mensual de Conflictos Sociales 2004` and `Reporte Conflictos Sociales
2005`. Those are unnumbered document/bundle leads. The April 2004 research lower
bound remains a coverage hypothesis: no monthly rows for 2004/2005 and no
unobserved grid month were fabricated or classified as an absent report.

## Entry scoping and live structural findings

The live catalogue uses `wp-pagenavi`, not the initially assumed generic
`pagination` class. It also contains malformed nested Bootstrap cards. The parser
now treats nested peer cards/articles/list items as separate source-entry
boundaries so an unrelated `Reporte Igualdad y No Violencia` card cannot inherit
an adjacent conflict report's title, date, or links. Search dates remain scoped to
their own result items, and thematic `h3`-`h6` structures preserve their own
Spanish title, description, date, and downloads.

Historical reference-period recognition retains the exact visible span. It
supports the evidenced `Jun-2013` and `Abril -2021` forms while rejecting compact
identifiers and forward/reverse publication dates. Small report numbers such as
`N° 23 Enero 2006` are not mistaken for calendar-day prefixes.

## Duplicates, source ambiguities, and suspected versions

Overlapping catalogue, search, thematic, and landing observations are retained as
separate evidence. Identical URLs are not treated as identical bytes until an
authorized hash receipt exists.

Three official thematic entries visibly contain multiple direct-file links:

- report 69 / 2009-11 links both `reporte-69.pdf` and a filename referring to
  `conflictos_reporte_61_marzo2009.pdf`;
- report 153 / 2016-11 links both its report-153 file and a report-155 filename;
- report 169 / 2018-03 links both its report-169 file and a report-156 filename.

The records preserve both URLs and classify them for later review; they do not
repair the source page or assert alternate bytes. Report 252 also has a landing
slug containing `enero-2025` while its visible title/file metadata says February
2025. Reports 261 and 263 expose opaque `10.pdf.pdf` and `10.pdf` links. Their
future pilot associations are explicitly unresolved.

The stale embedded PDF title `RCS N° 126` is never used as identity evidence. The
report-269 alert 58-versus-34 totals and case `1514-0726` saying it entered as new
in August 2026 inside the July 2026 report remain M2 source-discrepancy candidates;
M1 neither opens the PDF bodies nor corrects them.

## Discovery schema and receipts

Discovery `v0.3.0` replaces ambiguous page-wide metadata with separate nullable
`source_page_title_original`, `entry_title_original`,
`entry_publication_date_original`, and `entry_description_original` fields. It
also defines strict per-attempt HTTP receipts, traversal/run summaries, and the
reviewed non-executable pilot plan. Every candidate identity value remains paired
with its own evidence classification and provenance observation.

Prior discovery schemas are unchanged and pinned by tree digests. Migration from
`v0.2.0` requires re-parsing the exact HTML; old page-global dates cannot be copied
mechanically. Scientific `v0.2.0` remains the approved M1 working baseline, not
the final M2 gold schema. The five M2-01 ontology questions in
`docs/29_open_questions.md` remain unresolved.

## Exact proposed M1-03 pilot set (not executed)

The machine-readable source is
`config/acquisition_pilots/m1_03_reports_260_269_v1.yaml`. It is fixed to
`authorization_status: not_authorized`, 10 reports, 20 logical URLs, and the ten
already documented local hashes. The exact proposed URL pairs are:

| Report | Candidate month | Landing page | Direct-file candidate |
|---:|---|---|---|
| 260 | `2025-10` | `https://www.defensoria.gob.pe/documentos/reporte-de-conflictos-sociales-n-o-260-octubre-2025/` | `https://www.defensoria.gob.pe/wp-content/uploads/2025/11/Reporte-Mensual-de-Conflictos-Sociales-N°-260-Oct_2025.pdf` |
| 261 | `2025-11` | `https://www.defensoria.gob.pe/documentos/reporte-de-conflictos-sociales-n-o-261-noviembre-2025/` | `https://www.defensoria.gob.pe/wp-content/uploads/2025/12/10.pdf.pdf` (opaque; unresolved) |
| 262 | `2025-12` | `https://www.defensoria.gob.pe/documentos/reporte-de-conflictos-sociales-n-o-262-diciembre-2025/` | `https://www.defensoria.gob.pe/wp-content/uploads/2026/01/Reporte-de-conflictos-sociales-n.º-262-–-diciembre-2025.pdf` |
| 263 | `2026-01` | `https://www.defensoria.gob.pe/documentos/reporte-de-conflictos-sociales-n-o-263-enero-2026/` | `https://www.defensoria.gob.pe/wp-content/uploads/2026/02/10.pdf` (opaque; unresolved) |
| 264 | `2026-02` | `https://www.defensoria.gob.pe/documentos/reporte-de-conflictos-sociales-n-o-264-febrero-2026/` | `https://www.defensoria.gob.pe/wp-content/uploads/2026/03/Reporte-de-Conflictos-Sociales-n-264-febrero-26.pdf` |
| 265 | `2026-03` | `https://www.defensoria.gob.pe/documentos/reporte-de-conflictos-sociales-n-o-265-marzo-2026/` | `https://www.defensoria.gob.pe/wp-content/uploads/2026/04/Reporte-de-Conflictos-Sociales-n-265-VF.pdf` |
| 266 | `2026-04` | `https://www.defensoria.gob.pe/documentos/reporte-de-conflictos-sociales-n-o-266-abril-2026/` | `https://www.defensoria.gob.pe/wp-content/uploads/2026/05/Reporte-de-Conflictos-Sociales-n-266-VF.pdf` |
| 267 | `2026-05` | `https://www.defensoria.gob.pe/documentos/reporte-de-conflictos-sociales-n-o-267-mayo-2026/` | `https://www.defensoria.gob.pe/wp-content/uploads/2026/06/Reporte-de-Conflictos-Sociales-n-267-VF.pdf` |
| 268 | `2026-06` | `https://www.defensoria.gob.pe/documentos/reporte-de-conflictos-sociales-n-o-268-junio-2026/` | `https://www.defensoria.gob.pe/wp-content/uploads/2026/07/Reporte-de-Conflictos-Sociales-n-268.pdf` |
| 269 | `2026-07` | `https://www.defensoria.gob.pe/documentos/reporte-de-conflictos-sociales-n-o-269-julio-2026/` | `https://www.defensoria.gob.pe/wp-content/uploads/2026/08/Reporte-de-Conflictos-Sociales-n-269.pdf` |

The proposed dry run performs zero network requests and zero Dropbox writes. A
future authorized network mode must validate approved host, robots, status,
Content-Type, reasonable size, `%PDF-` magic, and SHA-256. Bytes differing from
the existing expected hash cause `STOP FOR REVIEW` before promotion; identical
bytes create no duplicate file; multiple URLs for identical bytes retain all URL
observations around one byte object. The complete still-unexecuted design is in
`docs/m1_acquisition_checkpoint.md`.

## Source integrity and Dropbox boundary

At `2026-08-27T21:35:32.7060002Z`, all 11 protected source hashes and byte sizes
matched the M0.1/M1-02 baseline. Their combined size remains 33,354,916 bytes.
Layers `02_extracted` through `07_releases` each contain zero files, and no
operational raw manifest was written.

The connected root now contains 82 directories, 111 files, and 33,453,193 bytes.
The sole count difference from the 110-file baseline is a zero-byte
`99_archive/.Rhistory` timestamped `2026-08-27T18:14:17Z`; it is outside raw and
derived layers and was left untouched. Full details are in
`docs/source_integrity_receipt_m1_02_1.md`.

## Quality and review gate

The integrated implementation was independently reviewed after the final parser
changes. The reviewers found no remaining Critical or Important issues. The exact
commit candidate passes frozen dependency sync, Ruff format/lint, strict Pyright,
the complete test suite, schema drift, repository data policy, pre-commit, and Git
diff checks. Git contains no full JSONL inventory, PDF, workbook, credential, or
Dropbox corpus object.

| Local check | Result |
|---|---|
| `uv sync --frozen --group dev` | Passed; 26 locked packages checked |
| `uv run ruff format --check .` | Passed; 138 files already formatted |
| `uv run ruff check .` | Passed |
| `uv run pyright` | Passed; 0 errors, 0 warnings |
| `uv run pytest -q` | Passed; 251 tests |
| `uv run python scripts/export_schemas.py --check` | Passed |
| `uv run python scripts/check_git_data_policy.py` | Passed |
| `uv run pre-commit run --all-files` | All hooks passed |
| `git diff --check` | Passed |

## Stop condition

This branch is ready for protected-main pull-request review. Do not merge it in
this task. Do not implement or run M1-03, write `01_raw/manifests/`, retrieve a
PDF body, begin M1-04, or begin M2 until Jorge explicitly approves the next
checkpoint.
