# M1-03 source-acquisition checkpoint

Status: **M1-03A is merged; M1-03B.1 comparison-readiness is implemented offline;
M1-03B.2 external execution is not authorized.**

M1-01/M1-02.2 and M1-03A are merged. M1-03B.1 adds a direct verified HTTPS
transport, closed execution identity, loader-sealed authorization, compare-only
runner, and durable one-shot ledger. Those paths are tested only with synthetic
transports and temporary roots. They do not authorize retrieval of a PDF/ZIP body,
a Dropbox write, real operational-ledger creation, staging, or raw promotion. The
first live byte comparison requires a separate owner-reviewed authorization
artifact created only after M1-03B.1 is audited and merged.

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

The `dry-run` behavior and arguments remain unchanged. It has no `network`,
`force`, or `authorize` escape hatch and does not instantiate a transport. Before emitting
anything, it validates the plan, merged baseline, receipt bytes at the pinned Git
commit and in the worktree, approved hosts and exact counts, all ten protected
paths/sizes/hashes, data-root safety, symbolic temporary/staging definitions, and
routine raw-write protection. Output is allowed only beneath ignored repository
`.cache`; its parent creation, temporary write, cleanup, and publication are bound
to retained repository directory handles so a junction swap cannot redirect the
write into `CONFLICT_DATA_ROOT`. It contains relative paths and public URLs, not
credentials or absolute Dropbox paths. The executable also recognizes the fixed
future mode `live-compare`, but it requires exact plan and authorization hashes and
the empty reviewed registry rejects every artifact before execution, transport,
temporary storage, or Dropbox mutation.

The reviewed run on 2026-08-28, repeated unchanged during the final M1-03B.1
validation on 2026-08-29, emitted 45 ordered actions and reported:

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

M1-03B.1 supplies a production direct-HTTPS transport but does not execute it.
Injected fake transports, synthetic HTML, and synthetic PDF bytes test the exact
landing-page and direct-file paths. Landing
bodies accept only bounded HTML/XHTML; file bodies require header-first status and
`application/pdf` checks, identity encoding, byte ceilings, `%PDF-` magic, and
streamed SHA-256. One sealed grant uses a shared atomic claim state across shallow
copies and dataclass replacement, and its immutable per-run budgets cannot be widened
or reset. Transport, body, close, and cleanup interruptions retain linked receipts.
Receipt metadata uses an exact rate-limit-header allowlist and stores only a
credential-stripped redirect location plus the original value's hash. Every selected
header value is single-line and bounded; unsafe values become SHA-256-bearing
redaction markers. Query-bearing acquisition URLs fail closed. Durable attempt
success is committed only after the acquisition engine consumes and validates the
full body; reaching EOF alone is not success. Selected response headers and explicit
redirect/retry continuations remain linked in the append-only ledger.

Every future completed temporary object must be compared with the pinned existing
source hash before storage action:

- **Different bytes:** `STOP_FOR_REVIEW`; preserve the successful attempt link and
  create no staging or promotion.
- **Identical bytes:** preserve the URL observation linked to its successful attempt;
  create no duplicate raw file.
- **Different URLs, identical bytes:** preserve every URL observation and one byte
  object.
- **Rerun of the same URL/hash:** idempotent; no duplicate observation.

Legacy promotion primitives remain tested only in pytest temporary directories and
are not imported or called by the compare-only runner. System-temp,
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

## M1-03B.1 authorization and manifest boundary

Acquisition `v0.2.0` defines the shape of a future authorization artifact, but
M1-03B.1 creates no authorized instance. The registry grant pins both the exact raw
artifact SHA-256 and its full semantic core. Those values, plan fingerprints, the
latest M1-03B.1 source receipt, execution commit, closed runtime tree, six exact
runtime-dependency `RECORD` pins, host, data-root identity, storage marker, and
compare-only capabilities must all agree. The loader returns a sealed
reviewed-authorization value; a raw valid-looking model cannot call the production
composition. Absence or mismatch fails before transport construction. No CLI option
can change pilot v2's `not_authorized` status or add capabilities.

The future mutable operational ledger belongs in Dropbox `01_raw/manifests/` only
after explicit authorization. M1-03B.1 implements its fixed-path writer and tests it
only in synthetic roots. A retained directory lease, kernel single-writer lock,
canonical hash-chained JSONL, global authorization-use index, per-record high-water
anchors, and deterministic one-shot ledger reject truncation, rollback, concurrent
writers, contradictory restarts, and reused terminal authorization. The claim binds
the exact authorization artifact SHA-256, run, plan, storage marker, host, and data
root. No durable record contains a credential, cookie, signed query, private absolute
path, or temporary path. Git contains only code, schemas, tests, and reviewed plans;
canonical `reports_manifest` remains M1-04 work. Public accessibility does not
establish redistribution rights.

The future supported live command must use the exact dedicated interpreter:
`.venv-live\Scripts\python.exe -I -S -B` on the reviewed Windows host. `uv run` is
not a supported production invocation. POSIX remains offline-test-only because
this version preserves identity-bound delete quarantine as cleanup pending instead
of using a raceable pathname unlink. Bootstrap and application preflight reject a
POSIX live request before authorization/GitHub, data-root, ledger, temporary, or
transport effects. In a separate
reviewed preparation step, an absent `.venv-live` must be created from the frozen
lock with `uv sync --frozen --no-dev --no-install-project --link-mode copy`; it must
not be silently reused or replaced. A standard-library-only bootstrap rejects
Python import-control and proxy/TLS/OpenSSL override environment variables before
OpenSSL-backed imports, and rejects site customization before project imports, then
checks exact artifact/registry
bytes, resolves protected `main` directly from the public GitHub API over
credential-free verified HTTPS, and validates every reviewed runtime file against
both the execution-tree manifest and its Git blob at the artifact's execution
commit. It invokes Git only from a fixed system path with a closed configuration
environment. Before site-packages is added after the standard library, the bootstrap
requires exactly the pinned runtime distribution set, verifies every
authorization-pinned dependency `RECORD` member, rejects unlisted files, competing
import candidates, standard-library shadows, or unverified bytecode, and disables
Pydantic plugins. The authorization loader is inside the closed runtime tree.

To avoid circular hashes, only four fixed future authorization artifacts are
outside the execution tree: the authorization JSON, execution-tree manifest,
registry JSON, and registry SHA-256 pin. The full registry core includes the
execution commit. Runtime requires a clean checkout whose `HEAD` equals the
credential-free public GitHub protected-`main` result; a locally rewritten
remote-tracking ref is not authority. The delta from the reviewed execution commit
may contain only those four paths. Thus changing the loader, any executable input,
or an untrusted local commit cannot silently authorize network use.

## Stop condition

Do not begin M1-03B.2, create a real authorized artifact, retrieve PDF/ZIP bodies,
write anything in the pre-existing empty `01_raw/manifests/` directory, create raw
staging, promote bytes, or begin M1-04/M2 until the research owner audits and merges
M1-03B.1 and then explicitly authorizes exact M1-03B.2 artifact bytes and scope.
