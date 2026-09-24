"""Separate real-v2 shapes. No real grant, policy, private sink or session is admitted.

The fixed empty registry is a reviewed source boundary, not caller-selected trust.
Parsing and comparing digests establish consistency only. Offline fixtures cannot
cross ``admit``; populating a registry requires a separately reviewed deployment.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, TypeAdapter, model_validator

from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.models.common import Sha256, StrictModel

from .access_policy import ACCESS_POLICY_V2_SHA256, AccessActor
from .operational_plan import build_operational_plan, evidence_json, make_candidate
from .references import sha256

_REGISTRY = b'{"grants":[],"version":"m2-real-registry-v2"}\n'
# Empty by construction; no loader argument, environment or CLI selects a registry.
_EMPTY_REGISTRY_SHA256 = hashlib.sha256(
    b'{"grants":[],"version":"m2-real-registry-v2"}\n'
).hexdigest()
PROPOSAL_SHA256 = "184ec60975b9ffe8c1e74b4b9f1bd431aa9738189e0ba093b3f3a76ab47ec0c0"
Ref = Annotated[str, Field(min_length=1, max_length=200, pattern=r"^[a-zA-Z0-9_-]+$")]
REQUIRED_CAPABILITIES = (
    "conditional_parent_identity",
    "exclusive_create_no_autorename",
    "conditional_delete_identity_version",
    "independent_sessions",
    "private_membership_and_links",
    "application_no_replace",
)


def registry_bytes() -> bytes:
    if sha256(_REGISTRY) != _EMPTY_REGISTRY_SHA256:
        raise ValueError("M2 registry pin mismatch")
    return _REGISTRY


def admit(raw: bytes, private_binding_reader: Callable[[], object]) -> None:
    """Reject before parsing untrusted grants or looking up credentials/private state."""
    registry_bytes()
    raise ValueError("production setup closed: no registered real grant")


class StrictConcurrency(StrictModel):
    mode: Literal["provider_atomic"] = "provider_atomic"
    required_guarantee: Literal["parent_identity_CAS"] = "parent_identity_CAS"


class CooperativeConcurrency(StrictModel):
    mode: Literal["supervised_cooperative"] = "supervised_cooperative"
    reviewed_policy_ref: Ref
    policy_sha256: Sha256
    scoped_session_ref: Ref
    session_evidence_sha256: Sha256
    not_before: AwareDatetime
    not_after: AwareDatetime


class ActorBinding(StrictModel):
    actor: AccessActor
    person_ref: Ref
    account_ref: Ref
    session_ref: Ref
    binding_sha256: Sha256


class SetupGrantV2(StrictModel):
    version: Literal["m2-real-setup-authorization-v2"] = "m2-real-setup-authorization-v2"
    grant_ref: Ref
    run_ref: Ref
    proposal_raw_sha256: Sha256
    component_sha256: dict[str, Sha256]
    candidate_sha256: Sha256
    access_policy_sha256: Sha256
    implementation_sha256: Sha256
    schedule_sha256: Sha256
    private_bindings_sha256: Sha256
    capability_sha256: dict[str, Sha256]
    sink_ref: Ref
    checkpoint_ref: Ref
    owner_authority_ref: Ref
    sessions: tuple[ActorBinding, ...]
    concurrency: Annotated[StrictConcurrency | CooperativeConcurrency, Field(discriminator="mode")]
    not_before: AwareDatetime
    not_after: AwareDatetime
    freshness_seconds: Annotated[int, Field(gt=0)]
    use_policy: Literal["one_run_no_redispatch"]
    cleanup_scope: Literal["receipt_owned_files_only", "prohibited"]

    @model_validator(mode="after")
    def invariants(self) -> SetupGrantV2:
        if self.not_after <= self.not_before:
            raise ValueError("unbounded validity")
        if set(self.capability_sha256) != set(REQUIRED_CAPABILITIES):
            raise ValueError("exact capability evidence references required")
        if len(self.sessions) != 3 or {x.actor for x in self.sessions} != {
            "coordinator",
            "annotator-a",
            "annotator-b",
        }:
            raise ValueError("three distinct actor bindings required")
        for field in ("person_ref", "account_ref", "session_ref"):
            if len({getattr(x, field) for x in self.sessions}) != 3:
                raise ValueError("independent people/accounts/sessions required")
        return self


def schedule() -> list[dict[str, object]]:
    """Reuse retained source objects; never reconstruct check mappings from a table."""
    plan = build_operational_plan(make_candidate())
    return [dict(row) for row in plan["checks"]]


def validate_grant(
    raw: bytes,
    request: bytes,
    components: dict[str, bytes],
    implementation_sha256: str,
    now: datetime,
) -> SetupGrantV2:
    """Consistency validator, deliberately not an authority issuer."""
    from .operational_plan import validate_setup_request

    evidence_json(raw)
    grant = SetupGrantV2.model_validate_json(raw)
    validate_setup_request(request, components, make_candidate())
    proposal = evidence_json(request)
    if (
        sha256(request) != PROPOSAL_SHA256
        or grant.proposal_raw_sha256 != PROPOSAL_SHA256
        or grant.component_sha256 != {n: sha256(b) for n, b in components.items()}
        or grant.candidate_sha256 != proposal["candidate_model_sha256"]
        or grant.access_policy_sha256 != ACCESS_POLICY_V2_SHA256
        or grant.implementation_sha256 != implementation_sha256
        or grant.schedule_sha256 != sha256(canonical_json_bytes(schedule()))
        or now.tzinfo is None
        or not grant.not_before <= now < grant.not_after
    ):
        raise ValueError("grant proposal/scope/implementation/validity mismatch")
    return grant


def require_concurrency(
    grant: SetupGrantV2, trusted_policy_digest: str | None, now: datetime
) -> None:
    """An independent admission source supplies policy trust, never a work-order flag."""
    policy = grant.concurrency
    if isinstance(policy, StrictConcurrency):
        raise ValueError("BLOCKED: Dropbox folder creation has no parent identity CAS")
    if (
        trusted_policy_digest != sha256(canonical_json_bytes(policy.model_dump(mode="json")))
        or not policy.not_before <= now < policy.not_after
    ):
        raise ValueError("BLOCKED: no independently admitted cooperative session policy")


def real_schema_bytes() -> bytes:
    """Additive shapes only; no change to frozen v1 or scientific contracts."""
    from .setup_dropbox import OriginalCapture, RealWorkOrder, ValidatedOutcome
    from .setup_evidence import ComponentReceipt

    schema = TypeAdapter(
        SetupGrantV2 | RealWorkOrder | OriginalCapture | ValidatedOutcome | ComponentReceipt
    ).json_schema()
    return (json.dumps(schema, sort_keys=True, indent=2) + "\n").encode()


def export_real_schema(root: Path) -> Path:
    path = root / "execution" / "setup_real_v2.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(real_schema_bytes())
    return path
