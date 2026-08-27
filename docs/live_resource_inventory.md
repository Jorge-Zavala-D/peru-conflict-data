# Live resource inventory

Inventory date: 2026-08-27 (Europe/Berlin)

Scope: Milestone 0 read-only inspection of the live GitHub repository and the configured Dropbox data root. This is not a corpus manifest and does not authorize Milestone 1 discovery or acquisition.

## GitHub and local checkout

| Item | Verified state |
|---|---|
| Repository | `Jorge-Zavala-D/peru-conflict-data` |
| Visibility | Public |
| Default branch | `main` |
| Remote | `https://github.com/Jorge-Zavala-D/peru-conflict-data.git` |
| Live/default-branch commit at inspection | `14b913f390056a74b598de08742be1120515dda6` |
| Default-branch contents before M0 | `README.md`, `LICENSE` |
| Current local branch | `codex/milestone-0-foundation` |
| Connected GitHub scope | Authenticated; connector reported pull, push, and administration permission for the current account |
| Mutations during inventory | None to GitHub; no commit, push, pull request, merge, issue, or release |

The existing `LICENSE` is the MIT license and is retained byte-for-byte. Its pre- and post-foundation SHA-256 baseline is:

```text
7838bc30d3402b894dc236cc3cc9a62933f3dd6ec71ff21f02f1044f38b5edff
```

The dedicated branch exists locally. It has not been published or merged.

## Dropbox root

Resolved local root:

```text
%USERPROFILE%\Dropbox (Personal)\Research & Consulting\1 Research\Defensoria Social Conflicts Database
```

The authenticated Dropbox connector resolved the same personal Dropbox and returned the complete top-level listing (`has_more: false`). The local mount and connector agreed on the nine top-level directories. A recursive local inventory found 82 directories, 110 files, and 33,453,193 bytes. The only substantive source inputs currently present are the official workbook and reports 260-269; downstream processing directories are empty apart from the archived initialization package.

### Complete directory hierarchy at inspection

```text
00_external/
  defensoria_provided/
01_raw/
  manifests/
  reports/
    2004/ ... 2024/
    2025/
    2026/
02_extracted/
  layout/
  ocr/
  page_images/
  tables/
  text/
03_parsed/
  cases/
  demands/
  dialogue/
  protests/
  reports/
  violence/
04_linked/
  case_month/
  entity_resolution/
  geography/
05_database/
  duckdb/
  parquet/
06_validation/
  benchmark_results/
  discrepancies/
  logs/
  manual_review/
07_releases/
  v0.1/
99_archive/
  peru-conflict-data_codex-initialization/
    repo_seed/
      .agents/skills/{corpus-manifest,entity-resolution,extract-report,
        manual-adjudication,pdf-forensics,release-dataset,
        source-discrepancy,validate-report}/
      .codex/agents/
      .github/workflows/
      config/
      docs/adr/
      fixtures/
      notebooks/
      schemas/
      scripts/
      src/peru_conflicts/
      tests/
```

The `2004`-`2024` year directories exist but are empty. Their existence is a storage convention, not evidence that reports were discovered or that years correspond to parser regimes.

### Mount and permission behavior

- Dropbox directories are Windows reparse points with archive attributes, consistent with Dropbox-managed cloud synchronization.
- The current Windows account has filesystem write permission. That is not an immutability guarantee.
- Milestone 0 performed only reads against `00_external`, `01_raw`, and `99_archive`.
- Routine project code therefore enforces a second boundary: those zones are classified read-only, and only `02_extracted` through `07_releases` are exposed as writable derived locations.
- Online-only placeholders may require hydration before a local reader can open them. Presence in a directory listing alone is not proof that bytes are locally available.

## Administrative workbook

| Field | Value |
|---|---|
| Relative path | `00_external/defensoria_provided/Base15-26.xlsx` |
| Role | Complementary official administrative evidence; not the canonical case universe |
| Size | 238,489 bytes |
| SHA-256 | `4fb9e973b5a063527e7e9ccce4634daa07139a14116a926eb0f76b72377b19fb` |
| Workbook sheets | 1 |
| Sheet name | `Base 2015-2026` |
| Used range | `A1:Q3258` |
| Dimensions | 3,258 rows by 17 columns, including the header row |
| Non-empty cells | 37,368 |

The sheet/range metadata was independently read through the bundled spreadsheet runtime. No cell was changed and no converted copy was written into Dropbox or Git.

## Reports 260-269 source-integrity snapshot

Reference months below are **provisional**: they were read from the filename and first-page report title, not promoted to a canonical manifest. Native-text character counts are diagnostics, not extraction-quality scores.

| Report | Provisional month | Relative path | Bytes | Pages | Native-text chars | SHA-256 |
|---:|---|---|---:|---:|---:|---|
| 260 | 2025-10 | `01_raw/reports/2025/Reporte-Mensual-de-Conflictos-Sociales-N°-260-Oct_2025.pdf` | 2,721,478 | 121 | 439,865 | `89c066ed6d5ca1822ac23e032a6a8a639690328c4b3eb97ec638233f691f2e42` |
| 261 | 2025-11 | `01_raw/reports/2025/Reporte-de-conflictos-sociales-n.º-261.pdf` | 2,775,469 | 132 | 454,915 | `0eb248d8748deeffaacf9f84bd95512f42a59ffe4e0eb352f48a77cca6cf87a7` |
| 262 | 2025-12 | `01_raw/reports/2025/Reporte-de-conflictos-sociales-n.º-262-–-diciembre-2025.pdf` | 2,620,335 | 120 | 385,338 | `09e03dbba9d315f888f6d7fc71344bc1547e6b5cc8ffabe666d3ad5d691333bf` |
| 263 | 2026-01 | `01_raw/reports/2026/Reporte-de-Conflictos-Sociales-n-263.pdf` | 2,497,688 | 109 | 369,105 | `7a7ff1283308a4412aa6b163138d2d77d70d1b064f6025f130f2594fbbbb77e7` |
| 264 | 2026-02 | `01_raw/reports/2026/Reporte-de-Conflictos-Sociales-n-264-febrero-26.pdf` | 4,539,029 | 104 | 349,687 | `5d7e9a506d402915d994456fb9a69e371788613e583d8a215975705c7cad0ddd` |
| 265 | 2026-03 | `01_raw/reports/2026/Reporte-de-Conflictos-Sociales-n-265-VF.pdf` | 3,447,435 | 99 | 318,182 | `e469d73033fbd3d747f82848fe4578212ccd4bd2e2b84391b5ac5c3c38350ecf` |
| 266 | 2026-04 | `01_raw/reports/2026/Reporte-de-Conflictos-Sociales-n-266-VF.pdf` | 3,527,150 | 102 | 340,201 | `4e6b6292b7a4783740cc60d41a04c6b449d3123a5928f5cf291557148d30055b` |
| 267 | 2026-05 | `01_raw/reports/2026/Reporte-de-Conflictos-Sociales-n-267-VF.pdf` | 3,483,005 | 102 | 336,342 | `350dc9e9f8dda4062fad4cb67550260587ef37278d8e4a189749256b77a5c021` |
| 268 | 2026-06 | `01_raw/reports/2026/Reporte-de-Conflictos-Sociales-n-268.pdf` | 3,794,450 | 122 | 425,285 | `7f88adff71db230b1a3b5789a94c134e42a85cb6ef832ad295017c105353d630` |
| 269 | 2026-07 | `01_raw/reports/2026/Reporte-de-Conflictos-Sociales-n-269.pdf` | 3,710,388 | 117 | 389,606 | `93d8c66efeb83a9d58bc4918a2db00939dff5be8b2820407d84e05c66d783182` |

All ten PDFs exposed native text on every page in this coarse diagnostic. No alternate byte versions of these report numbers were present in the inspected root. Each PDF nevertheless carried the same stale/conflicting embedded `/Title` metadata, `RCS N° 126`; report identity must therefore come from verified page evidence and manifest records, never document metadata alone.

## Differences from the bootstrap snapshot

- Live `main` contained only `README.md` and `LICENSE`; the full proposed scaffold existed only under `99_archive/.../repo_seed`.
- The live Dropbox hierarchy and the archived storage design agree at the top level, but only reports 260-269 and `Base15-26.xlsx` are populated source inputs.
- The archive seed did not include an implementation, a real lockfile, or evidence-backed live hashes/page counts.
- The seed's 16 JSON Schema files were permissive stubs. The working M0 branch replaces them with generated schemas backed by strict models.
- The seed's example Codex configuration and custom-agent files required updates to current syntax before use.

## Inventory limitations

This snapshot proves presence and byte identity only for the eleven inspected source files. It does not establish corpus completeness, official URL provenance, historical report availability, redistribution rights, parser accuracy, or benchmark truth. Those questions belong to later authorized milestones.
