"""Coordinator-only, append-only launch review packets; never launch authority."""

import json
import re
from contextlib import ExitStack
from pathlib import Path
from typing import Annotated, Any, Literal, cast

import yaml
from pydantic import Field

from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.models.common import Sha256, StrictModel

from .launch import (
    ACCESS_POLICY_V2,
    ACCESS_POLICY_V2_SHA256,
    CEREMONY_STEPS,
    DRAFT_FALSE_FLAGS,
    LaunchCandidate,
    compose_identity,
    private_eligibility_template,
    real_access_test_template,
    verify_candidate,
)
from .references import sha256
from .runtime_build import NeutralViewIdentity, RuntimeManifest, write_new_tree
from .runtime_cli import document, read_file

RECEIPT_NAMES = (
    "postmerge_verification_receipt.json",
    "protected_main_ci_receipt.json",
    "ruleset_receipt.json",
    "owner_readiness_custody_receipt.json",
    "isolated_runtime_neutrality_receipt.json",
    "runtime_equivalence_receipt.json",
    "synthetic_launch_rehearsal_receipt.json",
    "dropbox_readonly_receipt.json",
    "principal_review_receipt.json",
)
EXTERNAL_ROOT = "06_validation/m2_benchmark/annotation_runs/m2-02-v1"
AREAS = (
    ("coordinator/custody", "Source, authority and private eligibility custody"),
    (
        "annotator-a/issue",
        "Private issued-package area; A may list/read but not write",
    ),
    (
        "annotator-a/submission",
        "Private account-scoped A draft workspace with normal list/read/write semantics",
    ),
    (
        "annotator-b/issue",
        "Private issued-package area; B may list/read but not write",
    ),
    (
        "annotator-b/submission",
        "Private account-scoped B draft workspace with normal list/read/write semantics",
    ),
    (
        "coordinator/locked/annotator-a",
        "Immutable A locks; append-only application protocol",
    ),
    (
        "coordinator/locked/annotator-b",
        "Immutable B locks; append-only application protocol",
    ),
    ("coordinator/supersession", "Explicit single-parent lock replacement lineage"),
    ("coordinator/comparison", "Comparison only after both valid locks"),
    ("coordinator/adjudication", "Later M2-03 adjudication, not authorized now"),
    (
        "coordinator/held-out-sealed",
        "Private benchmark-role routing and sealed results",
    ),
    (
        "coordinator/receipts",
        "Authority, access, eligibility, issuance and lock receipts",
    ),
)

ACCESS_ROW_COUNT = len(ACCESS_POLICY_V2.acl_expectations)

# Each row is a question for the owner, not a decision by this software.
DECISIONS = (
    (
        "POSTMERGE-M2-02A-VERIFIED",
        "Accept the protected-main recovery identity and preserved M2-02A custody?",
        "PR15 merge/tree/parents, accepted PR13 ancestry, postmerge CI, "
        "ruleset and frozen-byte receipts",
        "Rely on reviewed readiness lineage",
        "Stop and reconcile authority lineage",
        "Reviewing stale or substituted authority",
    ),
    (
        "ISOLATED-RUNTIME",
        "Accept the independent runtime design and exact selected runtime identity?",
        "Runtime and Python-environment manifests, exact stdlib/native bytes, "
        "interpreter/dependencies and separately trusted launcher plan; independent "
        "pre-execution provisioning verification and protected custody remain future prerequisites",
        "Accept runtime design for later private provisioning",
        "Revise runtime design before launch",
        "Repository access or an untrusted bootstrap exposes coordinator knowledge",
    ),
    (
        "RUNTIME-NEUTRALITY",
        "Accept runtime and human-view neutrality with canonical validation equivalence?",
        "Source/import audits, leakage and equivalence tests, "
        "original/derived identity inventories",
        "Accept tested projection policy",
        "Block distribution and repair neutrality or semantic drift",
        "Partition leakage or changed scientific validation",
    ),
    (
        "EXTERNAL-TOPOLOGY",
        "Accept the exact proposed areas and least-privilege access design?",
        "Typed private draft topology, ACL policy and separate application immutability controls; "
        "no area creation evidence is claimed",
        "Approve topology design only",
        "Revise topology; no external write follows",
        "Inherited shares expose cross-annotator or coordinator content",
    ),
    (
        "ELIGIBILITY-PROTOCOL",
        "Accept the private distinct-human and exposure attestation protocol?",
        "Blank private template, role/exposure rules and exact composite identity bindings",
        "Approve eligibility protocol only",
        "Revise private eligibility protocol",
        "Ineligible or model-assisted annotators contaminate independence",
    ),
    (
        "AB-ACCESS-TEST-PROTOCOL",
        f"Accept all {ACCESS_ROW_COUNT} derived real-account ACL checks and evidence procedure?",
        "Typed v2 actor/resource/list-read-write/expected-outcome matrix and policy identity; "
        "private account-scoped read/write drafts, read-only issued packages and explicit "
        "foreign/coordinator denials; all statuses NOT RUN",
        "Approve later test protocol only",
        "Revise protocol before provisioning",
        "Path assumptions mistaken for observed account isolation",
    ),
    (
        "HELDOUT-SEALING-LAUNCH-PROTOCOL",
        "Accept coordinator-only routing and held-out sealing at launch?",
        "Coordinator protocol, neutral view audit and explicit annotator list/read/write denials "
        "for held-out-sealed",
        "Approve sealing design only",
        "Block launch until secrecy is demonstrable",
        "Held-out labels or partition assignments leak into development",
    ),
    (
        "ISSUANCE-CEREMONY",
        "Accept the ordered fail-closed future issuance ceremony?",
        "Exact authority/runtime/package/reference/eligibility/access/issuance "
        "sequence and negative rehearsal",
        "Approve ceremony design only",
        "Revise ceremony; issue nothing",
        "Unverified recipients or self-consistent replacement bytes are issued",
    ),
    (
        "PRODUCTION-LOCK-PRECONDITIONS",
        "Accept all later lock and immutable supersession prerequisites?",
        "Owner launch gate, dual confirmation, complete inspection, "
        "resolved/unresolved slots and fork rejection",
        "Approve preconditions only; locking remains disabled",
        "Revise preconditions before any real lock",
        "Incomplete evidence or ambiguous supersession becomes a final record",
    ),
    (
        "ANNOTATOR-A-ELIGIBILITY",
        "Is privately identified human A eligible for the exact A composite?",
        "Future private real-person attestation, exposure history and composite pins",
        "Accept A eligibility for that identity only",
        "Do not assign or issue A",
        "Contaminated or mismatched human A",
    ),
    (
        "ANNOTATOR-B-ELIGIBILITY",
        "Is privately identified human B eligible for the exact B composite?",
        "Future private real-person attestation, exposure history and composite pins",
        "Accept B eligibility for that identity only",
        "Do not assign or issue B",
        "Contaminated or mismatched human B",
    ),
    (
        "DISTINCT-HUMANS",
        "Do verified private identities establish two distinct human persons?",
        "Coordinator private identity verification beyond account/token inequality",
        "Accept distinct-person requirement only",
        "Replace assignment and repeat private checks",
        "One person operates both independent roles",
    ),
    (
        "REAL-AB-ACCESS-ISOLATION",
        "Have all required outcomes passed using the actual separate accounts?",
        "Future timestamped private real-account test evidence "
        f"for all {ACCESS_ROW_COUNT} derived ACL checks and exact composites",
        "Accept observed isolation for tested state only",
        "Repair permissions and rerun all affected tests",
        "Cross-access survives inherited memberships or old links",
    ),
    (
        "REAL-EXTERNAL-WRITE-AUTHORIZATION",
        "Authorize the exact future external writes and permission changes?",
        "Separate explicit owner scope, private destinations, operation list "
        "and verified authority",
        "Permit only separately scoped future writes",
        "Keep external execution root absent and writes prohibited",
        "Design approval is misread as write authorization",
    ),
    (
        "REAL-PACKAGE-ISSUANCE",
        "Does actual role-specific delivery match independently pinned receipts and bytes?",
        "Future A/B eligibility and original issuance receipts plus reviewed "
        "derived/runtime binding, recipient/time and independent byte checks",
        "Accept actual verified delivery only",
        "Quarantine/revoke delivery and repeat ceremony",
        "Draft or rehearsal receipts mistaken for real issuance",
    ),
    (
        "ANNOTATION-LAUNCH",
        "Authorize annotation start after every preceding operational gate passes?",
        "Separate owner launch record on protected main, actual "
        "eligibility/isolation/issuance and verified start ceremony",
        "Authorize the exact later start only",
        "Keep annotation unstarted",
        "Preparation or readiness mistaken for launch authority",
    ),
)


class ArtifactPin(StrictModel):
    path: str
    sha256: Sha256


class ReviewInputs(StrictModel):
    candidate: ArtifactPin
    candidate_model_sha256: Sha256
    runtime: ArtifactPin
    views: list[ArtifactPin] = Field(min_length=2, max_length=2)
    evidence: dict[str, ArtifactPin] = Field(default_factory=dict)
    raw_evidence: dict[str, ArtifactPin] = Field(default_factory=dict)
    expected_source_snapshot_sha256: Sha256 | None = None
    expected_final_head_sha: str | None = None
    expected_merge_ref_sha: str | None = None


COMPLETION_CHECKS = frozenset(
    (
        "new_m2",
        "all_m2",
        "benchmark",
        "scientific",
        "guards_acquisition",
        "full_pytest",
        "ruff_format",
        "ruff_lint",
        "pyright_windows",
        "pyright_linux",
        "schema_drift",
        "data_policy",
        "staged_byte_policy",
    )
)
TEST_CHECKS = frozenset(
    ("new_m2", "all_m2", "benchmark", "scientific", "guards_acquisition", "full_pytest")
)
CI_CONTEXTS = frozenset(("quality (3.12)", "quality (3.13)", "windows-acquisition-safety"))
CommitSha = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]


class MeasuredCheck(StrictModel):
    gate: str
    command: str = Field(min_length=1)
    exit_code: int
    passed: int | None = Field(ge=0)
    failed: int = Field(ge=0)
    skipped: int = Field(ge=0)
    source_snapshot_sha256: Sha256


class MinorFinding(StrictModel):
    finding: str = Field(min_length=1)
    disposition: str = Field(min_length=1)


class MeasuredReview(StrictModel):
    source_snapshot_sha256: Sha256
    review_range: str = Field(min_length=1)
    critical: int = Field(ge=0)
    important: int = Field(ge=0)
    minor_findings: list[MinorFinding]


class MeasuredCIContext(StrictModel):
    name: str
    conclusion: Literal["success"]
    head_sha: CommitSha
    merge_ref_sha: CommitSha
    run_id: str = Field(min_length=1)


class MeasuredCI(StrictModel):
    head_sha: CommitSha
    merge_ref_sha: CommitSha
    source_snapshot_sha256: Sha256
    new_m2_safety_skips: int = Field(ge=0)
    contexts: list[MeasuredCIContext]


class CompletionGates(StrictModel):
    kind: Literal["M2_02B1_MEASURED_COMPLETION_GATES"]
    source_files: dict[str, Sha256]
    source_snapshot_sha256: Sha256
    checks: list[MeasuredCheck]
    review: MeasuredReview
    ci: MeasuredCI


class StageSource(StrictModel):
    artifact: str
    sha256: Sha256


class TechnicalStageReceipt(StrictModel):
    """A typed derivation from captured observations, never a new measurement."""

    kind: Literal["M2_02B1_MEASURED_TECHNICAL_STAGE"]
    stage: str
    status: Literal["MEASURED_PASS"]
    bindings: dict[str, Any]
    observations: dict[str, Any]
    sources: dict[str, StageSource]


TECHNICAL_STAGES = (*RECEIPT_NAMES, "final_ci_receipt.json")
HARDENING_RECEIPTS = (
    "access_policy_v2_receipt.json",
    "python_environment_trust_receipt.json",
    "runtime_identity_receipt.json",
)
BASELINE_FIELDS = (
    "protected_main_merge_sha",
    "protected_main_merge_tree",
    "readiness_v3_sha256",
    "evidence_v5_sha256",
    "reference_manifest_sha256",
)
RUNTIME_STAGES = frozenset(
    (
        "isolated_runtime_neutrality_receipt.json",
        "runtime_equivalence_receipt.json",
        "synthetic_launch_rehearsal_receipt.json",
    )
)


def _object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("stage observation must be an object")
    return cast(dict[str, Any], value)


def _equal(actual: object, expected: object) -> None:
    # Canonical bytes distinguish booleans from integers and reject extra observations.
    if canonical_json_bytes(actual) != canonical_json_bytes(expected):
        raise ValueError("technical stage observation or identity differs")


def _fields(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    _equal({key: actual.get(key) for key in expected}, expected)


def _inventory_rows(value: Any) -> dict[str, str]:
    if not isinstance(value, list) or not value:
        raise ValueError("stage evidence requires a nonempty file inventory")
    result: dict[str, str] = {}
    for item in cast(list[Any], value):
        row = _object(item)
        name, digest = row.get("path"), row.get("sha256")
        if (
            not isinstance(name, str)
            or not name
            or name in result
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            raise ValueError("stage file inventory is malformed or duplicated")
        result[name] = digest
    return result


def _validate_technical_stages(
    candidate: LaunchCandidate, gates: CompletionGates, files: dict[str, bytes]
) -> None:
    baseline = candidate.model_dump(mode="json", include=set(BASELINE_FIELDS))
    runtime_binding = {
        **baseline,
        "source_snapshot_sha256": gates.source_snapshot_sha256,
        "runtime_sha256": candidate.identities[0].runtime_sha256,
        "view_sha256s": [identity.view_sha256 for identity in candidate.identities],
    }
    for name in TECHNICAL_STAGES:
        stage = TechnicalStageReceipt.model_validate_json(files[name])
        _equal(stage.stage, name)
        required_sources = (
            {"observation", "baseline"}
            if name == "dropbox_readonly_receipt.json"
            else {"observation"}
        )
        if set(stage.sources) != required_sources:
            raise ValueError("technical stage source roles differ")
        captured: dict[str, dict[str, Any]] = {}
        for role, ref in stage.sources.items():
            # Only separately captured raw evidence can substantiate a normalized stage.
            if not ref.artifact.startswith("raw_evidence/") or ref.artifact not in files:
                raise ValueError("technical stage has no captured raw observation")
            data = files[ref.artifact]
            if sha256(data) != ref.sha256:
                raise ValueError("technical stage source hash mismatch")
            captured[role] = document(data)
        raw = captured["observation"]
        if "status" in raw and raw["status"] not in (
            "completed",
            "POSTMERGE_VERIFIED_DESIGN_REVIEW_PENDING",
            "MEASURED_PASS",
            "PASS",
            "COMPLETE",
        ):
            raise ValueError("technical stage raw observation is not measured success")
        for outcome, expected in (
            ("conclusion", "success"),
            ("exit_code", 0),
            ("success", True),
            ("failed", 0),
        ):
            if outcome in raw:
                _equal(raw[outcome], expected)
        expected_bindings = baseline
        if name in RUNTIME_STAGES:
            expected_bindings = runtime_binding
        elif name in ("principal_review_receipt.json", "final_ci_receipt.json"):
            expected_bindings = {**baseline, "source_snapshot_sha256": gates.source_snapshot_sha256}
        _equal(stage.bindings, expected_bindings)

        if name == "postmerge_verification_receipt.json":
            _fields(
                raw,
                {
                    "merge": candidate.protected_main_merge_sha,
                    "tree": candidate.protected_main_merge_tree,
                    "recovery_pr": 15,
                    "original_feature_preserved": True,
                    "status": "POSTMERGE_VERIFIED_DESIGN_REVIEW_PENDING",
                    "parents": [
                        "cffe543c85738266c9bdd71bd011c5fe329d5481",
                        "2ab5eb92d4c732d73a198e3b64690a7356f0ac2b",
                    ],
                },
            )
            expected_observations: dict[str, Any] = {"merge_verified": True}
        elif name == "protected_main_ci_receipt.json":
            _fields(
                raw,
                {
                    "head_sha": candidate.protected_main_merge_sha,
                    "status": "completed",
                    "conclusion": "success",
                },
            )
            jobs = raw.get("jobs")
            if not isinstance(jobs, list):
                raise ValueError("historical CI jobs are absent")
            pairs = [
                (_object(job).get("name"), _object(job).get("conclusion"))
                for job in cast(list[Any], jobs)
            ]
            _equal(
                sorted(pairs, key=lambda pair: str(pair[0])),
                [(context, "success") for context in sorted(CI_CONTEXTS)],
            )
            expected_observations = {
                "required_contexts": sorted(CI_CONTEXTS),
                "conclusion": "success",
            }
        elif name == "ruleset_receipt.json":
            ruleset = _object(raw.get("ruleset"))
            _fields(ruleset, {"id": 21658925, "enforcement": "active", "bypass_actors": []})
            refs = _object(_object(ruleset.get("conditions")).get("ref_name"))
            _equal(refs.get("include"), ["refs/heads/main"])
            _equal(refs.get("exclude"), [])
            rule_rows = ruleset.get("rules")
            if not isinstance(rule_rows, list):
                raise ValueError("protected-main rules are absent")
            rules = {
                _object(rule).get("type"): _object(rule) for rule in cast(list[Any], rule_rows)
            }
            if not {
                "deletion",
                "non_fast_forward",
                "pull_request",
                "required_status_checks",
            }.issubset(rules):
                raise ValueError("protected-main safety rules are incomplete")
            _equal(
                _object(rules["pull_request"].get("parameters")).get(
                    "required_review_thread_resolution"
                ),
                True,
            )
            checks = _object(rules["required_status_checks"].get("parameters"))
            _equal(checks.get("strict_required_status_checks_policy"), True)
            contexts = checks.get("required_status_checks")
            if not isinstance(contexts, list):
                raise ValueError("required CI contexts absent from ruleset")
            _equal(
                sorted(str(_object(item).get("context")) for item in cast(list[Any], contexts)),
                sorted(CI_CONTEXTS),
            )
            expected_observations = {"ruleset_id": 21658925, "protected_main_enforced": True}
        elif name == "owner_readiness_custody_receipt.json":
            _fields(
                raw,
                {
                    "merge_sha": candidate.protected_main_merge_sha,
                    "merge_tree": candidate.protected_main_merge_tree,
                    "readiness_sha256": candidate.readiness_v3_sha256,
                    "evidence_v5_sha256": candidate.evidence_v5_sha256,
                    "owner_readiness_approved": True,
                    "annotation_launch_approved": False,
                    "approval_sha256": candidate.contract_identity.owner_readiness_approval_sha256,
                },
            )
            expected_observations = {
                "owner_readiness_approved": True,
                "annotation_launch_approved": False,
            }
        elif name in RUNTIME_STAGES:
            _fields(
                raw,
                {
                    "kind": "MEASURED_LOCAL_TEST_EXECUTION",
                    "exit_code": 0,
                    "skipped": 0,
                    "annotation_started": False,
                    "real_packages_issued": False,
                    "human_gold_created": False,
                },
            )
            passed = raw.get("passed")
            if type(passed) is not int or passed <= 0:
                raise ValueError("runtime stage has no measured passing tests")
            measured = _inventory_rows(raw.get("files"))
            required = {
                "src/peru_conflicts/execution/runtime_build.py",
                "src/peru_conflicts/execution/runtime_cli.py",
                "src/peru_conflicts/execution/neutral_forms.py",
            }
            test = "tests/unit/test_m2_isolated_runtime.py"
            if name == "synthetic_launch_rehearsal_receipt.json":
                required.add("src/peru_conflicts/execution/launch.py")
                test = "tests/unit/test_m2_launch_preflight.py"
            required.add(test)
            command = raw.get("command")
            if (
                not required.issubset(measured)
                or not isinstance(command, str)
                or test not in command
            ):
                raise ValueError("runtime stage has no applicable measured test coverage")
            if any(gates.source_files.get(path) != digest for path, digest in measured.items()):
                raise ValueError("runtime stage measured stale or unrelated source files")
            expected_observations = {
                "synthetic_test_coverage_passed": True,
                "real_annotation_performed": False,
            }
        elif name == "dropbox_readonly_receipt.json":
            _fields(raw, {"dropbox_writes": 0, "m2_external_root_absent": True})
            original = _inventory_rows(captured["baseline"].get("verified_hashes"))
            current = _inventory_rows(raw.get("verified_hashes"))
            if any(current.get(path) != digest for path, digest in original.items()):
                raise ValueError("Dropbox baseline evidence changed or is missing")
            expected_observations = {
                "dropbox_writes": 0,
                "m2_external_root_absent": True,
                "preserved_baseline_files": len(original),
            }
        elif name == "principal_review_receipt.json":
            _equal(raw.get("kind"), "MEASURED_INDEPENDENT_PRINCIPAL_REVIEW")
            expected_observations = gates.review.model_dump(mode="json")
            _equal(raw.get("review"), expected_observations)
        else:
            _equal(raw.get("kind"), "MEASURED_FINAL_BRANCH_CI")
            expected_observations = gates.ci.model_dump(mode="json")
            _equal(raw.get("ci"), expected_observations)
        _equal(stage.observations, expected_observations)


def _validate_completion(
    workspace: Path,
    inputs: ReviewInputs,
    files: dict[str, bytes],
    stack: ExitStack,
    candidate: LaunchCandidate,
) -> CompletionGates:
    if "completion_gates.json" not in files or any(name not in files for name in TECHNICAL_STAGES):
        raise ValueError("completion requires all measured receipt inputs")
    gates = CompletionGates.model_validate_json(files["completion_gates.json"])
    expected = inputs.expected_source_snapshot_sha256
    if not expected or expected != gates.source_snapshot_sha256 or not gates.source_files:
        raise ValueError("completion source snapshot is not independently pinned")
    if sha256(canonical_json_bytes(gates.source_files)) != expected:
        raise ValueError("completion source inventory digest differs")
    required_sources = {
        path.relative_to(workspace).as_posix()
        for directory in ("src", "scripts", "tests", "docs", "config", "schemas", ".github")
        for path in (workspace / directory).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }
    required_sources.update(
        name
        for name in (
            "AGENTS.md",
            "pyproject.toml",
            "uv.lock",
            "Makefile",
            ".gitignore",
            ".pre-commit-config.yaml",
        )
        if (workspace / name).is_file()
    )
    if not required_sources.issubset(gates.source_files):
        raise ValueError("completion source inventory omits governing or implementation files")
    for name, digest in gates.source_files.items():
        # A source inventory is a repository-relative recipe, never a path capability.
        if "\\" in name or not name or any(part in ("", ".", "..") for part in name.split("/")):
            raise ValueError("invalid completion source path")
        source = workspace / name
        if source.is_absolute() and not source.is_relative_to(workspace):
            raise ValueError("completion source escapes workspace")
        if sha256(read_file(source, stack)) != digest:
            raise ValueError("completion source bytes changed")
    if (
        len(gates.checks) != len(COMPLETION_CHECKS)
        or frozenset(check.gate for check in gates.checks) != COMPLETION_CHECKS
    ):
        raise ValueError("completion check set is incomplete or duplicated")
    for check in gates.checks:
        if check.source_snapshot_sha256 != expected or check.exit_code != 0 or check.failed != 0:
            raise ValueError("completion check did not pass for reviewed source")
        if check.gate in TEST_CHECKS and (check.passed is None or check.passed == 0):
            raise ValueError("completion test group has no measured passing cases")
        if check.gate == "new_m2" and check.skipped != 0:
            raise ValueError("new M2 safety tests were skipped")
    review = gates.review
    if review.source_snapshot_sha256 != expected or review.critical or review.important:
        raise ValueError("completion independent review is stale or blocking")
    ci = gates.ci
    if (
        ci.source_snapshot_sha256 != expected
        or ci.head_sha != inputs.expected_final_head_sha
        or ci.merge_ref_sha != inputs.expected_merge_ref_sha
        or ci.new_m2_safety_skips != 0
    ):
        raise ValueError("completion CI identities or safety execution differ")
    if (
        len(ci.contexts) != len(CI_CONTEXTS)
        or frozenset(context.name for context in ci.contexts) != CI_CONTEXTS
    ):
        raise ValueError("completion CI contexts incomplete or duplicated")
    if any(
        context.head_sha != ci.head_sha or context.merge_ref_sha != ci.merge_ref_sha
        for context in ci.contexts
    ):
        raise ValueError("completion CI context is stale")
    _validate_technical_stages(candidate, gates, files)
    return gates


def _json(value: object) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def proposed_topology() -> dict[str, object]:
    return {
        "kind": "PROPOSED_EXTERNAL_TOPOLOGY_NOT_EXECUTED",
        "access_policy_version": ACCESS_POLICY_V2.policy_version,
        "access_policy_sha256": ACCESS_POLICY_V2_SHA256,
        "root": EXTERNAL_ROOT,
        "created": False,
        "dropbox_writes": 0,
        "sharing_changes": 0,
        "areas": [
            {
                "path": f"{EXTERNAL_ROOT}/{path}",
                "purpose": purpose,
                "owner": "coordinator",
                "acl_expectations": [
                    row.model_dump(mode="json")
                    for row in ACCESS_POLICY_V2.acl_expectations
                    if row.resource == path
                ],
                "application_controls": [
                    row.model_dump(mode="json")
                    for row in ACCESS_POLICY_V2.application_controls
                    if row.resource == path
                ],
                "exists_created_by_task": False,
            }
            for path, purpose in AREAS
        ],
        "conditions": [
            "Never share the run root or a coordinator ancestor with annotators.",
            "Test inherited memberships, groups and previous links with real accounts.",
            "Two distinct privately eligible humans; no model is an annotator.",
            "Permissions and version history do not prove append-only immutability.",
        ],
        "real_account_tests_status": "NOT RUN",
    }


def _dossier() -> dict[str, object]:
    return {
        "kind": "OWNER_LAUNCH_DECISION_DOSSIER_UNRESOLVED",
        "launch_authority": False,
        "decisions": [
            {
                "decision_id": identifier,
                "question": question,
                "evidence_required": evidence,
                "approval_consequence": approval,
                "rejection_consequence": rejection,
                "can_decide_in_m2_02b1": index < 9,
                "launch_dependency": (
                    "Required before future annotation start; approval of a design item "
                    "alone executes nothing."
                ),
                "principal_risk": risk,
                "response": None,
                "status": "UNRESOLVED",
            }
            for index, (identifier, question, evidence, approval, rejection, risk) in enumerate(
                DECISIONS
            )
        ],
    }


def _dossier_markdown(dossier: dict[str, Any]) -> bytes:
    lines = [
        "# Owner launch review dossier",
        "",
        "All 16 responses are null. This draft grants no authority.",
        "",
    ]
    for row in dossier["decisions"]:
        lines.extend([f"## {row['decision_id']}", "", row["question"], ""])
        for key in (
            "evidence_required",
            "approval_consequence",
            "rejection_consequence",
            "can_decide_in_m2_02b1",
            "launch_dependency",
            "principal_risk",
            "response",
            "status",
        ):
            value = "null" if row[key] is None else str(row[key])
            lines.append(f"- {key.replace('_', ' ')}: {value}")
        lines.append("")
    return ("\n".join(lines) + "\n").encode()


def hardening_receipt_documents(
    candidate: LaunchCandidate, runtime: RuntimeManifest
) -> dict[str, dict[str, object]]:
    """Derive review bindings from captured rehearsal bytes, never production trust."""
    return {
        "access_policy_v2_receipt.json": {
            "kind": "M2_02B1B_ACCESS_POLICY_V2_REVIEW_ONLY",
            "access_policy_sha256": ACCESS_POLICY_V2_SHA256,
            "protocol_version": candidate.access_control_test_protocol_version,
            "policy": ACCESS_POLICY_V2.model_dump(mode="json"),
            "acl_check_count": ACCESS_ROW_COUNT,
            "real_account_tests_executed": 0,
            "real_account_test_status": "NOT RUN",
        },
        "python_environment_trust_receipt.json": {
            "kind": "M2_02B1B_PYTHON_ENVIRONMENT_REHEARSAL_ONLY",
            "runtime_sha256": runtime.runtime_sha256,
            "python_environment_sha256": runtime.python_environment_sha256,
            "python_environment_manifest_sha256": runtime.python_environment_manifest_sha256,
            "environment": runtime.python_environment.model_dump(mode="json"),
            "production_approved": False,
            "independent_pre_execution_provisioning_verification": "NOT RUN",
            "external_os_and_system_library_trust": "NOT RUN",
        },
        "runtime_identity_receipt.json": {
            "kind": "M2_02B1B_RUNTIME_IDENTITY_REHEARSAL_ONLY",
            "runtime_sha256": runtime.runtime_sha256,
            "access_policy_sha256": candidate.access_policy_sha256,
            "identities": [identity.model_dump(mode="json") for identity in candidate.identities],
            "production_approved": False,
        },
    }


def prepare_review(
    workspace_root: Path,
    snapshot_name: str,
    inputs: ReviewInputs,
    *,
    require_complete: bool = False,
    cache_namespace: str = "m2-02b1",
) -> Path:
    """Capture pinned inputs and write a new ignored snapshot; perform no external action.

    The caller supplies a trusted workspace root (the CLI fixes it to this repository).
    Supplied receipts are preserved byte-for-byte and are not independently re-attested.
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", snapshot_name):
        raise ValueError("invalid snapshot name")
    workspace_root = workspace_root.absolute()
    if workspace_root.resolve(strict=True) != workspace_root:
        raise ValueError("workspace cannot be aliased")
    if cache_namespace not in {"m2-02b1", "m2-02b1b"}:
        raise ValueError("invalid cache namespace")
    hardening = cache_namespace == "m2-02b1b"
    cache = workspace_root / ".cache" / cache_namespace
    output = cache / snapshot_name
    for path in (workspace_root / ".cache", cache, output):
        if path.is_symlink() or path.resolve() != path.absolute():
            raise ValueError("output cannot be aliased")
    if output.exists():
        raise ValueError("snapshot already exists")
    unknown = set(inputs.evidence) - {
        *RECEIPT_NAMES,
        *HARDENING_RECEIPTS,
        "completion_gates.json",
        "core_tests_measured_receipt.json",
        "regression_groups_measured_receipt.json",
        "final_ci_receipt.json",
        "blank_runtime_structure_receipt.json",
        "red_evidence_receipt.json",
        "neutral_view_build_receipt.json",
    }
    if unknown:
        raise ValueError("unknown evidence receipt name")
    if any(
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", name) for name in inputs.raw_evidence
    ):
        raise ValueError("invalid raw evidence filename")
    sources: dict[str, dict[str, object]] = {}
    with ExitStack() as stack:

        def capture(name: str, pin: ArtifactPin) -> bytes:
            data = read_file(Path(pin.path).absolute(), stack)
            if sha256(data) != pin.sha256:
                raise ValueError(f"input hash mismatch: {name}")
            sources[name] = {"path": pin.path, "bytes": len(data), "sha256": pin.sha256}
            return data

        candidate_bytes = capture("candidate", inputs.candidate)
        candidate = LaunchCandidate.model_validate_json(json.dumps(yaml.safe_load(candidate_bytes)))
        runtime_bytes = capture("runtime", inputs.runtime)
        runtime = RuntimeManifest.model_validate_json(runtime_bytes)
        view_bytes = [capture(f"view_{index}", pin) for index, pin in enumerate(inputs.views)]
        views = [NeutralViewIdentity.model_validate_json(data) for data in view_bytes]
        identities = tuple(
            compose_identity(original.original, view, runtime)
            for original, view in zip(candidate.identities, views, strict=True)
        )
        verify_candidate(candidate, inputs.candidate_model_sha256, identities)
        files = {name: capture(name, pin) for name, pin in inputs.evidence.items()}
        for data in files.values():
            document(data)
        for name, pin in inputs.raw_evidence.items():
            files[f"raw_evidence/{name}"] = capture(f"raw_evidence/{name}", pin)
        if hardening:
            for name, expected in hardening_receipt_documents(candidate, runtime).items():
                if name not in files:
                    if require_complete:
                        raise ValueError(f"hardening requires current receipt: {name}")
                else:
                    try:
                        _equal(document(files[name]), expected)
                    except ValueError as error:
                        raise ValueError(
                            f"hardening receipt is stale or inconsistent: {name}"
                        ) from error
        completion = (
            _validate_completion(workspace_root, inputs, files, stack, candidate)
            if require_complete
            else None
        )
        required = (*TECHNICAL_STAGES, *HARDENING_RECEIPTS) if hardening else TECHNICAL_STAGES
        missing = [name for name in required if name not in files]
        for name in missing:
            files[name] = _json(
                {
                    "kind": "UNMEASURED_REVIEW_STAGE",
                    "stage": name,
                    "status": "NOT RUN",
                    "reason": "No independently pinned measured receipt supplied.",
                    "success": None,
                }
            )
        files["isolated_runtime_manifest.json"] = runtime_bytes
        files["annotator_a_neutral_view_manifest.json"] = view_bytes[0]
        files["annotator_b_neutral_view_manifest.json"] = view_bytes[1]
        files["proposed_external_topology.json"] = _json(proposed_topology())
        files["private_eligibility_template.json"] = _json(private_eligibility_template())
        access = [
            receipt.model_dump(mode="json") for receipt in real_access_test_template(identities)
        ]
        files["launch_access_test_protocol_receipt.json"] = _json(
            {
                "kind": "REAL_ACCOUNT_ACCESS_PROTOCOL_NOT_EXECUTED",
                "protocol_version": candidate.access_control_test_protocol_version,
                "access_policy_sha256": candidate.access_policy_sha256,
                "acl_check_count": ACCESS_ROW_COUNT,
                "checks": access,
                "application_controls": [
                    row.model_dump(mode="json") for row in ACCESS_POLICY_V2.application_controls
                ],
                "real_account_tests_executed": 0,
                "ceremony_steps": CEREMONY_STEPS,
            }
        )
        dossier = _dossier()
        files["owner_launch_decision_dossier.json"] = _json(dossier)
        files["owner_launch_decision_dossier.md"] = _dossier_markdown(dossier)
        files["proposed_pr_body.md"] = (
            "# M2-02B.1 isolated annotation launch preparation\n\n"
            "Prepares a source-neutral runtime, distinct original/derived package custody, "
            "strict launch candidate, private eligibility and real-account access protocols, "
            "and an unresolved 16-decision owner dossier. "
            "Production launch and locking remain disabled.\n\n"
            f"Protected-main readiness recovery: `{candidate.protected_main_merge_sha}`; "
            f"tree `{candidate.protected_main_merge_tree}`. This is not final branch CI.\n\n"
            f"Runtime aggregate: `{runtime.runtime_sha256}`.\n\n"
            "Validation: consult the byte-pinned supplied evidence in final_m2_02b1_packet.json. "
            "Missing stages are NOT RUN; supplied receipt content "
            "is not a fresh re-attestation.\n\n"
            f"All {ACCESS_ROW_COUNT} derived real-account ACL tests remain NOT RUN; "
            "all 16 owner responses remain null. "
            "No real humans, eligibility or issuance records, external areas, Dropbox writes, "
            "package delivery, annotation, production locks, gold, parser work or M3 authority.\n\n"
            "Future operation requires separate owner approval, private verification "
            "of two distinct eligible humans, actual account-isolation tests "
            "and separately authorized external writes.\n"
        ).encode()
        packet = {
            "cache_namespace": cache_namespace,
            "hardening_review_status": (
                "M2_02B1_OWNER_LAUNCH_DESIGN_REVIEW_READY_AFTER_HARDENING"
                if hardening and completion is not None
                else "INCOMPLETE"
                if hardening
                else "NOT APPLICABLE"
            ),
            "kind": "M2_02B1_REVIEW_PREPARATION_ONLY",
            "launch_authority": False,
            "completion_gates_satisfied": completion is not None,
            "completion_gates_status": "MEASURED_INPUTS_VALIDATED" if completion else "NOT RUN",
            "completion_gate_evidence": completion.model_dump(mode="json") if completion else None,
            "missing_measured_receipts": missing,
            "supplied_receipts": sorted(inputs.evidence),
            "receipt_claims_independently_reverified": False,
            "candidate_file_sha256": inputs.candidate.sha256,
            "candidate_model_sha256": inputs.candidate_model_sha256,
            "owner_readiness_approved": True,
            **dict.fromkeys(DRAFT_FALSE_FLAGS, False),
            "identities": [identity.model_dump(mode="json") for identity in identities],
            "source_artifacts": sources,
            "artifacts": {
                name: {"bytes": len(data), "sha256": sha256(data)}
                for name, data in sorted(files.items())
            },
        }
        files["final_m2_02b1_packet.json"] = _json(packet)
        # A sidecar binds the packet without a circular self-hash.
        files["SHA256SUMS.txt"] = "".join(
            f"{sha256(data)}  {len(data)}  {name}\n" for name, data in sorted(files.items())
        ).encode()
        cache.mkdir(parents=True, exist_ok=True)
        write_new_tree(output, files)
    return output
