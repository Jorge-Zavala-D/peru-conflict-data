# M1-03A Source Acquisition Design

Status: owner-approved implementation contract, 2026-08-28.

## Objective

Implement and verify the acquisition subsystem without retrieving a PDF or ZIP
body and without writing anywhere in `CONFLICT_DATA_ROOT`. M1-03A exposes only a
zero-network, zero-Dropbox dry run. The first live comparison remains M1-03B and
requires a separate reviewed authorization artifact.

## Baseline and immutable inputs

- M1 squash-merged `main`: `9281ebb2fcfbb6626dfcbebff98347a7ff9291d2`.
- Latest source receipt: `docs/source_integrity_receipt_m1_02_2.md`.
- Receipt SHA-256:
  `963a9b317f8485c58e4b8b7f408a4c8739ea23f0260fd7c368656f99d17a4cc2`.
- Pilot v1 remains byte-identical at
  `config/acquisition_pilots/m1_03_reports_260_269_v1.yaml`.
- Scientific schemas v0.1.0/v0.2.0 and discovery schemas
  v0.1.0/v0.2.0/v0.3.0 remain immutable.

## Contract separation

M1-03A introduces `peru_conflicts.acquisition` and
`schemas/acquisition/v0.1.0`. It does not relax the v1-only discovery pilot
model or regenerate discovery v0.3. The new acquisition contract contains:

- the merged-baseline v2 pilot plan;
- the deterministic dry-run result;
- acquisition attempt and ledger records;
- the shape of a future separately reviewed network-authorization artifact.

No authorization artifact is created in M1-03A. No CLI flag can synthesize or
override one.

## Pilot v2

Pilot v2 preserves the reviewed reports 260-269, their twenty logical public
URLs, uncertainty for reports 261 and 263, request limits, and disposition
semantics. It changes only the version identity and baseline pointers:

- plan ID `m1-03-reports-260-269-v2`;
- acquisition schema `0.1.0`;
- merged M1 baseline SHA;
- latest M1-02.2 receipt path and digest.

The raw YAML SHA-256, canonical semantic SHA-256, and ordered target-set
SHA-256 are distinct fingerprints. The caller must supply the exact raw YAML
digest; mismatch fails before YAML parsing.

## Dry-run architecture

The dry-run entry point accepts only:

```text
--plan PATH --require-plan-sha256 HEX --mode dry-run [--output .cache/...json]
```

There is no `network`, `force`, or `authorize` mode. The dry-run path does not
import, construct, or call a transport. It validates, in fail-closed order:

1. caller-supplied plan digest and reviewed plan digest;
2. plan schema/version, `not_authorized` status, hosts, counts, limits, and
   symbolic temporary/staging locations;
3. the pinned M1 commit exists and is an ancestor of the current branch;
4. the receipt bytes at the pinned commit and in the worktree match the plan;
5. `CONFLICT_DATA_ROOT` resolves safely and exposes all nine zones;
6. every protected benchmark path remains logically and physically inside
   `01_raw/reports`;
7. each protected file's stable byte count and SHA-256 match the plan;
8. routine writes to `01_raw` remain rejected.

Only after every check succeeds may canonical JSON be printed or atomically
written beneath the repository's ignored `.cache` directory. Output never
contains an absolute Dropbox path, cookies, authorization data, or raw headers.
It reports `network_requests: 0` and `dropbox_writes: 0` and lists the exact
ordered actions a future authorized pilot would attempt.

## Future network core

M1-03A defines transport-neutral logic tested only with fake transports and
synthetic PDF bytes. It has no real HTTP transport implementation and no CLI
route to the engine.

The future core enforces:

- exact authoritative HTTPS hosts and default port only;
- robots checks per origin before a source request;
- serial attempts spaced by at least two seconds;
- at most two retries and five redirect hops;
- a global 60-attempt budget that dominates per-request allowances;
- exact reviewed landing and direct-file URL scope, with query-bearing URLs rejected;
- bounded HTML/XHTML landing validation and PDF status/header validation before body
  iteration;
- `application/pdf` with optional parameters, identity content encoding,
  size bounds, exact `%PDF-` prefix, streamed byte count and SHA-256;
- a single-use sealed grant with one shared atomic claim state across object copies
  and immutable run-scoped request and byte budgets;
- logical/resolved system-temp confinement plus directory-handle-bound creation,
  streaming, cleanup, and finalization; Windows leases deny directory deletion or
  replacement, while POSIX child operations use directory descriptors;
- cleanup of only run-owned partial files after failure or interruption;
- structured attempt/failure receipts that survive cleanup and sanitize redirect
  evidence without retaining credentials or query tokens; unsafe selected header
  values become bounded SHA-256-bearing redaction markers.

An absent or mismatched future authorization artifact fails before the
transport factory is invoked.

## Disposition, versioning, and promotion

Downloaded bytes are compared to the pinned existing source hash before any
storage action:

- equal bytes produce another URL observation and no duplicate raw object;
- different bytes produce `STOP_FOR_REVIEW` and no staging or promotion;
- multiple URLs with equal bytes remain multiple observations linked to one
  byte object;
- reruns are idempotent by normalized URL plus observed SHA-256.

Future promotion logic is tested only in temporary directories. It enforces logical
and resolved source/staging/destination roots, rejects symlink/reparse and hardlink
aliases, and holds identity-checked handles for the source, stage, destination, and
their parent chains across every mutation. POSIX child operations are descriptor
relative; Windows directory leases deny rename/delete replacement. The primitive
copies to a unique same-filesystem stage, independently rehashes it, and uses an
atomic no-replace publication operation. If cancellation or another catchable error
occurs after the destination may exist, it removes only the owned stage, revalidates
an unaliased byte-identical destination, and raises a typed outcome carrying the
verified committed result; cancellation is not silently swallowed. It never uses
`os.replace` for raw publication.

## Operational ledger boundary

Strictly revalidated typed ledger records and deterministic serialization are
implemented, including successful-attempt links for byte comparisons, matching
failure references, exact reviewed-plan binding for expected hashes/paths, and
complete unforked redirect chains rooted at the pinned direct URL. Run-specific
collision evidence requires `stop_for_review` closure. No production ledger file or
record is created; the pre-existing Dropbox manifest directory remains empty. Tests
serialize only beneath pytest temporary
directories. The future mutable ledger remains in Dropbox
`01_raw/manifests/`; Git contains only models, schemas, code, tests, and reviewed
plans. Canonical `reports_manifest` remains M1-04 work.

## Verification and stop condition

M1-03A closes only after the zero-network dry run, full repository quality gate,
source-integrity recheck, independent read-only safety review, exact-head PR
checks for Python 3.12 and 3.13, and confirmation that the PR is open and
unmerged. M1-03B, M1-04, PDF processing, OCR, extraction, and M2 remain
prohibited.
