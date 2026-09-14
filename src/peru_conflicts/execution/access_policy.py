"""Versioned access expectations for the future M2-02 real-account ceremony.

This module declares reviewable expectations only.  It neither provisions an
account nor performs an access check.
"""

from __future__ import annotations

import hashlib
from itertools import product
from types import MappingProxyType
from typing import Literal, Self

from pydantic import Field, model_validator

from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.models.common import StrictModel

AccessActor = Literal["annotator-a", "annotator-b", "coordinator"]
AccessResource = Literal[
    "annotator-a/issue",
    "annotator-a/submission",
    "annotator-b/issue",
    "annotator-b/submission",
    "coordinator/custody",
    "coordinator/comparison",
    "coordinator/adjudication",
    "coordinator/held-out-sealed",
    "coordinator/receipts",
    "coordinator/locked/annotator-a",
    "coordinator/locked/annotator-b",
    "coordinator/supersession",
]
AccessOperation = Literal["list", "read", "write"]
AclOutcome = Literal["ALLOW", "DENY"]
LockedResource = Literal["coordinator/locked/annotator-a", "coordinator/locked/annotator-b"]

ACTORS: tuple[AccessActor, ...] = ("annotator-a", "annotator-b", "coordinator")
RESOURCES: tuple[AccessResource, ...] = (
    "annotator-a/issue",
    "annotator-a/submission",
    "annotator-b/issue",
    "annotator-b/submission",
    "coordinator/custody",
    "coordinator/comparison",
    "coordinator/adjudication",
    "coordinator/held-out-sealed",
    "coordinator/receipts",
    "coordinator/locked/annotator-a",
    "coordinator/locked/annotator-b",
    "coordinator/supersession",
)
OPERATIONS: tuple[AccessOperation, ...] = ("list", "read", "write")


# Historical v1 content is retained byte-for-byte in meaning and protected from
# mutation.  It is not the active protocol.
ACCESS_CHECKS_V1 = MappingProxyType(
    {
        "a-read-own-issue": ("annotator-a", "read", "annotator-a/issue", "allow"),
        "a-write-own-submission": (
            "annotator-a",
            "write",
            "annotator-a/submission",
            "allow",
        ),
        "b-read-own-issue": ("annotator-b", "read", "annotator-b/issue", "allow"),
        "b-write-own-submission": (
            "annotator-b",
            "write",
            "annotator-b/submission",
            "allow",
        ),
        **{
            f"coordinator-{operation}-{area}-{role}": (
                "coordinator",
                operation,
                f"annotator-{role}/{area}",
                "allow",
            )
            for role in ("a", "b")
            for area in ("issue", "submission")
            for operation in ("list", "read")
        },
        **{
            f"{role}-{operation}-other-{area}": (
                f"annotator-{role}",
                operation,
                f"annotator-{other}/{area}",
                "deny",
            )
            for role, other in (("a", "b"), ("b", "a"))
            for area in ("issue", "submission")
            for operation in ("list", "read")
        },
        **{
            f"{role}-{operation}-{area}": (
                f"annotator-{role}",
                operation,
                f"coordinator/{area}",
                "deny",
            )
            for role in ("a", "b")
            for area in (
                "custody",
                "comparison",
                "adjudication",
                "held-out-sealed",
                "receipts",
                "locked/annotator-a",
                "locked/annotator-b",
                "supersession",
            )
            for operation in ("list", "read")
        },
        **{
            f"coordinator-{operation}-custody": (
                "coordinator",
                operation,
                "coordinator/custody",
                "allow",
            )
            for operation in ("list", "read")
        },
    }
)


class AccessExpectation(StrictModel):
    """One ACL outcome that a future real-account test must observe."""

    check_id: str = Field(pattern=r"^[a-z0-9][a-z0-9/-]*$")
    actor: AccessActor
    resource: AccessResource
    operation: AccessOperation
    expected_outcome: AclOutcome
    control_layer: Literal["ACL"] = "ACL"
    rationale_id: str = Field(pattern=r"^ACL-[A-Z0-9-]+$")


class ApplicationImmutabilityRule(StrictModel):
    """A provenance rule applied after ACL-authorized coordinator writes."""

    control_id: str = Field(pattern=r"^APP-[A-Z0-9-]+$")
    actor: Literal["coordinator"] = "coordinator"
    resource: LockedResource
    operation: Literal["write"] = "write"
    expected_outcome: Literal["APPLICATION_CONTROLLED"] = "APPLICATION_CONTROLLED"
    control_layer: Literal["APPLICATION"] = "APPLICATION"
    rationale_id: str = Field(pattern=r"^APP-[A-Z0-9-]+$")
    rule: Literal["accepted bytes are hash-controlled and superseded append-only"] = (
        "accepted bytes are hash-controlled and superseded append-only"
    )


class AccessPolicy(StrictModel):
    """Complete, versioned ACL matrix plus non-ACL immutability controls."""

    policy_version: Literal["m2-02-real-access-tests-v2"] = "m2-02-real-access-tests-v2"
    acl_expectations: tuple[AccessExpectation, ...] = Field(min_length=1)
    application_controls: tuple[ApplicationImmutabilityRule, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def complete_and_unique(self) -> Self:
        check_ids = [row.check_id for row in self.acl_expectations]
        routes = [(row.actor, row.resource, row.operation) for row in self.acl_expectations]
        rationale_ids = [row.rationale_id for row in self.acl_expectations]
        rationale_ids.extend(row.rationale_id for row in self.application_controls)
        control_ids = [row.control_id for row in self.application_controls]
        expected_routes = set(product(ACTORS, RESOURCES, OPERATIONS))
        if len(check_ids) != len(set(check_ids)):
            raise ValueError("access check IDs must be unique")
        if len(routes) != len(set(routes)):
            raise ValueError("access actor/resource/operation routes must be unique")
        if set(routes) != expected_routes:
            raise ValueError("access policy must cover every actor/resource/operation route")
        if len(rationale_ids) != len(set(rationale_ids)):
            raise ValueError("access rationale IDs must be unique")
        if len(control_ids) != len(set(control_ids)):
            raise ValueError("application control IDs must be unique")
        expected_controls = {
            ("coordinator", resource, "write")
            for resource in (
                "coordinator/locked/annotator-a",
                "coordinator/locked/annotator-b",
            )
        }
        actual_controls = {
            (row.actor, row.resource, row.operation) for row in self.application_controls
        }
        if actual_controls != expected_controls:
            raise ValueError("application controls must cover both accepted-byte lock areas")
        return self


def _outcome(
    actor: AccessActor, resource: AccessResource, operation: AccessOperation
) -> AclOutcome:
    if actor == "coordinator":
        return "ALLOW"
    if resource == f"{actor}/submission":
        return "ALLOW"
    if resource == f"{actor}/issue" and operation in ("list", "read"):
        return "ALLOW"
    return "DENY"


def _check_id(actor: AccessActor, resource: AccessResource, operation: AccessOperation) -> str:
    role = actor.removeprefix("annotator-")
    if actor == "coordinator":
        if resource.startswith("annotator-"):
            owner, area = resource.split("/", maxsplit=1)
            return f"coordinator-{operation}-{area}-{owner.removeprefix('annotator-')}"
        return f"coordinator-{operation}-{resource.removeprefix('coordinator/')}"
    if resource.startswith("annotator-"):
        owner, area = resource.split("/", maxsplit=1)
        relationship = "own" if owner == actor else "other"
        return f"{role}-{operation}-{relationship}-{area}"
    return f"{role}-{operation}-{resource.removeprefix('coordinator/')}"


def _rationale_id(check_id: str) -> str:
    return "ACL-" + check_id.replace("/", "-").upper()


def _build_v2() -> AccessPolicy:
    expectations = tuple(
        AccessExpectation(
            check_id=(check_id := _check_id(actor, resource, operation)),
            actor=actor,
            resource=resource,
            operation=operation,
            expected_outcome=_outcome(actor, resource, operation),
            rationale_id=_rationale_id(check_id),
        )
        for actor, resource, operation in product(ACTORS, RESOURCES, OPERATIONS)
    )
    control_specs: tuple[tuple[str, LockedResource], ...] = (
        ("A", "coordinator/locked/annotator-a"),
        ("B", "coordinator/locked/annotator-b"),
    )
    controls = tuple(
        ApplicationImmutabilityRule(
            control_id=f"APP-ACCEPTED-BYTES-{role}",
            resource=resource,
            rationale_id=f"APP-HASH-CONTROLLED-SUPERSESSION-{role}",
        )
        for role, resource in control_specs
    )
    return AccessPolicy(acl_expectations=expectations, application_controls=controls)


ACCESS_POLICY_V2 = _build_v2()
ACCESS_POLICY_V2_SHA256 = hashlib.sha256(
    canonical_json_bytes(ACCESS_POLICY_V2.model_dump(mode="json"))
).hexdigest()

# Compatibility view for existing receipt iteration.  Only the active v2 ACL
# rows appear here; application controls are intentionally separate.
ACCESS_CHECKS = MappingProxyType(
    {
        row.check_id: (
            row.actor,
            row.operation,
            row.resource,
            row.expected_outcome.lower(),
        )
        for row in ACCESS_POLICY_V2.acl_expectations
    }
)

ACCESS_EXPECTATIONS_BY_ID = MappingProxyType(
    {row.check_id: row for row in ACCESS_POLICY_V2.acl_expectations}
)
