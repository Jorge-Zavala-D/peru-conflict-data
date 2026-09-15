# M2-02 annotation launch protocol

This is a coordinator-only preparation protocol for `m2-02-v1`. It is not an
annotator handout and grants no launch, external-write, issuance, or lock authority.
The launch-design candidate v2 is owner-approved for design only: nine technical/design
decisions are approved and seven operational launch decisions remain unresolved/null.
The approval is recorded in `config/benchmark/m2_02b1_launch_design_approval_v1.yaml`;
`config/benchmark/m2_02_launch_candidate_v2.yaml` binds its exact bytes and preserves
the reviewed v1 candidate unchanged. Design approval is not annotation launch approval.
All 108 mechanically derived v2 ACL checks remain `NOT RUN`. The complete
54-row v1 matrix remains immutable historical evidence, not the active protocol.
No private person identity, contact detail, exposure history, or actual attestation
belongs in Git.

## Authority and separate gates

Owner readiness v3 and evidence index v5 establish the reviewed M2-02A content
baseline: scientific schema v0.3.1 and benchmark metric v0.1.1. The accepted
recovery is PR15 merge `995b54115f94454fc81d4af36f138add43ba8614`, tree
`67284c356125d4f9758dc28a9e6c92a45cab3553`, with parents
`cffe543c85738266c9bdd71bd011c5fe329d5481` and
`2ab5eb92d4c732d73a198e3b64690a7356f0ac2b`. Jorge accepted the earlier PR13
squash ancestry; its reviewed head `8a8709d2c7f755922da5acb17bbfd73d3ba0105f`
remains a separate substantive readiness identity. Postmerge run `34747429249`
is historical protected-main evidence, not final M2-02B.1 branch CI.

| Gate | Meaning and required evidence |
| --- | --- |
| Owner readiness | Approval of the exact M2-02A content and its frozen custody; no launch authority. |
| Launch preparation | Tested runtime, candidate, protocols and unresolved owner dossier; no operational execution. |
| Launch approval | A separate reviewed owner record on protected main, binding the exact run and operational scope. |
| Package issuance | Actual delivery to the privately verified role recipient, with exact eligibility, original issuance and derived/runtime custody evidence. |
| Annotation start | Explicit start recorded only after the ordered ceremony and independently verified delivery. |
| Locking | A later separately enabled boundary requiring full validation and independent human/coordinator confirmations. |
| Comparison | Coordinator-only comparison after both current valid immutable locks; retain unresolved and unmatched observations. |
| Adjudication | Separately authorized, append-only evidence-based decisions; never editing earlier locks in place. |
| Gold creation | A later separately approved, versioned artifact with full provenance; preparation, comparison and adjudication are not gold. |

`production_launch_preflight()` and the existing `production_lock_preflight()`
continue to reject real operation. Passing synthetic tests does not change those
boundaries. Parser work, normative start-key scoring amendments and M3 remain
separately unapproved.

## Exact package and runtime custody

The original package ID, original `PACKAGE_MANIFEST.json` SHA-256, reference
aggregate and file inventories preserve their original meanings. A neutral
human view is a distinct immutable derivative with its own `NEUTRAL_VIEW.json`,
aggregate and complete file-set identity. It retains the original manifest and
references. Its neutral date-pair document removes only the reviewed attribution
preface and preserves the normative suffix; its form guide preserves the
normative CSV instructions. Never relabel a derived-view digest as the original
package digest or reuse an old package receipt as derived-view authority.

The composite identity binds original package/manifest/reference/contract,
neutral view and file set, runtime and file set, field registry, contract,
launcher, interpreter, dependency inventory and complete Python environment
manifest/aggregate. The candidate YAML byte SHA and
canonical-model SHA are different pins. Neither a candidate nor a self-consistent
replacement receipt supplies its own authority: expected pins must arrive from
independently trusted coordinator custody.

The runtime source is selected from canonical validators under a reviewed policy.
It has no repository discovery, local package install, `PYTHONPATH` bootstrap,
partition routing, owner approval, or scoring dependency. The separately trusted
launcher validates captured bytes before importing the verified dependency and
runtime closure. Package edits invalidate their pinned inventory.

For the currently supported **unissued local rehearsal only**, an independently
provisioned base interpreter runs a separately trusted launcher outside the
repository with `-I -S -B`. The runtime directory, copied allowlisted dependencies,
neutral package directory and unissued receipt are also external to the repository
in a temporary rehearsal directory. The invocation shape is:

```text
<independently-trusted-python.exe> -I -S -B <trusted-root>/launcher.py
  --runtime <runtime-root> --dependencies <dependency-root>
  --package <neutral-view-root> --issuance <trusted-root>/unissued-binding.json
  --runtime-sha256 <runtime-aggregate> --dependency-sha256 <dependency-inventory>
  --launcher-sha256 <launcher-bytes> --interpreter-sha256 <base-interpreter-bytes>
  --python-environment-sha256 <environment-aggregate>
  --python-environment-manifest-sha256 <environment-manifest-bytes>
  --view-sha256 <view-aggregate> --package-sha256 <original-manifest-bytes>
  --contract-sha256 <contract-bytes> --issuance-sha256 <independent-receipt-bytes>
  --role annotator-a validate
```

The line breaks above are explanatory; pass these arguments as a single command
or an argument array. Commands are `page`, `position`, `slots`,
`inspection-template` and `validate`; `validate --require-complete` requires actual
complete inspection and resolved or explicitly unresolved slots. A successful
validation of blank real-source views has zero discoveries/records and remains
incomplete. It is structural compatibility, not annotation or human rehearsal.

The required `PythonEnvironmentTrustManifest` is path-neutral rehearsal evidence.
It binds CPython's exact version/build/compiler, platform, machine architecture,
pointer width and ABI, interpreter bytes, the complete pure stdlib, available
Python zip archives, extension modules and distribution runtime files. Windows
inventory covers `Lib`, `DLLs`, Tcl runtime when present, and root DLL/executable
files. Supported Linux installations have a dedicated CPython distribution
prefix, such as the CI setup-python installation. Inventory covers the configured
stdlib including `lib-dynload`, Python executables/archives, every distribution
shared object under `lib`/`lib64` (including multiarch and private subdirectories),
and bundled Tcl/Tk runtime data. Internal file symlink targets are explicitly
bound. Shared system prefixes such as `/usr` and `/usr/local`, external link
targets, and aliased native runtime directories fail closed; they are not
supported installation layouts. These checks do not assert that an arbitrary
custom prefix is independently approved or owned by the distribution; that
requires the separate pre-execution provisioning review. Windows dedicated layouts
fail closed on any `._pth` entry (including `python._pth` and versioned
`python313._pth`) in the distribution root or interpreter directory, and on
`pyvenv.cfg` in either directory or its immediate parent. These bounded startup
configuration checks do not establish trust in inputs Python already consumed.
Bytecode/cache directories,
`site-packages`, `dist-packages` and user packages are excluded; the separately
allowlisted dependency inventory remains independently pinned. External OS
loaders, kernels, linked system libraries and hardware form an explicit separate
trust boundary. The manifest contains no installation root or private absolute
paths. Both annotators must have identical environment identities; no environment
equivalence contract is approved. Changed stdlib bytes with unchanged interpreter
and dependency bytes invalidate the environment and all earlier bindings.

An executable copied from an untrusted package cannot establish its own trust by
checking its own hash. The launcher, interpreter and expected pins therefore need
separately reviewed custody before execution. A repository development interpreter
or repository launcher path is not the independent operational trust root.
Before any future production invocation, a separately trusted mechanism must
independently authenticate and provision the interpreter, stdlib, native runtime,
launcher and dependencies, then protect their custody throughout execution.
The running Python process has already used stdlib modules before it can hash
them: its checks cannot authenticate those loaded modules, establish this trust
root, or prevent later environment mutation. `-I -S -B` and the launcher's
captured-byte checks provide in-process consistency against separately supplied
pins only. `-B` prevents bytecode writes, not bytecode reads. Because `.pyc` files
and `__pycache__` remain excluded, future independently trusted pre-execution
provisioning must remove or reject caches, or independently validate their
derivation from the pinned source bytes, before Python starts. This rehearsal
does not implement that production mechanism. The same stdlib-only
inventory/validation policy is used by the
builder and from runtime-pinned captured bytes by the launcher, with no
repository fallback. All generated manifests have `production_approved: false`;
self-consistent rehearsal hashes never constitute production provisioning or
launch approval. This change implements no production provisioning mechanism.
`UNISSUED_RUNTIME_REHEARSAL` is currently the supported receipt kind. The CLI's
`--issuance` argument name does not turn that receipt into real issuance. Future
private provisioning and support for real launch-authorized runtime bindings need
separate review, owner authorization and account testing. Do not provision them
or invent real issuance receipts during M2-02B.1.

## Proposed external areas and least privilege

All paths below are relative to the proposed root
`06_validation/m2_benchmark/annotation_runs/m2-02-v1`. The area paths are unchanged;
the approved access semantics are hardened. These are proposed paths, not directories
to create in this task.

| Area | Annotator A ACL | Annotator B ACL | Coordinator ACL / purpose |
| --- | --- | --- | --- |
| `coordinator/custody` | Deny list/read/write | Deny list/read/write | Allow list/read/write; source, authority and private eligibility custody |
| `annotator-a/issue` | Allow list/read; deny write | Deny list/read/write | Allow list/read/write; verified A delivery |
| `annotator-a/submission` | Allow list/read/write in private account-scoped draft workspace | Deny list/read/write | Allow list/read/write; receive A independently |
| `annotator-b/issue` | Deny list/read/write | Allow list/read; deny write | Allow list/read/write; verified B delivery |
| `annotator-b/submission` | Deny list/read/write | Allow list/read/write in private account-scoped draft workspace | Allow list/read/write; receive B independently |
| `coordinator/locked/annotator-a` | Deny list/read/write | Deny list/read/write | Allow list/read/write; application hash control preserves accepted A bytes |
| `coordinator/locked/annotator-b` | Deny list/read/write | Deny list/read/write | Allow list/read/write; application hash control preserves accepted B bytes |
| `coordinator/supersession` | Deny list/read/write | Deny list/read/write | Allow list/read/write; single-parent replacement lineage |
| `coordinator/comparison` | Deny list/read/write | Deny list/read/write | Allow list/read/write; compare only after both valid locks |
| `coordinator/adjudication` | Deny list/read/write | Deny list/read/write | Allow list/read/write; later M2-03 only |
| `coordinator/held-out-sealed` | Deny list/read/write | Deny list/read/write | Allow list/read/write; private benchmark-role routing/results |
| `coordinator/receipts` | Deny list/read/write | Deny list/read/write | Allow list/read/write; authority, access, eligibility, issuance and lock receipts |

The coordinator owns all areas and must be able to list/read/write where necessary
to provision and receive materials. Never share the run root or a coordinator
ancestor with either annotator. Inspect inherited group membership, existing shares and old links;
path separation alone is not access isolation. Use only role-specific grants.
Coordinator write permission is operationally required. Accepted bytes are instead
hash-controlled and superseded append-only by the application/provenance layer;
that rule is not an ACL denial. A public upload-only file request is not a substitute
for the required private account-scoped list/read/write draft workspace. A view-only
link interface cannot grant edit access, while a file-request upload URL does not
grant destination browse access; neither proves future account ACLs. If the required
private semantics cannot be enforced, launch is blocked. No links, invitations,
uploads, directories or sharing changes are authorized by this proposal.

## Future private eligibility and real-account tests

Privately identify two distinct human persons, assign one role each, and verify
identity beyond different account names or tokens. Each must attest that they have
not seen the other annotator's work, machine-generated source answers or prefill,
parser predictions, held-out labels or partition assignments, and that they will
not use Codex, ChatGPT or another model as annotator. Bind attestation, role,
exposure history and timestamp to the exact run/original package/reference/view/
runtime/contract composite. Keep real names, contacts and exposure histories in
private coordinator custody. Blank templates are not attestations.

After separately authorized private provisioning, perform every ACL row derived from
the typed `m2-02-real-access-tests-v2` policy (currently 108 rows) from
`launch_access_test_protocol_receipt.json` using the **actual accounts**. For each
check record private account identity, time, exact actor/operation/resource,
expected uppercase `ALLOW` or `DENY` outcome, control layer, unique rationale ID,
and independently reviewable observation evidence. Use a harmless separately
authorized test file for each own-submission write. Test A/B list/read on each own
issued area and list/read/write in each own private draft workspace; deny own-issued
writes. Deny all three operations on the other annotator's issue/submission and every
coordinator-only area. Test coordinator list/read/write wherever operationally
needed. Inspect that distributed content has no partition
metadata or prohibited machine aids in addition to these permission probes.

`PASS` means the specified outcome was actually observed: a denied-read check
passes only when reading was denied. `FAIL` means a different outcome. `NOT RUN`
means no valid real-account observation exists. Missing, failed, stale, duplicate
or substituted checks block issuance. The current real receipt model accepts
only `NOT RUN`; recording real outcomes requires separately reviewed launch
support. Synthetic PASS/FAIL receipts must retain their synthetic kind.

## Future issuance and annotation start

The ordered ceremony must fail closed. Verify protected-main launch authority;
exact runtime; exact A/B original and derived manifests; references; the two
private eligibility attestations; distinct persons; all real access tests;
explicit external-write authorization; exact external paths and permissions;
role-specific eligibility bindings; role-specific original issuance receipts and
the separately reviewed derived/runtime bindings. Then deliver A only to A and B
only to B, independently verify the delivered bytes, record recipient and issue
timestamp, and only then record annotation start. External-write authority must
precede any external operation, including account-test uploads and provisioning.
Authorization to design a topology is insufficient for that preparation.

Any failure leaves launch false. Do not reuse stale pins or silently replace
records. The synthetic ceremony asserts invented prerequisites and remains
`SYNTHETIC_REHEARSAL_ONLY`, including its success case. Its original synthetic
issuance receipts and runtime rehearsal receipt bytes are independently pinned;
neither is evidence of real issuance. No real step is executed in M2-02B.1.

## Later lock, supersession and held-out sealing

A future lock requires separate owner launch authority, valid actual human
eligibility and access pair, exact original and derived/runtime issuance custody,
validated submission, full page/family inspection and every declared required
slot resolved or explicitly unresolved. Unknown remains null, never zero. The
human explicitly confirms this lock and the coordinator separately confirms it.
Incomplete or invalid writes leave prior accepted locks intact. A correction must
name the current immutable parent, retain its predecessor and evidence, and append
a new version. Reject stale parents, missing parents, duplicate/conflicting heads,
forks or ambiguous supersession; never choose a branch silently or overwrite a
prior lock. Current production locking remains disabled even for otherwise valid
synthetic custody.

The coordinator compares only the two current valid locks, retaining A-only,
B-only and unresolved observations. Adjudication is a later append-only decision
process; canonical data is never edited directly. Gold creation and release need
their own later authority and provenance checks.

Coordinator-only fixed routing remains pilots 264/269, parser development
260/262/266/268, held-out evaluation 261/263/265/267. Humans receive source report
identifiers but no partition roles. Keep this protocol, routing, comparisons,
adjudications and sealed held-out results out of human issue areas and runtime.
Held-out labels must not enter parser-development workflows.

## Generate and complete a review snapshot

The following generator documents historical pre-approval v1 review packets.
Those immutable packets correctly retain sixteen null responses. The current
design-approved successor is candidate v2 and its separate M2-02B.1c approval;
it does not rewrite or retroactively approve the historical dossier. Exactly nine
design decisions are approved, and exactly seven operational decisions remain null.

`uv run python scripts/prepare_m2_launch_review.py <inputs.json> <new-snapshot-name>`
is a **coordinator development** command. It writes exclusively beneath the
repository's ignored `.cache/m2-02b1/<new-snapshot-name>/`. Existing snapshots and
supplied evidence remain unchanged. The inputs JSON supplies independent
`{path, sha256}` pins for `candidate`, `runtime`, and the ordered A/B `views`, plus
`candidate_model_sha256` and named `evidence` receipts. The generator reads strict
models, validates candidate/current governing bytes and composite alignment,
captures supplied receipts and records every input/output byte count and SHA-256.
It does not re-attest a supplied receipt's substantive claims.

Optional `raw_evidence` maps safe filenames to the same `{path, sha256}` pins;
JUnit XML, raw command output and detailed CI observations are preserved unchanged
under the snapshot's `raw_evidence/` directory and included in the byte inventory.

Each snapshot includes the requested receipts, typed topology, all v2 ACL rows as
NOT RUN tests, the policy version and identity, separately typed application controls,
blank private eligibility template, JSON/Markdown 16-decision dossier, proposed
PR body, final packet and a non-circular `SHA256SUMS.txt`. Missing stages have
explicit `NOT RUN` placeholders. The first nine dossier items can be technical
owner review decisions during M2-02B.1; the remaining seven require unavailable
real operational facts. Every response remains null in every generated snapshot.

After actual final measurements, `--require-complete` requires all named receipts
and strict `completion_gates.json`: nonempty source file/hash inventory; independent
source-snapshot, final-head and merge-ref pins in the input manifest; all 13
measured check groups; positive pytest counts, zero failures and zero skipped new
M2 safety tests; independent review at that source snapshot with Critical 0 and
Important 0 plus recorded Minor dispositions; and success of all three required
CI contexts at that final head/merge reference. Source bytes are checked again.
Keep the detailed CI receipt with actual platform/Python versions, per-job counts,
raw job/step evidence and the exact head/tree separate from the historical
protected-main receipt. The normalized completion gate is not an approval record
and cannot infer trustworthy observations from a bare `PASS` field.

The 13 check IDs are `new_m2`, `all_m2`, `benchmark`, `scientific`,
`guards_acquisition`, `full_pytest`, `ruff_format`, `ruff_lint`, `pyright_windows`,
`pyright_linux`, `schema_drift`, `data_policy` and `staged_byte_policy`. Full-suite
known skips are documented separately; they cannot excuse skipped new safety
tests. Tests/review bind ordered source content independently of a Git commit;
final CI additionally binds the final head and merge reference. Any changed
reviewed source requires appropriately refreshed evidence. Even a complete
packet remains review preparation: owner launch responses and all real operational
flags remain unresolved/false.

### Technical-stage completion receipts

Ordinary preparation continues to preserve historical receipts as supplied, without
re-attesting them. Complete mode requires ten distinct normalized technical-stage
receipts: the nine named historical/runtime/review receipts plus a separate
`final_ci_receipt.json`. A normalized receipt is an explicit derivation from captured
measurements; changing its label cannot cure a missing or contradictory observation.
Never overwrite the original receipts. Place original bytes under `raw_evidence`
and bind them in the normalized receipt using this exact envelope:

```json
{
  "kind": "M2_02B1_MEASURED_TECHNICAL_STAGE",
  "stage": "principal_review_receipt.json",
  "status": "MEASURED_PASS",
  "bindings": {},
  "observations": {},
  "sources": {
    "observation": {
      "artifact": "raw_evidence/original-principal-review.json",
      "sha256": "<independently recorded SHA-256 of those original bytes>"
    }
  }
}
```

`stage` must equal its actual named receipt. All envelopes bind the candidate's
exact `protected_main_merge_sha`, `protected_main_merge_tree`, `readiness_v3_sha256`,
`evidence_v5_sha256` and `reference_manifest_sha256`. Runtime neutrality, equivalence
and synthetic rehearsal additionally bind `source_snapshot_sha256`, `runtime_sha256`
and the ordered A/B `view_sha256s`. Principal review and final CI additionally bind
`source_snapshot_sha256`. No extra or omitted binding/observation fields are accepted.

The `sources.observation` artifact must be separately captured raw JSON with its
matching hash. Dropbox additionally requires `sources.baseline`, a separately
captured original readonly inventory and hash. The following exact observation
objects are derived and checked against their underlying raw records:

| Technical stage | Normalized observations and required raw evidence |
| --- | --- |
| `postmerge_verification_receipt.json` | `merge_verified: true`; raw historical receipt must identify the candidate merge/tree, both accepted recovery parents, recovery PR15, preserved original feature and `POSTMERGE_VERIFIED_DESIGN_REVIEW_PENDING` checkpoint. This historical checkpoint is not a claim that final implementation review is pending or complete. |
| `protected_main_ci_receipt.json` | `required_contexts`: sorted three required context names, `conclusion: success`; raw run must be completed/success at the historical candidate merge and contain exactly those successful jobs. |
| `ruleset_receipt.json` | `ruleset_id: 21658925`, `protected_main_enforced: true`; raw ruleset must include main with no exclusions, have no bypass actors, prevent deletion/non-fast-forward, require resolved review threads and all three strict required contexts. |
| `owner_readiness_custody_receipt.json` | `owner_readiness_approved: true`, `annotation_launch_approved: false`; raw custody must also match merge/tree/readiness/evidence pins and the contract's owner-readiness approval SHA. |
| Each of the three runtime/equivalence/synthetic-rehearsal receipts | `synthetic_test_coverage_passed: true`, `real_annotation_performed: false`; raw `MEASURED_LOCAL_TEST_EXECUTION` must have exit 0, positive passed count, zero skips, no annotation/issuance/gold, applicable test command and source/test hashes matching the completion inventory. This supports synthetic test coverage, not real annotation or actual-account tests. |
| `dropbox_readonly_receipt.json` | `dropbox_writes: 0`, `m2_external_root_absent: true`, `preserved_baseline_files`: original inventory count; raw observation must report zero writes/absent root and preserve every original path/hash in the separately pinned baseline. |
| `principal_review_receipt.json` | Exact `completion_gates.review` object; raw JSON must have `kind: MEASURED_INDEPENDENT_PRINCIPAL_REVIEW` and an identical `review` object. Preserve the underlying independent review report as additional raw evidence. |
| `final_ci_receipt.json` | Exact `completion_gates.ci` object; raw JSON must have `kind: MEASURED_FINAL_BRANCH_CI` and an identical `ci` object. Preserve detailed platform/Python/job/count observations alongside it. It must not substitute the historical main run. |

Runtime test evidence must hash the measured `runtime_build.py`, `runtime_cli.py`,
`neutral_forms.py` and `test_m2_isolated_runtime.py`; synthetic launch additionally
requires measured `launch.py` and instead the applicable `test_m2_launch_preflight.py`
command/test hash. Every file listed in that measured receipt must match the final
source inventory. Applicable unchanged earlier measurements can therefore retain
their actual scope without being mislabeled a fresh final run.

An underlying `NOT RUN`, failed outcome, stale identity, missing file, substituted
summary, or mismatch with normalized observations rejects technical completion even
when all input hashes have been refreshed. All derived v2 **operational** ACL rows remain
NOT RUN and the 16 owner responses remain null; they must never be changed to satisfy
these technical checks. This validates consistency of pinned local records, not
remote authentication or the truthfulness of an invented observation. Actual
measurement, independent review and owner authority remain separate responsibilities.

### M2-02B.1b hardening evidence renewal

Use `scripts/prepare_m2_launch_review.py INPUTS NEW_SNAPSHOT --cache-namespace m2-02b1b`
for hardening snapshots. Only `m2-02b1` and `m2-02b1b` are accepted namespaces;
the historical default remains available to reproduce the prior review workflow.
All snapshots remain append-only. Historical `.cache/m2-02b1` receipts, original
A/B packages and existing neutral views are preserved. Pin the historical packet
as raw evidence to distinguish its commit, runtime and CI from the renewed review.

Hardening mode requires three additional receipts before `--require-complete`
can succeed: `access_policy_v2_receipt.json`,
`python_environment_trust_receipt.json`, and `runtime_identity_receipt.json`.
`hardening_receipt_documents(candidate, runtime)` derives their exact expected
content from the current strict candidate and measured rehearsal runtime. The
policy receipt binds the full v2 policy and derived ACL count with zero executed
real-account checks. The environment receipt binds both environment hashes and
the complete inventory, retains `production_approved: false`, and records
independent provisioning and external OS/system-library trust as NOT RUN.
The runtime receipt binds the ordered A/B composite identities and policy.
Supplied stale or substituted receipts fail even when preparing an incomplete
snapshot; missing receipts are explicit NOT RUN placeholders. A hash refresh
alone cannot make old policy or environment content current.

An initial hardening packet has `hardening_review_status: INCOMPLETE`.
Only validated current local gates, independent principal review, exact final-head
Linux/Windows CI and all required technical and hardening receipts can yield
`M2_02B1_OWNER_LAUNCH_DESIGN_REVIEW_READY_AFTER_HARDENING`. That technical status
still leaves every launch flag false, all sixteen owner responses null and all
real-account ACL checks NOT RUN. The measured rehearsal distribution is not an
approved production environment. Decision 6 presents v2 access evidence for
later owner review; it does not choose or approve that decision. Before any future
production invocation, a separately trusted mechanism must independently verify
the pinned Python installation before execution and protect its custody throughout
execution; the launcher's consistency check cannot authenticate already used stdlib.
