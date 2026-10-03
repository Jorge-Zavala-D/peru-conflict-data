"""Manual consistency checks and a CLOSED, synthetic-only original/accepted consumer.

Independent context and witness pins are out-of-band trust inputs, not fields an
imported observation can approve. Hash equality is consistency, not event truth.
No function performs provider work or admits real launch/storage authority.
"""

from __future__ import annotations

import json
from collections.abc import Generator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, TypeAdapter

from peru_conflicts.acquisition.fs_safety import DirectoryLease, DirectoryLeaseError
from peru_conflicts.acquisition.persistent_ledger import (
    _KernelLock,  # pyright: ignore[reportPrivateUsage]
)
from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.models.common import Sha256, StrictModel

from .access_policy import (
    ACCESS_POLICY_V2,
    ACTORS,
    RESOURCES,
    AccessActor,
    AccessExpectation,
    AccessOperation,
    AccessResource,
)
from .coordination import (
    EligibilityAttestation,
    EligibilityBinding,
    IssuedPackageIdentity,
    bind_eligibility_pair,
    package_identity,
)
from .neutral_forms import validate_neutral_forms
from .packages import FORM_HEADERS, PackageManifest, verify_package
from .references import sha256
from .runtime_build import NeutralViewIdentity
from .setup_evidence import publish, require_offline_root

PROFILE = "M2-02-OWNER-ASSISTED-EVIDENCE-V1"
Profile = Literal["M2-02-OWNER-ASSISTED-EVIDENCE-V1"]
ManualMode = Literal["SYNTHETIC", "MANUALLY_WITNESSED"]
Role = Literal["annotator-a", "annotator-b"]


def digest_value(value: object) -> str:
    return sha256(canonical_json_bytes(value))


def digest(value: StrictModel) -> str:
    return digest_value(value.model_dump(mode="json"))


class ManualTarget(StrictModel):
    actor: AccessActor
    resource: AccessResource
    session_ref: str = Field(min_length=1)
    namespace: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    parent_id: str = Field(min_length=1)
    probe_id: str = Field(min_length=1)
    probe_sha256: Sha256
    ownership_ref: str = Field(min_length=1)


class ManualConcealmentRule(StrictModel):
    """Independently approved, provider-grounded context; never a capture boolean."""

    provider_document_sha256: Sha256
    approval_ref: str = Field(min_length=1)
    target_context_sha256: Sha256


class ManualBinding(StrictModel):
    profile: Profile = PROFILE
    run_id: Literal["m2-02-v1", "synthetic-run"]
    mode: ManualMode
    source_sha256: Sha256
    policy_sha256: Sha256
    coordinator_ref: str = Field(min_length=1)
    witness_ref: str = Field(min_length=1)
    owner_ref: str = Field(min_length=1)
    not_before: AwareDatetime
    not_after: AwareDatetime
    targets: tuple[ManualTarget, ...]
    concealment: ManualConcealmentRule | None = None


def _binding(value: ManualBinding) -> ManualBinding:
    value = ManualBinding.model_validate_json(value.model_dump_json())
    routes = [(t.actor, t.resource) for t in value.targets]
    expected = {(a, r) for a in ACTORS for r in RESOURCES}
    if len(routes) != 36 or set(routes) != expected:
        raise ValueError("manual target context must cover the exact 36 actor/resources")
    if value.policy_sha256 != digest(ACCESS_POLICY_V2):
        raise ValueError("manual policy differs from unchanged canonical 108 mappings")
    if (
        value.not_before >= value.not_after
        or len({value.coordinator_ref, value.witness_ref, value.owner_ref}) != 3
    ):
        raise ValueError("independent owner/coordinator/witness and finite window required")
    if (value.mode == "SYNTHETIC") != (value.run_id == "synthetic-run"):
        raise ValueError("synthetic evidence cannot become real run evidence")
    if value.concealment is not None and value.concealment.target_context_sha256 != digest_value(
        [t.model_dump(mode="json") for t in value.targets]
    ):
        raise ValueError("concealment rule differs from independently admitted target context")
    sessions = [{t.session_ref for t in value.targets if t.actor == actor} for actor in ACTORS]
    if (
        any(len(s) != 1 for s in sessions)
        or len({session for group in sessions for session in group}) != 3
    ):
        raise ValueError("distinct actor-authenticated sessions required")
    return value


class ManualProbeCleanup(StrictModel):
    """Observed cooperative probe cleanup, NOT provider CAS or retry certification."""

    ownership_ref: str
    probe_id: str
    probe_sha256: Sha256
    target_id: str
    before_observed: bool
    after_absent: bool
    completed_at: AwareDatetime


class ManualOperationOriginal(StrictModel):
    """Secret-free retained result/export description; independent witness required."""

    kind: Literal["MANUAL_OPERATION_ORIGINAL_V1"] = "MANUAL_OPERATION_ORIGINAL_V1"
    actor: AccessActor
    session_ref: str
    namespace: str
    locator: str
    operation: AccessOperation
    scope_complete: bool
    target_id: str
    parent_id: str
    before_exists: bool
    after_exists: bool
    status: int = Field(ge=100, le=599)
    error: (
        Literal[
            "no_write_permission", "not_found", "authentication", "restricted_content", "ambiguous"
        ]
        | None
    )
    observed_id: str | None = None
    returned_locator: str | None = None
    entry_ids: tuple[str, ...] = ()
    listing_complete: bool = False
    read_sha256: Sha256 | None = None
    write_sha256: Sha256 | None = None
    autorenamed: bool = False
    cleanup: ManualProbeCleanup | None = None


class ManualObservation(StrictModel):
    kind: Literal["INDEPENDENTLY_WITNESSED_MANUAL_OBSERVATION_V1"] = (
        "INDEPENDENTLY_WITNESSED_MANUAL_OBSERVATION_V1"
    )
    binding_sha256: Sha256
    sequence: int = Field(ge=1)
    check_id: str
    actor: AccessActor
    resource: AccessResource
    operation: AccessOperation
    started_at: AwareDatetime
    completed_at: AwareDatetime | None
    state: Literal["STARTED", "ACKNOWLEDGED_ASYNC", "COMPLETED", "UNKNOWN"]
    original_sha256: Sha256


class ManualApplicationControl(StrictModel):
    kind: Literal["SYNTHETIC_MANUAL_CONSUMER_CONTROL_V1"] = "SYNTHETIC_MANUAL_CONSUMER_CONTROL_V1"
    control_id: Literal["APP-ACCEPTED-BYTES-A", "APP-ACCEPTED-BYTES-B"]
    role: Role
    binding_sha256: Sha256
    consumer_sha256: Sha256
    store_sha256: Sha256
    original_sha256: Sha256
    preserved_sha256: Sha256
    checkpoint_sha256: Sha256
    overwrite_error: Literal["FileExistsError"]
    supersession_sha256: Sha256
    started_at: AwareDatetime
    completed_at: AwareDatetime


class ManualWitnessIndex(StrictModel):
    kind: Literal["INDEPENDENT_MANUAL_WITNESS_INDEX_V1"] = "INDEPENDENT_MANUAL_WITNESS_INDEX_V1"
    binding_sha256: Sha256
    mode: ManualMode
    witness_ref: str
    observation_sha256s: tuple[Sha256, ...]
    control_sha256s: tuple[Sha256, ...] = ()
    progress_sha256s: tuple[Sha256, ...] = ()


class ManualOutcome(StrictModel):
    check: AccessExpectation
    result: Literal["PASS", "FAIL", "INCONCLUSIVE"]
    reason: str
    original_sha256: Sha256


class ManualIsolationReport(StrictModel):
    kind: Literal["MANUAL_TECHNICAL_CONSISTENCY_NOT_OWNER_ACCEPTANCE_V1"] = (
        "MANUAL_TECHNICAL_CONSISTENCY_NOT_OWNER_ACCEPTANCE_V1"
    )
    binding_sha256: Sha256
    witness_index_sha256: Sha256
    outcomes: tuple[ManualOutcome, ...]
    controls: tuple[ManualApplicationControl, ...]
    unresolved_action_refs: tuple[str, ...]
    first_action_at: AwareDatetime
    completed_at: AwareDatetime | None
    complete_consistency: bool
    real_isolation_approved: Literal[False] = False


def _classify(
    binding: ManualBinding,
    check: AccessExpectation,
    observation: ManualObservation,
    original: ManualOperationOriginal,
) -> ManualOutcome:
    result: Literal["PASS", "FAIL", "INCONCLUSIVE"] = "INCONCLUSIVE"
    reason = "unestablished operation/context/effect"
    target = next(
        t for t in binding.targets if (t.actor, t.resource) == (check.actor, check.resource)
    )
    context_ok = (
        original.actor == target.actor
        and original.session_ref == target.session_ref
        and original.namespace == target.namespace
        and original.locator == target.locator
        and original.operation == check.operation
        and original.scope_complete
        and original.target_id == target.target_id
        and original.parent_id == target.parent_id
        and original.before_exists
        and original.after_exists
    )
    if context_ok and observation.state == "COMPLETED":
        denied = original.status == 409 and (
            (check.operation == "write" and original.error == "no_write_permission")
            or (
                check.operation in ("list", "read")
                and original.error == "not_found"
                and binding.concealment is not None
            )
        )
        succeeded = (
            original.status == 200
            and original.error is None
            and original.observed_id == target.probe_id
        )
        if succeeded and check.expected_outcome == "DENY":
            result, reason = "FAIL", "unexpected forbidden success"
        elif denied and (
            original.observed_id is not None
            or original.returned_locator is not None
            or original.entry_ids
            or original.listing_complete
            or original.read_sha256 is not None
            or original.write_sha256 is not None
            or original.cleanup is not None
            or original.autorenamed
        ):
            reason = "denial contradicts retained success/effect evidence"
        elif denied:
            result = "PASS" if check.expected_outcome == "DENY" else "FAIL"
            reason = "scoped explicit write denial or separately admitted concealment"
        elif succeeded:
            located = original.returned_locator == target.locator and not original.autorenamed
            cleanup = original.cleanup
            valid_cleanup = cleanup is not None and (
                cleanup.ownership_ref == target.ownership_ref
                and cleanup.probe_id == target.probe_id
                and cleanup.probe_sha256 == target.probe_sha256
                and cleanup.target_id == target.target_id
                and cleanup.before_observed
                and cleanup.after_absent
                and observation.completed_at is not None
                and observation.started_at <= cleanup.completed_at <= observation.completed_at
            )
            confirmed = (
                (
                    check.operation == "list"
                    and original.listing_complete
                    and len(original.entry_ids) == len(set(original.entry_ids))
                    and target.probe_id in original.entry_ids
                )
                or (check.operation == "read" and original.read_sha256 == target.probe_sha256)
                or (
                    check.operation == "write"
                    and original.write_sha256 == target.probe_sha256
                    and valid_cleanup
                )
            )
            if located and confirmed:
                result, reason = "PASS", "target-bound observed operation and owned probe cleanup"
            elif original.autorenamed or not located:
                result, reason = "FAIL", "replacement or unexpected/auto-renamed target"
    return ManualOutcome(
        check=check, result=result, reason=reason, original_sha256=observation.original_sha256
    )


def verify_manual_observations(
    binding: ManualBinding,
    observations: Sequence[ManualObservation],
    originals: Mapping[str, bytes],
    witness_raw: bytes,
    *,
    trusted_witness_sha256: str,
    controls: Sequence[ManualApplicationControl] = (),
    progress: Sequence[ManualActionEvent] = (),
) -> ManualIsolationReport:
    """Read-only; trusted context/pin must come independently, not from imported evidence."""
    binding = _binding(binding)
    observations = tuple(
        ManualObservation.model_validate_json(o.model_dump_json()) for o in observations
    )
    controls = tuple(
        ManualApplicationControl.model_validate_json(c.model_dump_json()) for c in controls
    )
    if sha256(witness_raw) != trusted_witness_sha256:
        raise ValueError("manual witness differs from independently trusted pin")
    witness = ManualWitnessIndex.model_validate_json(witness_raw)
    if (witness.binding_sha256, witness.mode, witness.witness_ref) != (
        digest(binding),
        binding.mode,
        binding.witness_ref,
    ):
        raise ValueError("wrong manual witness/context/mode")
    if witness.observation_sha256s != tuple(
        digest(o) for o in observations
    ) or witness.control_sha256s != tuple(digest(c) for c in controls):
        raise ValueError("substituted observation/control differs from independent witness")
    unresolved = verify_manual_progress(
        binding, progress, originals, trusted_event_sha256s=witness.progress_sha256s
    )
    checks = ACCESS_POLICY_V2.acl_expectations
    if len(observations) != len(checks):
        raise ValueError("exact 108 manual check IDs required")
    outcomes: list[ManualOutcome] = []
    previous = binding.not_before
    for sequence, (check, observation) in enumerate(zip(checks, observations, strict=True), 1):
        if (
            observation.sequence,
            observation.check_id,
            observation.actor,
            observation.resource,
            observation.operation,
            observation.binding_sha256,
        ) != (
            sequence,
            check.check_id,
            check.actor,
            check.resource,
            check.operation,
            digest(binding),
        ):
            raise ValueError("manual mapping/order/source/run differs from canonical schedule")
        if not previous <= observation.started_at <= binding.not_after:
            raise ValueError("stale or out-of-order manual evidence")
        if (
            observation.completed_at is not None
            and not observation.started_at <= observation.completed_at <= binding.not_after
        ):
            raise ValueError("invalid completion time")
        if (observation.state == "COMPLETED") != (observation.completed_at is not None):
            raise ValueError("started/unknown is not completed evidence")
        previous = observation.completed_at or observation.started_at
        raw = originals.get(observation.original_sha256)
        if raw is None or sha256(raw) != observation.original_sha256:
            raise ValueError("missing or substituted retained original")
        outcomes.append(
            _classify(binding, check, observation, ManualOperationOriginal.model_validate_json(raw))
        )
    if controls:
        if binding.mode != "SYNTHETIC":
            raise ValueError("synthetic consumer controls are not real isolation evidence")
        expected = [
            (c.control_id, c.resource.rsplit("/", 1)[1])
            for c in ACCESS_POLICY_V2.application_controls
        ]
        if [(c.control_id, c.role) for c in controls] != expected or len(
            {c.store_sha256 for c in controls}
        ) != 2:
            raise ValueError("two distinct A/B consumer controls required, not ACL rows")
        for control in controls:
            if (
                control.binding_sha256 != digest(binding)
                or control.consumer_sha256 != sha256(Path(__file__).read_bytes())
                or control.original_sha256 != control.preserved_sha256
                or control.checkpoint_sha256 != control.original_sha256
                or not binding.not_before
                <= control.started_at
                <= control.completed_at
                <= binding.not_after
            ):
                raise ValueError("control source/binding/prior-byte/checkpoint mismatch")
    starts = (
        [o.started_at for o in observations]
        + [c.started_at for c in controls]
        + [e.at for e in progress]
    )
    ends = (
        [o.completed_at for o in observations if o.completed_at is not None]
        + [c.completed_at for c in controls]
        + [e.at for e in progress]
    )
    return ManualIsolationReport(
        binding_sha256=digest(binding),
        witness_index_sha256=sha256(witness_raw),
        outcomes=tuple(outcomes),
        controls=controls,
        unresolved_action_refs=unresolved,
        first_action_at=min(starts),
        completed_at=max(ends)
        if not unresolved and all(o.completed_at is not None for o in observations)
        else None,
        complete_consistency=len(controls) == 2
        and not unresolved
        and all(o.result == "PASS" for o in outcomes),
    )


class ManualActionEvent(StrictModel):
    sequence: int = Field(ge=1)
    action_ref: str = Field(min_length=1)
    kind: Literal["mutation", "reconcile"]
    state: Literal["STARTED", "ACKNOWLEDGED_ASYNC", "COMPLETED", "UNKNOWN"]
    at: AwareDatetime
    binding_sha256: Sha256
    actor: AccessActor
    resource: AccessResource
    session_ref: str
    namespace: str
    target_id: str
    witness_ref: str
    evidence_sha256: Sha256


def verify_manual_progress(
    binding: ManualBinding,
    events: Sequence[ManualActionEvent],
    originals: Mapping[str, bytes],
    *,
    trusted_event_sha256s: Sequence[str],
) -> tuple[str, ...]:
    """No dispatcher/retry: unresolved effects permit only read-only reconciliation."""
    binding = _binding(binding)
    if tuple(digest(e) for e in events) != tuple(trusted_event_sha256s):
        raise ValueError("progress differs from independently trusted witness events")
    states: dict[str, str] = {}
    contexts: dict[str, tuple[str, str, str]] = {}
    previous: datetime | None = None
    for sequence, value in enumerate(events, 1):
        event = ManualActionEvent.model_validate_json(value.model_dump_json())
        target = next(
            t for t in binding.targets if (t.actor, t.resource) == (event.actor, event.resource)
        )
        raw = originals.get(event.evidence_sha256)
        if (
            (
                event.binding_sha256,
                event.session_ref,
                event.namespace,
                event.target_id,
                event.witness_ref,
            )
            != (
                digest(binding),
                target.session_ref,
                target.namespace,
                target.target_id,
                binding.witness_ref,
            )
            or raw is None
            or not raw
            or sha256(raw) != event.evidence_sha256
            or not binding.not_before <= event.at <= binding.not_after
        ):
            raise ValueError("progress run/source/actor/session/namespace/target/original mismatch")
        context = (event.actor, event.resource, event.target_id)
        if event.action_ref in contexts and contexts[event.action_ref] != context:
            raise ValueError("progress action target substitution")
        contexts[event.action_ref] = context
        if event.sequence != sequence or (previous is not None and event.at < previous):
            raise ValueError("progress order/time mismatch")
        previous = event.at
        current = states.get(event.action_ref)
        if event.kind == "reconcile":
            if (
                current not in ("STARTED", "UNKNOWN", "ACKNOWLEDGED_ASYNC")
                or event.state != "COMPLETED"
            ):
                raise ValueError("reconciliation needs an unresolved original action")
        elif event.state == "STARTED":
            if current is not None or any(state != "COMPLETED" for state in states.values()):
                raise ValueError("repeat/dependent mutation prohibited while effect uncertain")
        elif current != "STARTED":
            raise ValueError("missing start or repeated/unknown mutation completion")
        states[event.action_ref] = event.state
    return tuple(ref for ref, state in states.items() if state != "COMPLETED")


class ManualMaterialIdentity(StrictModel):
    """Versioned manual relationship; historical originals/views remain unissued."""

    original: IssuedPackageIdentity
    view: NeutralViewIdentity
    field_registry_sha256: Sha256
    official_report_sha256s: tuple[Sha256, ...]
    surface: Literal["NON_EXECUTABLE_VIEWER_UTF8_EDITOR"] = "NON_EXECUTABLE_VIEWER_UTF8_EDITOR"


def manual_material_identity(
    files: Mapping[str, bytes], view: NeutralViewIdentity, *, field_registry_sha256: str
) -> ManualMaterialIdentity:
    identity = package_identity(files)
    view = NeutralViewIdentity.model_validate_json(view.model_dump_json())
    if set(view.file_hashes) != set(files) or any(
        view.file_hashes[name] != sha256(raw)
        for name, raw in files.items()
        if name not in ("DATE_PAIR_INTERPRETATION.md", "FORM_GUIDE.md")
    ):
        raise ValueError("manual view has missing, private/extra or substituted source files")
    if (view.original_package_id, view.original_package_sha256, view.contract_sha256) != (
        identity.package_id,
        identity.manifest_sha256,
        sha256(canonical_json_bytes(identity.contract_identity.model_dump(mode="json")) + b"\n"),
    ):
        raise ValueError("manual view differs from preserved original/contract")
    return ManualMaterialIdentity(
        original=identity,
        view=view,
        field_registry_sha256=field_registry_sha256,
        official_report_sha256s=tuple(r.source_sha256 for r in verify_package(files).references),
    )


STAGES = (
    "SETUP_PERMISSION",
    "ISOLATION_ACCEPTANCE",
    "ENVIRONMENT_CUSTODY_APPROVAL",
    "DELIVERY_PERMISSION",
    "DELIVERY_ACCEPTANCE",
    "ANNOTATION_LAUNCH_PERMISSION",
)
Stage = Literal[
    "SETUP_PERMISSION",
    "ISOLATION_ACCEPTANCE",
    "ENVIRONMENT_CUSTODY_APPROVAL",
    "DELIVERY_PERMISSION",
    "DELIVERY_ACCEPTANCE",
    "ANNOTATION_LAUNCH_PERMISSION",
]


class ManualDecisionOriginal(StrictModel):
    kind: Literal["MANUAL_SCOPED_DECISION_ORIGINAL_V1"] = "MANUAL_SCOPED_DECISION_ORIGINAL_V1"
    stage: Stage
    state: Literal["PROSPECTIVE_PERMISSION", "ACTUAL_ACCEPTANCE"]
    mode: ManualMode
    binding_sha256: Sha256 | None
    setup_scope_sha256: Sha256 | None = None
    material_pair_sha256: Sha256
    eligibility_pair_sha256: Sha256
    isolation_sha256: Sha256 | None
    issuer_ref: str
    witness_ref: str
    predecessor_sha256: Sha256 | None
    recorded_at: AwareDatetime


def manual_setup_scope_sha256(binding: ManualBinding) -> str:
    """Prospective plan, not final report or provider-assigned object identities."""
    binding = _binding(binding)
    scope = binding.model_dump(mode="json", exclude={"targets", "concealment"})
    scope["planned_targets"] = [
        t.model_dump(mode="json", exclude={"target_id", "parent_id", "probe_id"})
        for t in binding.targets
    ]
    scope["concealment"] = (
        binding.concealment.model_dump(mode="json", exclude={"target_context_sha256"})
        if binding.concealment is not None
        else None
    )
    return digest_value(scope)


class ManualStoreAdmission(StrictModel):
    """Explicit fake authority for disposable component/launch stores, never real grants."""

    kind: Literal["SYNTHETIC_MANUAL_STORE_ADMISSION_V1"] = "SYNTHETIC_MANUAL_STORE_ADMISSION_V1"
    purpose: Literal["COMPONENT_CONTROL", "OFFLINE_LAUNCH_PROOF"]
    mode: Literal["SYNTHETIC"] = "SYNTHETIC"
    run_id: Literal["synthetic-run"] = "synthetic-run"
    profile: Profile = PROFILE
    binding_sha256: Sha256
    source_sha256: Sha256
    owner_ref: str
    coordinator_ref: str
    witness_ref: str
    not_before: AwareDatetime
    not_after: AwareDatetime
    eligibility: tuple[EligibilityBinding, ...]
    material_pair_sha256: Sha256
    decision_sha256s: tuple[Sha256, ...] = ()
    real_launch_authorized: Literal[False] = False


class ManualLaunchVerification(StrictModel):
    kind: Literal["MANUAL_LINKAGE_NOT_REAL_LAUNCH_AUTHORITY_V1"] = (
        "MANUAL_LINKAGE_NOT_REAL_LAUNCH_AUTHORITY_V1"
    )
    binding_sha256: Sha256
    material_pair_sha256: Sha256
    decision_sha256s: tuple[Sha256, ...]
    synthetic_ready: bool
    real_launch_authorized: Literal[False] = False
    storage: ManualStoreAdmission | None = None


def verify_manual_delivery(
    binding: ManualBinding,
    isolation: ManualIsolationReport,
    materials: Sequence[ManualMaterialIdentity],
    eligibility: Sequence[EligibilityBinding],
    decisions: Sequence[bytes],
    *,
    trusted_decision_sha256s: Sequence[str],
    at: datetime,
    people: Sequence[EligibilityAttestation],
    packages: Sequence[Mapping[str, bytes]],
) -> ManualLaunchVerification:
    binding = _binding(binding)
    materials = tuple(
        ManualMaterialIdentity.model_validate_json(m.model_dump_json()) for m in materials
    )
    eligibility = tuple(
        EligibilityBinding.model_validate_json(e.model_dump_json()) for e in eligibility
    )
    if eligibility != bind_eligibility_pair(people, packages):
        raise ValueError(
            "manual delivery eligibility differs from actual blind A/B attestations/packages"
        )
    if len(materials) != len(packages) or any(
        manual_material_identity(
            files, material.view, field_registry_sha256=material.field_registry_sha256
        )
        != material
        for material, files in zip(materials, packages, strict=True)
    ):
        raise ValueError("manual materials differ from actual source/view/reference relationship")
    if (
        len(materials) != 2
        or len(eligibility) != 2
        or tuple(m.original.role for m in materials) != ("annotator-a", "annotator-b")
    ):
        raise ValueError("manual delivery requires exact independent A/B material pair")
    if (
        not binding.not_before <= at <= binding.not_after
        or isolation.binding_sha256 != digest(binding)
        or not isolation.complete_consistency
        or isolation.unresolved_action_refs
        or tuple(o.check for o in isolation.outcomes) != ACCESS_POLICY_V2.acl_expectations
        or any(o.result != "PASS" for o in isolation.outcomes)
        or len(isolation.controls) != 2
        or isolation.completed_at is None
        or not binding.not_before <= isolation.first_action_at <= isolation.completed_at <= at
    ):
        raise ValueError("current complete isolation consistency and two controls required")
    if len({e.private_person_token_sha256 for e in eligibility}) != 2 or any(
        e.identity != m.original for e, m in zip(eligibility, materials, strict=True)
    ):
        raise ValueError("wrong role, exposed/ineligible or substituted A/B eligibility")
    if (
        any(m.original.run_id != binding.run_id for m in materials)
        or materials[0].original.contract_identity != materials[1].original.contract_identity
        or materials[0].official_report_sha256s != materials[1].official_report_sha256s
        or materials[0].field_registry_sha256 != materials[1].field_registry_sha256
    ):
        raise ValueError("manual run/reference/contract/field registry differs")
    pair_sha = digest_value([m.model_dump(mode="json") for m in materials])
    eligibility_sha = digest_value([e.model_dump(mode="json") for e in eligibility])
    pins = tuple(sha256(raw) for raw in decisions)
    if len(decisions) != 6 or pins != tuple(trusted_decision_sha256s):
        raise ValueError("six independently trusted actual/prospective decisions required")
    previous: str | None = None
    previous_at = binding.not_before
    for stage, raw in zip(STAGES, decisions, strict=True):
        decision = ManualDecisionOriginal.model_validate_json(raw)
        setup = stage == "SETUP_PERMISSION"
        state = (
            "ACTUAL_ACCEPTANCE"
            if stage in ("ISOLATION_ACCEPTANCE", "DELIVERY_ACCEPTANCE")
            else "PROSPECTIVE_PERMISSION"
        )
        if (
            decision.stage,
            decision.state,
            decision.mode,
            decision.binding_sha256,
            decision.setup_scope_sha256,
            decision.material_pair_sha256,
            decision.eligibility_pair_sha256,
            decision.isolation_sha256,
            decision.issuer_ref,
            decision.witness_ref,
            decision.predecessor_sha256,
        ) != (
            stage,
            state,
            binding.mode,
            None if setup else digest(binding),
            manual_setup_scope_sha256(binding) if setup else None,
            pair_sha,
            eligibility_sha,
            None if setup else digest(isolation),
            binding.owner_ref,
            binding.witness_ref,
            previous,
        ) or not previous_at <= decision.recorded_at <= at:
            raise ValueError("manual decision ordering, scope or acceptance/permission mismatch")
        if setup and not decision.recorded_at < isolation.first_action_at:
            raise ValueError("setup permission must precede independently witnessed actions")
        if stage == "ISOLATION_ACCEPTANCE" and decision.recorded_at < isolation.completed_at:
            raise ValueError("isolation acceptance must follow actual completed evidence")
        previous, previous_at = sha256(raw), decision.recorded_at
    storage = None
    if binding.mode == "SYNTHETIC":
        storage = ManualStoreAdmission(
            purpose="OFFLINE_LAUNCH_PROOF",
            binding_sha256=digest(binding),
            source_sha256=binding.source_sha256,
            eligibility=eligibility,
            material_pair_sha256=pair_sha,
            decision_sha256s=pins,
            owner_ref=binding.owner_ref,
            coordinator_ref=binding.coordinator_ref,
            witness_ref=binding.witness_ref,
            not_before=binding.not_before,
            not_after=binding.not_after,
        )
    return ManualLaunchVerification(
        binding_sha256=digest(binding),
        material_pair_sha256=pair_sha,
        decision_sha256s=pins,
        synthetic_ready=storage is not None,
        storage=storage,
    )


class ManualOriginalIntake(StrictModel):
    kind: Literal["MANUAL_ORIGINAL_INTAKE_V1"] = "MANUAL_ORIGINAL_INTAKE_V1"
    evidence_label: Literal["SYNTHETIC_NOT_HUMAN_SUBMISSION"] = "SYNTHETIC_NOT_HUMAN_SUBMISSION"
    admission_sha256: Sha256
    identity: IssuedPackageIdentity
    at: AwareDatetime
    form_sha256s: dict[str, Sha256]
    mechanically_complete: bool
    validation_error: str | None


class ManualPublicationEvidence(StrictModel):
    kind: Literal["SYNTHETIC_MANUAL_PUBLICATION_EVIDENCE_V1"] = (
        "SYNTHETIC_MANUAL_PUBLICATION_EVIDENCE_V1"
    )
    stage: Literal["PUBLICATION_PERMISSION", "HUMAN_COMPLETION_REQUEST", "COORDINATOR_CONFIRMATION"]
    admission_sha256: Sha256
    intake_sha256: Sha256
    role: Role
    actor_ref: str
    witness_ref: str
    recorded_at: AwareDatetime
    predecessor_evidence_sha256: Sha256 | None


class ManualAcceptedOriginal(StrictModel):
    kind: Literal["MANUAL_ACCEPTED_ORIGINAL_V1"] = "MANUAL_ACCEPTED_ORIGINAL_V1"
    evidence_label: Literal["SYNTHETIC_NOT_HUMAN_SUBMISSION"] = "SYNTHETIC_NOT_HUMAN_SUBMISSION"
    admission_sha256: Sha256
    role: Role
    sequence: int
    original_intake_sha256: Sha256
    previous_sha256: Sha256 | None
    supersedes: Sha256 | None
    permission_sha256: Sha256
    completion_sha256: Sha256
    confirmation_sha256: Sha256
    publication_evidence: tuple[PinnedManualPublicationEvidence, ...] = Field(
        min_length=3, max_length=3
    )
    gold: Literal[False] = False


class PinnedManualPublicationEvidence(StrictModel):
    """Pin is supplied independently, not taken from an imported record's claim."""

    original: ManualPublicationEvidence
    trusted_sha256: Sha256


def _storage(value: ManualStoreAdmission) -> ManualStoreAdmission:
    value = ManualStoreAdmission.model_validate_json(value.model_dump_json())
    if value.source_sha256 != sha256(Path(__file__).read_bytes()):
        raise ValueError("current manual consumer source differs from admitted bytes")
    if (
        value.not_before >= value.not_after
        or len({value.owner_ref, value.coordinator_ref, value.witness_ref}) != 3
    ):
        raise ValueError("independent scoped manual custody window required")
    if (
        tuple(e.identity.role for e in value.eligibility) != ("annotator-a", "annotator-b")
        or len({e.private_person_token_sha256 for e in value.eligibility}) != 2
        or any(e.identity.run_id != "synthetic-run" for e in value.eligibility)
    ):
        raise ValueError("synthetic manual storage requires eligible distinct A/B")
    if value.purpose == "OFFLINE_LAUNCH_PROOF" and len(value.decision_sha256s) != 6:
        raise ValueError("manual store lacks actual delivery/launch decision linkage")
    return value


def _claim(
    root: DirectoryLease, checkpoint: DirectoryLease, admission: ManualStoreAdmission
) -> bytes:
    return canonical_json_bytes(
        {
            "kind": "SYNTHETIC_MANUAL_STORAGE_CLAIM_V1",
            "admission": digest(admission),
            "store": str(root.resolved),
            "checkpoint": str(checkpoint.resolved),
        }
    )


@contextmanager
def _directories(
    root: Path, checkpoint: Path, admission: ManualStoreAdmission, *, create: bool = False
) -> Generator[tuple[DirectoryLease, DirectoryLease], None, None]:
    admission = _storage(admission)
    require_offline_root(root)
    require_offline_root(checkpoint)
    with ExitStack() as stack:
        directory = stack.enter_context(DirectoryLease.acquire(root))
        index = stack.enter_context(DirectoryLease.acquire(checkpoint))
        if (
            directory.resolved == index.resolved
            or directory.resolved in index.resolved.parents
            or index.resolved in directory.resolved.parents
        ):
            raise ValueError("independent checkpoint directory required")
        stream = stack.enter_context(index.open_child_append("writer.lock"))
        lock = _KernelLock(stream)
        lock.acquire()
        stack.callback(lock.release)
        claim = _claim(directory, index, admission)
        if create:
            if directory.list_child_names() or set(index.list_child_names()) != {"writer.lock"}:
                raise ValueError("new manual store/checkpoint must be unused; no reset")
            publish(directory, "claim.json", claim)
            publish(index, "claim.json", claim)
        for store in (directory, index):
            with store.open_child_read("claim.json") as original:
                if original.read() != claim:
                    raise ValueError("manual storage source/admission/path drift")
        yield directory, index


def initialize_manual_store(root: Path, checkpoint: Path, admission: ManualStoreAdmission) -> None:
    with _directories(root, checkpoint, admission, create=True):
        pass


def _read(directory: DirectoryLease, name: str) -> bytes:
    with directory.open_child_read(name) as original:
        return original.read()


def _history(
    directory: DirectoryLease, index: DirectoryLease, admission: ManualStoreAdmission
) -> tuple[dict[str, ManualOriginalIntake], tuple[ManualAcceptedOriginal, ...]]:
    names = sorted(n for n in directory.list_child_names() if n != "claim.json")
    checkpoints = sorted(
        n for n in index.list_child_names() if n not in ("claim.json", "writer.lock")
    )
    if checkpoints != [n + ".json" if n.startswith("intake-") else n for n in names]:
        raise ValueError("split/partial manual publication; preserve, do not repair")
    intakes: dict[str, ManualOriginalIntake] = {}
    accepted: list[ManualAcceptedOriginal] = []
    current: dict[str, str] = {}
    for name in names:
        if name.startswith("intake-"):
            with directory.acquire_child(name) as child:
                raw = _read(child, "receipt.json")
                receipt = ManualOriginalIntake.model_validate_json(raw)
                if name != "intake-" + digest(receipt) or receipt.admission_sha256 != digest(
                    admission
                ):
                    raise ValueError("intake identity/source mismatch")
                if set(child.list_child_names()) != {
                    *FORM_HEADERS,
                    "receipt.json",
                } or receipt.form_sha256s != {n: sha256(_read(child, n)) for n in FORM_HEADERS}:
                    raise ValueError("original bytes missing/substituted")
                intakes[digest(receipt)] = receipt
        elif name.startswith("accepted-"):
            raw = _read(directory, name)
            record = ManualAcceptedOriginal.model_validate_json(raw)
            if (
                name != f"accepted-{len(accepted) + 1:06d}.json"
                or record.sequence != len(accepted) + 1
                or record.admission_sha256 != digest(admission)
                or record.previous_sha256 != (digest(accepted[-1]) if accepted else None)
                or record.supersedes != current.get(record.role)
            ):
                raise ValueError("accepted order/chain/current predecessor mismatch")
            accepted.append(record)
            current[record.role] = digest(record)
        else:
            raise ValueError("unknown manual storage entry")
        if _read(
            index, name + ".json" if name.startswith("intake-") else name
        ) != canonical_json_bytes({"entry": name, "sha256": sha256(raw)}):
            raise ValueError("corrupt independent manual checkpoint")
    for record in accepted:
        intake = intakes.get(record.original_intake_sha256)
        if (
            intake is None
            or intake.identity.role != record.role
            or not intake.mechanically_complete
        ):
            raise ValueError("accepted history lacks complete role-owned original")
        pins = _verify_publication_evidence(admission, intake, record.publication_evidence)
        if pins != (record.permission_sha256, record.completion_sha256, record.confirmation_sha256):
            raise ValueError("accepted history permission/completion/confirmation hash mismatch")
    if len({r.completion_sha256 for r in accepted}) != len(accepted):
        raise ValueError("replayed completion request")
    return intakes, tuple(accepted)


def intake_manual_originals(
    root: Path,
    checkpoint: Path,
    admission: ManualStoreAdmission,
    files: Mapping[str, bytes],
    *,
    at: datetime,
) -> ManualOriginalIntake:
    admission = _storage(admission)
    if not admission.not_before <= at <= admission.not_after:
        raise ValueError("original intake outside admitted synthetic window")
    manifest = verify_package(files, allow_drafts=True)
    expected = next(e.identity for e in admission.eligibility if e.identity.role == manifest.role)
    if package_identity(files, allow_drafts=True) != expected:
        raise ValueError("original role/source/package differs from manual admission")
    validation_error = None
    mechanically_complete = False
    try:
        mechanically_complete = validate_neutral_forms(files, expected_package=manifest).complete
    except ValueError as error:
        validation_error = str(error)
    receipt = ManualOriginalIntake(
        admission_sha256=digest(admission),
        identity=expected,
        at=at,
        form_sha256s={n: sha256(files[n]) for n in FORM_HEADERS},
        mechanically_complete=mechanically_complete,
        validation_error=validation_error,
    )
    with _directories(root, checkpoint, admission) as (directory, index):
        _history(directory, index, admission)
        name = "intake-" + digest(receipt)
        if directory.child_exists(name):
            raise ValueError("original intake replay/conflict; bytes retained")
        with directory.acquire_child(name, create=True) as child:
            for filename in FORM_HEADERS:
                publish(child, filename, files[filename])
            raw = canonical_json_bytes(receipt.model_dump(mode="json"))
            publish(child, "receipt.json", raw)
        publish(index, name + ".json", canonical_json_bytes({"entry": name, "sha256": sha256(raw)}))
        _history(directory, index, admission)
    return receipt


def read_manual_intake(
    root: Path, checkpoint: Path, admission: ManualStoreAdmission, intake_sha256: str
) -> dict[str, bytes]:
    with _directories(root, checkpoint, admission) as (directory, index):
        intakes, _ = _history(directory, index, admission)
        if intake_sha256 not in intakes:
            raise ValueError("unknown original intake")
        with directory.acquire_child("intake-" + intake_sha256) as child:
            return {n: _read(child, n) for n in FORM_HEADERS}


def read_manual_history(
    root: Path, checkpoint: Path, admission: ManualStoreAdmission
) -> tuple[ManualAcceptedOriginal, ...]:
    with _directories(root, checkpoint, admission) as (directory, index):
        return _history(directory, index, admission)[1]


def _verify_publication_evidence(
    admission: ManualStoreAdmission,
    receipt: ManualOriginalIntake,
    records: Sequence[PinnedManualPublicationEvidence],
) -> tuple[str, ...]:
    expected = next(e for e in admission.eligibility if e.identity.role == receipt.identity.role)
    previous: str | None = None
    previous_at = receipt.at
    for stage, pinned, actor in zip(
        ("PUBLICATION_PERMISSION", "HUMAN_COMPLETION_REQUEST", "COORDINATOR_CONFIRMATION"),
        records,
        (admission.owner_ref, expected.private_person_token_sha256, admission.coordinator_ref),
        strict=True,
    ):
        original = ManualPublicationEvidence.model_validate_json(pinned.original.model_dump_json())
        if (
            digest(original) != pinned.trusted_sha256
            or (
                original.stage,
                original.admission_sha256,
                original.intake_sha256,
                original.role,
                original.actor_ref,
                original.predecessor_evidence_sha256,
            )
            != (stage, digest(admission), digest(receipt), receipt.identity.role, actor, previous)
            or original.witness_ref != admission.witness_ref
            or not previous_at <= original.recorded_at <= admission.not_after
        ):
            raise ValueError(
                "missing/substituted scoped permission, completion request "
                "or independent confirmation"
            )
        previous, previous_at = digest(original), original.recorded_at
    return tuple(digest(p.original) for p in records)


def publish_manual_accepted(
    root: Path,
    checkpoint: Path,
    admission: ManualStoreAdmission,
    files: Mapping[str, bytes],
    receipt: ManualOriginalIntake,
    permission: PinnedManualPublicationEvidence,
    completion_request: PinnedManualPublicationEvidence,
    confirmation: PinnedManualPublicationEvidence,
    *,
    predecessor: str | None,
) -> ManualAcceptedOriginal:
    admission = _storage(admission)
    receipt = ManualOriginalIntake.model_validate_json(receipt.model_dump_json())
    expected = next(e for e in admission.eligibility if e.identity.role == receipt.identity.role)
    records = (permission, completion_request, confirmation)
    _verify_publication_evidence(admission, receipt, records)
    manifest = PackageManifest.model_validate_json(files["PACKAGE_MANIFEST.json"])
    validate_neutral_forms(files, expected_package=manifest, require_complete=True)
    if (
        package_identity(files, allow_drafts=True) != expected.identity
        or receipt.identity != expected.identity
        or receipt.validation_error is not None
    ):
        raise ValueError("accepted package/source/role differs from original admission")
    with _directories(root, checkpoint, admission) as (directory, index):
        intakes, history = _history(directory, index, admission)
        if (
            intakes.get(digest(receipt)) != receipt
            or not receipt.mechanically_complete
            or receipt.form_sha256s != {n: sha256(files[n]) for n in FORM_HEADERS}
        ):
            raise ValueError("accepted publication requires exact complete preserved originals")
        current = next((r for r in reversed(history) if r.role == receipt.identity.role), None)
        if predecessor != (digest(current) if current else None) or any(
            r.completion_sha256 == completion_request.trusted_sha256 for r in history
        ):
            raise ValueError("wrong predecessor, second current branch or replayed completion")
        record = ManualAcceptedOriginal(
            admission_sha256=digest(admission),
            role=receipt.identity.role,
            sequence=len(history) + 1,
            original_intake_sha256=digest(receipt),
            previous_sha256=digest(history[-1]) if history else None,
            supersedes=predecessor,
            permission_sha256=permission.trusted_sha256,
            completion_sha256=completion_request.trusted_sha256,
            confirmation_sha256=confirmation.trusted_sha256,
            publication_evidence=records,
        )
        raw = canonical_json_bytes(record.model_dump(mode="json"))
        name = f"accepted-{record.sequence:06d}.json"
        publish(directory, name, raw)
        publish(index, name, canonical_json_bytes({"entry": name, "sha256": sha256(raw)}))
        _history(directory, index, admission)
    return record


def manual_consumer_control(
    root: Path,
    checkpoint: Path,
    admission: ManualStoreAdmission,
    *,
    role: Role,
    supersession_sha256: str,
    at: datetime,
) -> ManualApplicationControl:
    """Destructive attempt only against already accepted disposable synthetic bytes."""
    with _directories(root, checkpoint, admission) as (directory, index):
        intakes, history = _history(directory, index, admission)
        chain = [r for r in history if r.role == role]
        if (
            len(chain) < 2
            or digest(chain[-1]) != supersession_sha256
            or chain[-1].supersedes != digest(chain[-2])
        ):
            raise ValueError("actual consumer append-only supersession required")
        started_at = min(i.at for i in intakes.values() if i.identity.role == role)
        if (
            not max(p.original.recorded_at for r in chain for p in r.publication_evidence)
            <= at
            <= admission.not_after
        ):
            raise ValueError("consumer control must follow publication within admitted window")
        name = f"accepted-{chain[-2].sequence:06d}.json"
        raw = _read(directory, name)
        try:
            publish(directory, name, b"SYNTHETIC prohibited overwrite")
        except DirectoryLeaseError as error:
            if not isinstance(error.__cause__, FileExistsError):
                raise
        else:
            raise ValueError("consumer no-replace failed")
        preserved = _read(directory, name)
        if preserved != raw:
            raise ValueError("consumer prior original changed")
        checkpoint_data = _read(index, name)
        if checkpoint_data != canonical_json_bytes({"entry": name, "sha256": sha256(raw)}):
            raise ValueError("consumer checkpoint changed")
        return ManualApplicationControl(
            control_id="APP-ACCEPTED-BYTES-A" if role == "annotator-a" else "APP-ACCEPTED-BYTES-B",
            role=role,
            binding_sha256=admission.binding_sha256,
            consumer_sha256=sha256(Path(__file__).read_bytes()),
            store_sha256=sha256(str(directory.resolved).encode()),
            original_sha256=sha256(raw),
            preserved_sha256=sha256(preserved),
            checkpoint_sha256=sha256(raw),
            overwrite_error="FileExistsError",
            supersession_sha256=supersession_sha256,
            started_at=started_at,
            completed_at=at,
        )


def manual_schema_bytes() -> bytes:
    """Additive manual receipt schema; native/scientific/V2/V3 schemas unchanged."""
    schema = TypeAdapter(
        ManualBinding
        | ManualOperationOriginal
        | ManualObservation
        | ManualWitnessIndex
        | ManualActionEvent
        | ManualApplicationControl
        | ManualDecisionOriginal
        | ManualMaterialIdentity
        | ManualIsolationReport
        | ManualLaunchVerification
        | ManualStoreAdmission
        | ManualOriginalIntake
        | ManualPublicationEvidence
        | ManualAcceptedOriginal
    ).json_schema()
    return (json.dumps(schema, indent=2, sort_keys=True) + "\n").encode()


def export_manual_schema(output_root: Path) -> Path:
    path = output_root / "execution" / "owner_assisted_v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(manual_schema_bytes())
    return path
