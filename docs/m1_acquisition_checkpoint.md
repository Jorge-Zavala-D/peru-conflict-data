# M1-03 source-acquisition checkpoint

Status: **M1-03A implementation and zero-network dry run complete for review;
M1-03B network execution not authorized.**

M1-01/M1-02.2 are merged. M1-03A defines and tests the acquisition subsystem but
does not authorize retrieval of a PDF/ZIP body, a Dropbox write, operational-ledger
creation, staging, or raw promotion. The first live byte comparison requires a
separate research-owner-reviewed authorization artifact after this branch is merged.

## Versioned reviewed inputs

Pilot v1 remains the byte-identical pre-M1-merge artifact at
`config/acquisition_pilots/m1_03_reports_260_269_v1.yaml`, SHA-256
`59480d3845ba3fb2ce14f0d1fce01b93472ca1c86e189a4a67d6fa9d9599a6b7`.
It remains `authorization_status: not_authorized` and is not silently repointed.

Pilot v2 is the M1-03A recipe at
`config/acquisition_pilots/m1_03_reports_260_269_v2.yaml`. It preserves the same
ten targets, twenty logical official URLs, uncertainty for reports 261 and 263,
request limits, and disposition semantics while pinning:

- squash-merged M1 `main` commit
  `9281ebb2fcfbb6626dfcbebff98347a7ff9291d2`;
- `docs/source_integrity_receipt_m1_02_2.md`, SHA-256
  `963a9b317f8485c58e4b8b7f408a4c8739ea23f0260fd7c368656f99d17a4cc2`;
- raw plan SHA-256
  `d5cab626ba167fc45c8b5147d04bc40f85aec3a952d7fd4dbd5543b20631b4c4`;
- canonical semantic SHA-256
  `e4b8ca609af2290563dab312488da0017ec67f5c8e05dbdf269861262b979c5b`;
- ordered target-set SHA-256
  `721cf0e307c122facad5fdd64228b5a9c3789cc159b8a77e3b0e1536677594e1`.

Pilot v2 also remains `authorization_status: not_authorized`. A caller must supply
its exact raw SHA-256; a mismatch fails before YAML parsing. Pydantic and generated
acquisition `v0.1.0` schemas pin the reviewed contract.

## M1-03A dry-run command

```powershell
$env:CONFLICT_DATA_ROOT = 'X:\path\to\Defensoria Social Conflicts Database'
uv run python scripts/acquire_official_sources.py `
  --plan config/acquisition_pilots/m1_03_reports_260_269_v2.yaml `
  --require-plan-sha256 d5cab626ba167fc45c8b5147d04bc40f85aec3a952d7fd4dbd5543b20631b4c4 `
  --mode dry-run `
  --output .cache/m1-03a/dry-run-plan.json
```

The CLI accepts only `dry-run`. It has no `network`, `force`, or `authorize`
escape hatch and does not import or instantiate a transport. Before emitting
anything, it validates the plan, merged baseline, receipt bytes at the pinned Git
commit and in the worktree, approved hosts and exact counts, all ten protected
paths/sizes/hashes, data-root safety, symbolic temporary/staging definitions, and
routine raw-write protection. Output is allowed only beneath ignored repository
`.cache`; its parent creation, temporary write, cleanup, and publication are bound
to retained repository directory handles so a junction swap cannot redirect the
write into `CONFLICT_DATA_ROOT`. It contains relative paths and public URLs, not
credentials or absolute Dropbox paths.

The reviewed run on 2026-08-28 emitted 45 ordered actions and reported:

| Field | Result |
|---|---:|
| Existing PDFs verified | 10 |
| Existing PDF bytes verified | 33,116,427 |
| Logical future URLs | 20 |
| Network requests | 0 |
| Dropbox writes | 0 |

The ignored output was 10,733 bytes with SHA-256
`f5230af0226b156dc5d4c6957381298a06514d28f4aed838ce1e464cefdedb40`.
Before and after the run, Dropbox remained 82 directories, 111 files, and
33,453,193 bytes; all eleven protected source hashes matched the M1-02.2 receipt,
and `02_extracted` through `07_releases` remained empty.

## Hard future request envelope

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
| Total accepted bytes | 500,000,000 bytes |

Robots requests, initial requests, redirects, and retries share the global attempt
budget. Exhaustion stops before transport use. Only exact approved HTTPS hosts and
default ports are accepted; redirect destinations are revalidated and each origin
requires robots permission. `Retry-After` may lengthen but never shorten the
two-second spacing.

## Future response and disposition contract

M1-03A contains no live HTTP transport. Injected fake transports, synthetic HTML,
and synthetic PDF bytes test the exact landing-page and direct-file paths. Landing
bodies accept only bounded HTML/XHTML; file bodies require header-first status and
`application/pdf` checks, identity encoding, byte ceilings, `%PDF-` magic, and
streamed SHA-256. One sealed grant uses a shared atomic claim state across shallow
copies and dataclass replacement, and its immutable per-run budgets cannot be widened
or reset. Transport, body, close, and cleanup interruptions retain linked receipts.
Receipt metadata uses an exact rate-limit-header allowlist and stores only a
credential-stripped redirect location plus the original value's hash. Every selected
header value is single-line and bounded; unsafe values become SHA-256-bearing
redaction markers. Query-bearing acquisition URLs fail closed.

Every future completed temporary object must be compared with the pinned existing
source hash before storage action:

- **Different bytes:** `STOP_FOR_REVIEW`; preserve the successful attempt link and
  create no staging or promotion.
- **Identical bytes:** preserve the URL observation linked to its successful attempt;
  create no duplicate raw file.
- **Different URLs, identical bytes:** preserve every URL observation and one byte
  object.
- **Rerun of the same URL/hash:** idempotent; no duplicate observation.

Promotion primitives are tested only in pytest temporary directories. System-temp,
run, raw, staging, and destination paths must pass logical and resolved containment
checks with symlink/reparse aliases rejected. Identity-checked directory handles stay
open across streaming, copying, cleanup, and publication. Windows child creation,
reading, deletion, and rename are resolved through native `RootDirectory`-relative
handle operations, so a junction swap cannot redirect a child syscall; POSIX child
operations use directory descriptors. A post-operation parent-identity loss rolls
back the just-created destination through its bound handle. The primitive copies to
a unique same-filesystem stage, independently rehashes it, and publishes with an
atomic no-replace operation. Existing or race-created names are accepted only after
a stable regular-file identity check; symlink/reparse and hardlink aliases are
rejected. Existing names are never overwritten. If a catchable interruption or
another in-process error occurs after publication may have committed, only the owned
stage is removed and a typed exception carries the verified, stable, unaliased,
byte-identical committed result; user cancellation is not silently swallowed. On
pre-commit failure, only the run-owned partial/stage is removed; receipts and all
pre-existing objects remain.

These guarantees do not yet claim power-loss or hard-process-kill recovery between
filesystem publication and durable ledger recording. Before any M1-03B raw
promotion, the reviewed design must add durable pre-publication intent plus startup
reconciliation, and test that recovery path without weakening no-overwrite or
source-version preservation.

## Authorization and manifest boundary

The model defines the shape of a future authorization artifact, but M1-03A creates
no instance. Absence or mismatch of that separate artifact fails before a transport
factory is invoked. No CLI option can change pilot v2's `not_authorized` status.

The future mutable operational ledger belongs in Dropbox `01_raw/manifests/` only
after explicit authorization. M1-03A provides strictly revalidated typed records,
attempt/failure referential integrity, source-attempt links for byte comparisons,
exact reviewed-plan binding for expected hashes and paths, and run-specific collision
evidence that permits only a `stop_for_review` terminal. Redirect-destination
observations require one complete, unforked same-run chain back to the pinned direct
URL. It provides a deterministic
serializer but no production ledger writer or path. Git contains code, schemas,
tests, and reviewed plans. Canonical `reports_manifest` remains M1-04 work. Public
accessibility does not establish redistribution rights.

## Stop condition

Do not begin M1-03B, retrieve PDF/ZIP bodies, write anything in the pre-existing
empty `01_raw/manifests/` directory, create raw staging, promote bytes, or begin
M1-04/M2 until the research owner audits and explicitly authorizes the next artifact
and scope.
