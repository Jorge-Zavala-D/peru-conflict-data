# M1-03B.1 live-comparison readiness design

Date: 2026-08-29
Branch: `codex/m1-03b1-live-comparison-readiness`
Base: `fcd3605c4ec265ffc8420bc5c43f7c5e967af781`

## Scope and proof obligation

The research owner explicitly authorizes M1-03B.1 on this branch. This work
prepares, but does not perform, a comparison-only live pilot for the ten already
protected reports 260–269. The prior `AGENTS.md` milestone paragraph describes
the superseded M1-03A gate and will be updated to this narrower authorization.
It does not authorize M1-03B.2.

This branch makes no external Defensoría PDF/ZIP request and no write beneath
`CONFLICT_DATA_ROOT`. Production persistence and network code are exercised only
with synthetic transports, synthetic bytes, and temporary data roots. The later
M1-03B.2 pilot may compare official remote bytes with pinned local bytes. It may
not stage or promote raw data. Equal bytes produce provenance without a duplicate.
Different bytes produce association-uncertain collision evidence and
`stop_for_review`; they are not silently classified as an alternate report
version, and their temporary bytes are removed after the durable evidence record.

## Immutable inputs

The following remain byte-identical: scientific schemas v0.1.0/v0.2.0; discovery
schemas v0.1.0/v0.2.0/v0.3.0; acquisition schemas v0.1.0; pilot plans v1/v2; and
existing integrity receipts. Tests pin their repository snapshots or file hashes.
Acquisition v0.2.0 is additive and records the genuinely new authorization,
execution-tree, transport, evidence, and durable-ledger semantics.

## Nine boundaries

### 1. Canonical URL and production transport

Acquisition URL validation occurs on the exact supplied text before any
normalization. The accepted form is absolute HTTPS, an approved exact host,
default port only, no user information, no query, and no fragment. It rejects
controls, backslashes, invalid percent escapes, percent-encoded slash/backslash/
NUL/control/dot-segment forms, and decoded `.` or `..` segments. A single
canonical wire-target function UTF-8 encodes Unicode path components, emits
uppercase percent triplets, and never changes path semantics. Evidence retains
the source-original URL separately from its normalized identity and canonical
wire target.

`StandardLibraryStreamingTransport` implements the existing `StreamingTransport`
protocol using direct `http.client.HTTPSConnection`. It disables automatic
redirects, uses a verified default TLS context with `check_hostname = True`,
`CERT_REQUIRED`, and no key log, and ignores proxy configuration by never using a
proxy-aware client. Live preflight rejects proxy and TLS-override environment
variables, including `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`,
`SSL_CERT_FILE`, `SSL_CERT_DIR`, and `SSLKEYLOGFILE`, instead of inheriting an
unreviewed trust or routing boundary.

Only GET is accepted. The sealed timeout is 30 seconds. Caller headers may not
include Authorization, Cookie, Proxy-Authorization, Host, connection-management
fields, request-body framing fields, or line breaks. `Accept-Encoding: identity`
and the stable project User-Agent are mandatory. Raw ordered response-header pairs
are validated before conversion to a read-only mapping. Duplicate safety-critical
headers (`Content-Length`, `Content-Type`, `Content-Encoding`, `Location`,
`Transfer-Encoding`, and `Retry-After`) are rejected. A header-first wrapper yields
bounded chunks and exposes explicit close behavior. Transport exceptions become a
stable class-only error so URLs, proxy values, and secrets cannot enter receipts.

Redirects are not generally same-host permissive. A redirect request is allowed
only when it remains HTTPS/default-port on an approved host alias and the
canonical wire path is equivalent to the exact reviewed URL; queries, path changes,
and off-host destinations stop before the next request.

### 2. Authorization and execution identity

Acquisition v0.2.0 defines an authorization artifact that binds:

- schema, authorization ID, status, comparison-only scope, and owner/timestamp;
- exact plan raw, semantic, and ordered-target fingerprints;
- the protected-source receipt path, merged commit, and SHA-256;
- the exact reviewed execution-code Git commit;
- a closed execution-tree manifest hash and execution-tree content hash;
- exact installed `RECORD` file paths and SHA-256 values for Pydantic, PyYAML, and
  their four runtime dependencies;
- reports 260–269 in exact order and exact approved hosts;
- explicit capabilities (network comparison and operational-ledger writing; no
  staging, promotion, full-corpus expansion, or historical acquisition);
- the exact storage-namespace marker hash, data-root identity hash, and execution
  host identity hash;
- the strict redirect policy; and
- one-shot, same-authorization/same-run restart semantics.

The closed execution tree requires one exact sorted list: every acquisition runtime
module including the authorization loader, their project imports, the acquisition
CLI script, pilot v2, the final M1-03B.1 source receipt, `pyproject.toml`, and
`uv.lock`. An incomplete or widened list fails. Four fixed files are deliberately
external trust anchors to avoid a circular hash: the future authorization artifact,
execution manifest, authorization registry, and registry SHA-256 pin. A future
authorization-only protected-main commit may change only those paths. Runtime
requires clean `HEAD` to equal protected `main` resolved directly from the public
GitHub API over credential-free verified HTTPS; a locally writable remote-tracking
ref is not authority. It requires the artifact's execution commit to be its
ancestor, compares every manifest entry to both that commit's Git blob and current
bytes, and rejects every non-anchor delta. Git is invoked only from a fixed system
path under a closed configuration environment.

The executable starts under the fixed `.venv-live` Python using `-I -S -B` with
standard-library code only. `uv run` is not part of the production invocation.
Before OpenSSL-backed or project imports, it rejects Python import-control and
proxy/TLS/OpenSSL override environment variables and site
customization, checks exact artifact bytes and the registry/pin, resolves public
protected-main evidence, and validates the closed execution tree. It then verifies
the exact authorization-pinned dependency `RECORD` files and every hashed member,
requires the exact pinned distribution set, rejects standard-library shadows,
unlisted files, competing import candidates, and required-package bytecode, disables
Pydantic plugins, and adds only the reviewed `src` and exact repository `.venv-live`
site-packages paths after the standard library. That environment must have been
created separately from the frozen lock with runtime-only copy-mode installs.
Loaded module origins are rechecked. The application loader
repeats hash-before-parse validation and requires both exact raw-artifact and full
semantic grants in the fixed registry, whose bytes must match its separately tracked
digest pin before registry parsing.
Only the loader can return the sealed reviewed-authorization wrapper accepted by
production composition; a raw Pydantic artifact is not executable authority.
The production registry and pin represent no grants in M1-03B.1, so no
valid-looking artifact enables live use. A pure validator accepts synthetic
registry data only as a unit-test seam; production loading has no registry override
parameter. After M1-03B.1 is merged, the owner may create and byte-approve an
artifact that binds that merge as its execution commit. A separate protected-main
PR then adds only the artifact/manifest, exact-byte plus full-semantic registry grant
(including the execution commit), and updated pin. This avoids a self-referential commit hash while
preventing a locally invented clean commit from becoming authority. Tests reject
dirty/alternate registry bytes, a commit-changed artifact, a non-protected-main
anchor commit, and any runtime/loader change outside the anchors. CLI flags cannot
replace a capability, identity, scope, host, or redirect-policy field.

### 3. Storage instance and one-shot evidence

A future M1-03B.2 authorization must contain and pin the canonical bytes and hash of
a stable manifest-namespace marker, plus the identity of the approved data root and
execution host. After artifact/execution/source/root/host validation, but before any
transport construction, the runner acquires the manifest lock. It atomically
creates the marker with create-no-replace, flush/fsync, and identity revalidation
when absent, or requires byte-exact identity when present. A mismatch or racing
creator stops for review. Marker creation is an inert storage-instance bootstrap,
not an authorization-use claim.

A global append-only authorization-use index and deterministic per-authorization
ledger then form a paired record. After the marker is exact, the index claim is
durably appended before per-authorization ledger creation and later records ledger
creation and terminal state. A crash after marker creation but before the global
claim may safely retry the exact marker check. A crash after the global claim but
before ledger creation resumes only by completing that same deterministic ledger;
it may never create a second run. Missing or contradictory members stop for review.
The same authorization cannot be reused against a copied/switched data root or
another host.

`data_root_identity_hash` is the canonical hash of the resolved absolute root path,
platform/host identity, filesystem volume or device ID, root file ID/inode, and the
owner-reviewed marker nonce. The ledger recomputes that tuple from the retained root
directory lease before it acquires any child writer.
Replacing the root at the same path or copying its marker/files to another root or
host fails. A legitimate filesystem migration that changes these stable IDs
requires a new reviewed authorization; portability across such a move is not
claimed.

Local evidence cannot cryptographically prove prior use if an actor deliberately
deletes both the index and ledger. The design makes deletion detectable while
either member or the pinned namespace marker survives and states this limitation
explicitly; it does not claim a remote transparency log or tamper-proof authority.

The only raw-tree write grant is opaque and narrow: it can bind the retained
`01_raw/manifests` directory and create/append the exact namespace marker,
authorization-use index, lock, and deterministic per-authorization ledger names.
It cannot resolve arbitrary children, create staging, write raw report paths, or
invoke publication code. Production code exposes no general raw-write capability.

### 4. Compare-only orchestration

The runner has four fail-closed phases:

1. Complete the isolated pre-import trust bootstrap, then load the exact plan and
   authorization; validate the execution tree, source receipt, all ten local
   paths/sizes/hashes through retained parent/file handles, data-root and manifest identities,
   storage marker, host identity, fixed system-temp path, prohibited capabilities,
   URL policy, and proxy/TLS/OpenSSL environment. This finishes before construction of a
   transport, connection factory, or DNS-capable object.
2. Acquire the manifest lock; bootstrap or verify the exact marker; hydrate and
   claim the canonical use index; create or hydrate the deterministic ledger;
   validate restart state, explicitly close every dangling attempt as
   `crash_outcome_unknown` with null accepted bytes while retaining its reservation,
   record `MISSING_EVIDENCE`, reject terminal/reused authorizations, and reconcile
   only deterministic run-owned temporary names through retained descent from the
   OS temp root. Complete unaccepted objects are fingerprinted durably before
   deletion. Recovery stops for review before transport construction.
3. Process 260–269 in plan order. For each landing/PDF request, durably claim the
   attempt and its budget before calling transport. Persist the result, verify the
   landing association, stream PDF bytes, rehash the corresponding local source
   immediately before and after comparison, persist the disposition, then remove
   the temporary object. A collision or any unclassified failure stops immediately.
4. Rehash all ten protected sources and recompute the complete terminal graph from
   durable records. Persist `completed` only when all ten ordered targets have one
   valid landing association, one accepted PDF byte object, one equal comparison,
   and cleanup evidence with no unfinished attempt or unresolved issue. Collision
   dominates as `stop_for_review`; cleanup uncertainty leaves the run active, and
   controlled policy/infrastructure failure is `abandoned` only when no owned temp
   bytes remain and the ledger is safe.

The runner imports no raw publication primitive and accepts no storage/promotion
callback. Tests enforce the absence of the publication module and primitive from the
compare-only runner.

### 5. Attempt and byte-budget durability

Every possible transport call is preceded by a canonical, fsynced `attempt_started`
record containing the deterministic ordinal, request role, URL evidence IDs, and
reserved budget. A PDF attempt conservatively reserves the per-file ceiling before
network construction; a landing attempt reserves its HTML ceiling. An
`attempt_finished` record records status, selected safe response headers, actual
accepted bytes, and a complete body hash only after engine-level body validation.
EOF alone is not success. A following redirect or retry attempt carries an explicit
link to the prior durable outcome. Hydration writes an explicit
`crash_outcome_unknown` outcome with null accepted bytes for every dangling claim,
counts it as consumed, retains its full reservation, records `MISSING_EVIDENCE`, and
forces stop-for-review before another transport. No terminal may coexist with an
unfinished claim. It never refunds an uncertain attempt. A completed outcome may replace a reservation with
the actual accepted bytes only through a monotonic, validated state transition.
Repeated crashes therefore exhaust rather than reset the 60-attempt and total-byte
budgets. Crash-injection tests cover before/after claim fsync, transport return,
streaming, outcome append, comparison append, and cleanup append.

Temporary tokens derive only from authorization, report, and durable attempt
ordinal; the filename retains the report/PDF role, for example
`report-260-<deterministic-token>.pdf.partial`. No UUID or clock controls ownership.
Hydration has an explicit recovery table for absent, partial, accepted-complete,
unaccepted-complete, and unexpected names. Unaccepted complete bytes are size/hash
fingerprinted in a durable observation before removal and classified rather than
reused; unexpected aliases or identities stop. Cleanup failure remains an active
restart condition until the owned object is removed.

Deletion is platform-explicit. The reviewed Windows path marks the retained native
file handle for deletion after an atomic quarantine rename. POSIX has no reviewed
identity-conditional unlink-by-descriptor primitive, so it durably syncs and
preserves the quarantine, records cleanup pending, and cannot reach a successful
live terminal. Atomic POSIX quarantine requires `renameat2(RENAME_NOREPLACE)`; an
interruptible hard-link/unlink fallback is forbidden. M1-03B.2 authorization is
therefore Windows-only unless a later reviewed contract adds safe POSIX deletion.
The standard-library bootstrap and application execution boundary independently
enforce the platform gate before artifact/GitHub, data-root, ledger, temporary, or
transport effects; dry-run and offline tests remain cross-platform.

### 6. Landing-page evidence and unresolved associations

A bounded HTML parser inspects only anchors inside the exact fetched landing
document. The reviewed direct URL must appear exactly or as the same canonical URL
under the strict URL rules. Duplicate anchors resolving to that one canonical URL
collapse as repeated support. A distinct PDF-like canonical URL is a competing
candidate only when a finalized bounded entry/card ancestor contains the exact
target report number and conflict-report family phrase; this order-independent pure predicate is the sole
plausibility rule. Zero reviewed support is missing evidence; reviewed support plus
any distinct competing candidate is ambiguity. Other institutional PDF links are
ignored. Opaque filenames for 261/263 receive no filename-based identity inference.

Evidence preserves landing body SHA-256 and byte count, exact source text span,
character and byte offsets where determinable, excerpt hash, parser version, source
attempt ID, source-original href when safe, normalized identity, canonical wire URL,
and the complete bounded candidate set. A raw href containing a query, credential,
control, or out-of-policy target is never persisted verbatim; only a safe
classification and hash are retained.

Landing-page observation is distinct from report identity association. Reports 261
and 263 retain their reviewed unresolved/opaque-filename uncertainty even if a
landing page contains the reviewed direct link. Equal bytes establish byte equality
with the protected object, not independent report identity. Different bytes remain
an association-uncertain collision candidate requiring review, not an automatically
accepted alternate version.

### 7. Durable operational ledger

The future fixed location is `01_raw/manifests/`; the CLI cannot choose another
destination. Retained component leases bind the data root, `01_raw`, and
`manifests` directory through identity-checked handle-relative operations. The
append descriptor remains open and its file identity, link count, and parent chain
are checked before and after every write. Replacement, unlink, extra hard links,
reparse/junction substitution, or directory swap stops safely.

The lock is a kernel-held advisory lock (`flock` on POSIX and a retained Windows
locking primitive), not a lock-file-existence convention. It is single-host by
design, with the authorization separately bound to that host. Tests cover
subprocess contention, abrupt process termination, and reacquisition.

The ledger is canonical UTF-8 JSONL with LF endings. Every record has a contiguous
sequence number and previous-record hash. Each append is strict-model revalidated
against a cloned state, written, flushed, and fsynced before claimed state changes.
The runner then appends/fsyncs a use-index high-water anchor containing the
authorization ID, ledger sequence, and ledger-head hash before proceeding.
Hydration requires exact agreement with the latest anchor: ledger-ahead,
index-ahead, missing complete final lines, or independent rollback of either file
stops for review. A crash between ledger append and anchor append leaves an explicit
non-resumable mismatch; it is not silently repaired. Coherent rollback/deletion of
both files remains part of the disclosed total-local-evidence limitation.

The containing directory is synced where the platform supports it when a file is
first created. A complete canonical LF-terminated record found after an uncertain
fsync is treated as committed only when its high-water anchor also agrees after
revalidation. An incomplete or noncanonical tail is not repaired or truncated and
stops future hydration. The durability claim is local operating-system
acknowledgement only, not Dropbox cloud replication.

Record identity is deterministic. Same ID/same canonical bytes is idempotent; same
ID/different bytes and alternate IDs for the same logical event are rejected. The
global claim and run origin bind the exact authorization artifact SHA-256 as well as
the plan, host, storage, and execution identities. The v0.2 records cover run
identity, attempt claims/outcomes and continuation links, landing associations,
byte objects, comparisons/collisions, cleanup, issue classifications, and terminal
state. No record contains an absolute private path, credential, cookie, signed URL,
or system-temp path.

### 8. State, issues, and terminal truth

`unused -> active -> completed | stop_for_review | abandoned`

- `unused`: no paired use evidence exists; the exact authorization may make its
  durable global claim once.
- `active`: canonical paired records exist without terminal state; only the same
  exact plan, artifact, execution tree, data-root marker, host, and run may resume.
- terminal states: the authorization is spent and cannot start or continue.
- malformed/truncated/contradictory evidence and a collision without its matching
  terminal are non-success states requiring owner review; they are never repaired.

Terminal hydration recomputes rather than trusts summary claims. `completed`
requires exactly reports 260–269 in order, with the required landing, PDF, equality,
cleanup, source-rehash, and budget graph and no collision. A collision always
dominates `completed` or `abandoned`.

Issue classification is independent of terminal state. Records preserve at least
`PARSER_ERROR`, `MISSING_EVIDENCE`, `AMBIGUITY`, `SOURCE_INCONSISTENCY`,
`POLICY_VIOLATION`, and `INFRASTRUCTURE_FAILURE`; terminal status never silently
collapses a scientific/source problem into a generic operational failure. Missing,
empty, and numeric zero remain distinct in every serialized model.

### 9. CLI and absence of live authorization

`dry-run` retains its existing arguments and behavior. A future `live-compare`
subcommand accepts only the exact plan path/hash and authorization path/hash. It
uses the fixed registry, environment-resolved data root, fixed manifest location,
fixed system-temp location, and production transport. In M1-03B.1 it always fails
at the empty reviewed registry before transport construction, DNS/socket use,
temporary creation, ledger creation, or Dropbox mutation. There is no
force/authorize/registry/host/URL/range/destination/promotion/insecure option.

## Failure and disposition matrix

| Evidence | Classification and terminal behavior | Raw effect |
|---|---|---|
| Ten equal byte comparisons with complete graph | `completed` | none |
| Landing lacks reviewed association | `MISSING_EVIDENCE`; `stop_for_review` | none |
| Competing landing associations | `AMBIGUITY`; `stop_for_review` | none |
| First different byte object | association-uncertain collision; `stop_for_review` | none; temp removed after evidence |
| Source contradiction | `SOURCE_INCONSISTENCY`; `stop_for_review` | none |
| Parser defect | `PARSER_ERROR`; `stop_for_review` | none |
| Network/policy/path failure | classified policy/infrastructure failure; `abandoned` only if durable state is safe | none |
| Changed local source, malformed/reused authorization, or corrupt ledger | fail before transport or stop for review | none |

Compare-only completion is neither corpus completeness, alternate-version
adjudication, nor redistribution permission.

## Verification

Fixture tests cover canonical URL/wire behavior, transport TLS/proxy/header rules,
strict redirects, authorization byte pins and closed execution tree, storage/host
one-shot identity, landing source evidence, durable attempt reservations,
persistence faults, subprocess locks, restart and deterministic temp recovery,
exact target ordering, source TOCTOU rechecks, collision dominance, cleanup, issue
taxonomy, and the absence of publication calls. Network-blocking integration tests
prohibit external sockets/DNS and prove registry rejection precedes factories.
Windows CI executes the filesystem/ledger suite. The final gate reruns the unchanged
M1-03A dry run and rechecks Dropbox and all eleven sources before and after.
