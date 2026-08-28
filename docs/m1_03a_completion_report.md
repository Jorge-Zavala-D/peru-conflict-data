# M1-03A completion report

Status: **complete for pull-request review; M1-03B remains prohibited**.

## Scope and merged baseline

PR #2 was squash-merged before this work. The verified M1 baseline is `main` commit
`9281ebb2fcfbb6626dfcbebff98347a7ff9291d2`; merge-triggered GitHub Actions run
`33154108607` passed `quality (3.12)` and `quality (3.13)`. The protected-main
ruleset remained active. M1-03A was developed from that exact commit on
`codex/m1-03-source-acquisition`.

M1-03A implemented only an acquisition engine, synthetic future-behavior tests,
and a real preflight that made zero network requests and zero Dropbox writes. It
did not retrieve a PDF/ZIP body, create a transport implementation, write an
operational ledger, stage or promote a raw object, or begin M1-04/M2.

## Versioned pilot and schema

The pre-merge pilot v1 remains unchanged, with SHA-256
`59480d3845ba3fb2ce14f0d1fce01b93472ca1c86e189a4a67d6fa9d9599a6b7`.
The separately versioned v2 plan preserves the ten reports, twenty logical URLs,
uncertainty for reports 261 and 263, safety limits, and disposition policy while
pinning the merged M1 baseline and latest receipt:

| Fingerprint | SHA-256 |
|---|---|
| v2 YAML bytes | `d5cab626ba167fc45c8b5147d04bc40f85aec3a952d7fd4dbd5543b20631b4c4` |
| v2 canonical semantics | `e4b8ca609af2290563dab312488da0017ec67f5c8e05dbdf269861262b979c5b` |
| ordered target set | `721cf0e307c122facad5fdd64228b5a9c3789cc159b8a77e3b0e1536677594e1` |
| merged M1-02.2 receipt | `963a9b317f8485c58e4b8b7f408a4c8739ea23f0260fd7c368656f99d17a4cc2` |

Pilot v2 remains `authorization_status: not_authorized`. Acquisition schemas are
new under `schemas/acquisition/v0.1.0/`; no scientific or discovery schema snapshot
was regenerated or mutated.

## Dry-run proof

The definitive preflight ran between `2026-08-28T12:25:33.0658826Z` and
`2026-08-28T12:25:33.8819932Z`. It validated the caller-supplied plan digest,
strict plan contract, merged Git/receipt baseline, data-root safety, protected-zone
write policy, and the path, size, and SHA-256 of every existing report 260-269.

| Result | Value |
|---|---:|
| Existing report files verified | 10 |
| Existing report bytes verified | 33,116,427 |
| Logical future URLs | 20 |
| Ordered actions emitted | 45 |
| Network requests | 0 |
| Dropbox writes | 0 |

The only output was ignored repository file `.cache/m1-03a/dry-run-plan.json`,
10,733 bytes, SHA-256
`f5230af0226b156dc5d4c6957381298a06514d28f4aed838ce1e464cefdedb40`.
The complete source receipt is `docs/source_integrity_receipt_m1_03a.md`.
The handle-relative writer was replayed after final hardening at
`2026-08-28T13:05:46.6943786Z`; it reproduced the identical output hash while the
complete data-root snapshot remained byte-for-byte unchanged.

Before and after the run, Dropbox contained 82 directories, 111 files, and
33,453,193 bytes. All eleven protected source inputs matched the M1-02.2 baseline.
Layers `02_extracted` through `07_releases` remained empty; `01_raw/.staging/`
remained absent; and the pre-existing `01_raw/manifests/` directory remained empty.

## Implemented safeguards

- The executable accepts only `dry-run`; there is no network, force, or authorize
  switch and the dry-run path never constructs a transport.
- The sole ignored repository-cache output is created and published through retained
  directory handles; a Windows junction-swap regression proves it cannot be
  redirected into `CONFLICT_DATA_ROOT`.
- A future transport requires a separate exact authorization artifact before its
  factory can run. The sealed grant has one shared, atomic claim state across
  object copies and rejects post-review policy mutation.
- Fake-transport tests enforce robots policy, exact approved HTTPS authority,
  redirect and retry limits, serial two-second spacing, the 60-attempt budget,
  header-first MIME/size checks, PDF magic, streamed hashing, safe receipts, and
  interrupted-download cleanup.
- Temporary and publication mutations are bound to identity-checked directory
  handles. Windows child creation, reading, deletion, and rename use native
  `RootDirectory`-relative handles with junction-swap regressions; POSIX child
  operations are descriptor-relative. Publication is no-replace, rehashed,
  idempotent, and never uses `os.replace` for a raw object.
- If interruption or another error lands after publication may have committed, a
  typed outcome carries the revalidated byte-identical destination while preserving
  cancellation semantics. Same-name/different-byte observations stop for review.
- Catchable in-process interruption recovery is tested. Hard-kill/power-loss
  recovery remains an explicit M1-03B gate requiring durable pre-publication intent
  and startup reconciliation before any raw promotion.
- Operational-ledger records are append-only and plan-bound. Redirect observations
  require a complete, unforked chain rooted at the pinned direct URL; collision runs
  may close only with `stop_for_review`. No production ledger file was created.
- The repository policy now rejects ZIP as well as the existing forbidden source,
  data, secret, and large-file classes, including staged index blobs.

## Verification and independent review

The complete local test suite passes with **412 passed and 2 platform-capability
skips**. Ruff formatting/lint, strict Pyright for both Windows and Linux,
all acquisition, scientific, and discovery schema-drift checks, repository data
policy, staged-blob policy, pre-commit, and Git diff checks pass. The frozen
dependency environment is unchanged and installs with
`uv sync --frozen --group dev`.

Independent read-only reviews tested the exact integrated authorization, dry-run,
ledger, and storage boundaries. Findings concerning cloneable grants, redirect
chain provenance, selected-header bounds, raw-path grammar, directory-swap races,
and post-publication interruption were corrected and converted into regression
tests. No Critical or Important issue remains in the reviewed areas.

## Stop and next authorization

M1-03B remains separately gated. This branch contains no live transport and no
authorization artifact. Do not retrieve official PDF/ZIP bytes, write the empty
operational manifest directory, create raw staging, promote bytes, or begin M1-04
or M2 until the research owner audits this PR and explicitly authorizes a new,
versioned network artifact and scope.
