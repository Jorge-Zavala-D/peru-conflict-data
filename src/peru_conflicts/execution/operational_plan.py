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


def build_operational_plan(candidate: OperationalCandidate) -> dict[str, Any]:
    """Exact proposal only: derives routes from the approved policy, performs no I/O."""
    candidate = OperationalCandidate.model_validate_json(candidate.model_dump_json())
    topology = cast(dict[str, Any], proposed_topology())
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
                "preparation": (
                    "Coordinator creates probe after scoped write approval."
                    if row.operation != "write"
                    else "Target absent before test; actor attempts unique probe creation."
                ),
                "cleanup": {
                    "path": probe_path,
                    "expected_sha256": sha256(probe),
                    "rule": "Receipt-bound exact probe removal only after scoped authorization.",
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
        "controls; inspect ancestor/group/link inheritance."
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
        "After separate issuance authority only, deliver A package to A issue "
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
    root = str(proposed_topology()["root"])
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


def validate_environment_candidate(raw: bytes, *, expected_sha256: str) -> dict[str, Any]:
    """Portable evidence validation, not native authentication or owner approval."""
    if sha256(raw) != expected_sha256:
        raise ValueError("independent environment evidence pin required")
    document = json.loads(raw)
    if not isinstance(document, dict):
        raise ValueError("environment evidence must be an object")
    data = cast(dict[str, Any], document)
    required = {
        "kind": "PRODUCTION_ENVIRONMENT_CANDIDATE_NOT_APPROVED",
        "protected_main": MERGE_SHA,
        "runtime_file_set_sha256": REVIEW_BINDINGS["runtime_file_set_sha256"],
        "dependency_manifest_sha256": REVIEW_BINDINGS["dependency_sha256"],
    }
    if any(data.get(k) != v for k, v in required.items()):
        raise ValueError("environment authority identities differ")
    if (
        data.get("production_candidate_prepared") is not True
        or data.get("production_environment_approved") is not False
        or data.get("candidate_python_executed") is not False
    ):
        raise ValueError("native preparation cannot imply execution or approval")
    for key in ("os", "platform", "trust_boundary", "python_provenance", "launcher_usage"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise ValueError("environment trust declaration missing")
    inventory = data.get("file_hashes")
    if not isinstance(inventory, dict):
        raise ValueError("complete prepared inventory required")
    inventory = cast(dict[str, Any], inventory)
    if len(inventory) != 2222:
        raise ValueError("complete prepared inventory required")
    for name, digest in inventory.items():
        if (
            not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or "\\" in name
            or ":" in name
            or name.startswith("/")
            or any(part in ("", ".", "..") for part in name.split("/"))
        ):
            raise ValueError("invalid environment inventory entry")
    if (
        inventory.get("python-v2/python.exe") != REVIEW_BINDINGS["interpreter_sha256"]
        or inventory.get("trusted_launcher.py") != REVIEW_BINDINGS["launcher_sha256"]
    ):
        raise ValueError("interpreter or launcher identity differs")
    stages = data.get("stages")
    if not isinstance(stages, dict):
        raise ValueError("all native stages required")
    stages = cast(dict[str, Any], stages)
    if set(stages) != {
        "python-v2",
        "dependencies-v1",
        "runtime-v1",
    }:
        raise ValueError("all native stages required")
    for stage, count, pin in (
        ("python-v2", 2046, REVIEW_BINDINGS["python_environment_manifest_sha256"]),
        ("dependencies-v1", 152, REVIEW_BINDINGS["dependency_sha256"]),
        ("runtime-v1", 19, "4d5f8273ff210cf39eb2b105743b26ac8f3e1e1e5851e342dee09f41a9c8b346"),
    ):
        if not isinstance(stages[stage], dict) or not isinstance(
            stages[stage].get("receipt"), dict
        ):
            raise ValueError("native stage must contain an object receipt")
        receipt = cast(dict[str, Any], stages[stage]["receipt"])
        if (
            receipt.get("files_verified") != count
            or type(receipt.get("files_verified")) is not int
            or receipt.get("expected_manifest_sha256") != pin
            or receipt.get("production_candidate_prepared") is not True
            or receipt.get("production_environment_approved") is not False
            or receipt.get("python_executed") is not False
        ):
            raise ValueError("native stage identity or state differs")
    return data


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
