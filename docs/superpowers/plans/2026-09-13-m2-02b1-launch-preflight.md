# M2-02B.1 Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development, with task-scoped review and final principal review.

**Goal:** Produce an isolated, source-neutral annotation-launch preflight candidate; never launch annotation.

**Architecture:** Reuse one neutral validation core through a deterministic allowlisted runtime. Keep partition routing, benchmark submission projection, approvals and external operations coordinator-only.

**Tech stack:** Python 3.12–3.13, Pydantic, pytest, uv, Ruff, Pyright; no new service or source acquisition.

**Spec:** `docs/superpowers/specs/2026-09-13-m2-02b1-launch-preflight-design.md`, approved by Jorge in this task.

## Global constraints

- Work only on `codex/m2-02b1-launch-preflight`, based on `995b54115f94454fc81d4af36f138add43ba8614`.
- No Dropbox writes, real people, attestations, issuance, annotation, gold, parser work, scoring amendment, or production locking.
- Frozen schemas, existing approvals, evaluator and M3 bytes must remain unchanged.
- Runtime must not expose partitions, coordinator/private data, model answers, or repository paths.
- All 16 future launch decisions remain null; all launch flags false; real access tests NOT RUN.
- Preserve every existing validation rule. No duplicate normative validator.
- Use invented fixtures and temporary directories. Record RED before implementation.
- Prefer one final implementation commit; workers must not commit, stage, push, or change branches.
- Record task progress and review evidence under ignored `.cache/m2-02b1/`.

## Task 1: Neutral draft validation core

**Files:** create `src/peru_conflicts/execution/neutral_forms.py`; modify `src/peru_conflicts/execution/annotation.py`; create `tests/unit/test_m2_neutral_forms.py`.

**Consumes:** Existing strict declarations, inventory, evidence, date-pair and inspection behavior.
**Produces:** `validate_neutral_forms(files, *, expected_package, require_complete=False) -> NeutralDraft`, returning neutral per-discovery field annotations/inventory, discoveries, unresolved rows, inspections and completeness, without partitions or benchmark submissions. Existing `validate_forms` remains the coordinator adapter and returns the same `ValidatedDraft` as before.

- [ ] RED: add a test which invokes the new neutral entry point on an invented blank package, checks `complete is False`, and rejects any serialized partition or submission field. Initially assert the entry point exists before calling it, so missing behavior produces an assertion failure.
- [ ] RED: add an invented complete zero-discovery case, a discovered case with explicit unresolved source values, and malformed/evidence/inspection cases; capture baseline coordinator outcomes before moving code.
- [ ] Extract neutral parsing/validation without duplicated rule bodies. Keep required field derivation authoritative and design its input so the later runtime can receive a pinned neutral field registry without repository reads.
- [ ] Preserve coordinator `validate_forms(files, partitions, *, expected_package, require_complete=False)` API and resulting benchmark payloads, hashes, IDs and completeness. It calls the shared core and constructs submissions afterward.
- [ ] GREEN: run `uv run pytest tests/unit/test_m2_neutral_forms.py tests/unit/test_m2_annotation.py tests/unit/test_m2_benchmark_alignment.py tests/unit/test_m2_date_correction.py tests/unit/test_m2_owner_readiness_approval.py`.
- [ ] Run Ruff and both Pyright targets for changed code. Write task report with exact RED/GREEN results. Independent task review before downstream integration.

## Task 2: Deterministic isolated runtime and custody

**Files:** create `src/peru_conflicts/execution/runtime_build.py`, `src/peru_conflicts/execution/runtime_cli.py`, `scripts/build_annotator_runtime.py`, `tests/unit/test_m2_isolated_runtime.py`; narrowly factor shared source definitions only if necessary.

**Consumes:** Task 1 neutral validation entry point and canonical neutral model definitions.
**Produces:** `build_runtime(output_root: Path) -> RuntimeManifest`; a deterministic file inventory and aggregate identity; isolated page/position/slots/inspection-template/validate commands.

- [ ] RED: execute a built runtime from a temporary directory with repository imports/config unavailable; require neutral commands to work and reject prohibited imports/data. Missing builder must first fail an explicit existence assertion.
- [ ] Create a versioned explicit source/dependency allowlist. Select canonical definitions without copying partition enums, coordinator models, evaluator, extraction commands, registry adjudication types, or repository config. Do not maintain alternate validation rule implementations.
- [ ] Pin the neutral field registry and validation dependencies at build time. Bundle verification takes trusted expected runtime, contract, package and issuance identities from outside the bundle; never infer authority from self-consistent contents.
- [ ] Reuse retained-handle path custody where applicable. Test traversal, symlinks/junctions, replacement, additional files, altered references/instructions/form headers, stale and self-consistent substituted packages/receipts.
- [ ] Expose only the five requested human functions; no extraction, lock, scoring, launch, machine discovery or search command.
- [ ] Test formula-looking text, leading zeros, explicit value types, date-looking strings, Unicode preservation and malformed CSV using literal expected outputs.
- [ ] Compare canonical and isolated acceptance/rejection and neutral output for every existing family, state, evidence type, incomplete/zero/unresolved case. Stop if scientifically equivalent isolation cannot be demonstrated safely.
- [ ] GREEN: run all new runtime and neutral-form tests plus existing M2 validation regressions on the current platform; ensure all new tests are platform-independent or exercise explicit cross-platform fail-closed behavior.

## Task 3: Draft launch contract and synthetic preflight

**Files:** create `src/peru_conflicts/execution/launch.py`, `config/benchmark/m2_02_launch_candidate_v1.yaml`, `tests/unit/test_m2_launch_preflight.py`.

**Consumes:** Verified merge/approval/readiness/evidence identities and Task 2 runtime identity.
**Produces:** Strict draft candidate, blank private eligibility binding template, typed access-test NOT RUN/PASS/FAIL receipts, and synthetic-only prerequisite evaluation. Existing production lock remains prohibited.

- [ ] RED: fail launch-without-owner-approval, access-test-NOT-RUN and production-lock-before-launch tests before adding candidate logic.
- [ ] Make candidate approval flags literal false. Bind exact runtime/package/reference and governing contract identities; malformed or stale identities fail before any operation.
- [ ] Model distinct-person/role eligibility and exact identity bindings without real PII fixtures. Reject same-human, wrong-role, cross-package and substituted-identity cases.
- [ ] Model the ordered future ceremony as prerequisite validation with no I/O issuer. Any missing/failed private attestation, real access check, external-write authority or launch authority must deny launch. Synthetic success is explicitly a rehearsal, never production authorization.
- [ ] Ensure existing `production_lock_preflight()` remains fail-closed and all old issuance tests pass.
- [ ] GREEN: run new launch tests and existing coordination, issuance and active-contract tests; independent task review.

## Task 4: Operational protocol and evidence generation

**Files:** create `docs/m2_02_annotation_launch_protocol.md`, `scripts/prepare_m2_launch_review.py`; update `docs/m2_02_coordinator_checklist.md`; add `tests/unit/test_m2_launch_review.py`. Only if required, update the Git data-policy guard and its tests.

**Consumes:** Tasks 1–3 manifests, receipts and strict candidate.
**Produces:** All user-required ignored `.cache/m2-02b1/` receipts, topology, runtime/package neutrality and equivalence evidence, JSON/Markdown 16-decision dossier and proposed PR body.

- [ ] RED: generate a review packet in a temporary root; assert all 16 responses are null, every real-account test NOT RUN, no real external path created, and hashes bind the supplied artifacts.
- [ ] Define exact coordinator/A/B/submission/locked/supersession/comparison/adjudication/sealed/receipt topology with least-privilege proposed access. Do not create or share any external area.
- [ ] State all launch and lock prerequisites, human/coordinator confirmations, immutable supersession and rejection behavior. Distinguish readiness, preparation, approval, issuance, start, lock, comparison, adjudication and gold.
- [ ] Dossier IDs: POSTMERGE-M2-02A-VERIFIED, ISOLATED-RUNTIME, RUNTIME-NEUTRALITY, EXTERNAL-TOPOLOGY, ELIGIBILITY-PROTOCOL, AB-ACCESS-TEST-PROTOCOL, HELDOUT-SEALING-LAUNCH-PROTOCOL, ISSUANCE-CEREMONY, PRODUCTION-LOCK-PRECONDITIONS, ANNOTATOR-A-ELIGIBILITY, ANNOTATOR-B-ELIGIBILITY, DISTINCT-HUMANS, REAL-AB-ACCESS-ISOLATION, REAL-EXTERNAL-WRITE-AUTHORIZATION, REAL-PACKAGE-ISSUANCE, ANNOTATION-LAUNCH.
- [ ] Each row contains question, required evidence, approval/rejection consequences, eligibility for this review stage, launch dependency and risk; last seven require unavailable real operational facts.
- [ ] Rehearse invented happy/negative paths; receipt success must come from executed tests, never a static claim. Record sizes and hashes for every final local artifact.
- [ ] GREEN: execute review generator tests and data-policy tests; independent task review.

## Task 5: Whole-branch validation, review and PR

**Files:** final ignored evidence receipts and PR metadata; no research data.

- [ ] Run new tests, all M2, benchmark, scientific/schema, repository-guard and acquisition groups, then full pytest with exact totals.
- [ ] Run `uv run ruff format --check .`, `uv run ruff check .`, both Pyright platforms, `uv run python scripts/export_schemas.py --check`, and `uv run python scripts/check_git_data_policy.py`; run staged-byte policy after explicit staging of expected files.
- [ ] Dispatch an independent principal review of the full change against the approved spec and original user instructions. Resolve every Critical/Important finding; report Minor findings.
- [ ] Reverify all frozen hashes and read-only Dropbox inventory/26 hashes/M1 package/M2 root absence.
- [ ] Commit once when practical: `Prepare M2-02 annotation launch preflight`. Push normally and open the new PR. Do not merge.
- [ ] Require fresh exact-head Linux 3.12/3.13 and Windows CI, inspect raw logs for all new tests, verify zero behind main, clean mergeability and zero unresolved threads.
- [ ] Populate final receipts and report M2_02B1_OWNER_LAUNCH_REVIEW_READY only after all gates pass. All real operational decisions remain unresolved.
