# M1-03B.1 completion and readiness report

Status: ready for pull-request audit; M1-03B.2 remains prohibited.

Branch: `codex/m1-03b1-live-comparison-readiness`

Verified base: `fcd3605c4ec265ffc8420bc5c43f7c5e967af781`

The exact committed head, pull request, and final GitHub Actions run belong in the
live PR record after the tree is frozen. They are deliberately not chased by a
self-referential CI-receipt commit.

## Outcome

M1-03B.1 implements, entirely with synthetic/local evidence, the production
machinery for a future one-shot comparison of the already protected reports
260–269. It does not create authority to use that machinery. The canonical reviewed
authorization registry is empty, no `authorized` artifact exists, and
`live-compare` fails before transport construction, temporary storage, or an
operational Dropbox write.

M1-03A's `dry-run` is unchanged: it validates ten protected PDFs, twenty logical
URLs, and 45 ordered future actions while making zero network requests and zero
Dropbox writes.

## Change summary

| Area | Files and result |
|---|---|
| Governance and CI | `.github/workflows/ci.yml` extends the real Windows acquisition suite to every new M1-03B.1 safety module. `AGENTS.md`, `README.md`, and `docs/execution_plan.md` keep M1-03B.2, raw promotion, M1-04, and M2 closed. |
| Authorization | `scripts/acquire_official_sources.py`, `models_v2.py`, and `authorization.py` define a standard-library-only `-I -S -B` bootstrap from a dedicated `.venv-live`, strict v0.2 artifacts, a separately pinned reviewed registry, exact raw-artifact plus full-semantic grants, independent public-GitHub-main evidence, closed Git execution, exact dependency closure and `RECORD` pins, execution tree, receipt, plan/target/limit fingerprints, capabilities, storage identity, and one-shot semantics. The bootstrap and application preflight both reject non-Windows live mode before protected/network state; the registry remains empty. |
| Transport and landing evidence | `transport.py`, `attempt_transport.py`, and `landing.py` implement direct verified HTTPS, explicit header-first bounded streaming, sanitized evidence, scheduler/receipt integration, deterministic Unicode path handling, no automatic redirects/proxies/credentials/cookies, and exact source-visible landing-link association. |
| Compare-only composition | `live_compare.py` performs complete local/Git/authorization/storage preflight before transport creation. Retained handle-relative bindings cover every protected source parent and PDF for the whole run. `compare_runner.py` processes exactly 260–269 in order, creates no raw duplicate, and stops on first link drift, collision, source change, cleanup uncertainty, or policy/infrastructure failure. It never imports or calls publication. |
| Durable evidence and recovery | `persistent_ledger.py`, `temp_recovery.py`, and `fs_safety.py` provide retained directory identity, directory-entry sync, a fixed manifest namespace, kernel single-writer locking, canonical hash-chained JSONL, a global one-shot use index with high-water anchors, explicit unknown-crash evidence, pre-delete complete-object fingerprints, deterministic restart-visible delete quarantine, and handle-relative run-owned system-temp recovery from the OS temp root. Accepted cleanup rehashes exact bytes and treats disappearance or replacement as pending. Windows uses retained-handle deletion; POSIX deliberately preserves quarantine and leaves cleanup pending because no reviewed identity-conditional unlink primitive is available. All production-write behavior is tested only beneath pytest temporary roots. |
| Versioned contract | `schemas/acquisition/v0.2.0/`, `schema_export.py`, and the migration note add six strict v0.2 contracts without changing acquisition v0.1 or any scientific/discovery snapshot. |
| Tests | New unit/integration files cover authorization, transport, attempts, landing evidence, ledger/restart, temporary recovery, compare-only outcomes, CLI fail-closed behavior, and Windows-native manifest operations. Existing dry-run and immutable-plan coverage remains active. |
| Documentation | `docs/m1_acquisition_checkpoint.md`, the design/specification, implementation plan, live-comparison protocol, this readiness report, and `docs/source_integrity_receipt_m1_03b1.md` describe exact claims and stop boundaries. |

## Contract fingerprints and immutability

- acquisition v0.2 schema-tree SHA-256:
  `da6f39205d0bc473bfb6b80ff7dab424b7bf8f8d9ce4fa04113813fa4b65b485`;
- empty reviewed registry SHA-256:
  `1ee550b4b5989124356e27c0034c88df68ac3d5e58aa66b13c7b33afb9f4f522`;
- acquisition v0.1 tree remains:
  `b1029c80de6bbb5f293407070ed165936ff892d436018273f5e5b60dd74f2c61`;
- discovery v0.3 tree remains:
  `00cbf40848c24d24eea454e25682061d5725abe01c24c6479ffa6d30fffd821b`;
- pilot v1 remains:
  `59480d3845ba3fb2ce14f0d1fce01b93472ca1c86e189a4a67d6fa9d9599a6b7`;
- pilot v2 remains:
  `d5cab626ba167fc45c8b5147d04bc40f85aec3a952d7fd4dbd5543b20631b4c4`.

Pinned tests also retain the scientific v0.1/v0.2 and discovery v0.1/v0.2 tree
digests. No old schema, pilot, or receipt was rewritten.

## Authorization and execution identity

A future owner-reviewed v0.2 artifact must pin its own exact SHA-256, the exact raw
and semantic pilot fingerprints, ordered targets and hard limits, the latest
protected-source receipt and hash, the reviewed execution Git commit and closed
runtime tree, six exact installed dependency `RECORD` pins, reports 260–269,
approved hosts, compare-only capabilities, redirect policy, storage marker,
execution host/data-root identities, owner/timestamp, and same-run one-shot restart
rule.

The only reviewed future live host is Windows, using
`.venv-live\Scripts\python.exe -I -S -B
scripts\acquire_official_sources.py ...`. A POSIX environment may exercise
offline validation, but it is not eligible for M1-03B.2 authorization because this
version refuses raceable pathname deletion and preserves the quarantine as cleanup
pending. The bootstrap and application execution preflight enforce that boundary
before artifact/GitHub, data-root, ledger, temporary, or transport effects. `uv`
may prepare the otherwise-absent Windows
environment in a separate reviewed frozen, runtime-only, copy-mode ceremony, but it
is not part of the live invocation. The standard-library bootstrap runs before
application imports, rejects Python path/site customization and
proxy/TLS/OpenSSL override environment variables before OpenSSL-backed imports,
verifies the fixed
artifact's exact bytes and full-field registry core, resolves the public protected
`main` head directly from GitHub over credential-free verified HTTPS, and rejects a
locally moved remote-tracking ref. Git runs from a fixed system path with hostile
ambient configuration removed. Every runtime input, including the authorization
loader, is matched to both the reviewed commit and manifest; installed Pydantic,
PyYAML, and their four runtime dependencies are verified through exact owner-pinned
wheel `RECORD` files, the exact distribution set, unlisted files, and competing
import candidates before site-packages is added after the standard library.
Pydantic plugins are disabled. Only
the fixed future authorization artifact, manifest, registry, and registry pin may
differ in a later protected-main authorization-only commit.

The Pydantic loader repeats byte/schema/registry validation and returns a sealed
capability; production composition rejects a raw model. No flag can add authority,
URLs, reports, hosts, retries, bytes, staging, or promotion. A future M1-03B.2
authorization requires a separate owner-reviewed protected-main change after this
branch is merged so the exact execution commit and receipt bytes exist.

## Transport and landing association

The transport uses `http.client.HTTPSConnection` directly with the default verified
CA/hostname stack, port 443, no environment proxy inheritance, a 30-second timeout,
identity content encoding, a stable transparent user agent, and no credentials or
cookies. Redirects are returned to the policy engine rather than followed
automatically. Status and tightly bounded/sanitized headers arrive before a body is
read. Approved HTML and PDF bodies are streamed incrementally under separate byte
ceilings and always closed. External-facing errors are classified without retaining
secret-bearing exception text.

Landing verification requires the reviewed direct URL (or one exact safe normalized
equivalent) in a bounded source-visible link. Opaque file names for reports 261 and
263 remain explicitly unresolved associations. A missing or competing link prevents
the PDF request; the runner never substitutes a crawled candidate.

## Ledger, restart, and temporary bytes

The future operational ledger has one fixed location under
`01_raw/manifests/`, a canonical namespace marker, a retained directory lease,
kernel single-writer lock, canonical append-only JSONL, fsync at every claimed
durability boundary, a global hash-chained authorization-use index, and a per-run
hash chain anchored after every record. It rejects malformed/truncated content,
line removal, inconsistent high-water anchors, record reuse, terminal reuse,
concurrent writers, alias/reparse/hardlink escapes, or changed execution/storage
identity.

An interrupted partial run resumes only with the same exact authorization bytes,
plan, deterministic run, execution tree, host, data root, and marker. A durable
attempt claim without an outcome is explicitly reconciled as
`crash_outcome_unknown`, keeps its full reservation, records `MISSING_EVIDENCE`, and
never asserts zero bytes. Any complete temporary object is fingerprinted before it
is deleted, and the authorization stops for review before new transport. Attempts
and reserved bytes therefore cannot be reset. Completion requires the exact
ten-report graph plus four matching source-rehash phases for every report and no
unresolved issue. Terminal reuse is prohibited.

PDF bytes exist only in a run directory reached by retained handle-relative descent
from the operating-system temp root. Partial names are deterministically removed; a
complete name is reused only when it matches one successful durable attempt and
passes size, magic, byte-count, and hash checks. An unaccepted complete name is
removed and classified. Cleanup failure leaves the run active and restartable until
the owned object is removed; it cannot strand bytes behind an `abandoned` terminal.
The compare-only runner has no raw-stage or publication dependency.

## Adversarial findings resolved

Independent design reviews and RED/GREEN implementation tests led to these material
hardening decisions:

- the registry grant now pins both exact raw artifact bytes and the semantic hash of
  every field, including the reviewed execution commit;
- credential-free verified HTTPS to GitHub supplies independent protected-main
  evidence, so a local `update-ref`, fake `git` in `PATH`, or hostile `GIT_*`
  configuration cannot manufacture owner review;
- a standard-library `-I -S` bootstrap validates authorization and execution-tree
  evidence before application imports, rejects `PYTHONPATH`/site customization, and
  preserves standard-library precedence, verifies authorization-pinned wheel
  `RECORD` files, rejects standard-library shadows/unverified bytecode, and
  constrains module origins to reviewed `src` and the frozen environment;
- runtime inputs are an exact closed path set, not an authorization-selected subset;
- run and use-index origins bind the exact authorization artifact hash as well as
  semantic identity;
- retained directory leases supply the storage identity used at execution time,
  closing a root-swap preflight gap;
- body EOF is not durable success: the engine must accept MIME, encoding, size,
  `%PDF-`, and SHA-256 first;
- redirect/retry attempts carry explicit continuation links and safe response-header
  evidence;
- restart cleanup can recover a successful attempt even when no in-memory receipt
  exists;
- unmatched attempt claims are durably classified as crash outcomes with unknown
  byte evidence, retain their reservation, and stop for review after safe recovery;
- landing association uses the nearest deterministic semantic source card, so
  headings that follow a link remain visible while a page-level wrapper cannot turn
  an unrelated sibling PDF into false ambiguity;
- new ledger/index directory entries are synced at creation, temporary recovery
  binds every component from the OS temp root, and cleanup uncertainty cannot create
  a terminal while owned bytes remain;
- a quarantine rename is directory-synced before cleanup evidence; POSIX requires
  atomic no-replace rename and cannot claim deletion because a pathname
  check/unlink pair is not identity-conditional;
- every protected source parent is retained handle-relatively and every hash uses a
  held unaliased file descriptor; junction, parent replacement, and hardlink tests
  cover the Windows-native path;
- a completed graph now requires pre-network, comparison-before,
  comparison-after, and terminal protected-source rehashes for every report, all
  equal to the pinned source hash.

The ledger can detect inconsistent or independently rolled-back local evidence, but
cannot cryptographically detect a coordinated rollback of every local ledger/index
file by an actor who controls the storage. This limitation is explicit; it does not
weaken normal crash/restart fail-closed behavior.

## Validation evidence

The corrected integrated snapshot's local quality record is:

- frozen dependency sync: passed;
- Ruff format/check: passed;
- strict Pyright for Python 3.12 and 3.13 on Windows and Linux: passed;
- complete pytest on local CPython 3.12.13: 608 passed, 8 declared local
  capability skips;
- complete pytest in an isolated local CPython 3.13.5 environment: 608 passed, 8
  declared local capability skips;
- all scientific, discovery, and acquisition schema drift checks: passed;
- repository and staged-blob data-policy checks: passed;
- pre-commit and Git diff checks: passed;
- repeat exact-snapshot review is the final pre-commit gate; its result belongs in
  commit/PR audit metadata so recording it cannot change the tree that was reviewed.

The PR record is the authoritative location for the final exact head and GitHub
Actions evidence for `quality (3.12)`, `quality (3.13)`, and
`windows-acquisition-safety`; no CI-result receipt commit is created.

The repository ruleset change is the sole external governance blocker. The
supported GitHub integration has no ruleset-write operation, and the available
browser session is not authenticated to repository settings. No credential store
or token workaround was attempted. Ruleset `21658925` therefore still requires the
two quality matrix contexts; the owner-authorized, still-pending action is to add
only `windows-acquisition-safety` as the third context without changing any other
property. The Windows job remains present and mandatory for this PR's release gate
even while that repository-admin metadata action awaits an authenticated owner UI.

## Zero-network and zero-Dropbox evidence

No live comparison command was executed. Integration tests block unexpected
external connection construction, and all transport/body scenarios use injected
synthetic objects or local temporary files. The final real dry run again reported
10 protected PDFs, 20 logical URLs, 45 actions, `network_requests = 0`, and
`Dropbox_writes = 0`, with the unchanged 10,733-byte output hash documented in the
source-integrity receipt.

Read-only before/after Dropbox inventories both returned 82 directories, 111 files,
33,453,193 bytes, an empty `01_raw/manifests/`, no `01_raw/.staging/`, and empty
layers `02_extracted` through `07_releases`. All eleven protected hashes were
unchanged.

## Remaining stop gate

M1-03B.1 does not prove site availability, current remote byte equality, general
raw-acquisition recovery, corpus completeness, or redistribution rights. A future
M1-03B.2 would require the exact separately reviewed registry and authorization
bytes, then perform at most one serial comparison of the ten reviewed landing/PDF
pairs. Identical bytes produce provenance only; source-link drift stops before the
PDF; the first different-byte object is classified as an unresolved candidate
alternate and stops; network/policy/storage failure records non-success and stops.

Until that separate authorization exists: do not contact a Defensoría PDF/ZIP
endpoint, write the real operational ledger, create raw staging, promote bytes,
begin historical acquisition, M1-04, M2, extraction, OCR, or parsing.
