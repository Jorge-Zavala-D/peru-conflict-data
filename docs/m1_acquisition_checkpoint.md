# M1-03 raw-acquisition checkpoint (not authorized)

M1-01/M1-02.1 are read-only. This document and the pilot recipe do not authorize
network retrieval of PDF bodies, writes to Dropbox, or raw promotion. M1-03 is the
first exceptional workflow that could write `01_raw` and requires Jorge's separate
explicit approval after review of this checkpoint.

## Reviewed machine-readable input

The proposed first pilot consumes only
`config/acquisition_pilots/m1_03_reports_260_269_v1.yaml`, not an ephemeral
`.cache/.../records.jsonl`. The plan contains public official URLs and the already
documented paths, byte counts, and SHA-256 values of the ten existing benchmark
PDFs. It is an immutable acquisition recipe, not the mutable operational ledger.

The plan is fixed to:

- reports 260-269, exactly 10 landing URLs and 10 direct-file candidates;
- authoritative hosts `defensoria.gob.pe` and `www.defensoria.gob.pe` only;
- association uncertainty for the opaque report-261 `10.pdf.pdf` and report-263
  `10.pdf` URLs;
- `authorization_status: not_authorized` and null expected remote hashes;
- target-set fingerprint
  `721cf0e307c122facad5fdd64228b5a9c3789cc159b8a77e3b0e1536677594e1`;
- plan-file SHA-256
  `59480d3845ba3fb2ce14f0d1fce01b93472ca1c86e189a4a67d6fa9d9599a6b7`;
- baseline receipt `docs/source_integrity_receipt_m1_02.md` at Git commit
  `85a91ebba407610931e7e37b21b0ddddc15edbd1`, whose SHA-256 is
  `cfab73b44aded55a803e8bda000fd2e67ae4b7eca904769f73e96b317e615837`.

The Pydantic model, generated JSON Schema, and tests pin these values. Changing
the YAML alone fails validation and does not widen authority.

## Proposed command and bounded dry run

The future acquisition entry point is deliberately not implemented in M1-02.1.
If M1-03 is authorized, its exact proposed dry-run command is:

```powershell
uv run python scripts/acquire_official_sources.py `
  --plan config/acquisition_pilots/m1_03_reports_260_269_v1.yaml `
  --require-plan-sha256 59480d3845ba3fb2ce14f0d1fce01b93472ca1c86e189a4a67d6fa9d9599a6b7 `
  --mode dry-run
```

`dry-run` means exactly zero network requests, zero Dropbox writes, and zero
promotions. It validates the plan/schema/digest, approved hosts, baseline source
paths/sizes/hashes, request budget, temporary/staging paths, and then prints the
ordered plan and proposed ledger mutations. A successful dry run is evidence for
review; it does not authorize the later network or promotion mode.

## Hard request envelope

The reviewed pilot cannot exceed:

| Control | Bound |
|---|---:|
| Reports | 10 |
| Logical landing/direct URLs | 20 |
| Concurrency | 1 |
| Inter-request delay | at least 2.0 seconds |
| Retries after an initial attempt | 2 per request |
| Request timeout | 30 seconds |
| Redirect hops | 5 per URL |
| Total transport attempts | 60 |
| One accepted PDF | 1,024-50,000,000 bytes |
| Total downloaded bytes | 500,000,000 bytes |

Robots requests, initial requests, redirect hops, and retries all consume the
single 60-attempt budget. The client must stop before issuing an attempt that
would exceed the budget; a retry allowance never overrides the global cap.

## Required validation and disposition

Before any network request, validate in order: authorization status; plan schema
and digest; approved hosts; and every existing raw path, size, and SHA-256 against
the pinned baseline. For each eventual response, validate in order: approved host
and redirect chain; robots permission; 2xx status; PDF Content-Type; reasonable
size; `%PDF-` magic signature; and streamed SHA-256. Never interpret a response
body before its type and bounds permit the read, and never retain credentials or
cookies in receipts.

Every completed temporary object is compared with the existing pinned raw hash
before any raw promotion:

- **Different bytes:** stop for human review. Do not overwrite, promote, rename,
  or create an alternate raw file during this first pilot.
- **Identical bytes:** record the URL/HTTP/hash observation but create no duplicate
  raw file.
- **Different official URLs, identical bytes:** preserve every URL observation and
  one byte-object identity; do not duplicate bytes.

Only a later separately reviewed disposition could move an approved new byte
version. That future path must stream-copy from the unique system temporary
directory to
`CONFLICT_DATA_ROOT/01_raw/.staging/m1-03-pilot-260-269`, rehash the staged file,
and use a same-filesystem atomic rename. No direct cross-filesystem rename is
treated as atomic.

## Retry, idempotency, and abandonment

The transport is serial, honors `Retry-After`, records every attempt with UTC
timestamps and selected safe headers, and retries only allowlisted transient
failures within both caps. The operational idempotency identity is the normalized
source URL plus observed SHA-256; byte-object deduplication is by SHA-256. Redirect
changes and HTTP metadata changes remain separate observations.

On failure or interruption, preserve the failure receipt, close the run as
abandoned, and remove only that run's partial system-temporary or staging files.
Leave all pre-existing raw files byte-for-byte untouched. There is no automated
rollback that deletes an already promoted raw object.

## Manifest and rights boundary

After write authorization, mutable discovery/acquisition status, attempts,
retrieval metadata, local paths, collisions, and alternate-version observations
belong in Dropbox `01_raw/manifests/`. Git contains the plan schema, code, rules,
tests, and this reviewed recipe. Canonical `reports_manifest` remains a later
reproducible Parquet/DuckDB output. Public accessibility does not establish public
redistribution rights for PDFs, `Base15-26.xlsx`, or source-derived releases.

M1-03 remains stopped until Jorge explicitly approves this checkpoint and a
reviewed implementation of the proposed command.
