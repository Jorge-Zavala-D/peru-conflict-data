# M2-02B.1 isolated launch-preflight design

Status: DESIGN OWNER-APPROVED by Jorge; implementation authorized, not annotation
launch or additional scientific approval.

This approves implementation of this design only. It does not resolve any of the
16 future owner-launch dossier decisions, which remain null pending their own
evidence-based review.

## Verified starting point

PR #15 restored the owner-approved M2-02A tree through merge commit
`995b54115f94454fc81d4af36f138add43ba8614`, with parents
`cffe543c85738266c9bdd71bd011c5fe329d5481` and
`2ab5eb92d4c732d73a198e3b64690a7356f0ac2b`.
Its tree is `67284c356125d4f9758dc28a9e6c92a45cab3553`, exactly the
approved PR #13 tree. The original feature branch remains intact.
Protected-main push run `34747429249` passed all three required jobs.
The earlier PR #13 squash ancestry was explicitly accepted by Jorge; the
subsequent accidental revert and recovery are retained, not rewritten.

Owner readiness remains approved. Annotation launch, production locking,
human gold, parser work, normative start-key scoring, M3 approval, real
human assignment, and Dropbox execution writes remain unauthorized.

## Owner-approved architectural decision

Extract a shared source-neutral validation core from existing execution
helpers, keeping coordinator routing and benchmark-submission construction
outside the annotator runtime. Build a deterministic allowlisted bundle
from that core. Both repository-side and isolated callers use the same
validation implementation; there is no separately maintained scientific
validator.

The existing `readiness_cli.py` imports `PartitionRole` and coordinator
issuance models. Its current validation call supplies a placeholder
partition and constructs benchmark submissions internally. Therefore it
cannot simply be copied, with its transitive imports, into the human bundle.

Alternatives considered:

- Copy the full Python package: minimal refactoring, but exposes coordinator,
  partition, and evaluator material. Rejected as incompatible with blinding.
- Reimplement validation in a separate runtime: easier packaging, but creates
  scientific divergence risk. Rejected.
- Shared neutral core plus coordinator adapter: recommended; requires a
  reviewed refactor and equivalence tests, but preserves a single source of
  validation rules without distributing coordinator information.

## Component boundaries

1. Neutral core: strict CSV reading, declaration/instance coverage, source
   positions, typed evidence, source-value/date-pair validation, and explicit
   inspection completeness. It receives verified neutral inputs and returns
   neutral draft validation results. It performs no routing, locking,
   adjudication, evaluation, or source-answer inference.
2. Coordinator adapter: assigns the fixed private partition and constructs
   existing benchmark submissions after neutral validation. Frozen schemas,
   approved keys, metric behavior, and evaluator bytes remain unchanged.
3. Bundle builder: selects explicit files and dependencies, rejects unexpected
   imports/files, records every byte hash and an aggregate identity. It copies
   neither Git metadata nor repository config into the annotator artifact.
4. Isolated entry point: runs without repository access, checks externally
   supplied trusted runtime/package/issuance identities, then exposes only
   page viewing, human-selected position conversion, empty slots, inspection
   templates, and draft validation. No production lock or launch command.
5. Coordinator launch preflight: evaluates proposed bindings and prerequisites
   without performing issuance, account operations, or external writes.

## Authority and integrity

Build-time authority comes from the verified protected-main readiness
contract. Runtime trust must not come solely from a self-reported package or
manifest: expected identities are separately supplied by the future approved
issuance ceremony. A self-consistent substituted bundle/package/receipt must
fail against those trusted expected identities.

The isolated runtime must not consult repository configuration after build.
Its allowlisted contract material contains only neutral validation inputs;
coordinator documents are bound by digest, not copied into the human bundle.
Validation errors and successful output must not disclose benchmark roles.

Package/reference reads retain strict path and retained-handle custody checks.
Reject traversal, aliases, symlinks/junctions, replacement races, extra files,
modified reference bytes, modified instructions and blank-form headers.
CSV values remain text unless the human explicitly selected a value type;
no formula evaluation, inferred dates, leading-zero coercion, or implicit
Unicode normalization is permitted.

## Launch candidate and private operational design

Create a new draft launch candidate, not a new approval. All launch, real-human,
attestation, external-root, external-write, access-pass, issuance, annotation,
locking, gold, parser, and M3 flags remain false. Bind the verified merge,
readiness/approval/evidence, schemas, metric, critical fields, references,
packages, and proposed runtime identities without circular commit provenance.

Prepare blank private eligibility templates with role, distinct-human,
machine-answer exposure, cross-human exposure, benchmark-role blinding,
and exact run/package/reference/runtime bindings. No person is assigned.
Real-account permission tests retain NOT RUN, PASS, and FAIL as distinct
states; every real test remains NOT RUN in this task.

Propose separate coordinator, A/B issue and submission, immutable lock,
supersession, comparison, adjudication, held-out sealing, and receipt areas
under the user-specified external root. Generate an ignored topology manifest
only; create no Dropbox directory, share, link, or invitation.

The future ceremony requires approved launch authority, exact runtime and
package custody, two eligible distinct humans, successful real-account
isolation, explicit external-write authority, exact issuance and byte
verification before annotation can start. Production lock has its own later
human/coordinator confirmation and validated-completeness requirements.

## Evidence and tests

Use RED-first negative tests for runtime leakage, stale runtime/package
authority, launch without approval, access tests NOT RUN, and prelaunch lock.
Test positive synthetic counterparts and the complete adversarial list in
Jorge's M2-02B.1 instructions. Never use real humans or completed real forms.

Before refactoring, retain baseline synthetic acceptance/rejection results.
Compare the old coordinator validation behavior with the refactored shared
core and coordinator adapter, then compare repository and isolated execution
over the same synthetic cases. Include every approved family, state, typed
evidence form, date pair, boundary disagreement, unresolved discovery, and
inspection-completeness outcome. No validation rule may be weakened to package
the runtime. Stop with BLOCKED_ISOLATED_RUNTIME_DESIGN if equivalent isolation
cannot be achieved safely.

Scan semantic data locations, import closure, manifests, emitted diagnostics,
and full file inventory for prohibited disclosure; avoid treating ordinary
safety prose as an answer leak. Test the bundle in a clean directory with
repository access unavailable. Run Windows and Linux safety/equivalence tests.

Generate the requested ignored evidence receipts and 16-question owner dossier;
every owner response remains null. The first nine concern technical/design
review; the final seven require real operational facts unavailable here.

## Delivery gate

Run all requested focused/full tests and quality checks, an independent
principal review with zero Critical/Important findings, and fresh exact-head
PR CI. Keep original authority, historical schemas, evaluator, and M3 gate
byte-identical. Verify zero behind main and unchanged external inventory.

Only then report M2_02B1_OWNER_LAUNCH_REVIEW_READY. Do not merge the new PR,
claim launch approval, assign humans, issue packages, or create human gold.

Implementation is authorized. This design does not substitute for the
future unresolved owner-launch dossier or private operational approvals.
