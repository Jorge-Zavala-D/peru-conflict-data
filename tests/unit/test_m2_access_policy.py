"""Access-policy tests use policy declarations only; no real account access occurs."""

import json

import pytest
from pydantic import ValidationError

from peru_conflicts.execution.access_policy import (
    ACCESS_CHECKS_V1,
    ACCESS_POLICY_V2,
    ACCESS_POLICY_V2_SHA256,
    AccessExpectation,
    AccessPolicy,
)
from peru_conflicts.execution.launch import ACCESS_CHECKS, AccessReceipt
from peru_conflicts.hashing import canonical_json_bytes

EXPECTED_BY_ACTOR_RESOURCE = {
    "annotator-a": {
        "annotator-a/issue": ("ALLOW", "ALLOW", "DENY"),
        "annotator-a/submission": ("ALLOW", "ALLOW", "ALLOW"),
        "annotator-b/issue": ("DENY", "DENY", "DENY"),
        "annotator-b/submission": ("DENY", "DENY", "DENY"),
        "coordinator/custody": ("DENY", "DENY", "DENY"),
        "coordinator/comparison": ("DENY", "DENY", "DENY"),
        "coordinator/adjudication": ("DENY", "DENY", "DENY"),
        "coordinator/held-out-sealed": ("DENY", "DENY", "DENY"),
        "coordinator/receipts": ("DENY", "DENY", "DENY"),
        "coordinator/locked/annotator-a": ("DENY", "DENY", "DENY"),
        "coordinator/locked/annotator-b": ("DENY", "DENY", "DENY"),
        "coordinator/supersession": ("DENY", "DENY", "DENY"),
    },
    "annotator-b": {
        "annotator-a/issue": ("DENY", "DENY", "DENY"),
        "annotator-a/submission": ("DENY", "DENY", "DENY"),
        "annotator-b/issue": ("ALLOW", "ALLOW", "DENY"),
        "annotator-b/submission": ("ALLOW", "ALLOW", "ALLOW"),
        "coordinator/custody": ("DENY", "DENY", "DENY"),
        "coordinator/comparison": ("DENY", "DENY", "DENY"),
        "coordinator/adjudication": ("DENY", "DENY", "DENY"),
        "coordinator/held-out-sealed": ("DENY", "DENY", "DENY"),
        "coordinator/receipts": ("DENY", "DENY", "DENY"),
        "coordinator/locked/annotator-a": ("DENY", "DENY", "DENY"),
        "coordinator/locked/annotator-b": ("DENY", "DENY", "DENY"),
        "coordinator/supersession": ("DENY", "DENY", "DENY"),
    },
    "coordinator": {
        "annotator-a/issue": ("ALLOW", "ALLOW", "ALLOW"),
        "annotator-a/submission": ("ALLOW", "ALLOW", "ALLOW"),
        "annotator-b/issue": ("ALLOW", "ALLOW", "ALLOW"),
        "annotator-b/submission": ("ALLOW", "ALLOW", "ALLOW"),
        "coordinator/custody": ("ALLOW", "ALLOW", "ALLOW"),
        "coordinator/comparison": ("ALLOW", "ALLOW", "ALLOW"),
        "coordinator/adjudication": ("ALLOW", "ALLOW", "ALLOW"),
        "coordinator/held-out-sealed": ("ALLOW", "ALLOW", "ALLOW"),
        "coordinator/receipts": ("ALLOW", "ALLOW", "ALLOW"),
        "coordinator/locked/annotator-a": ("ALLOW", "ALLOW", "ALLOW"),
        "coordinator/locked/annotator-b": ("ALLOW", "ALLOW", "ALLOW"),
        "coordinator/supersession": ("ALLOW", "ALLOW", "ALLOW"),
    },
}

EXPECTED_ROUTES = [
    (actor, resource, operation, outcomes[index])
    for actor, resources in EXPECTED_BY_ACTOR_RESOURCE.items()
    for resource, outcomes in resources.items()
    for index, operation in enumerate(("list", "read", "write"))
]


def test_annotator_a_cannot_write_issued_package_area() -> None:
    assert any(
        actor == "annotator-a"
        and operation == "write"
        and resource == "annotator-a/issue"
        and outcome == "deny"
        for actor, operation, resource, outcome in ACCESS_CHECKS.values()
    )


@pytest.mark.parametrize(
    ("actor", "resource"),
    [
        ("annotator-a", "annotator-b/issue"),
        ("annotator-a", "annotator-b/submission"),
        ("annotator-b", "annotator-a/issue"),
        ("annotator-b", "annotator-a/submission"),
        ("annotator-a", "coordinator/custody"),
        ("annotator-a", "coordinator/comparison"),
        ("annotator-a", "coordinator/adjudication"),
        ("annotator-a", "coordinator/held-out-sealed"),
        ("annotator-a", "coordinator/receipts"),
        ("annotator-a", "coordinator/locked/annotator-a"),
        ("annotator-a", "coordinator/locked/annotator-b"),
        ("annotator-a", "coordinator/supersession"),
        ("annotator-b", "coordinator/custody"),
        ("annotator-b", "coordinator/comparison"),
        ("annotator-b", "coordinator/adjudication"),
        ("annotator-b", "coordinator/held-out-sealed"),
        ("annotator-b", "coordinator/receipts"),
        ("annotator-b", "coordinator/locked/annotator-a"),
        ("annotator-b", "coordinator/locked/annotator-b"),
        ("annotator-b", "coordinator/supersession"),
    ],
)
def test_annotators_cannot_write_foreign_or_coordinator_areas(actor: str, resource: str) -> None:
    assert (actor, "write", resource, "deny") in ACCESS_CHECKS.values()


@pytest.mark.parametrize(("actor", "resource", "operation", "expected_outcome"), EXPECTED_ROUTES)
def test_v2_declares_each_actor_resource_operation_outcome(
    actor: str, resource: str, operation: str, expected_outcome: str
) -> None:
    matches = [
        row
        for row in ACCESS_POLICY_V2.acl_expectations
        if (row.actor, row.resource, row.operation) == (actor, resource, operation)
    ]
    assert len(matches) == 1
    assert matches[0].expected_outcome == expected_outcome
    assert matches[0].control_layer == "ACL"


def test_active_compatibility_rows_are_derived_from_typed_v2_acl_rows() -> None:
    expected = {
        row.check_id: (
            row.actor,
            row.operation,
            row.resource,
            row.expected_outcome.lower(),
        )
        for row in ACCESS_POLICY_V2.acl_expectations
    }
    assert dict(ACCESS_CHECKS) == expected
    assert len(ACCESS_CHECKS) == len(EXPECTED_ROUTES)


def test_historical_v1_matrix_remains_complete_and_unchanged() -> None:
    import hashlib

    assert len(ACCESS_CHECKS_V1) == 54
    assert (
        hashlib.sha256(canonical_json_bytes(dict(ACCESS_CHECKS_V1))).hexdigest()
        == "55da64005b5e57ac0578595d65e01a7a359efc7a34232226dcdcc7ae7643df72"
    )
    with pytest.raises(TypeError):
        ACCESS_CHECKS_V1["changed"] = (  # type: ignore[index]
            "annotator-a",
            "read",
            "annotator-a/issue",
            "allow",
        )


def test_policy_identity_and_unique_rationales_are_reviewable() -> None:
    assert ACCESS_POLICY_V2.policy_version == "m2-02-real-access-tests-v2"
    assert len(ACCESS_POLICY_V2_SHA256) == 64
    rationale_ids = [row.rationale_id for row in ACCESS_POLICY_V2.acl_expectations]
    rationale_ids.extend(row.rationale_id for row in ACCESS_POLICY_V2.application_controls)
    assert len(rationale_ids) == len(set(rationale_ids))
    assert all(
        row.expected_outcome in {"ALLOW", "DENY"} for row in ACCESS_POLICY_V2.acl_expectations
    )


def test_application_immutability_does_not_replace_coordinator_acl_writes() -> None:
    controls = ACCESS_POLICY_V2.application_controls
    assert {
        (row.actor, row.resource, row.operation, row.expected_outcome, row.control_layer)
        for row in controls
    } == {
        (
            "coordinator",
            "coordinator/locked/annotator-a",
            "write",
            "APPLICATION_CONTROLLED",
            "APPLICATION",
        ),
        (
            "coordinator",
            "coordinator/locked/annotator-b",
            "write",
            "APPLICATION_CONTROLLED",
            "APPLICATION",
        ),
    }
    for resource in (
        "coordinator/locked/annotator-a",
        "coordinator/locked/annotator-b",
    ):
        assert ("coordinator", "write", resource, "allow") in ACCESS_CHECKS.values()
    assert all(
        row.expected_outcome != "APPLICATION_CONTROLLED"
        for row in ACCESS_POLICY_V2.acl_expectations
    )


def test_policy_rejects_missing_duplicate_and_lowercase_acl_rows() -> None:
    payload = ACCESS_POLICY_V2.model_dump(mode="json")
    with pytest.raises(ValidationError, match="cover every"):
        AccessPolicy.model_validate_json(
            json.dumps({**payload, "acl_expectations": payload["acl_expectations"][:-1]})
        )
    with pytest.raises(ValidationError, match="check IDs must be unique"):
        AccessPolicy.model_validate_json(
            json.dumps(
                {
                    **payload,
                    "acl_expectations": [
                        *payload["acl_expectations"],
                        payload["acl_expectations"][0],
                    ],
                }
            )
        )
    row = payload["acl_expectations"][0]
    with pytest.raises(ValidationError):
        AccessExpectation.model_validate({**row, "expected_outcome": "allow"})


def _a_issued_write_receipt(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": "REAL_ACCOUNT_ACCESS_TEST",
        "check_id": "a-write-own-issue",
        "actor": "annotator-a",
        "resource": "annotator-a/issue",
        "operation": "write",
        "expected_outcome": "DENY",
        "control_layer": "ACL",
        "rationale_id": "ACL-A-WRITE-OWN-ISSUE",
        "composite_pair_sha256": "a" * 64,
        "status": "NOT RUN",
    }
    payload.update(changes)
    return payload


def test_real_receipt_can_represent_only_a_matching_not_run_policy_row() -> None:
    receipt = AccessReceipt.model_validate(_a_issued_write_receipt())
    assert receipt.status == "NOT RUN"
    assert receipt.expected_outcome == "DENY"


@pytest.mark.parametrize("status", ["PASS", "FAIL"])
def test_real_receipt_rejects_access_outcomes_during_draft(status: str) -> None:
    with pytest.raises(ValidationError, match="remain NOT RUN"):
        AccessReceipt.model_validate(_a_issued_write_receipt(status=status))


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("actor", "annotator-b"),
        ("resource", "annotator-a/submission"),
        ("operation", "read"),
        ("expected_outcome", "ALLOW"),
        ("control_layer", "APPLICATION"),
        ("rationale_id", "ACL-WRONG-ROUTE"),
    ],
)
def test_receipt_rejects_cross_route_or_wrong_expected_outcome(
    field: str, replacement: str
) -> None:
    with pytest.raises(ValidationError):
        AccessReceipt.model_validate(_a_issued_write_receipt(**{field: replacement}))
