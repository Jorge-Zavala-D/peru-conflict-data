# M1-03B comparison-only protocol

Status: M1-03B.1 production machinery implemented and synthetic-tested. M1-03B.2
external execution is prohibited until a later exact-byte research-owner
authorization exists.

## What each stage proves

| Stage | Proven claim | Not authorized or claimed |
|---|---|---|
| M1-03A | Pilot v2, ten protected sources, twenty logical URLs, and 45 dry-run actions validate with zero network and zero Dropbox writes | Network, operational ledger, staging, promotion |
| M1-03B.1 | Direct HTTPS transport, landing association, loader-sealed authorization, one-shot ledger/restart, deterministic temporary recovery, and compare-only orchestration work with synthetic evidence | Any Defensoría PDF/ZIP request, real ledger write, actual authorization, raw mutation |
| M1-03B.2 (future) | At most one separately authorized comparison of reports 260–269 under the exact merged runtime and storage identity | Reports 1–259, crawling, general acquisition, staging/promotion, M1-04/M2 |

Compare-only success is byte/provenance evidence for ten already protected files. It
is not corpus completeness, report-identity adjudication, permission to redistribute
source files, or a power-loss-safe raw-promotion claim.

## Required future authorization ceremony

M1-03B.1 contains an empty canonical registry, its matching SHA-256 pin, and no
`authorized` artifact. A later M1-03B.2 proposal must use a separate protected-main
review after the M1-03B.1 squash commit exists:

1. Treat that merged commit as the immutable execution commit. Generate its exact
   closed execution-tree manifest and one canonical authorization artifact binding
   that commit, the manifest, the protected-source receipt, plan/target/limit
   fingerprints, exact installed dependency `RECORD` pins, reports 260–269, the two
   approved hosts, storage/host identities, compare-only capabilities, owner/time,
   and same-run one-shot restart policy.
2. Have the research owner review the exact artifact bytes and SHA-256. In one
   separate PR, add the artifact and manifest, add the registry entry containing
   both the exact raw artifact SHA-256 and the semantic core hash over **every**
   artifact field, and update the registry pin to the new registry SHA-256. No
   executable file may change in this authorization-only PR.
3. After that PR is merged, run only from that exact clean commit. Before project or
   third-party imports, the bootstrap resolves the public `main` head directly from
   GitHub over verified, credential-free HTTPS and requires local `HEAD` to equal
   that independent value. A locally moved remote-tracking ref is not authority.
   Runtime accepts the delta from the reviewed execution commit only when every
   changed path is one of the four fixed external trust anchors: the authorization
   artifact, execution manifest, registry, or registry pin.

The command must supply both exact file hashes. The loader hashes before parsing,
checks the independently pinned registry, and returns a sealed value; a raw model or
CLI switch cannot grant authority. A later authorization ceremony must first require
that `.venv-live` is absent, then prepare it separately from execution:

```powershell
if (Test-Path -LiteralPath .venv-live) { throw '.venv-live already exists; stop for review' }
$env:UV_PROJECT_ENVIRONMENT = '.venv-live'
try {
    uv sync --frozen --no-dev --no-install-project --link-mode copy
} finally {
    Remove-Item Env:UV_PROJECT_ENVIRONMENT
}
```

This preparation may contact the configured package index and therefore is not part
of the authorized live process. It must finish and be reviewed before invocation.
Copy mode makes every pinned dependency member an unaliased file. The fixed Windows
production invocation shape is then:

```text
.venv-live\Scripts\python.exe -I -S -B scripts\acquire_official_sources.py --mode live-compare \
  --plan config/acquisition_pilots/m1_03_reports_260_269_v2.yaml \
  --require-plan-sha256 <reviewed-plan-sha256> \
  --authorization <reviewed-artifact-path> \
  --require-authorization-sha256 <reviewed-artifact-sha256>
```

This is protocol documentation, not an executable authorization. No current
registry entry permits the command to proceed.

## Closed runtime and transport

The supported live executable begins with a standard-library-only bootstrap and
requires Python `-I -S -B` from the exact `.venv-live` interpreter. It never invokes
`uv` in the authorized process. Before importing project or third-party modules it
rejects Python import-control and proxy/TLS/OpenSSL override environment variables
before importing OpenSSL-backed modules, and rejects site
customization, validates the
exact fixed-path artifact and exact-byte/full-field registry grant, resolves public
protected-main identity directly from GitHub, checks the external-anchor-only Git
delta, and compares every manifest entry with both working-tree and reviewed-commit
bytes. Git is invoked from a fixed system path with a closed environment and config.
Standard-library paths retain precedence. Before adding repository `src` and the
exact `.venv-live` site-packages root, the bootstrap requires exactly the six pinned
runtime distributions, verifies every file through authorization-pinned wheel
`RECORD` data, rejects unlisted files and competing import candidates, disables
Pydantic plugin discovery, rejects standard-library shadows and bytecode caches, and
then rechecks every required module origin. A normal direct import of the
application is not the supported production command.

The execution manifest contains the authorization loader itself and the fixed
sorted runtime list enforced independently by bootstrap and application code. It
excludes only the four external authorization artifacts described above to avoid a
circular hash. Registry and pin must match; all four must be clean tracked bytes on
protected remote main. A local clean commit, caller-selected execution commit,
locally rewritten `refs/remotes/origin/main`, `PATH` Git shim, hostile `GIT_*`
configuration, dependency change, or loader/runtime-path change fails before
Defensoría transport construction.

The production transport uses direct standard-library HTTPS with the default trusted
CA stack, hostname verification, port 443, no automatic redirects, a 30-second
timeout, identity content encoding, stable User-Agent, and no credentials/cookies.
It rejects proxy/TLS/OpenSSL override environment variables. Only the reviewed Defensoría
hosts and canonical reviewed paths are admitted. Unicode source paths are encoded to
one canonical UTF-8 wire target. Query strings, fragments, user information,
nondefault ports, unsafe escapes, duplicate critical headers, control-bearing
headers, or path-changing/off-host redirects fail before body interpretation.

## Fail-closed execution order

### Phase 1: local preflight

Before transport construction or operational writes, validate the isolated
bootstrap, exact plan and sealed authorization, protected-main execution commit/tree
and clean repository, latest source receipt in Git and the working tree,
`CONFLICT_DATA_ROOT`, absent raw staging, host/data-root identity, hard request
envelope, and all ten local paths/sizes/SHA-256 values. Every component from the
data root through `01_raw/reports/<year>` is retained by a directory handle and each
PDF is hashed through a retained handle-relative file descriptor. Reject ambient
proxy/TLS/OpenSSL overrides, reparse/junction parents, symlinks, and hardlink aliases.

### Phase 2: one-shot ledger and recovery

Acquire retained leases for the root, `01_raw`, and fixed `manifests` child; obtain a
kernel single-writer lock; require/create the exact namespace marker; hydrate and
validate the global use index and deterministic per-authorization ledger; and bind
the exact authorization artifact SHA-256, plan, run, execution tree, host, root, and
marker. Truncation, noncanonical JSONL, hash/sequence mismatch, anchor rollback,
contradictory use, terminal reuse, alias/reparse/hardlink, or concurrent writer stops.

Only then reconcile deterministic run-owned system-temporary names through retained
handles from the operating-system temp root. Owned partials are removed with durable
evidence. A complete object is reusable only when it matches one successful durable
PDF attempt, size limits, `%PDF-` magic, byte count, and SHA-256. A complete object
without durable success is fingerprinted durably before deletion, then removed and
classified, never reused. Unexpected names,
intermediate junctions, or identities stop without guessing. A cleanup failure
leaves the run active; restart must remove the owned bytes before any terminal may
be written.

Windows is the only reviewed live-comparison host in this version. Its retained
file handle supports identity-bound deletion after a durable, atomic quarantine
rename. POSIX has no reviewed primitive that conditionally unlinks the inode held by
an open descriptor; a pathname `stat` followed by `unlink` is raceable. Therefore
POSIX cleanup deliberately preserves the durably synced `.delete` quarantine and
leaves cleanup pending. The POSIX no-replace operation requires an atomic
`renameat2(RENAME_NOREPLACE)` implementation and never falls back to an interruptible
hard-link/unlink pair. A future POSIX authorization is prohibited until a separately
reviewed exact-deletion design exists. Both the standard-library bootstrap and the
application execution boundary reject POSIX `live-compare` before authorization
artifact/GitHub processing, data-root access, ledger creation, temporary storage,
transport construction, or DNS.

### Phase 3: reports 260–269 in exact order

For each report, durably reserve the attempt before transport use, then:

1. request robots evidence as required by the existing engine;
2. fetch the exact landing URL;
3. require source-visible support for the reviewed direct URL;
4. retain reports 261/263 as unresolved opaque-filename associations;
5. fetch only the exact reviewed PDF URL into the identity-bound system-temp run
   directory;
6. validate HTTP status, selected headers, MIME, identity encoding, byte ceilings,
   `%PDF-`, and streamed SHA-256;
7. mark durable success only after full engine validation;
8. rehash the corresponding protected local source before and after comparison;
9. persist byte/comparison evidence; and
10. rehash the accepted PDF through a retained delete-capable handle, atomically
    move that exact object to a deterministic restart-visible quarantine, remove it,
    and only then persist cleanup evidence. A missing, replaced, or conflicting
    object leaves cleanup pending. On POSIX, the absence of a reviewed exact-handle
    deletion primitive also leaves the quarantine and cleanup pending.

Every redirect/retry attempt is explicitly linked to its predecessor. Reaching EOF
without engine acceptance becomes a rejected attempt, not success. No code path in
the runner imports or invokes staging/publication.

### Phase 4: terminal truth

`completed` requires an exact ordered graph for all ten reports: landing
association, accepted byte object, identical comparison, cleanup, and terminal
source rehash, with no unresolved issue or unfinished attempt. On restart, every
durable attempt claim lacking an outcome receives an explicit
`crash_outcome_unknown` record with nullable observed bytes, retains its full
reservation, and creates `MISSING_EVIDENCE`. Recovery fingerprints any complete
temporary object before deleting it, then terminates `stop_for_review` before a new
transport can be constructed. It never fabricates zero transferred bytes. A
terminal authorization is spent. Ordinary cleanup-pending recovery may resume only
under the same exact artifact, plan, deterministic run, execution tree,
host/root/marker, and validated active ledger; restart never resets the 60-attempt
or 500,000,000-byte ceilings.

## Outcomes and mandatory stops

| Observation | Durable classification / terminal | Required action |
|---|---|---|
| All ten remote objects equal pinned local bytes | `completed` | Keep provenance; create no duplicate raw file; stop M1-03B.2 |
| Reviewed link absent or a qualified competing link appears | `MISSING_EVIDENCE` or `AMBIGUITY`; `stop_for_review` | Do not request/guess a replacement binary; stop |
| First remote hash differs | association-uncertain different-byte comparison plus `AMBIGUITY`; `stop_for_review` | Preserve hash/attempt evidence, remove temp, do not promote or continue |
| Protected local source changes | `POLICY_VIOLATION`; non-success | Stop; do not reinterpret baseline |
| Network, robots, header, MIME, TLS, path, budget, or storage failure | classified policy/infrastructure non-success | Stop; persist failure only if safe; never claim completion |
| Ledger corruption, rollback, reuse, or persistence uncertainty | fail closed | Do not repair/truncate automatically; owner review required |

Different bytes are only candidate alternate official bytes. They are not a new raw
version until a later, separately designed promotion-recovery workflow and explicit
owner decision exist.

## Hard envelope and rights

The immutable bounds remain 10 reports, 20 reviewed logical URLs, serial execution,
minimum two-second spacing, retry cap 2, timeout 30 seconds, five redirect hops, 60
total attempts, 1,024–50,000,000 bytes per PDF, and 500,000,000 accepted bytes. No
flag can widen them. Public web accessibility does not establish permission to
redistribute Defensoría PDFs, the administrative workbook, or source-derived
releases.
