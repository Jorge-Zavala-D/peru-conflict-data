# M1-01/M1-02 review report

Status: M1-01/M1-02 complete for review; M1-03 is not authorized or executed.
The branch remains `codex/m1-01-02-corpus-discovery`. This report deliberately
does not claim a complete historical corpus.

## Final read-only run

Command:

```powershell
uv run python scripts/discover_official_sources.py `
  --output .cache/m1-discovery-2026-08-27-final9 `
  --page-cap 120 `
  --max-landing-pages 24
```

The run used the approved configuration: four starting HTML surfaces (catalogue,
two distinct official search queries, and thematic page), serial concurrency 1,
2.0-second delay, retry cap 2, and no PDF/binary requests.

| Measure | Observed |
|---|---:|
| HTML/robots response receipts | 148 |
| HTTP successes / failures | 148 / 0 |
| Pages visited | 123 |
| Provisional records in ignored inventory | 574 |
| Distinct candidate report numbers | 73 (188–269) |
| Distinct candidate reference months | 68 |
| Distinct landing URLs in records | 74 |
| Distinct direct-download URLs in records | 24 |
| Records retaining source-original publication dates | 286 |
| Hosts in final response receipts | `www.defensoria.gob.pe` only |
| PDF/ZIP/workbook requests | 0 |
| Dropbox writes or active derived-layer files | 0 |

The final run was captured at `2026-08-27T19:15:35.03416+02:00`. Its 148
responses were 147 `text/html` pages plus one `text/plain` robots response, all
HTTP 200, with no errors. The final temporary receipt is
`.cache/m1-discovery-2026-08-27-final9/` and is
not tracked or intended as a public source index. It contains `records.jsonl`,
`requests.jsonl`, and `summary.json`. Every surface stopped at `no_next_link`;
that means the observed traversal reached its local terminal condition, not that
the research corpus is complete.

## Historical candidate coverage

The coverage hypothesis is April 2004 onward (268 months through July 2026). The
HTML-visible candidate records provide 68 distinct months, from 2020-02 through
2026-07, with the following observed runs:

- 2020-02 through 2021-02;
- 2021-10 through 2021-11;
- 2022-03 through 2026-07.

The 200 missing grid months are unresolved, not zeros: 2004-04 through 2020-01,
2021-03 through 2021-09, and 2021-12 through 2022-02. The thematic page visibly
links an archive labelled 2004, an archive labelled 2005, and 2006 report labels,
but those links were not downloaded. This establishes official historical leads,
not observed report files.

Candidate report numbers 188–269 were visible in the audited HTML records. The
unobserved values inside that numeric range are 206–211 and 214–216. This is an
observed-number gap only; report numbering is not assumed to be a complete monthly
or historical universe. Values below 188 and any alternate numbering regimes
remain unenumerated by this bounded HTML pass.

## Surfaces and source-domain evidence

The official catalogue exposed linked pagination through `/page/120/`. Both search
queries returned overlapping but non-identical landing-page candidates. The Paz
Social thematic page states that monitoring began in 2004 and visibly exposes 2004,
2005, and 2006 leads alongside unrelated institutional material. Individual
landing pages expose visible title/publication metadata and official upload links.
The site-wide HTML title is generic and was not used as report identity evidence.

Only `www.defensoria.gob.pe` appeared in final responses. The bare host's Zimbra
root behavior and its separate robots response are recorded in the robots receipt.
No redirect destination or third-party mirror was promoted.

## Ambiguities, duplicates, and suspected alternate versions

The search surfaces intentionally produce duplicate candidate observations for the
same report/month; these are retained as separate source observations and can later
be reconciled without claiming byte identity. Examples include repeated 221–269
records across the two queries. The HTML evidence also preserves known contradictions:

- the report 252 landing slug says `enero-2025` while the visible candidate metadata
  and modern sequence support a February-2025 candidate;
- report 227 appears through landing URLs whose slugs/month labels differ;
- report 223 appears through a generic landing URL and an October-2022 candidate;
- two thematic-page URLs contain `reporte_61` (`.../2009/12/conflictos_reporte_61_marzo2009.pdf`
  and `.../2009/04/conflictos_reporte_61.pdf`). They are suspected identity/version
  candidates only; no PDF body was requested and no byte relationship is asserted.

Four article-local direct links have opaque names: two `3.pdf` URLs under the
2024/10 and 2024/12 upload paths, `10.pdf.pdf` under 2025/12, and `10.pdf` under
2026/02. They are retained as unresolved source observations, without report
identity or byte-version claims. The latter two appear on the 261 and 263 landing
pages; their landing-page context is reported separately from identity evidence.

The stale embedded PDF `/Title` value `RCS N° 126` is not used by discovery code.
The report-269 benchmark observations remain future M2 discrepancy candidates:
the alert narrative's 58 total with a 51/2/5 breakdown versus Cuadro N.° 1's 34
with a 28/2/4 breakdown, and case `1514-0726` saying `Ingresó como caso nuevo:
Agosto 2026` inside a July 2026 report.

## Schema and manifest decisions

The current discovery contract is versioned separately at `schemas/discovery/v0.2.0/`;
`schemas/discovery/v0.1.0/` is retained unchanged as the first discovery snapshot.
Scientific `schemas/v0.1.0/` and `schemas/v0.2.0/` were not modified. Identity
evidence is paired and observation-linked; URL roles and redirect chains are
structured; source inconsistencies are classified without correction. No public
Git source index was created. Git contains schema/code/rules/tests and reviewed
methodological receipts; the future mutable acquisition ledger belongs in Dropbox
`01_raw/manifests/`; canonical report manifests belong in Parquet/DuckDB.

The only discovery-schema change in this pass is the versioned addition of nullable
`page_title_original` and `publication_date_original` fields. The bounded run below was
repeated after that change so its provisional records are emitted under `v0.2.0`; no prior
schema directory was rewritten. The migration note is
`docs/schema_migrations/discovery_v0.1.0_to_v0.2.0.md`.

For the ten modern benchmark landing pages, the source-original metadata observed in
final9 is:

| Candidate | Candidate reference period | Publication date original |
|---:|---|---|
| 260 | `2025-10` | `14/11/2025` |
| 261 | `2025-11` | `12/12/2025` |
| 262 | `2025-12` | `13/01/2026` |
| 263 | `2026-01` | `13/02/2026` |
| 264 | `2026-02` | `16/03/2026` |
| 265 | `2026-03` | `29/04/2026` |
| 266 | `2026-04` | `18/05/2026` |
| 267 | `2026-05` | `26/06/2026` |
| 268 | `2026-06` | `16/07/2026` |
| 269 | `2026-07` | `13/08/2026` |

## Exact first bounded acquisition proposal (not executed)

After Jorge reviews `docs/m1_acquisition_checkpoint.md`, the first internal
acquisition proposal is capped at **10 report landing URLs plus at most 10 linked
file URLs**, one candidate each for reports 260–269. The two opaque file URLs are
kept explicitly as uncertain candidates:

| Candidate | Landing page | Direct file candidate observed in HTML |
|---|---|---|
| 260 | `https://www.defensoria.gob.pe/documentos/reporte-de-conflictos-sociales-n-o-260-octubre-2025/` | `https://www.defensoria.gob.pe/wp-content/uploads/2025/11/Reporte-Mensual-de-Conflictos-Sociales-N°-260-Oct_2025.pdf` |
| 261 | `https://www.defensoria.gob.pe/documentos/reporte-de-conflictos-sociales-n-o-261-noviembre-2025/` | `https://www.defensoria.gob.pe/wp-content/uploads/2025/12/10.pdf.pdf` (opaque; unresolved) |
| 262 | `https://www.defensoria.gob.pe/documentos/reporte-de-conflictos-sociales-n-o-262-diciembre-2025/` | `https://www.defensoria.gob.pe/wp-content/uploads/2026/01/Reporte-de-conflictos-sociales-n.º-262-–-diciembre-2025.pdf` |
| 263 | `https://www.defensoria.gob.pe/documentos/reporte-de-conflictos-sociales-n-o-263-enero-2026/` | `https://www.defensoria.gob.pe/wp-content/uploads/2026/02/10.pdf` (opaque; unresolved) |
| 264 | `https://www.defensoria.gob.pe/documentos/reporte-de-conflictos-sociales-n-o-264-febrero-2026/` | `https://www.defensoria.gob.pe/wp-content/uploads/2026/03/Reporte-de-Conflictos-Sociales-n-264-febrero-26.pdf` |
| 265 | `https://www.defensoria.gob.pe/documentos/reporte-de-conflictos-sociales-n-o-265-marzo-2026/` | `https://www.defensoria.gob.pe/wp-content/uploads/2026/04/Reporte-de-Conflictos-Sociales-n-265-VF.pdf` |
| 266 | `https://www.defensoria.gob.pe/documentos/reporte-de-conflictos-sociales-n-o-266-abril-2026/` | `https://www.defensoria.gob.pe/wp-content/uploads/2026/05/Reporte-de-Conflictos-Sociales-n-266-VF.pdf` |
| 267 | `https://www.defensoria.gob.pe/documentos/reporte-de-conflictos-sociales-n-o-267-mayo-2026/` | `https://www.defensoria.gob.pe/wp-content/uploads/2026/06/Reporte-de-Conflictos-Sociales-n-267-VF.pdf` |
| 268 | `https://www.defensoria.gob.pe/documentos/reporte-de-conflictos-sociales-n-o-268-junio-2026/` | `https://www.defensoria.gob.pe/wp-content/uploads/2026/07/Reporte-de-Conflictos-Sociales-n-268.pdf` |
| 269 | `https://www.defensoria.gob.pe/documentos/reporte-de-conflictos-sociales-n-o-269-julio-2026/` | `https://www.defensoria.gob.pe/wp-content/uploads/2026/08/Reporte-de-Conflictos-Sociales-n-269.pdf` |

The table uses official-host paths with the host expanded by the approved allowlist.
It is a proposed acquisition set, not an authorization. Reports 260–269 already
exist in the M0 raw benchmark; any future acquisition must preserve alternate bytes
and collision evidence rather than overwrite them.

## Source-integrity recheck and active-layer boundary

At `2026-08-27T17:23:00.0554282Z`, a read-only PowerShell recheck recomputed
SHA-256 over the eleven
existing source inputs. All hashes and byte sizes matched the M0.1 receipt in
`docs/source_integrity_receipt_m0_1.md`; the detailed current receipt is
`docs/source_integrity_receipt_m1_02.md`. The complete Dropbox root still contains
82 directories, 110 files, and 33,453,193 bytes. The source inputs total 33,354,916
bytes. File counts under `02_extracted`, `03_parsed`, `04_linked`, `05_database`,
`06_validation`, and `07_releases` are all zero. No file was added, removed, or
modified by M1-01/M1-02, and no write was made to `01_raw`.

## Local quality-gate receipt

The final staged tree passed the complete repository gate:

| Check | Result |
|---|---|
| `uv sync --frozen --group dev` | Passed; 26 locked packages checked |
| `uv run ruff format --check .` | Passed; 126 files formatted |
| `uv run ruff check .` | Passed |
| `uv run pyright` | Passed; 0 errors, 0 warnings, 0 information messages |
| `uv run pytest -q` | Passed; 152 tests |
| `uv run python scripts/export_schemas.py --check` | Passed |
| `uv run python scripts/check_git_data_policy.py` | Passed |
| `uv run pre-commit run --all-files` | All hooks passed |
| `git diff --cached --check` and `git diff --check` | Passed |

No dependency was added and `uv.lock` was not changed. The repository data-policy
guard found no source corpus, binary data, secret, or disallowed large file in Git.

## Stop condition

M1-01/M1-02 are now ready for Jorge's review. No M2 work, parser/OCR work, entity
resolution, geocoding, LLM extraction, raw promotion, or canonical materialization
starts from this branch. M1-03 remains blocked until the separate checkpoint is
explicitly approved.
