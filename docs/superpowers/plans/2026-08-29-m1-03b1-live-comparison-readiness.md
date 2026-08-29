# M1-03B.1 live-comparison readiness implementation plan

> Execute test-first on `codex/m1-03b1-live-comparison-readiness`. M1-03B.2 is not
> authorized. Every external Defensoría PDF/ZIP request and every Dropbox write is
> prohibited.

## Task 1: lock governance and immutable baselines

- Verify base `fcd3605c4ec265ffc8420bc5c43f7c5e967af781`, clean branch, merge CI,
  Dropbox inventory, and all protected hashes.
- Add only `windows-acquisition-safety` to ruleset 21658925 after action-time
  confirmation, then reread every preserved setting.
- Add digest tests for prior acquisition schema tree, pilot v1/v2, and prior
  integrity receipts.
- Acceptance: no immutable byte changes; ruleset has exactly three required checks.

## Task 2: specify acquisition v0.2.0 contracts

- RED: authorization scope/capability/timestamp/execution-tree/storage/host/one-shot
  tests; strict attempt, evidence, issue, collision, cleanup, and ledger-record tests.
- GREEN: add strict v0.2 models without changing v0.1 models.
- Export only `schemas/acquisition/v0.2.0/`; add migration note, registry schema,
  and drift tests.
- Acceptance: widened scope, wrong targets/order/host/storage identity, conflicting
  logical record IDs, and incomplete terminal graphs are structurally rejected.

## Task 3: implement byte-pinned authorization and execution-tree validation

- RED: wrong artifact hash before parse; exact raw artifact reserialization;
  separately pinned fixed-registry
  rejection; dirty/alternate registry blob; commit substitution in an otherwise
  identical artifact; self-consistent unreviewed
  artifact/registry commit; malformed or unregistered artifact;
  plan/target/source-receipt/storage/host mismatch; dirty, untracked, or shadowed
  execution inputs; wrong execution commit/tree; public protected-main mismatch;
  locally rewritten remote-tracking ref; fake `PATH` Git or hostile Git
  configuration; tampered dependency or `RECORD`; standard-library shadow or
  unverified bytecode; non-anchor delta; prohibited capabilities; copied
  root/replaced same-path root; and synthetic pure-validator acceptance.
- GREEN: separate digest pin for the fixed empty production registry, exact-byte and
  full-semantic grant core, standard-library `-I -S` bootstrap before application
  imports, credential-free public-GitHub-main/anchor-only trust, fixed closed Git
  execution, byte-first loader, exact dependency `RECORD` validation before
  site-packages, standard-library precedence, pure test validator, closed
  execution-tree manifest including the loader, module-origin verification, exact
  root identity tuple, and immutable receipt validation.
- Acceptance: registry or preflight failure occurs before transport/connection/DNS,
  temp, lock, ledger, or data-root mutation; no real authorized artifact exists.

## Task 4: implement canonical URL and production transport

- RED: pre-normalization query rejection; credentials/fragments/ports/controls;
  invalid/encoded separators and dot segments; Unicode and percent-triplet wire
  behavior; verified TLS; proxy/TLS/OpenSSL environment rejection; dangerous request and
  duplicate response headers; header-first bounded reads; close; sanitized errors;
  and strict canonical-path redirect policy.
- GREEN: one canonical URL/wire implementation and direct
  `http.client.HTTPSConnection` wrapper with injected factories for synthetic tests.
- Acceptance: no external host is contacted; all network-capable construction is
  behind the sealed grant; source, normalized, and wire representations remain
  distinct.

## Task 5: implement source-preserving landing association

- RED: exact/canonical link, duplicate identical anchors, deterministic bounded-card
  competing-candidate predicate, linked source span and offsets, candidate-set
  evidence, 261/263 unresolved association, unsafe-href redaction,
  missing/unrelated/ambiguous links, and publication-date/non-identity negatives.
- GREEN: bounded `HTMLParser` association verifier with exact body/excerpt hashes
  and parser version.
- Acceptance: PDF request is impossible without reviewed landing evidence, and
  byte equality cannot silently adjudicate report identity.

## Task 6: implement paired use index and persistent operational ledger

- RED: storage marker/root/host binding; absent/exact/mismatched/racing marker;
  crash after marker creation; global claim before per-auth ledger; crash after
  claim but before ledger creation; missing/contradictory pair; canonical
  append/fsync; record sequence/previous hash; use-index high-water anchors;
  complete uncertain append; noncanonical/incomplete tail; removal of one or more
  complete ledger lines; removal of the latest anchor; independent rollback of
  either file; crash between ledger append and anchor append; deterministic IDs;
  alternate logical IDs;
  subprocess lock contention/termination/reacquisition; retained file identity,
  link-count, junction/reparse/hardlink, unlink/replacement, and directory-swap
  attacks.
- GREEN: narrow identity-bound manifest grant, canonical marker bootstrap,
  kernel-held lock, hash-chained append-only use index and ledger, high-water
  anchoring, canonical JSONL writer, strict hydration, and state machine.
- Acceptance: tests write only temporary synthetic roots; production code cannot
  perform a general raw write; real `01_raw/manifests/` remains empty.

## Task 7: implement durable budgets and deterministic temp recovery

- RED: attempt claim persisted before each transport call; dangling claim consumes
  attempt/full reservation and receives an explicit unknown-crash outcome with null
  accepted bytes, a `MISSING_EVIDENCE` issue, and stop-for-review before any new
  transport; monotonic completion accounting; repeated-crash budget exhaustion;
  deterministic names; absent/partial/complete/unexpected recovery; complete-object
  fingerprinting before deletion; and crash points around claim, transport,
  streaming, outcome, comparison, and cleanup.
- GREEN: claim/outcome transitions, evidence-honest unfinished-attempt
  reconciliation, hydration counters, conservative byte reservations,
  component-by-component OS temp leases, pre-delete observations, deterministic
  restart-visible deletion quarantine, accepted-object rehash, and
  authorization/report/role/ordinal temp naming.
- Acceptance: no restart resets attempts or byte budgets; no UUID/clock establishes
  ownership; unexpected temp state stops safely; quarantine directory entries are
  synced; POSIX never uses a link/unlink rename fallback or a raceable
  stat/pathname-unlink claim, and remains cleanup-pending rather than claiming
  success.

## Task 8: implement compare-only runner and future-failing CLI

- RED: all source/code/root/host/environment/use-index preflight before factories;
  retained protected-source parent/file handles; intermediate Windows junctions,
  hardlink aliases, and parent replacement;
  exact 260–269 order; landing-before-PDF; per-source immediate before/after rehash;
  final ten-source rehash; equal/no raw write; collision/source issue dominance;
  ledger and fail-once cleanup/restart failures; strict terminal graph with no
  unfinished attempt; no publication import/call;
  runtime path audit; exact scope; and empty-registry CLI failure with blocked
  socket/DNS/temp/Dropbox spies.
- GREEN: orchestrator using sealed grant, paired ledger, durable budgets, transport,
  landing verifier, fixed temp root, and a `live-compare` CLI with no override flags.
- GREEN: direct `.venv-live` `-I -S -B` bootstrap with exact dependency closure;
  environment preparation is separate from invocation and `uv run` is rejected as
  a production trust boundary.
- Acceptance: synthetic ten-target run completes; collision stops first; no staging,
  promotion, or raw report path is reachable.

## Task 9: documentation and no-network/integrity proofs

- Update README, AGENTS, execution plan, acquisition checkpoint/protocol, schema
  migration note, and M1-03B.1 completion/source-integrity reports.
- Document local-OS durability, single-host locking, total-evidence-deletion limit,
  unresolved 261/263 identity, collision-temp deletion, and future B.2 two-step
  registry-trust-root plus exact-artifact authorization ceremony accurately.
- Rerun the exact M1-03A dry run and confirm 10/20/45/0/0 and deterministic digest.
- Take read-only Dropbox inventories and hashes before/after.
- Acceptance: no claim of raw-promotion crash safety, cloud durability, corpus
  completeness, alternate-version adjudication, or redistribution rights.

## Task 10: exact-snapshot review and quality gate

- Freeze the integrated diff and obtain three independent read-only reviews:
  transport/authorization; ledger/restart/storage; governance/provenance/stops.
- Turn every Critical/Important finding into a regression or explicit evidence-based
  decision; repeat review after each substantive fix.
- Run frozen sync, Ruff format/lint, four strict Pyright version/platform
  combinations, full pytest on local 3.12 and 3.13, all schema drift, working/staged
  data guards, pre-commit, secret scan, and Git diff/whitespace checks.
- Acceptance: no unresolved Critical/Important finding and all gates green.

## Task 11: PR and exact CI evidence

- Commit focused changes, push normally, open one PR to protected `main`, and do not
  merge.
- Wait for and inspect raw logs for `quality (3.12)`, `quality (3.13)`, and
  `windows-acquisition-safety` on the exact head.
- Report exact interpreter/runtime/test/skip evidence and stop with M1-03B.2
  prohibited.
