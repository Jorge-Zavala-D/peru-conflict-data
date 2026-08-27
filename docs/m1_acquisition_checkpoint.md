# M1-03 raw-acquisition checkpoint (not yet authorized)

M1-01 and M1-02 are read-only work governed by the discovery protocol. No acquisition or
raw write is authorized by this document. M1-03 is the first exceptional workflow allowed to write to
Dropbox `01_raw` and requires Jorge's explicit approval after review of the design below.

## Proposed command and scope

Use a versioned, resumable acquisition command that consumes a reviewed source-discovery
record and writes only the specific official URL/report-version records approved for the
bounded run. A dry-run must print planned requests, destination paths, existing-byte
comparisons, rate-limit schedule, and expected manifest mutations without network writes or
filesystem promotion.

The following is the exact proposed bounded command shape. It is **not implemented or
executed in M1-01/M1-02**, and the placeholder script must not be created or invoked until
this checkpoint is approved:

```powershell
uv run python scripts/acquire_official_sources.py `
  --discovery-record .cache/m1-discovery-2026-08-27-final9/records.jsonl `
  --report-range 260:269 `
  --max-reports 10 `
  --max-urls 20 `
  --concurrency 1 `
  --delay-seconds 2.0 `
  --retry-cap 2 `
  --timeout-seconds 30 `
  --temp-dir <temporary-directory-outside-CONFLICT_DATA_ROOT> `
  --manifest-root <CONFLICT_DATA_ROOT>\01_raw\manifests `
  --dry-run
```

The bounded proposal is ten report landing URLs (260–269) and at most ten linked
file URLs, including the two opaque candidates (`10.pdf` and `10.pdf.pdf`) as
uncertain URLs rather than silently resolving them. It permits at most 20 URL
requests, one request at a time, a minimum two-second inter-request delay, and two
retries after the initial attempt. A real run would first perform a dry run and show
the exact URL list, redirect/host decisions, destination paths, existing-byte
comparisons, and planned ledger mutations. A dry run must promote zero files.

## Required safety behavior

1. Download to a uniquely named temporary file outside the final report path.
2. Stream bytes while recording HTTP status, headers, redirect chain, URL, attempt number,
   timestamps, and tool/version metadata.
3. Hash the completed temporary bytes before promotion.
4. Atomically promote the file only after hash and content-type/size checks pass; never
   overwrite an existing byte version.
5. If the same report filename already exists with different bytes, retain both under
   distinct source-version identities and record collision evidence in the operational
   ledger. Same bytes may be idempotently acknowledged without a second copy.
6. Use bounded retries with exponential backoff, an explicit request timeout, a declared
   user agent, and a host rate limit. Retry decisions and failures are receipt records.
7. Resume safely after interruption by verifying temporary-file and final-file hashes;
   never treat a partial file as an acquired source.

## Idempotency, rollback, and abandonment

The idempotency key is the normalized source URL plus the observed byte hash when
available. A repeated request yielding the same hash is acknowledged against the
existing receipt and does not create a duplicate. A same-name/different-byte result
gets a new source-version identity and collision record; it is never overwritten or
silently substituted. Redirect changes, HTTP metadata changes, and retry outcomes
remain separate receipt fields.

The temporary directory is created outside `CONFLICT_DATA_ROOT` and removed only
after a successful promotion or an explicitly abandoned dry run. On failure or
interruption, rollback removes temporary partial files and leaves every pre-existing
raw byte and manifest record untouched. There is no rollback operation that deletes
an already-promoted source; an operator instead abandons the run and reviews its
append-only receipts before retrying.

## Operational ledger boundary

All mutable discovery, request, retry, local-path, collision, alternate-byte, and
acquisition-status records belong in Dropbox `01_raw/manifests/`. Git contains the schema,
code, official-domain allowlist, tests, and methodology only. A later reviewed manifest
index may be small and immutable; it is not the operational ledger.

## Bounded dry-run acceptance

Before any raw write, the checkpoint review must show the exact command, source allowlist,
maximum URL/report count, concurrency (default one request at a time), delay, retry cap,
temporary directory, expected hashes if known, and rollback/abandon behavior. The dry run
must complete with zero promoted files and a receipt suitable for review. A successful dry
run does not itself authorize promotion.
