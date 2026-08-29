# M1-03B.1 source-integrity receipt

Date: 2026-08-29 (Europe/Berlin)

Scope: read-only verification for the offline M1-03B.1 production-readiness
package. No external Defensoría PDF/ZIP request, operational-ledger write, raw
staging, raw promotion, or other `CONFLICT_DATA_ROOT` write was authorized or
performed.

## Git and pilot identity

- verified branch base: `fcd3605c4ec265ffc8420bc5c43f7c5e967af781`;
- branch: `codex/m1-03b1-live-comparison-readiness`;
- immutable pilot v2 SHA-256:
  `d5cab626ba167fc45c8b5147d04bc40f85aec3a952d7fd4dbd5543b20631b4c4`;
- pilot semantic SHA-256:
  `e4b8ca609af2290563dab312488da0017ec67f5c8e05dbdf269861262b979c5b`;
- ordered target-set SHA-256:
  `721cf0e307c122facad5fdd64228b5a9c3789cc159b8a77e3b0e1536677594e1`.

The exact M1-03B.1 execution commit does not exist until this receipt and the
implementation are committed. A future M1-03B.2 authorization must independently
pin the merged execution commit, this receipt's exact bytes, and the closed runtime
tree. This receipt does not authorize network or Dropbox writes.

## Protected inputs

| Source | Bytes | SHA-256 |
|---|---:|---|
| `00_external/defensoria_provided/Base15-26.xlsx` | 238,489 | `4fb9e973b5a063527e7e9ccce4634daa07139a14116a926eb0f76b72377b19fb` |
| report 260 | 2,721,478 | `89c066ed6d5ca1822ac23e032a6a8a639690328c4b3eb97ec638233f691f2e42` |
| report 261 | 2,775,469 | `0eb248d8748deeffaacf9f84bd95512f42a59ffe4e0eb352f48a77cca6cf87a7` |
| report 262 | 2,620,335 | `09e03dbba9d315f888f6d7fc71344bc1547e6b5cc8ffabe666d3ad5d691333bf` |
| report 263 | 2,497,688 | `7a7ff1283308a4412aa6b163138d2d77d70d1b064f6025f130f2594fbbbb77e7` |
| report 264 | 4,539,029 | `5d7e9a506d402915d994456fb9a69e371788613e583d8a215975705c7cad0ddd` |
| report 265 | 3,447,435 | `e469d73033fbd3d747f82848fe4578212ccd4bd2e2b84391b5ac5c3c38350ecf` |
| report 266 | 3,527,150 | `4e6b6292b7a4783740cc60d41a04c6b449d3123a5928f5cf291557148d30055b` |
| report 267 | 3,483,005 | `350dc9e9f8dda4062fad4cb67550260587ef37278d8e4a189749256b77a5c021` |
| report 268 | 3,794,450 | `7f88adff71db230b1a3b5789a94c134e42a85cb6ef832ad295017c105353d630` |
| report 269 | 3,710,388 | `93d8c66efeb83a9d58bc4918a2db00939dff5be8b2820407d84e05c66d783182` |

The ten report PDFs total 33,116,427 bytes. The eleven protected inputs total
33,354,916 bytes. Hashes were recomputed from the connected local Dropbox bytes
before and after the final validation window and matched the prior reviewed
receipts.

## Dropbox before/after inventory

Both read-only observations returned the same state:

| Measure | Before | After |
|---|---:|---:|
| Directories | 82 | 82 |
| Files | 111 | 111 |
| Bytes | 33,453,193 | 33,453,193 |
| `00_external` files | 1 | 1 |
| `01_raw` files | 10 | 10 |
| `01_raw/manifests` files | 0 | 0 |
| `01_raw/.staging` exists | no | no |
| Files in each of `02_extracted` through `07_releases` | 0 | 0 |
| `99_archive` files | 100 | 100 |

The extra archived zero-byte `99_archive/.Rhistory` already documented in M1
remained untouched.

## Final zero-network dry run

The reviewed M1-03A dry-run command was executed once against the protected local
files. It produced only ignored repository output at
`.cache/m1-03a/dry-run-plan.json` and reported:

- protected PDFs verified: 10;
- protected PDF bytes verified: 33,116,427;
- logical future URLs: 20;
- ordered actions: 45;
- network requests: 0;
- Dropbox writes: 0;
- output bytes: 10,733;
- output SHA-256:
  `f5230af0226b156dc5d4c6957381298a06514d28f4aed838ce1e464cefdedb40`.

The deterministic output hash is unchanged from M1-03A. The M1-03B.1
`live-compare` path was not run. The committed production authorization registry
contains zero grants, so no current artifact can authorize it.
