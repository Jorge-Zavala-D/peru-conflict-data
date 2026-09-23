# M2-02B.2 operational launch proposal

Status: **OWNER REVIEW DRAFT — NOT EXECUTED**. Nine launch-design decisions
remain approved. All seven operational decisions are UNRESOLVED, with null
responses. No person is assigned, real access test performed, package issued,
annotation started, production lock enabled, human gold created, or parser/M3
authority granted. Production-environment preparation is not environment approval.

The operational and annotation-launch candidate configurations bind the actual
PR #16 merge (`e33acf9350701f2c0141bf2d3f697c1bb69d2080`, tree
`8c7970063362f6b07029c7cd0d46a15c94bf2a5d`), the approved design and unchanged
scientific/benchmark/package/reference/view/runtime identities. Those bindings
are reviewed identity, not circular references to this subsequent proposal commit.

## Native environment candidate

### Corrected evidence contract (M2-02B.2B)

The V3 envelope supersedes, but never overwrites, historical candidate evidence.
Portable validation authenticates independently pinned raw Python, dependency and
runtime manifests before parsing them, then requires exact staged path/hash equality.
Counts are derived assertions, not authority. Manifest/receipt hashes cover exact
bytes; inventory hashes cover sorted compact JSON without a trailing newline.
Existing canonical-model hashes retain their original rules. The 2,217 reviewed
payload files are distinct from five extras: three stage receipts,
`runtime-v1/RUNTIME_MANIFEST.json`, and `trusted_launcher.py`. Each new receipt binds
its stage, constituent raw hash, complete inventory and verifier source hash.
Duplicate keys, case collisions, startup controls, bytecode, malformed authority
fields and coercible approval flags are rejected.

Native preparation requires Windows and PowerShell 7. Authentication, decoding and
parsing use the same retained bytes, with an 8 MiB ceiling enforced on the retained
stream before allocating the buffer. Source files are held against write/delete
sharing, directories against replacement, and exclusively created outputs against
write/delete sharing through publication. Exact final inventory checking precedes
the success receipt. Interrupted or extra-file candidates receive no success receipt;
partial evidence remains unusable and is preserved, not recursively deleted.

Directory handles do not prevent adding unrelated children. A concurrent writer
could add a file after the inventory observation and before receipt creation;
the receipt does not prove atomic directory publication. Preparation therefore
requires a private workspace without concurrent writers, and later use must reverify
the complete inventory under independently established protection.

This is a bounded preparation snapshot, not future filesystem immutability. The
private preparation workspace, native tooling and absence of hostile administrator
or kernel interference remain external trust assumptions. After handles are released,
later provisioning must independently authenticate and protect the installation at
use. Portable Python cannot authenticate the standard library it already executed.
Provenance assertions, independent provisioning, owner environment approval and
launch authority are separate gates, not consequences of a successful byte check.

`scripts/verify_m2_environment_candidate.ps1` checks an independently supplied
manifest byte pin before copying its files into a new bounded cache child. It
rejects reparse ancestry, unlisted startup controls, mismatched bytes and existing
destinations. It never invokes the interpreter being checked. Failed partial
copies are not usable candidates and receive no success receipt.

The candidate binds interpreter, standard library/native runtime, dependencies,
runtime bundle, launcher and platform. Python provenance comes from independently
matched public release archive bytes; runtime/dependency/launcher pins come from
the approved design. Native OS tooling, public release metadata, loader, kernel,
system libraries, filesystem and hardware remain explicit external trust inputs.
Local receipts distinguish byte consistency from that provenance and from owner
approval. The historical rehearsal bundle remains unchanged. The production
environment must receive a separate exact-byte owner approval before issuance.

The owner authorized isolated preparation outside the cloud-reparse-backed GitHub
checkout; this did not relax the reparse guard or authorize external operations.

## Private eligibility ceremony

1. Jorge privately nominates a potential A, then a potential B. No personnel data
   or exposure history is recorded in Git or in public PR metadata.
2. Coordinator privately checks blind-human eligibility: two distinct humans;
   neither exposed to machine aids, parser predictions, prefilled answers, the
   other's submissions, or pilot/development/held-out partition labels. Neither
   may use ChatGPT, Codex or another model to perform annotation.
3. Generate random opaque private person tokens, not unsalted name/email hashes.
   Independently confirm A differs from B and bind exactly one role to each human.
4. Bind each private attestation to candidate/run/package/reference/view/runtime/
   environment identities and timestamp. Preserve private supporting evidence in
   separately approved coordinator custody; expose only opaque bindings to code.
5. Jorge separately decides A eligibility, B eligibility and distinctness.
   Knowing the partition as coordinator does not establish blind-annotator eligibility.

The generated blank template records no actual attestation. Synthetic person
tokens and synthetic validation never establish real human eligibility.

## Bounded external setup and access testing — future authorization only

The additive [setup-authority bridge](m2_02_setup_bridge.md) provides an offline,
SYNTHETIC_ONLY manual-assisted work-order/evidence demonstration. It leaves the
proposal and all real decisions unchanged; production admission has no registered
real grant and rejects before dispatch. It is not a live Dropbox executor.

### Option 2 private-root successor

The owner selected Option 2 and approved
`/M2 Private Annotation Execution/m2-02-v1` as the planning target only.
Read-only inspection found neither the top-level parent nor run folder present
in the connected personal Dropbox namespace. The location is outside the
publicly linked research hierarchy; this is not evidence of actual A/B isolation.
The existing research root and its public link must remain untouched.

New local exports use `M2_SETUP_AUTHORIZATION_REQUEST_V3` under
`setup_request_v3/`. Folder creation proposals, probes, cleanup targets and blank
issuance paths all use the private root. Only `/` is asserted existing; both new
ancestors and every resource/probe directory are explicitly enumerated. The
historical V2 request remains reproducible by explicitly selecting version 2
in the request builder/validator; it is not accepted by the default V3 validator.
Historical snapshots and reviewed design identities are not rewritten.

All twelve logical resources, 108 ACL expectations, probe bytes and two separate
application controls are unchanged. Only the four A/B issue/submission leaves
may eventually be shared with their respective humans. Structural parents and
coordinator areas remain coordinator-only. Owner-only membership management,
effective links/groups and stable provider identities require separately
authorized setup and verification; Plus is not assumed to prevent recipient
copying or every recipient-created link. Personnel and exposure records remain
in separately approved local nonsynchronized custody, not Dropbox; execution
receipts may contain only permitted opaque references.

The selected path does not approve creation, sharing, access tests, environment,
issuance or launch. All private bindings remain null and all seven operational
decisions unresolved. The proposal remains non-executable. No canonical
`CONFLICT_DATA_ROOT` redirection is permitted.

### Historical V2 request

The `M2_SETUP_AUTHORIZATION_REQUEST_V2` bundle binds PR #16's actual merge,
design/access authority, candidate canonical-model identity, candidate export raw
hash, exact topology, 108 checks, probe fixtures and cleanup/containment specification.
Every component has a byte count and raw SHA-256; mixed snapshots or altered paths,
bytes, expectations or candidates fail validation. This is a new export, not a
rewrite of a historical request packet.

Every proposed directory, including `.access-probes` parents, is enumerated.
Pre-existing ancestors are `assert_existing`, not permission to create, reshare or
modify the research root. The observed existing `06_validation` is asserted;
the absent `m2_benchmark` and `annotation_runs` intermediate directories, as well as
new run/probe directories, are explicitly `create_new`. A list check
targets its resource directory and creates no file. A read check targets a known
coordinator-created object. A write check exclusively creates a known-absent probe
inside a verified existing parent. Cleanup is restricted to exact receipt-bound
synthetic files; research data and broad deletion remain excluded.

External-root identity, provider namespace, private account/role mappings, effective
groups, provider denial rules and private receipt destinations remain unresolved.
The bundle is a reviewable template, mechanically ineligible for execution or
decision-14 approval. Path/setup failures, missing objects, stale sessions, wrong
namespaces and network/client failures are INCONCLUSIVE, never denial PASS evidence.
Provider not-found counts as denial only under a separately reviewed concealment
rule with independently established object existence, exact target, and verified
account/session/namespace. The classifier tests this rule synthetically only.

Historical V2 run root: `06_validation/m2_benchmark/annotation_runs/m2-02-v1/`.
The generated plan includes all twelve approved resource folders and structural
ancestors, exact coordinator/A/B list/read/write outcomes, inheritance restrictions,
application controls and rollback conditions. Never share the root or any ancestor
with A/B. Grant only each reviewed leaf's exact effective access. Verify effective
group, link and inherited permissions, including pre-existing memberships.

If the actual Dropbox service/account model cannot support these permissions,
stop and report the capability gap; do not weaken the matrix or substitute a
filesystem ACL demonstration for actual account isolation.

REAL-EXTERNAL-WRITE-AUTHORIZATION requests only these six future operations:
reviewed folder creation, exact role permissions, minimal synthetic probe creation,
108 real-account checks, access receipts, and exact authorized probe cleanup.
It does **not** permit research-package issuance, human submissions, annotation,
locking, comparison, adjudication or gold. Approval of this proposal executes none.

After that separate approval, the coordinator creates the exact topology and
configures private role-bound accounts. The deterministic `.access-probes/`
fixtures contain only synthetic text, with exact byte hashes and per-check paths.
List checks require only the directory; read probes are prepared by coordinator.
Write probes must be absent before
the actor attempts exclusive creation. No research/human file is overwritten.

Run all 108 rows (3 roles × 12 resources × 3 operations), capturing private actor
binding, candidate pin, effective-permission evidence, outcome, timestamp,
probe-before/after hashes and cleanup receipt. Test the two coordinator application
immutability controls separately; they are not additional ACL rows or evidence
that a filesystem ACL alone ensures append-only publication.

All current rows are NOT RUN. A successful forbidden operation remains a failed
check: stop, preserve the receipt, contain the scoped grant, and do not issue any
package. No silent retries replacing failure evidence. Cleanup removes only exact
receipt-bound synthetic probes under separately authorized scope; never recursively
delete a parent or research data. Preserve immutable failure and cleanup evidence.
Only verified real outcomes can support REAL-AB-ACCESS-ISOLATION.

## Issuance and launch — separate decisions

Future issuance requires approved A/B eligibility, distinctness, scoped external
write authority, verified real isolation and exact environment approval. Verify
fresh protected-main authority and every package/reference/view/runtime/environment
pin against independently supplied authority, not receipt self-claims.

Under separately authorized issuance, A receives only the exact A neutral package
at A's issue path; B receives only B's. Never distribute coordinator wrappers,
partition labels or the other human's material. Each recipient independently
rehashes delivered bytes. Private receipts record recipient token, exclusive role,
delivery path, timestamp and complete composite identity. Jorge then decides
REAL-PACKAGE-ISSUANCE on verified delivery evidence, not on a proposed receipt.

ANNOTATION-LAUNCH additionally requires all six preceding decisions, exact fresh
protected-main authority, environment approval, issuance receipts and complete
identity alignment. The draft launch candidate cannot grant this authority.
Production launch and lock entry points remain closed. The future chain is launch
approval → human annotation → human completion → human lock request → coordinator
confirmation → immutable publication. No part of that chain executes here.

## Evidence and reproduction

The future sequence is: private eligible/distinct humans; scoped setup/testing
authorization; real account-isolation evidence; owner acceptance of isolation;
independent production-environment approval; separate prospective authorization of
exact issuance writes; verified role-specific delivery; decision 15 accepting actual
issuance evidence; decision 16 authorizing annotation. Acceptance of completed
delivery is not a prerequisite for requesting permission to perform delivery.
Setup-only permission never authorizes research-package issuance.

Live provider execution, private account binding, independently protected provisioning,
production issuance, annotation launch and production locking remain unimplemented
or closed pending separate technical and owner gates. Changing flags cannot make
this proposal executable. All seven operational responses remain null.

`uv run python scripts/prepare_m2_operational_plan.py SNAPSHOT` writes only a new
ignored `.cache/m2-02b2/SNAPSHOT/` proposal. Existing snapshots are never overwritten.
It creates no real authority, account, external directory, research package or
human record. Generated receipts explicitly describe plans rather than execution.
The seven-decision dossier separates questions, required/available/missing evidence,
dependencies, conditional recommendations, authority limits and containment.

Native candidate receipts, baseline/final CI, private-free synthetic results,
independent principal review and final artifact inventory are separate evidence.
Historical merged-main CI is not proof of the later implementation head. Final PR
delivery requires fresh full validation and exact-head Linux/Windows CI. No schema,
evaluator, critical-field, handbook, date, discovery, source/reference or original
package/view semantics are changed. Normative start-key scoring and M3 remain gated.
