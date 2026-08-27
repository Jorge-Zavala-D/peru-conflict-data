# M1-03 raw-acquisition checkpoint (not yet authorized)

M1-01 and M1-02 may be authorized independently, but no discovery or acquisition is
authorized by this document. M1-03 is the first exceptional workflow allowed to write to
Dropbox `01_raw` and requires Jorge's explicit approval after review of the design below.

## Proposed command and scope

Use a versioned, resumable acquisition command that consumes a reviewed source-discovery
record and writes only the specific official URL/report-version records approved for the
bounded run. A dry-run must print planned requests, destination paths, existing-byte
comparisons, rate-limit schedule, and expected manifest mutations without network writes or
filesystem promotion.

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
