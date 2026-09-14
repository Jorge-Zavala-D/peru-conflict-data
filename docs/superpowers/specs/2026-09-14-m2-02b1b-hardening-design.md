# M2-02B.1b hardening design

Jorge approved these design choices in the task conversation. This is design approval only, not approval of any of the sixteen launch decisions.

## Scope and authority

Continue PR #16 on codex/m2-02b1-launch-preflight from 109c40be0aac44d87d6e0e5471cecb4e57ed84c2. Main stays 995b54115f94454fc81d4af36f138add43ba8614. One further commit, no amend/force push/merge. Frozen scientific, benchmark, metric, critical-field, reference, package and M2-02A approval authority is unchanged. No real account test, human assignment, attestation, issuance, annotation, production lock, gold, parser/M3 work, acquisition or Dropbox write is authorized. All sixteen launch responses remain null.

## Access design approved by Jorge

Use private account-scoped read/write draft workspaces, not public upload-only file requests. Each annotator can list/read/write only their own draft area. Their issued package area permits list/read but denies write. All three operations are denied on the other annotator's areas and on every coordinator-only area. The coordinator has the operational list/read/write permissions necessary to provision and receive materials. Coordinator preservation of accepted bytes is an application/provenance control, not a fictional owner ACL denial.

A typed actor/resource/operation/expected-outcome/control-layer/rationale policy is the single source of truth. Outcomes distinguish ALLOW, DENY and APPLICATION_CONTROLLED. Derive real-account tests only from ACL rows; do not treat a hash check as proof of an enforceable denied write. Preserve the complete historical v1 matrix, introduce m2-02-real-access-tests-v2, and derive counts rather than fixing a target count. No real result other than NOT RUN is representable in this draft workflow.

Read-only connector capability inspection establishes that its view-link interface cannot grant edit access, and that file requests expose upload URLs without granting destination browse access. Neither establishes the actual future account ACLs. Actual account capabilities/provisioning remain unresolved launch facts. Private account-scoped folder semantics are the approved design requirement; inability to enforce them must block future launch, not silently substitute public bearer upload links.

## Python environment design approved by Jorge

Create a versioned path-neutral manifest for the exact Python implementation/version/build/platform/architecture, interpreter, complete approved stdlib file set (including archives), extension modules, bundled native runtime libraries, and separate third-party dependency identity. Exclude caches and site-packages, never inventory unrelated user packages, and explicitly document the OS/system-library trust root. Use deterministic relative logical paths and exact bytes; do not place usernames/private absolute paths in identities.

Bind the aggregate environment identity into RuntimeManifest, LaunchIdentity, both A/B identities, the draft LaunchCandidate, unissued rehearsal receipts and review evidence. Different stdlib with identical interpreter/dependencies must change identity and invalidate old bindings. Both annotators require the same environment unless a separately approved equivalence contract exists.

Future production requires independent pre-execution provisioning and verification by a separately trusted mechanism. Running Python to hash its own already-used stdlib cannot bootstrap that trust. The -I -S -B launcher performs consistency checks against independently supplied pins only. Generate a rehearsal manifest from the current test installation; do not claim production provisioning or approval. Draft rehearsal identity is not a production-approved environment.

## Testing, evidence and cleanup

Capture RED before each behavior change: missing own-issued/foreign/coordinator write denials, and same interpreter/dependencies with unbound stdlib. Preserve all earlier safety tests. Add stale/substituted environment, receipt and cross-role mismatch rejection. Use invented temporary fixtures only. Renew runtime/candidate/evidence deterministically under .cache/m2-02b1b without overwriting .cache/m2-02b1.

The only deletable real paths are the two previously disclosed disposable temporary rehearsal copies, after exact inventory, blankness/custody-independence verification and pre-deletion receipt. Uncertainty or an environment denial means CLEANUP_DEFERRED_SAFELY; no bypass. This does not authorize deletion of authoritative evidence or Dropbox material.

Full local quality, independent principal review with zero Critical/Important findings and new exact-head Linux/Windows CI are required before M2_02B1_OWNER_LAUNCH_DESIGN_REVIEW_READY_AFTER_HARDENING.
