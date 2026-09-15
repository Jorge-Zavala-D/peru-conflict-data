"""Design approval must never become operational launch authority."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

import pytest
import yaml

from peru_conflicts.execution import launch_design as contract

ROOT = Path(__file__).resolve().parents[2]


def test_coordinator_design_contract_is_available():
    assert importlib.util.find_spec("peru_conflicts.execution.launch_design") is not None


def test_owner_design_approval_is_recorded_separately():
    assert (ROOT / "config/benchmark/m2_02b1_launch_design_approval_v1.yaml").is_file()


def test_active_design_candidate_does_not_overwrite_v1():
    assert (ROOT / "config/benchmark/m2_02_launch_candidate_v2.yaml").is_file()


@pytest.fixture
def approval_payload() -> dict[str, Any]:
    path = ROOT / "config/benchmark/m2_02b1_launch_design_approval_v1.yaml"
    assert path.is_file()
    return yaml.safe_load(path.read_bytes())


def test_exact_decisions_and_operational_boundary(approval_payload: dict[str, Any]):
    approval = contract.LaunchDesignApproval.model_validate_json(json.dumps(approval_payload))
    assert [d.decision_id for d in approval.decisions] == [
        "POSTMERGE-M2-02A-VERIFIED",
        "ISOLATED-RUNTIME",
        "RUNTIME-NEUTRALITY",
        "EXTERNAL-TOPOLOGY",
        "ELIGIBILITY-PROTOCOL",
        "AB-ACCESS-TEST-PROTOCOL",
        "HELDOUT-SEALING-LAUNCH-PROTOCOL",
        "ISSUANCE-CEREMONY",
        "PRODUCTION-LOCK-PRECONDITIONS",
        "ANNOTATOR-A-ELIGIBILITY",
        "ANNOTATOR-B-ELIGIBILITY",
        "DISTINCT-HUMANS",
        "REAL-AB-ACCESS-ISOLATION",
        "REAL-EXTERNAL-WRITE-AUTHORIZATION",
        "REAL-PACKAGE-ISSUANCE",
        "ANNOTATION-LAUNCH",
    ]
    assert [d.status for d in approval.decisions] == ["APPROVED"] * 9 + ["UNRESOLVED"] * 7
    assert [d.response for d in approval.decisions[9:]] == [None] * 7
    assert approval.owner_launch_approved is False
    assert approval.production_python_environment_approved is False
    assert approval.independent_preexecution_provisioning_required is True


@pytest.mark.parametrize(
    "mutation",
    ["missing", "extra", "rename", "reorder", "duplicate", "approve_tenth", "expand_lock_scope"],
)
def test_decision_drift_rejected(approval_payload: dict[str, Any], mutation: str):
    payload = deepcopy(approval_payload)
    rows = payload["decisions"]
    if mutation == "missing":
        rows.pop()
    elif mutation == "extra":
        rows.append(deepcopy(rows[-1]))
    elif mutation == "rename":
        rows[0]["decision_id"] = "OTHER"
    elif mutation == "reorder":
        rows[0], rows[1] = rows[1], rows[0]
    elif mutation == "duplicate":
        rows[1] = deepcopy(rows[0])
    elif mutation == "approve_tenth":
        rows[9].update(status="APPROVED", response="APPROVE")
    else:
        rows[8]["scope"] += " Production locking is authorized now."
    with pytest.raises(ValueError):
        contract.LaunchDesignApproval.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "flag",
    [
        "owner_launch_approved",
        "annotation_launch_approved",
        "annotation_started",
        "real_humans_assigned",
        "real_eligibility_attestations_created",
        "external_root_created",
        "dropbox_writes_approved",
        "real_access_tests_passed",
        "real_issuance_receipts_created",
        "real_packages_issued",
        "production_locking_enabled",
        "human_gold_created",
        "parser_work_approved",
        "normative_metric_amendment_approved",
        "m3_owner_approved",
        "production_python_environment_approved",
    ],
)
@pytest.mark.parametrize("value", [True, 1, "false"])
def test_authority_escalation_or_coercion_rejected(
    approval_payload: dict[str, Any], flag: str, value: object
):
    approval_payload[flag] = value
    with pytest.raises(ValueError):
        contract.LaunchDesignApproval.model_validate_json(json.dumps(approval_payload))


def test_valid_v2_remains_unusable_for_launch_or_lock():
    from peru_conflicts.execution.coordination import production_lock_preflight
    from peru_conflicts.execution.launch import production_launch_preflight

    candidate = contract.validate_active_design()
    assert candidate.status == "design_approved_operational_pending"
    assert candidate.launch_design_approved is True
    with pytest.raises(ValueError, match="production"):
        production_launch_preflight()
    with pytest.raises(ValueError):
        production_lock_preflight([], [], [], [])


@pytest.mark.parametrize(
    "binding",
    [
        "access_policy_sha256",
        "python_environment_sha256",
        "annotator_a_view_sha256",
        "annotator_a_package_manifest_sha256",
        "runtime_sha256",
    ],
)
def test_substituted_review_binding_rejected(approval_payload: dict[str, Any], binding: str):
    approval_payload["bindings"][binding] = "0" * 64
    with pytest.raises(ValueError):
        contract.LaunchDesignApproval.model_validate_json(json.dumps(approval_payload))


def test_v1_cannot_be_used_as_active_design():
    payload = yaml.safe_load(
        (ROOT / "config/benchmark/m2_02_launch_candidate_v1.yaml").read_bytes()
    )
    with pytest.raises(ValueError):
        contract.LaunchDesignCandidate.model_validate_json(json.dumps(payload))


def test_complete_synthetic_custody_still_cannot_lock_after_design_approval():
    from peru_conflicts.execution import coordination as custody
    from peru_conflicts.execution.packages import build_package
    from peru_conflicts.execution.references import build_manifest

    assert contract.validate_active_design().launch_design_approved is True
    pages = {1: b"Invented evidence only.\n"}
    references = [(build_manifest(260, "a" * 64, pages, "b" * 64), pages)]
    packages = tuple(
        build_package("synthetic-run", role, references) for role in ("annotator-a", "annotator-b")
    )
    assignments: tuple[tuple[Literal["annotator-a", "annotator-b"], str], ...] = (
        ("annotator-a", "synthetic-a"),
        ("annotator-b", "synthetic-b"),
    )
    people = tuple(
        custody.EligibilityAttestation(
            role=role,
            private_person_token=token,
            distinct_human_confirmed=True,
            machine_answers_seen=False,
            parser_predictions_seen=False,
            machine_prefill_seen=False,
            other_submission_seen=False,
            partition_labels_received=False,
        )
        for role, token in assignments
    )
    bindings = custody.bind_eligibility_pair(people, packages)
    receipts = tuple(custody.issuance_receipt(binding) for binding in bindings)
    custody.verify_issuance_pair(people, packages, bindings, receipts)
    with pytest.raises(ValueError, match="production locking remains disabled"):
        custody.production_lock_preflight(people, packages, bindings, receipts)


def test_real_access_pass_cannot_follow_design_approval():
    from peru_conflicts.execution.launch import AccessReceipt, real_access_test_template

    candidate = contract.validate_active_design()
    rows = real_access_test_template(candidate.reviewed_candidate.identities)
    assert len(rows) == 108
    assert all(row.status == "NOT RUN" for row in rows)
    payload = rows[0].model_dump(mode="json")
    payload["status"] = "PASS"
    with pytest.raises(ValueError):
        AccessReceipt.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "change", ["approval_sha", "package", "view", "environment", "access", "launch"]
)
def test_substituted_candidate_cannot_validate(change: str):
    payload = yaml.safe_load(contract.CANDIDATE_PATH.read_bytes())
    if change == "approval_sha":
        payload["launch_design_approval_sha256"] = "0" * 64
    elif change == "launch":
        payload["owner_launch_approved"] = True
    elif change == "access":
        payload["reviewed_candidate"]["access_policy_sha256"] = "0" * 64
    else:
        identity = payload["reviewed_candidate"]["identities"][0]
        if change == "package":
            identity["original"]["manifest_sha256"] = "0" * 64
        else:
            identity["view_sha256" if change == "view" else "python_environment_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        contract.validate_active_design(candidate_bytes=json.dumps(payload).encode())


@pytest.mark.parametrize(
    "field",
    ["python_environment_design_approved", "independent_preexecution_provisioning_required"],
)
def test_design_safeguards_require_boolean_true(approval_payload: dict[str, Any], field: str):
    approval_payload[field] = 1
    with pytest.raises(ValueError):
        contract.LaunchDesignApproval.model_validate_json(json.dumps(approval_payload))


@pytest.mark.parametrize(
    "field,value",
    [
        ("approved_count", 9.0),
        ("pending_count", 7.0),
        ("decision_count", 16.0),
        ("launch_design_decisions_approved", 9.0),
        ("launch_operational_decisions_pending", 7.0),
    ],
)
def test_decision_counts_require_exact_integer_types(
    approval_payload: dict[str, Any], field: str, value: float
):
    approval_payload[field] = value
    with pytest.raises(ValueError):
        contract.LaunchDesignApproval.model_validate_json(json.dumps(approval_payload))
