# M1-02.1 source-integrity receipt

Verification timestamp: `2026-08-27T21:35:32.7060002Z` (UTC). This was a
read-only PowerShell verification using `Get-FileHash -Algorithm SHA256`. No
Dropbox file was created, edited, moved, or removed by the verification.

## Protected source inputs

| Relative path | Bytes | SHA-256 |
|---|---:|---|
| `00_external/defensoria_provided/Base15-26.xlsx` | 238,489 | `4fb9e973b5a063527e7e9ccce4634daa07139a14116a926eb0f76b72377b19fb` |
| `01_raw/reports/2025/Reporte-de-conflictos-sociales-n.º-261.pdf` | 2,775,469 | `0eb248d8748deeffaacf9f84bd95512f42a59ffe4e0eb352f48a77cca6cf87a7` |
| `01_raw/reports/2025/Reporte-de-conflictos-sociales-n.º-262-–-diciembre-2025.pdf` | 2,620,335 | `09e03dbba9d315f888f6d7fc71344bc1547e6b5cc8ffabe666d3ad5d691333bf` |
| `01_raw/reports/2025/Reporte-Mensual-de-Conflictos-Sociales-N°-260-Oct_2025.pdf` | 2,721,478 | `89c066ed6d5ca1822ac23e032a6a8a639690328c4b3eb97ec638233f691f2e42` |
| `01_raw/reports/2026/Reporte-de-Conflictos-Sociales-n-263.pdf` | 2,497,688 | `7a7ff1283308a4412aa6b163138d2d77d70d1b064f6025f130f2594fbbbb77e7` |
| `01_raw/reports/2026/Reporte-de-Conflictos-Sociales-n-264-febrero-26.pdf` | 4,539,029 | `5d7e9a506d402915d994456fb9a69e371788613e583d8a215975705c7cad0ddd` |
| `01_raw/reports/2026/Reporte-de-Conflictos-Sociales-n-265-VF.pdf` | 3,447,435 | `e469d73033fbd3d747f82848fe4578212ccd4bd2e2b84391b5ac5c3c38350ecf` |
| `01_raw/reports/2026/Reporte-de-Conflictos-Sociales-n-266-VF.pdf` | 3,527,150 | `4e6b6292b7a4783740cc60d41a04c6b449d3123a5928f5cf291557148d30055b` |
| `01_raw/reports/2026/Reporte-de-Conflictos-Sociales-n-267-VF.pdf` | 3,483,005 | `350dc9e9f8dda4062fad4cb67550260587ef37278d8e4a189749256b77a5c021` |
| `01_raw/reports/2026/Reporte-de-Conflictos-Sociales-n-268.pdf` | 3,794,450 | `7f88adff71db230b1a3b5789a94c134e42a85cb6ef832ad295017c105353d630` |
| `01_raw/reports/2026/Reporte-de-Conflictos-Sociales-n-269.pdf` | 3,710,388 | `93d8c66efeb83a9d58bc4918a2db00939dff5be8b2820407d84e05c66d783182` |

All 11 hashes and sizes match the M0.1/M1-02 baseline. Their combined size is
33,354,916 bytes. No source or raw byte changed.

## Connected-root state

The connected Dropbox root contains 82 directories, 111 files, and 33,453,193
bytes. The six active derived layers remain empty:

| Layer | Files |
|---|---:|
| `02_extracted` | 0 |
| `03_parsed` | 0 |
| `04_linked` | 0 |
| `05_database` | 0 |
| `06_validation` | 0 |
| `07_releases` | 0 |

The prior baseline contained 110 files: 11 source/raw inputs plus 99 archived
initialization files. The current extra file is
`99_archive/.Rhistory`, a zero-byte file with creation and modification timestamp
`2026-08-27T18:14:17Z` and empty-file SHA-256
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
It changes only the archive file count; total bytes are unchanged. It is outside
the source/raw and active derived layers, was not removed or modified, and is
reported as an external protected-tree delta rather than silently ignored.

No file exists under the active layers, no M1 operational manifest was written,
and the definitive reconnaissance artifacts exist only in the repository's
ignored `.cache/` directory.
