"""Coordinator-only operational proposals, never permission to execute them."""

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Self, cast

from pydantic import field_validator, model_validator

from peru_conflicts.models.common import Sha256, StrictModel

from .access_policy import ACCESS_POLICY_V2
from .contracts import AnnotationContractIdentity, validate_annotation_contract_alignment
from .launch import (
    RehearsalResult,
    model_sha256,
    private_eligibility_template,
    synthetic_launch_preflight,
)
from .launch_design import REVIEW_BINDINGS, DesignState, validate_active_design
from .launch_review import DECISIONS, proposed_topology
from .references import sha256
from .runtime_build import write_new_tree

MERGE_SHA = "e33acf9350701f2c0141bf2d3f697c1bb69d2080"
MERGE_TREE = "8c7970063362f6b07029c7cd0d46a15c94bf2a5d"
DESIGN_SHA = "82e61b502c8ecc6385a02531c081f1b9a90254bbc14098a6dd73c74f16e29c44"
CANDIDATE_V2_SHA = "0a3dd270a117ebc160253181045eb2b27b3532a7b12664d1965042f4e1ceea48"
OPERATIONAL_DECISIONS = tuple(row[0] for row in DECISIONS[9:])
PRIVATE_EXECUTION_ROOT = "/M2 Private Annotation Execution/m2-02-v1"


class PendingOperationalDecision(StrictModel):
    decision_id: str
    status: Literal["UNRESOLVED"] = "UNRESOLVED"
    response: None = None


class OperationalCandidate(DesignState):
    candidate_id: Literal["M2-02-OPERATIONAL-LAUNCH-CANDIDATE-V1"] = (
        "M2-02-OPERATIONAL-LAUNCH-CANDIDATE-V1"
    )
    status: Literal["owner_review_draft"] = "owner_review_draft"
    protected_main_merge_sha: str
    protected_main_merge_tree: str
    launch_design_approval_sha256: Sha256
    launch_candidate_v2_sha256: Sha256
    bindings: dict[str, Sha256]
    contract_identity: AnnotationContractIdentity
    decisions: tuple[PendingOperationalDecision, ...]

    @model_validator(mode="after")
    def exact_reviewed_authority(self) -> Self:
        validate_annotation_contract_alignment(self.contract_identity)
        if (self.protected_main_merge_sha, self.protected_main_merge_tree) != (
            MERGE_SHA,
            MERGE_TREE,
        ):
            raise ValueError("exact PR 16 merge authority required")
        if (self.launch_design_approval_sha256, self.launch_candidate_v2_sha256) != (
            DESIGN_SHA,
            CANDIDATE_V2_SHA,
        ):
            raise ValueError("reviewed design approval and candidate required")
        if self.bindings != REVIEW_BINDINGS:
            raise ValueError("operational custody bindings differ from approved design")
        if tuple(row.decision_id for row in self.decisions) != OPERATIONAL_DECISIONS:
            raise ValueError("exact seven unresolved operational decisions required")
        return self


def make_candidate() -> OperationalCandidate:
    """Build source-neutral draft from the still-valid approved design."""
    design = validate_active_design()
    return OperationalCandidate(
        protected_main_merge_sha=MERGE_SHA,
        protected_main_merge_tree=MERGE_TREE,
        launch_design_approval_sha256=DESIGN_SHA,
        launch_candidate_v2_sha256=CANDIDATE_V2_SHA,
        bindings=dict(REVIEW_BINDINGS),
        contract_identity=design.reviewed_candidate.contract_identity,
        decisions=tuple(PendingOperationalDecision(decision_id=x) for x in OPERATIONAL_DECISIONS),
    )


def validate_operational_candidate(
    candidate_bytes: bytes, *, expected_sha256: str, merge_sha: str, merge_tree: str
) -> OperationalCandidate:
    """Require an externally supplied byte pin and separately verified merge identity."""
    if sha256(candidate_bytes) != expected_sha256:
        raise ValueError("candidate bytes do not match independent expected pin")
    if (merge_sha, merge_tree) != (MERGE_SHA, MERGE_TREE):
        raise ValueError("independent main evidence does not match reviewed merge")
    validate_active_design()
    return OperationalCandidate.model_validate_json(candidate_bytes)


LAUNCH_EVIDENCE = (
    "fresh_protected_main_authority",
    "exact_production_environment_owner_approval",
    "private_eligibility_role_bindings",
    "exact_scoped_external_write_approval",
    "all_108_real_access_checks_and_two_application_controls",
    "exact_A_and_B_issuance_receipts",
    "package_reference_view_runtime_environment_alignment",
    "no_stale_evidence",
)


class AnnotationLaunchCandidate(DesignState):
    """An unapproved prerequisite contract, never a real launch permission."""

    candidate_id: Literal["M2-02-ANNOTATION-LAUNCH-CANDIDATE-V1"] = (
        "M2-02-ANNOTATION-LAUNCH-CANDIDATE-V1"
    )
    status: Literal["owner_review_draft"] = "owner_review_draft"
    operational_candidate_sha256: Sha256
    prerequisite_decisions: tuple[str, ...] = OPERATIONAL_DECISIONS[:-1]
    required_evidence: tuple[str, ...] = LAUNCH_EVIDENCE
    production_environment_approved: Literal[False] = False
    decision: PendingOperationalDecision = PendingOperationalDecision(
        decision_id="ANNOTATION-LAUNCH"
    )

    @field_validator("production_environment_approved", mode="before")
    @classmethod
    def no_environment_approval(cls, value: object) -> object:
        if value is not False:
            raise ValueError("environment preparation is not owner approval")
        return value

    @model_validator(mode="after")
    def exact_prerequisites(self) -> Self:
        if (
            self.operational_candidate_sha256 != model_sha256(make_candidate())
            or self.prerequisite_decisions != OPERATIONAL_DECISIONS[:-1]
            or self.required_evidence != LAUNCH_EVIDENCE
            or self.decision.decision_id != "ANNOTATION-LAUNCH"
        ):
            raise ValueError("exact current candidate and all launch prerequisites required")
        return self


def make_annotation_launch_candidate(candidate: OperationalCandidate) -> AnnotationLaunchCandidate:
    return AnnotationLaunchCandidate(operational_candidate_sha256=model_sha256(candidate))


def build_operational_plan(
    candidate: OperationalCandidate, *, setup_version: int = 3
) -> dict[str, Any]:
    """Exact proposal only: derives routes from the approved policy, performs no I/O."""
    candidate = OperationalCandidate.model_validate_json(candidate.model_dump_json())
    topology = cast(dict[str, Any], proposed_topology())
    if type(setup_version) is not int or setup_version not in (2, 3):
        raise ValueError("only reviewed setup versions 2 and 3 are supported")
    if setup_version == 3:
        old_root = str(topology["root"])
        topology["root"] = PRIVATE_EXECUTION_ROOT
        for area in topology["areas"]:
            area["path"] = PRIVATE_EXECUTION_ROOT + area["path"][len(old_root) :]
    parents: set[str] = set()
    for area in topology["areas"]:
        parents.update(str(p) for p in PurePosixPath(area["path"]).parents if str(p) != ".")
        area["allow_inheritance"] = False
        area["permissions"] = {
            actor: {
                row["operation"]: row["expected_outcome"]
                for row in area["acl_expectations"]
                if row["actor"] == actor
            }
            for actor in ("coordinator", "annotator-a", "annotator-b")
        }
        area["application_immutable"] = bool(area["application_controls"])
        area["rollback"] = (
            "On unexpected access stop issuance, revoke the scoped grant, preserve failure "
            "receipts. Remove only exact authorized synthetic probes; never research/human bytes."
        )
    topology["parents"] = [
        {
            "path": path,
            "purpose": "Structural coordinator-only ancestor; not an A/B share root",
            "share_with_annotators": False,
            "allow_inheritance": False,
            "permissions": {
                "coordinator": "list/read/write",
                "annotator-a": "DENY",
                "annotator-b": "DENY",
            },
            "rollback": "Revoke accidental grant; no recursive deletion of this ancestor.",
        }
        for path in sorted(parents)
    ]
    topology["share_root_with_annotators"] = False
    topology["inheritance"] = "No ancestor grants A/B access; verify effective group/link access."
    root = str(topology["root"])
    probe = b"M2-02B.2A SYNTHETIC ACCESS PROBE v1\n"
    rows: list[dict[str, Any]] = []
    for row in ACCESS_POLICY_V2.acl_expectations:
        target = f"{root}/{row.resource}"
        probe_path = f"{target}/.access-probes/{row.check_id.replace('/', '-')}.txt"
        rows.append(
            {
                **row.model_dump(mode="json"),
                "path": target,
                "probe_path": probe_path,
                "probe_sha256": sha256(probe),
                "probe_content_utf8": probe.decode(),
                "operation_target": target if row.operation == "list" else probe_path,
                "preparation_actor": "coordinator",
                "file_operation": {
                    "list": "none",
                    "read": "read_known_object",
                    "write": "exclusive_create",
                }[row.operation],
                "prerequisites": [
                    "verified_external_root_and_namespace",
                    "verified_private_actor_and_fresh_session",
                    "verified_existing_parent",
                    "scoped_setup_authorization",
                    {
                        "list": "verified_existing_directory",
                        "read": "verified_existing_object",
                        "write": "verified_absent_target",
                    }[row.operation],
                ],
                "preparation": (
                    {
                        "list": (
                            "Coordinator verifies existing directory; no probe file is created."
                        ),
                        "read": "Coordinator creates known probe after scoped write approval.",
                        "write": (
                            "Target absent before test; actor attempts exclusive probe creation."
                        ),
                    }[row.operation]
                ),
                "cleanup": {
                    "path": target if row.operation == "list" else probe_path,
                    "expected_sha256": None if row.operation == "list" else sha256(probe),
                    "rule": (
                        "No file created or removed; observe directory only."
                        if row.operation == "list"
                        else "Receipt-bound exact probe removal only after scoped authorization."
                    ),
                },
                "receipt_fields": [
                    "check_id",
                    "private_actor_binding",
                    "observed_outcome",
                    "recorded_at",
                    "candidate_sha256",
                    "effective_permissions_evidence_sha256",
                    "probe_before_sha256",
                    "probe_after_sha256",
                    "cleanup_receipt_sha256",
                ],
                "status": "NOT RUN",
            }
        )
    # Read-only baseline: only 06_validation exists; the M2 intermediate roots do not.
    create_directories = {
        root,
        "06_validation/m2_benchmark",
        "06_validation/m2_benchmark/annotation_runs",
    }
    existing_ancestors = ("06_validation",)
    if setup_version == 3:
        # Planning target only: both folders were absent at read-only inspection.
        create_directories = {root, str(PurePosixPath(root).parent)}
        existing_ancestors = ("/",)
    for area in topology["areas"]:
        path = PurePosixPath(area["path"])
        create_directories.update(
            str(p)
            for p in (path, *path.parents)
            if p == PurePosixPath(root) or PurePosixPath(root) in p.parents
        )
        create_directories.add(f"{path}/.access-probes")
    topology["directory_operations"] = [
        {"path": path, "operation": "assert_existing", "modify_or_reshare": False}
        for path in existing_ancestors
    ] + [
        {"path": path, "operation": "create_new", "modify_or_reshare": False}
        for path in sorted(create_directories)
    ]
    return {
        "kind": "OPERATIONAL_PLAN_NOT_EXECUTED",
        "candidate_sha256": model_sha256(candidate),
        "topology": topology,
        "checks": rows,
        "application_controls": [
            r.model_dump(mode="json") for r in ACCESS_POLICY_V2.application_controls
        ],
        "external_write_decision": "UNRESOLVED",
        "dropbox_writes": 0,
        "unexpected_allow_containment": (
            "Stop; preserve failure evidence; coordinator isolates reviewed probe path. "
            "Do not issue packages or silently replace observed outcome."
        ),
    }


def rehearse_operational_plan(
    candidate: OperationalCandidate, scenario: dict[str, Any], *, synthetic_external_write: bool
) -> RehearsalResult:
    """Reuse the existing invented-evidence validator; never perform an operation."""
    OperationalCandidate.model_validate_json(candidate.model_dump_json())
    if synthetic_external_write is not True:
        return RehearsalResult(
            prerequisites_satisfied=False, failures=("synthetic_scoped_write_missing",)
        )
    return synthetic_launch_preflight(**scenario)


def operational_dossier(candidate: OperationalCandidate) -> dict[str, Any]:
    """Coordinator-only questions and bounded future scope, not owner responses."""
    dependencies = {
        "ANNOTATOR-A-ELIGIBILITY": ["private_A_attestation"],
        "ANNOTATOR-B-ELIGIBILITY": ["private_B_attestation"],
        "DISTINCT-HUMANS": list(OPERATIONAL_DECISIONS[:2]),
        "REAL-AB-ACCESS-ISOLATION": [
            "DISTINCT-HUMANS",
            "REAL-EXTERNAL-WRITE-AUTHORIZATION",
            "108_expected_outcomes",
            "two_application_controls",
        ],
        "REAL-EXTERNAL-WRITE-AUTHORIZATION": [
            "exact_mutation_and_probe_plan",
            "private_role_bindings",
        ],
        "REAL-PACKAGE-ISSUANCE": [
            *list(OPERATIONAL_DECISIONS[:5]),
            "production_environment_owner_approval",
        ],
        "ANNOTATION-LAUNCH": list(OPERATIONAL_DECISIONS[:6]) + list(LAUNCH_EVIDENCE),
    }
    excluded = [
        "research_package_issuance",
        "human_submissions",
        "annotation",
        "locking",
        "comparison",
        "adjudication",
        "gold",
    ]
    scope = [
        "reviewed_topology_creation",
        "reviewed_role_permissions",
        "synthetic_probe_creation",
        "108_real_account_checks",
        "access_receipts",
        "exact_probe_cleanup",
    ]
    rows: list[dict[str, Any]] = []
    for identifier, question, evidence, approval, rejection, risk in DECISIONS[9:]:
        rows.append(
            {
                "decision_id": identifier,
                "status": "UNRESOLVED",
                "response": None,
                "question": question,
                "evidence_required": evidence,
                "available": [
                    "approved launch design",
                    "source-neutral operational proposal",
                    "synthetic tests only",
                ],
                "missing": dependencies[identifier],
                "dependencies": dependencies[identifier],
                "conditional_recommendation": (
                    "Approve only after exact fresh required evidence is "
                    "privately verified; no current recommendation is an owner "
                    "response."
                ),
                "authority": scope
                if identifier == "REAL-EXTERNAL-WRITE-AUTHORIZATION"
                else approval,
                "non_authorities": excluded
                if identifier == "REAL-EXTERNAL-WRITE-AUTHORIZATION"
                else [
                    "No automatic downstream approval",
                    "No parser, M3, gold or scientific-contract amendment",
                ],
                "reversibility": (
                    "Approval can be revoked prospectively; preserve append-only "
                    "decisions and evidence; disclosures cannot be undone."
                ),
                "containment": (
                    "Stop downstream work, quarantine affected evidence, revoke "
                    "scoped access where separately authorized; never repair "
                    "receipts silently."
                ),
                "failure_state": rejection,
                "principal_risk": risk,
            }
        )
    return {
        "kind": "OPERATIONAL_OWNER_REVIEW_ONLY",
        "candidate_sha256": model_sha256(candidate),
        "decisions": rows,
        "external_write_packet": {
            "decision_id": "REAL-EXTERNAL-WRITE-AUTHORIZATION",
            "status": "UNRESOLVED",
            "response": None,
            "allowed_future_scope": scope,
            "excluded": excluded,
            "executed": False,
            "setup_request": build_setup_request(candidate)[0],
        },
    }


ELIGIBILITY_STEPS = (
    "Owner privately nominates candidate A; do not store PII in Git.",
    (
        "Coordinator checks all blind-human eligibility criteria privately, "
        "including no model assistance."
    ),
    "Generate a private random opaque person token, never an unsalted personal identifier hash.",
    "Repeat nomination and eligibility for B independently.",
    "Privately verify two distinct humans and exclusive A/B role bindings.",
    (
        "Bind each private attestation to the exact operational candidate, run, "
        "package, reference, neutral view, runtime and environment."
    ),
    (
        "Owner decides A eligibility, B eligibility and distinct humans "
        "separately; preserve signed/timestamped private evidence."
    ),
    (
        "Keep names, contact and exposure histories only in separately approved "
        "private coordinator custody; export opaque bindings only."
    ),
)
ISSUANCE_STEPS = (
    (
        "Require approved A eligibility, B eligibility, distinct humans and "
        "scoped external-write authority."
    ),
    (
        "Require all 108 real account tests and two coordinator application "
        "controls; inspect ancestor/group/link inheritance and obtain owner "
        "acceptance of isolation."
    ),
    (
        "Require separate exact production-environment owner approval and fresh "
        "protected-main authority."
    ),
    (
        "Check composite package/reference/view/runtime/environment identities "
        "against the reviewed candidate, not receipt self-claims."
    ),
    (
        "Obtain separate prospective authorization of exact issuance writes; "
        "setup-only authority is insufficient. "
        "After that issuance authority only, deliver A package to A issue "
        "area and B package to B issue area; never coordinator metadata."
    ),
    (
        "Each eligible recipient independently rehashes delivered bytes and "
        "confirms its private role binding."
    ),
    (
        "Record timestamp, exact recipient token, role, delivery path and all "
        "composite pins in immutable private issuance receipts."
    ),
    (
        "Owner decides REAL-PACKAGE-ISSUANCE on verified delivery evidence; this "
        "does not approve ANNOTATION-LAUNCH."
    ),
)


def issuance_templates(candidate: OperationalCandidate) -> list[dict[str, Any]]:
    """Blank future receipts; populated real evidence is not accepted by this proposal."""
    root = PRIVATE_EXECUTION_ROOT
    return [
        {
            "kind": "BLANK_FUTURE_ISSUANCE_RECEIPT",
            "role": f"annotator-{role}",
            "run_id": "m2-02-v1",
            "delivery_path": f"{root}/annotator-{role}/issue",
            "operational_candidate_sha256": model_sha256(candidate),
            "package_manifest_sha256": candidate.bindings[
                f"annotator_{role}_package_manifest_sha256"
            ],
            "view_sha256": candidate.bindings[f"annotator_{role}_view_sha256"],
            **{
                key: candidate.bindings[key]
                for key in (
                    "reference_manifest_sha256",
                    "runtime_sha256",
                    "python_environment_sha256",
                    "python_environment_manifest_sha256",
                    "dependency_sha256",
                    "launcher_sha256",
                    "interpreter_sha256",
                )
            },
            "real_receipt_created": False,
            **dict.fromkeys(
                (
                    "recipient_token",
                    "issued_at",
                    "private_eligibility_receipt_sha256",
                    "production_environment_approval_sha256",
                    "real_access_receipt_sha256",
                    "external_write_approval_sha256",
                    "independent_delivered_byte_verification",
                    "recipient_confirmation_sha256",
                )
            ),
        }
        for role in ("a", "b")
    ]


def validate_issuance_templates(templates: object, candidate: OperationalCandidate) -> None:
    if templates != issuance_templates(candidate):
        raise ValueError("only exact role-bound blank future templates are permitted")


def build_setup_request(
    candidate: OperationalCandidate, *, setup_version: int = 3
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Self-contained proposed operations; unresolved private bindings prohibit execution."""
    plan = build_operational_plan(candidate, setup_version=setup_version)
    objects = {
        "operational_candidate.json": candidate.model_dump(mode="json"),
        "topology.json": plan["topology"],
        "access_checks.json": {
            "checks": plan["checks"],
            "application_controls": plan["application_controls"],
        },
        "probe_fixtures.json": [
            {
                key: row[key]
                for key in (
                    "check_id",
                    "probe_path",
                    "probe_sha256",
                    "probe_content_utf8",
                    "file_operation",
                    "preparation_actor",
                    "prerequisites",
                    "cleanup",
                )
            }
            for row in plan["checks"]
        ],
        "cleanup_containment.json": {
            "rule": (
                "Stop on unexpected allow; preserve append-only evidence. Remove only exact "
                "receipt-bound task probes after separate authorization; never recursive "
                "deletion or research bytes."
            ),
            "probes": [row["cleanup"] for row in plan["checks"] if row["operation"] != "list"],
            "evidence_destination": "PRIVATE_UNRESOLVED",
            "external_evidence_file_writes_authorized": False,
        },
    }
    components = {
        name: (json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2) + "\n").encode()
        for name, value in objects.items()
    }
    request = {
        "kind": f"M2_SETUP_AUTHORIZATION_REQUEST_V{setup_version}",
        "decision_id": "REAL-EXTERNAL-WRITE-AUTHORIZATION",
        "status": "UNRESOLVED",
        "response": None,
        "current_authorization": False,
        "execution_eligible": False,
        "decision_14_eligible": False,
        "protected_main_sha": MERGE_SHA,
        "protected_main_tree": MERGE_TREE,
        "launch_design_approval_raw_sha256": DESIGN_SHA,
        "access_policy_sha256": plan["topology"]["access_policy_sha256"],
        "candidate_model_sha256": model_sha256(candidate),
        "candidate_export_raw_sha256": sha256(components["operational_candidate.json"]),
        "hash_semantics": (
            "Component pins hash exact exported bytes; candidate_model_sha256 uses the "
            "existing launch model_sha256 contract."
        ),
        "components": {
            name: {"bytes": len(raw), "raw_sha256": sha256(raw)} for name, raw in components.items()
        },
        "private_bindings": dict.fromkeys(
            (
                "external_root_identity",
                "provider_namespace",
                "account_role_mapping",
                "group_memberships",
                "provider_denial_rule",
                "private_receipt_destination",
            )
        ),
        "excluded": [
            "research_package_issuance",
            "human_submissions",
            "annotation",
            "locking",
            "comparison",
            "adjudication",
            "gold",
        ],
        "observations": (
            "All 108 rows are NOT RUN. Path/setup/session/namespace/network/client "
            "errors are INCONCLUSIVE. Provider not-found is denial only with a "
            "separately reviewed concealment rule, independently established target "
            "existence and verified account/session/namespace."
        ),
        "later_gate": (
            "Exact private bindings, service capability verification, real executor and "
            "scoped owner authorization require separate review; changing flags cannot "
            "launch this template."
        ),
    }
    return request, components


def validate_setup_request(
    raw: bytes,
    components: dict[str, bytes],
    candidate: OperationalCandidate,
    *,
    setup_version: int = 3,
) -> None:
    request, expected_components = build_setup_request(candidate, setup_version=setup_version)
    if evidence_json(raw) != request or components != expected_components:
        raise ValueError("setup request/components differ from the exact unapproved snapshot")


def classify_access_observation(
    expected: Literal["ALLOW", "DENY"],
    observation: str,
    *,
    context_verified: bool,
    provider_concealment_rule_verified: bool = False,
) -> Literal["PASS", "FAIL", "INCONCLUSIVE"]:
    """Synthetic classification rule only; never performs or records an account check."""
    if not context_verified:
        return "INCONCLUSIVE"
    if observation == "not_found" and provider_concealment_rule_verified:
        observation = "authorization_denied"
    if observation not in {"success", "authorization_denied"}:
        return "INCONCLUSIVE"
    return "PASS" if (observation == "success") == (expected == "ALLOW") else "FAIL"


RUNTIME_MANIFEST_RAW_SHA256 = "4d5f8273ff210cf39eb2b105743b26ac8f3e1e1e5851e342dee09f41a9c8b346"


def evidence_json(raw: bytes) -> dict[str, Any]:
    """Decode once; duplicate authority fields never have last-key-wins semantics."""

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate evidence key")
            result[key] = value
        return result

    value = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("evidence object required")
    return cast(dict[str, Any], value)


def inventory_sha256(files: dict[str, str]) -> str:
    """SHA-256 of sorted compact JSON, no trailing newline (not a manifest raw hash)."""
    return sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    )


def validate_inventory(files: dict[str, str]) -> None:
    from .python_environment_policy import safe_relative

    seen: set[str] = set()
    if not files:
        raise ValueError("empty inventory")
    for name, digest in files.items():
        safe_relative(name)
        folded = name.casefold()
        if (
            folded in seen
            or any(part in {"__pycache__", "pyvenv.cfg"} for part in folded.split("/"))
            or folded.endswith(("._pth", ".pyc", ".pyo"))
            or any(part.endswith((" ", ".")) for part in name.split("/"))
            or not re.fullmatch(r"[a-f0-9]{64}", digest)
        ):
            raise ValueError("ambiguous, excluded or invalid inventory entry")
        seen.add(folded)


def _exact_evidence_booleans(value: Any) -> Any:
    if isinstance(value, dict):
        value = cast(dict[str, Any], value)
        for key in (
            "production_candidate_prepared",
            "production_environment_approved",
            "python_executed",
            "candidate_python_executed",
            "external_provenance_verified",
            "independent_provisioning_verified",
        ):
            if key in value and type(value[key]) is not bool:
                raise ValueError("evidence authority requires literal booleans")
    return value


class NativeStageReceipt(StrictModel):
    _booleans = model_validator(mode="before")(_exact_evidence_booleans)
    kind: Literal["NATIVE_PREPYTHON_CANDIDATE_BYTE_VERIFICATION_V2"]
    stage: str
    expected_manifest_sha256: Sha256
    inventory_sha256: Sha256
    verifier_sha256: Sha256
    files_verified: int
    production_candidate_prepared: Literal[True]
    production_environment_approved: Literal[False]
    python_executed: Literal[False]


class EnvironmentEvidence(StrictModel):
    _booleans = model_validator(mode="before")(_exact_evidence_booleans)
    kind: Literal["PRODUCTION_ENVIRONMENT_CANDIDATE_V3_NOT_APPROVED"]
    protected_main: str
    predecessor_raw_sha256: Sha256
    verifier_sha256: Sha256
    file_hashes: dict[str, Sha256]
    inventory_sha256: Sha256
    production_candidate_prepared: Literal[True]
    production_environment_approved: Literal[False]
    candidate_python_executed: Literal[False]
    external_provenance_verified: Literal[False]
    independent_provisioning_verified: Literal[False]
    provenance_evidence_raw_sha256: Sha256


class DependencyEvidence(StrictModel):
    file_hashes: dict[str, Sha256]
    versions: dict[str, str]
    python_version: str


def validate_environment_candidate(
    raw: bytes,
    *,
    expected_sha256: str,
    constituent_bytes: dict[str, bytes] | None = None,
    receipt_bytes: dict[str, bytes] | None = None,
    expected_verifier_sha256: str | None = None,
) -> dict[str, Any]:
    """Retained evidence consistency only; not provisioning, provenance or launch authority."""
    from .python_environment import PythonEnvironmentTrustManifest
    from .runtime_build import RuntimeManifest

    if sha256(raw) != expected_sha256:
        raise ValueError("independent environment evidence pin required")
    evidence = EnvironmentEvidence.model_validate(evidence_json(raw))
    pins = {
        "python-v2": REVIEW_BINDINGS["python_environment_manifest_sha256"],
        "dependencies-v1": REVIEW_BINDINGS["dependency_sha256"],
        "runtime-v1": RUNTIME_MANIFEST_RAW_SHA256,
    }
    if (
        evidence.protected_main != MERGE_SHA
        or evidence.verifier_sha256 != expected_verifier_sha256
        or constituent_bytes is None
        or set(constituent_bytes) != set(pins)
        or receipt_bytes is None
        or set(receipt_bytes) != set(pins)
    ):
        raise ValueError("independent constituent/procedure identities required")
    # Authenticate every raw file BEFORE parsing any constituent inventory.
    for stage, pin in pins.items():
        if sha256(constituent_bytes[stage]) != pin:
            raise ValueError("independent constituent raw hash differs")
    for value in constituent_bytes.values():
        evidence_json(value)
    python = PythonEnvironmentTrustManifest.model_validate_json(constituent_bytes["python-v2"])
    dependencies = DependencyEvidence.model_validate_json(constituent_bytes["dependencies-v1"])
    runtime = RuntimeManifest.model_validate_json(constituent_bytes["runtime-v1"])
    if (
        python.symlinks
        or runtime.python_environment != python
        or runtime.dependency_sha256 != pins["dependencies-v1"]
        or runtime.dependency_versions != dependencies.versions
        or runtime.python_version != dependencies.python_version
        or inventory_sha256(runtime.file_hashes) != REVIEW_BINDINGS["runtime_file_set_sha256"]
        or python.interpreter_sha256 != REVIEW_BINDINGS["interpreter_sha256"]
        or runtime.launcher_sha256 != REVIEW_BINDINGS["launcher_sha256"]
    ):
        raise ValueError("constituent cross-bindings differ")
    expected: dict[str, str] = {}
    for stage, files in (
        ("python-v2", python.file_hashes),
        ("dependencies-v1", dependencies.file_hashes),
        ("runtime-v1", runtime.file_hashes),
    ):
        validate_inventory(files)
        if "CANDIDATE_RECEIPT.json" in files:
            raise ValueError("receipt is not payload")
        receipt = NativeStageReceipt.model_validate(evidence_json(receipt_bytes[stage]))
        if (
            receipt.stage != stage
            or receipt.expected_manifest_sha256 != pins[stage]
            or receipt.inventory_sha256 != inventory_sha256(files)
            or receipt.verifier_sha256 != expected_verifier_sha256
            or receipt.files_verified != len(files)
        ):
            raise ValueError("native receipt stage/inventory/procedure mismatch")
        expected.update({f"{stage}/{name}": digest for name, digest in files.items()})
        expected[f"{stage}/CANDIDATE_RECEIPT.json"] = sha256(receipt_bytes[stage])
    expected["runtime-v1/RUNTIME_MANIFEST.json"] = pins["runtime-v1"]
    expected["trusted_launcher.py"] = REVIEW_BINDINGS["launcher_sha256"]
    validate_inventory(evidence.file_hashes)
    if evidence.file_hashes != expected or evidence.inventory_sha256 != inventory_sha256(expected):
        raise ValueError("complete constituent-derived inventory differs")
    return evidence.model_dump(mode="json")


def write_operational_proposal(workspace_root: Path, snapshot_name: str) -> Path:
    """Write only a new cache proposal. CLI fixes the trusted workspace root."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", snapshot_name):
        raise ValueError("invalid cache snapshot name")
    root = workspace_root.resolve(strict=True)
    cache = root / ".cache" / "m2-02b2"
    output = cache / snapshot_name
    for path in (root / ".cache", cache, output):
        if path.is_symlink() or path.is_junction() or path.resolve() != path.absolute():
            raise ValueError("cache output cannot be aliased")
    if output.exists():
        raise ValueError("existing snapshot cannot be overwritten")
    candidate = make_candidate()
    plan = build_operational_plan(candidate)
    dossier = operational_dossier(candidate)
    template = private_eligibility_template()
    template.update(
        dict.fromkeys(
            (
                "operational_candidate_sha256",
                "python_environment_sha256",
                "python_environment_manifest_sha256",
                "private_attestation_receipt_sha256",
            )
        )
    )
    objects = {
        "operational_candidate_receipt.json": {
            "kind": "DRAFT_CONTRACT_ONLY",
            "candidate": candidate.model_dump(mode="json"),
            "model_sha256": model_sha256(candidate),
        },
        "annotation_launch_candidate.json": make_annotation_launch_candidate(candidate).model_dump(
            mode="json"
        ),
        "proposed_dropbox_mutation_plan.json": plan["topology"],
        "mapped_108_acl_checks.json": {
            "kind": "NOT_EXECUTED",
            "checks": plan["checks"],
            "application_controls": plan["application_controls"],
        },
        "synthetic_access_fixture_plan.json": {
            "kind": "PLANNED_NOT_CREATED",
            "fixtures": [
                {
                    k: row[k]
                    for k in (
                        "check_id",
                        "probe_path",
                        "probe_sha256",
                        "probe_content_utf8",
                        "preparation",
                        "cleanup",
                    )
                }
                for row in plan["checks"]
            ],
        },
        "external_write_owner_decision_packet.json": dossier["external_write_packet"],
        "eligibility_workflow_receipt.json": {
            "kind": "FUTURE_WORKFLOW_ONLY",
            "real_attestation_created": False,
            "steps": ELIGIBILITY_STEPS,
            "template": template,
        },
        "issuance_ceremony_receipt.json": {
            "kind": "FUTURE_WORKFLOW_ONLY",
            "packages_issued": False,
            "steps": ISSUANCE_STEPS,
            "templates": issuance_templates(candidate),
        },
        "operational_launch_decision_dossier.json": dossier,
    }
    files = {
        name: (json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2) + "\n").encode()
        for name, value in objects.items()
    }
    request, components = build_setup_request(candidate)
    files.update({f"setup_request_v3/{name}": raw for name, raw in components.items()})
    files["setup_request_v3/REQUEST.json"] = (
        json.dumps(request, sort_keys=True, indent=2) + "\n"
    ).encode()
    markdown = [
        "# Seven operational decisions — UNRESOLVED",
        "",
        "No owner response or operational action is recorded.",
        "",
    ]
    for decision in dossier["decisions"]:
        markdown.extend(
            [
                f"## {decision['decision_id']}",
                "",
                *[
                    f"- {key}: {json.dumps(value, ensure_ascii=False)}"
                    for key, value in decision.items()
                ],
                "",
            ]
        )
    files["operational_launch_decision_dossier.md"] = ("\n".join(markdown) + "\n").encode()
    cache.mkdir(parents=True, exist_ok=True)
    write_new_tree(output, files)
    return output


def validate_operational_plan(plan: dict[str, Any], candidate: OperationalCandidate) -> None:
    """A generated draft cannot acquire unreviewed routes, permissions or results."""
    if plan != build_operational_plan(candidate):
        raise ValueError("operational proposal differs from the exact unperformed policy mapping")
