"""Synthetic, independent object/permission state; no people or provider operations."""

from __future__ import annotations

import importlib
import importlib.util
import json
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from test_m2_annotation import blank, complete, form, populated

from peru_conflicts.execution.access_policy import ACCESS_POLICY_V2, ACTORS, RESOURCES
from peru_conflicts.execution.coordination import EligibilityAttestation, bind_eligibility_pair
from peru_conflicts.execution.neutral_forms import rows as neutral_rows
from peru_conflicts.execution.references import sha256
from peru_conflicts.execution.runtime_build import build_neutral_view
from peru_conflicts.hashing import canonical_json_bytes

NOW = datetime(2026, 10, 2, 12, tzinfo=UTC)


def api() -> ModuleType:
    assert importlib.util.find_spec("peru_conflicts.execution.owner_assisted") is not None, (
        "separately typed owner-assisted evidence/consumer is not implemented"
    )
    return importlib.import_module("peru_conflicts.execution.owner_assisted")


def people() -> tuple[EligibilityAttestation, ...]:
    return tuple(
        EligibilityAttestation(
            role=role,
            private_person_token=f"SYNTHETIC-{role}",
            distinct_human_confirmed=True,
            machine_answers_seen=False,
            parser_predictions_seen=False,
            machine_prefill_seen=False,
            other_submission_seen=False,
            partition_labels_received=False,
        )
        for role in ("annotator-a", "annotator-b")
    )


def fixture() -> tuple[Any, list[Any], dict[str, bytes]]:
    """Permissions are a fixture ACL, not an expected_outcome-to-result conversion."""
    m = api()
    assert m.__file__ is not None
    targets = [
        m.ManualTarget(
            actor=actor,
            resource=resource,
            session_ref=f"synthetic-session-{actor}",
            namespace=f"synthetic-namespace-{actor}",
            locator=f"/synthetic/{resource}",
            target_id=f"id:folder-{resource}",
            parent_id="id:synthetic-parent",
            probe_id=f"id:probe-{resource}",
            probe_sha256=sha256(b"SYNTHETIC harmless probe"),
            ownership_ref=f"synthetic-owner-{actor}-{resource}",
        )
        for actor in ACTORS
        for resource in RESOURCES
    ]
    binding = m.ManualBinding(
        run_id="synthetic-run",
        mode="SYNTHETIC",
        source_sha256=sha256(Path(m.__file__).read_bytes()),
        policy_sha256=m.digest(ACCESS_POLICY_V2),
        coordinator_ref="synthetic-coordinator",
        witness_ref="synthetic-independent-witness",
        owner_ref="synthetic-owner",
        not_before=NOW,
        not_after=NOW + timedelta(hours=1),
        targets=tuple(targets),
        concealment=m.ManualConcealmentRule(
            provider_document_sha256="b" * 64,
            approval_ref="SYNTHETIC_CONCEALMENT_NOT_REAL_POLICY",
            target_context_sha256=m.digest_value([t.model_dump(mode="json") for t in targets]),
        ),
    )
    # Explicit independent fixture permission state and stable object inventory.
    permissions: dict[tuple[str, str], set[str]] = {}
    for resource in RESOURCES:
        permissions[("coordinator", resource)] = {"list", "read", "write"}
    for actor in ("annotator-a", "annotator-b"):
        permissions[(actor, f"{actor}/issue")] = {"list", "read"}
        permissions[(actor, f"{actor}/submission")] = {"list", "read", "write"}
    objects = {t.target_id: {"probe": t.probe_id, "hash": t.probe_sha256} for t in targets}
    observations: list[Any] = []
    originals: dict[str, bytes] = {}
    for sequence, check in enumerate(ACCESS_POLICY_V2.acl_expectations, 1):
        target = next(t for t in targets if (t.actor, t.resource) == (check.actor, check.resource))
        permitted = check.operation in permissions.get((check.actor, check.resource), set())
        obj = objects[target.target_id]
        original = m.ManualOperationOriginal(
            actor=check.actor,
            session_ref=target.session_ref,
            namespace=target.namespace,
            locator=target.locator,
            operation=check.operation,
            scope_complete=True,
            target_id=target.target_id,
            parent_id=target.parent_id,
            before_exists=True,
            after_exists=True,
            status=200 if permitted else 409,
            error=None
            if permitted
            else ("no_write_permission" if check.operation == "write" else "not_found"),
            observed_id=obj["probe"] if permitted else None,
            returned_locator=target.locator if permitted else None,
            entry_ids=(obj["probe"],) if permitted and check.operation == "list" else (),
            listing_complete=permitted and check.operation == "list",
            read_sha256=obj["hash"] if permitted and check.operation == "read" else None,
            write_sha256=obj["hash"] if permitted and check.operation == "write" else None,
            autorenamed=False,
            cleanup=m.ManualProbeCleanup(
                ownership_ref=target.ownership_ref,
                probe_id=obj["probe"],
                probe_sha256=obj["hash"],
                target_id=target.target_id,
                before_observed=True,
                after_absent=True,
                completed_at=NOW + timedelta(seconds=sequence * 2 + 1),
            )
            if permitted and check.operation == "write"
            else None,
        )
        raw = canonical_json_bytes(original.model_dump(mode="json"))
        key = sha256(raw)
        originals[key] = raw
        observations.append(
            m.ManualObservation(
                binding_sha256=m.digest(binding),
                sequence=sequence,
                check_id=check.check_id,
                actor=check.actor,
                resource=check.resource,
                operation=check.operation,
                started_at=NOW + timedelta(seconds=sequence * 2),
                completed_at=NOW + timedelta(seconds=sequence * 2 + 1),
                state="COMPLETED",
                original_sha256=key,
            )
        )
    return binding, observations, originals


def witness(
    binding: Any,
    observations: list[Any],
    controls: tuple[Any, ...] = (),
    progress: tuple[Any, ...] = (),
) -> bytes:
    m = api()
    return canonical_json_bytes(
        m.ManualWitnessIndex(
            binding_sha256=m.digest(binding),
            mode=binding.mode,
            witness_ref=binding.witness_ref,
            observation_sha256s=tuple(m.digest(o) for o in observations),
            control_sha256s=tuple(m.digest(c) for c in controls),
            progress_sha256s=tuple(m.digest(e) for e in progress),
        ).model_dump(mode="json")
    )


def verify(binding: Any, observations: list[Any], originals: dict[str, bytes]) -> Any:
    index = witness(binding, observations)
    return api().verify_manual_observations(
        binding, observations, originals, index, trusted_witness_sha256=sha256(index)
    )


def replace_original(
    observations: list[Any], originals: dict[str, bytes], index: int, **values: Any
) -> None:
    m = api()
    observation = observations[index]
    original = m.ManualOperationOriginal.model_validate_json(originals[observation.original_sha256])
    raw = canonical_json_bytes(original.model_copy(update=values).model_dump(mode="json"))
    originals[sha256(raw)] = raw
    observations[index] = observation.model_copy(update={"original_sha256": sha256(raw)})


def synthetic_publication_evidence(
    admission: Any, receipt: Any, *, at: datetime
) -> tuple[Any, ...]:
    m = api()
    human = next(
        e.private_person_token_sha256
        for e in admission.eligibility
        if e.identity.role == receipt.identity.role
    )
    records: list[Any] = []
    previous = None
    for stage, actor in zip(
        ("PUBLICATION_PERMISSION", "HUMAN_COMPLETION_REQUEST", "COORDINATOR_CONFIRMATION"),
        (admission.owner_ref, human, admission.coordinator_ref),
        strict=True,
    ):
        original = m.ManualPublicationEvidence(
            stage=stage,
            admission_sha256=m.digest(admission),
            intake_sha256=m.digest(receipt),
            role=receipt.identity.role,
            actor_ref=actor,
            recorded_at=at,
            predecessor_evidence_sha256=previous,
            witness_ref=admission.witness_ref,
        )
        previous = m.digest(original)
        records.append(
            m.PinnedManualPublicationEvidence(original=original, trusted_sha256=previous)
        )
    return tuple(records)


def component_admission(
    binding: Any,
    packages: tuple[dict[str, bytes], ...],
    persons: tuple[EligibilityAttestation, ...],
) -> Any:
    m = api()
    return m.ManualStoreAdmission(
        purpose="COMPONENT_CONTROL",
        binding_sha256=m.digest(binding),
        source_sha256=binding.source_sha256,
        eligibility=bind_eligibility_pair(persons, packages),
        material_pair_sha256=m.digest_value([sha256(p["PACKAGE_MANIFEST.json"]) for p in packages]),
        owner_ref=binding.owner_ref,
        coordinator_ref=binding.coordinator_ref,
        witness_ref=binding.witness_ref,
        not_before=binding.not_before,
        not_after=binding.not_after,
    )


def exercise_synthetic_manual_controls(
    tmp_path: Path,
    binding: Any,
    packages: tuple[dict[str, bytes], ...],
    persons: tuple[EligibilityAttestation, ...],
    *,
    at: datetime,
) -> tuple[Any, ...]:
    m = api()
    admission = component_admission(binding, packages, persons)
    controls: list[Any] = []
    for role in ("annotator-a", "annotator-b"):
        root, checkpoint = tmp_path / f"control-{role}", tmp_path / f"control-index-{role}"
        root.mkdir()
        checkpoint.mkdir()
        m.initialize_manual_store(root, checkpoint, admission)
        first = None
        for number in range(2):
            files = blank(role)
            complete(files)
            receipt = m.intake_manual_originals(
                root, checkpoint, admission, files, at=at + timedelta(seconds=number * 2)
            )
            evidence = synthetic_publication_evidence(
                admission, receipt, at=at + timedelta(seconds=number * 2 + 1)
            )
            current = m.publish_manual_accepted(
                root, checkpoint, admission, files, receipt, *evidence, predecessor=first
            )
            first = m.digest(current)
        controls.append(
            m.manual_consumer_control(
                root,
                checkpoint,
                admission,
                role=role,
                supersession_sha256=first,
                at=at + timedelta(seconds=4),
            )
        )
    return tuple(controls)


def delivery_fixture(
    tmp_path: Path,
    binding: Any,
    report: Any,
    packages: tuple[dict[str, bytes], ...],
    persons: tuple[EligibilityAttestation, ...],
    *,
    at: datetime,
) -> tuple[Any, ...]:
    m = api()
    materials: list[Any] = []
    for index, package in enumerate(packages):
        view = build_neutral_view(package, tmp_path / f"m2-readiness-neutral-{index}")
        materials.append(m.manual_material_identity(package, view, field_registry_sha256="c" * 64))
    eligibility = bind_eligibility_pair(persons, packages)
    raw: list[bytes] = []
    previous = None
    for stage in m.STAGES:
        record = m.ManualDecisionOriginal(
            stage=stage,
            state="ACTUAL_ACCEPTANCE"
            if stage in ("ISOLATION_ACCEPTANCE", "DELIVERY_ACCEPTANCE")
            else "PROSPECTIVE_PERMISSION",
            mode=binding.mode,
            binding_sha256=None if stage == "SETUP_PERMISSION" else m.digest(binding),
            setup_scope_sha256=m.manual_setup_scope_sha256(binding)
            if stage == "SETUP_PERMISSION"
            else None,
            material_pair_sha256=m.digest_value([x.model_dump(mode="json") for x in materials]),
            eligibility_pair_sha256=m.digest_value(
                [e.model_dump(mode="json") for e in eligibility]
            ),
            isolation_sha256=None if stage == "SETUP_PERMISSION" else m.digest(report),
            issuer_ref=binding.owner_ref,
            witness_ref=binding.witness_ref,
            predecessor_sha256=previous,
            recorded_at=NOW + timedelta(seconds=1) if stage == "SETUP_PERMISSION" else at,
        )
        encoded = canonical_json_bytes(record.model_dump(mode="json"))
        previous = sha256(encoded)
        raw.append(encoded)
    return materials, eligibility, tuple(raw), tuple(sha256(r) for r in raw)


@pytest.mark.parametrize("operation", ["list", "read", "write"])
def test_denial_with_contradictory_success_evidence_is_not_pass(operation: str) -> None:
    m = api()
    binding, observations, originals = fixture()
    index = next(
        i
        for i, check in enumerate(ACCESS_POLICY_V2.acl_expectations)
        if check.operation == operation and check.expected_outcome == "DENY"
    )
    observation = observations[index]
    target = next(
        t
        for t in binding.targets
        if (t.actor, t.resource) == (observation.actor, observation.resource)
    )
    # Explicit adverse original; its status remains the genuine scoped denial.
    replace_original(
        observations,
        originals,
        index,
        observed_id=target.probe_id,
        returned_locator=target.locator,
        entry_ids=(target.probe_id,) if operation == "list" else (),
        listing_complete=operation == "list",
        read_sha256=target.probe_sha256 if operation == "read" else None,
        write_sha256=target.probe_sha256 if operation == "write" else None,
        cleanup=m.ManualProbeCleanup(
            ownership_ref=target.ownership_ref,
            probe_id=target.probe_id,
            probe_sha256=target.probe_sha256,
            target_id=target.target_id,
            before_observed=True,
            after_absent=True,
            completed_at=observation.completed_at,
        )
        if operation == "write"
        else None,
    )
    # Re-witnessed adverse content must still not be admissible PASS.
    outcome = verify(binding, observations, originals).outcomes[index]
    assert outcome.result == "INCONCLUSIVE"


@pytest.mark.parametrize(
    "adverse", ["retrospective_setup", "early_isolation_acceptance", "setup_after_progress"]
)
def test_setup_permission_and_isolation_acceptance_bound_actual_actions(
    tmp_path: Path, adverse: str
) -> None:
    m = api()
    binding, observations, originals = fixture()
    packages = (blank("annotator-a"), blank("annotator-b"))
    persons = people()
    controls = exercise_synthetic_manual_controls(
        tmp_path, binding, packages, persons, at=NOW + timedelta(minutes=5)
    )
    progress = (
        (
            action_event(binding, originals, 1, "STARTED").model_copy(update={"at": NOW}),
            action_event(binding, originals, 2, "COMPLETED").model_copy(
                update={"at": NOW + timedelta(seconds=1)}
            ),
        )
        if adverse == "setup_after_progress"
        else ()
    )
    index = witness(binding, observations, controls, progress)
    report = m.verify_manual_observations(
        binding,
        observations,
        originals,
        index,
        trusted_witness_sha256=sha256(index),
        controls=controls,
        progress=progress,
    )
    materials, eligibility, decisions, _ = delivery_fixture(
        tmp_path, binding, report, packages, persons, at=NOW + timedelta(minutes=6)
    )
    changed: list[bytes] = []
    previous = None
    for number, raw in enumerate(decisions):
        record = m.ManualDecisionOriginal.model_validate_json(raw)
        at = (
            NOW + timedelta(minutes=6)
            if adverse == "retrospective_setup"
            else NOW + timedelta(seconds=number + 1)
        )
        if adverse == "setup_after_progress":
            at = NOW + timedelta(seconds=1) if number == 0 else NOW + timedelta(minutes=6)
        record = record.model_copy(update={"recorded_at": at, "predecessor_sha256": previous})
        encoded = canonical_json_bytes(record.model_dump(mode="json"))
        changed.append(encoded)
        previous = sha256(encoded)
    with pytest.raises(ValueError):
        m.verify_manual_delivery(
            binding,
            report,
            materials,
            eligibility,
            changed,
            trusted_decision_sha256s=tuple(sha256(r) for r in changed),
            at=NOW + timedelta(minutes=6),
            people=persons,
            packages=packages,
        )


def test_setup_permission_does_not_bind_future_final_evidence(tmp_path: Path) -> None:
    m = api()
    binding, observations, originals = fixture()
    report = verify(binding, observations, originals)
    _, _, decisions, _ = delivery_fixture(
        tmp_path,
        binding,
        report,
        (blank("annotator-a"), blank("annotator-b")),
        people(),
        at=NOW + timedelta(minutes=6),
    )
    permission = m.ManualDecisionOriginal.model_validate_json(decisions[0])
    assert permission.isolation_sha256 is None
    assert permission.binding_sha256 is None
    assert permission.recorded_at < observations[0].started_at


def test_prospective_scope_binds_plan_not_provider_assigned_ids() -> None:
    m = api()
    binding, _, _ = fixture()
    pin = m.manual_setup_scope_sha256(binding)
    targets = tuple(
        t.model_copy(
            update={"target_id": "new-folder", "parent_id": "new-parent", "probe_id": "new-probe"}
        )
        for t in binding.targets
    )
    rule = binding.concealment.model_copy(
        update={
            "target_context_sha256": m.digest_value([t.model_dump(mode="json") for t in targets])
        }
    )
    returned = binding.model_copy(update={"targets": targets, "concealment": rule})
    assert m.manual_setup_scope_sha256(returned) == pin
    assert m.digest(returned) != m.digest(binding)
    changed = targets[0].model_copy(update={"locator": "/wrong-planned-root"})
    targets = (changed, *targets[1:])
    rule = rule.model_copy(
        update={
            "target_context_sha256": m.digest_value([t.model_dump(mode="json") for t in targets])
        }
    )
    assert (
        m.manual_setup_scope_sha256(
            binding.model_copy(update={"targets": targets, "concealment": rule})
        )
        != pin
    )


def test_exact_108_independent_events_derive_results_not_caller_pass() -> None:
    binding, observations, originals = fixture()
    result = verify(binding, observations, originals)
    assert len(result.outcomes) == 108
    assert [r.result for r in result.outcomes] == ["PASS"] * 108
    assert [r.check for r in result.outcomes] == list(ACCESS_POLICY_V2.acl_expectations)
    assert sum(r.check.expected_outcome == "ALLOW" for r in result.outcomes) == 46
    assert sum(r.check.operation == "write" for r in result.outcomes) == 36
    assert not result.complete_consistency  # two actual consumer controls still required
    assert not result.real_isolation_approved


@pytest.mark.parametrize(
    "adverse",
    [
        "missing",
        "wrong_session",
        "scope",
        "no_policy",
        "ambiguous",
        "started",
        "unknown",
        "bad_cleanup",
        "forbidden_success",
    ],
)
def test_evidence_gaps_never_turn_into_expected_denial(adverse: str) -> None:
    binding, observations, originals = fixture()
    if adverse == "no_policy":
        binding = binding.model_copy(update={"concealment": None})
        observations = [
            o.model_copy(update={"binding_sha256": api().digest(binding)}) for o in observations
        ]
    elif adverse in ("started", "unknown"):
        observations[0] = observations[0].model_copy(
            update={"state": adverse.upper(), "completed_at": None}
        )
    elif adverse == "bad_cleanup":
        replace_original(observations, originals, 5, cleanup=None)
    else:
        changes: dict[str, Any] = {
            "missing": {"before_exists": False},
            "wrong_session": {"session_ref": "synthetic-wrong"},
            "scope": {"scope_complete": False},
            "ambiguous": {"error": "ambiguous"},
            "forbidden_success": {
                "status": 200,
                "error": None,
                "observed_id": "id:probe-annotator-b/issue",
            },
        }[adverse]
        # A's denied list of B's issue; the fixture still has an existing target.
        replace_original(observations, originals, 6, **changes)
    result = verify(binding, observations, originals)
    assert not result.complete_consistency
    assert any(
        r.result == ("FAIL" if adverse == "forbidden_success" else "INCONCLUSIVE")
        for r in result.outcomes
    )


@pytest.mark.parametrize(
    "adverse",
    [
        "missing",
        "duplicate",
        "mapping",
        "stale",
        "source",
        "original",
        "witness",
        "self_consistent_substitution",
    ],
)
def test_exact_coverage_and_independent_witness_pins_reject_substitution(adverse: str) -> None:
    binding, observations, originals = fixture()
    retained = witness(binding, observations)
    pin = sha256(retained)
    if adverse == "missing":
        observations.pop()
    elif adverse == "duplicate":
        observations[-1] = observations[0]
    elif adverse == "mapping":
        observations[0] = observations[0].model_copy(update={"actor": "coordinator"})
    elif adverse == "stale":
        observations[0] = observations[0].model_copy(
            update={"started_at": NOW - timedelta(seconds=1)}
        )
    elif adverse == "source":
        binding = binding.model_copy(update={"source_sha256": "f" * 64})
    elif adverse == "original":
        originals[observations[0].original_sha256] = b"substituted original"
    elif adverse == "witness":
        retained = retained.replace(b"synthetic-independent-witness", b"synthetic-self-witness")
    elif adverse == "self_consistent_substitution":
        replace_original(observations, originals, 0, read_sha256="f" * 64)
        retained = witness(binding, observations)  # internally matching is not independent trust
    with pytest.raises(ValueError):
        api().verify_manual_observations(
            binding, observations, originals, retained, trusted_witness_sha256=pin
        )


def action_event(
    binding: Any, originals: dict[str, bytes], sequence: int, state: str, kind: str = "mutation"
) -> Any:
    m = api()
    target = next(
        t for t in binding.targets if (t.actor, t.resource) == ("coordinator", "annotator-a/issue")
    )
    raw = canonical_json_bytes(
        {
            "kind": "SYNTHETIC_WITNESSED_ACTION",
            "sequence": sequence,
            "state": state,
            "action": "synthetic-share",
        }
    )
    originals[sha256(raw)] = raw
    return m.ManualActionEvent(
        sequence=sequence,
        action_ref="synthetic-share",
        kind=kind,
        state=state,
        at=NOW + timedelta(seconds=sequence),
        binding_sha256=m.digest(binding),
        actor=target.actor,
        resource=target.resource,
        session_ref=target.session_ref,
        namespace=target.namespace,
        target_id=target.target_id,
        witness_ref=binding.witness_ref,
        evidence_sha256=sha256(raw),
    )


def test_async_unknown_prefix_requires_read_only_reconciliation_not_repeat() -> None:
    m = api()
    binding, _, originals = fixture()
    events = [
        action_event(binding, originals, 1, "STARTED"),
        action_event(binding, originals, 2, "ACKNOWLEDGED_ASYNC"),
    ]

    def check(records: list[Any]) -> Any:
        return m.verify_manual_progress(
            binding, records, originals, trusted_event_sha256s=tuple(m.digest(e) for e in records)
        )

    assert check(events) == ("synthetic-share",)
    with pytest.raises(ValueError):
        check([*events, events[0].model_copy(update={"sequence": 3})])
    with pytest.raises(ValueError):
        check(
            [
                *events,
                events[0].model_copy(
                    update={
                        "sequence": 3,
                        "action_ref": "dependent-mutation",
                        "at": NOW + timedelta(seconds=3),
                    }
                ),
            ]
        )
    events.append(action_event(binding, originals, 3, "COMPLETED", "reconcile"))
    assert check(events) == ()
    wrong_context = [events[0].model_copy(update={"namespace": "wrong-synthetic-namespace"})]
    with pytest.raises(ValueError):
        check(wrong_context)


def test_original_intake_and_separately_confirmed_publication_are_connected(
    tmp_path: Path, record_property: Callable[[str, object], None]
) -> None:
    m = api()
    binding, observations, originals = fixture()
    report = verify(binding, observations, originals)
    packages = (blank("annotator-a"), blank("annotator-b"))
    # Controls run the same consumer as subsequent human-original support, in two stores.
    controls = exercise_synthetic_manual_controls(
        tmp_path, binding, packages, people(), at=NOW + timedelta(minutes=5)
    )
    index = witness(binding, observations, controls)
    report = m.verify_manual_observations(
        binding,
        observations,
        originals,
        index,
        trusted_witness_sha256=sha256(index),
        controls=controls,
    )
    assert report.complete_consistency
    materials, eligibility, decisions, pins = delivery_fixture(
        tmp_path, binding, report, packages, people(), at=NOW + timedelta(minutes=6)
    )
    launch = m.verify_manual_delivery(
        binding,
        report,
        materials,
        eligibility,
        decisions,
        trusted_decision_sha256s=pins,
        at=NOW + timedelta(minutes=6),
        people=people(),
        packages=packages,
    )
    assert launch.synthetic_ready and not launch.real_launch_authorized
    admission = launch.storage
    assert admission is not None
    root, checkpoint = tmp_path / "originals", tmp_path / "checkpoint"
    root.mkdir()
    checkpoint.mkdir()
    m.initialize_manual_store(root, checkpoint, admission)
    files = populated()
    rows = neutral_rows(files, "annotations.csv")
    value = next(r for r in rows if r["field_name"] == "case_name.name_original")
    value.update(
        state="observed", value_type="string", original_value="0007 Ñandú, conflicto\ntexto literal"
    )
    files["annotations.csv"] = form("annotations.csv", rows)
    receipt = m.intake_manual_originals(
        root, checkpoint, admission, files, at=NOW + timedelta(minutes=7)
    )
    assert receipt.mechanically_complete
    assert (
        m.read_manual_intake(root, checkpoint, admission, m.digest(receipt))["annotations.csv"]
        == files["annotations.csv"]
    )

    permission, completion_request, confirmation = synthetic_publication_evidence(
        admission, receipt, at=NOW + timedelta(minutes=8)
    )
    accepted = m.publish_manual_accepted(
        root,
        checkpoint,
        admission,
        files,
        receipt,
        permission,
        completion_request,
        confirmation,
        predecessor=None,
    )
    assert len(m.read_manual_history(root, checkpoint, admission)) == 1
    assert accepted.original_intake_sha256 == m.digest(receipt)
    assert not accepted.gold
    with pytest.raises(ValueError):
        m.publish_manual_accepted(
            root,
            checkpoint,
            admission,
            files,
            receipt,
            permission,
            completion_request,
            confirmation,
            predecessor=None,
        )
    assert (
        m.read_manual_intake(root, checkpoint, admission, m.digest(receipt))["annotations.csv"]
        == files["annotations.csv"]
    )

    record_property(
        "owner_assisted_synthetic_demo",
        json.dumps(
            {
                "profile": m.PROFILE,
                "mode": "SYNTHETIC",
                "mappings": [r.model_dump(mode="json") for r in report.outcomes],
                "controls": [c.model_dump(mode="json") for c in controls],
                "launch": {
                    "synthetic_ready": launch.synthetic_ready,
                    "real_launch_authorized": launch.real_launch_authorized,
                },
                "original_sha256s": receipt.form_sha256s,
                "consumer": {
                    "accepted_kind": accepted.kind,
                    "accepted_sha256": m.digest(accepted),
                    "gold": accepted.gold,
                    "literal_bytes_preserved": True,
                },
            },
            sort_keys=True,
        ),
    )


def test_synthetic_controls_cannot_be_relabelled_as_real_manual_evidence(tmp_path: Path) -> None:
    m = api()
    binding, observations, originals = fixture()
    controls = exercise_synthetic_manual_controls(
        tmp_path,
        binding,
        (blank("annotator-a"), blank("annotator-b")),
        people(),
        at=NOW + timedelta(minutes=5),
    )
    binding = binding.model_copy(update={"mode": "MANUALLY_WITNESSED", "run_id": "m2-02-v1"})
    observations = [
        o.model_copy(update={"binding_sha256": m.digest(binding)}) for o in observations
    ]
    controls = tuple(c.model_copy(update={"binding_sha256": m.digest(binding)}) for c in controls)
    retained = witness(binding, observations, controls)
    with pytest.raises(ValueError):
        m.verify_manual_observations(
            binding,
            observations,
            originals,
            retained,
            trusted_witness_sha256=sha256(retained),
            controls=controls,
        )


def test_current_consumer_source_drift_rejects_before_store_initialization(tmp_path: Path) -> None:
    m = api()
    binding, _, _ = fixture()
    admission = component_admission(binding, (blank("annotator-a"), blank("annotator-b")), people())
    admission = admission.model_copy(update={"source_sha256": "f" * 64})
    root, checkpoint = tmp_path / "drift-root", tmp_path / "drift-index"
    root.mkdir()
    checkpoint.mkdir()
    with pytest.raises(ValueError):
        m.initialize_manual_store(root, checkpoint, admission)
    assert list(root.iterdir()) == []
    assert list(checkpoint.iterdir()) == []


@pytest.mark.parametrize("check_id", [r.check_id for r in ACCESS_POLICY_V2.acl_expectations])
def test_every_changed_mapping_rejects_even_with_matching_witness(check_id: str) -> None:
    m = api()
    binding, observations, originals = fixture()
    index = next(i for i, o in enumerate(observations) if o.check_id == check_id)
    observations[index] = observations[index].model_copy(
        update={"operation": "read" if observations[index].operation != "read" else "write"}
    )
    retained = witness(binding, observations)
    with pytest.raises(ValueError):
        m.verify_manual_observations(
            binding, observations, originals, retained, trusted_witness_sha256=sha256(retained)
        )


def test_caller_pass_and_native_relabelling_are_not_manual_observations() -> None:
    m = api()
    _, observations, _ = fixture()
    for extras in ({"result": "PASS"}, {"kind": "NATIVE_PROVIDER_CAPTURE"}):
        with pytest.raises(ValueError):
            m.ManualObservation.model_validate_json(
                canonical_json_bytes(observations[0].model_dump(mode="json") | extras)
            )


@pytest.mark.parametrize(
    "adverse",
    [
        "missing_actual_delivery",
        "permission_as_acceptance",
        "wrong_role",
        "same_human",
        "exposed",
        "stale",
        "forged_isolation",
        "substituted_decision",
    ],
)
def test_delivery_ceremony_requires_actual_linked_evidence(tmp_path: Path, adverse: str) -> None:
    m = api()
    binding, observations, originals = fixture()
    packages = (blank("annotator-a"), blank("annotator-b"))
    persons = people()
    controls = exercise_synthetic_manual_controls(
        tmp_path, binding, packages, persons, at=NOW + timedelta(minutes=5)
    )
    retained = witness(binding, observations, controls)
    report = m.verify_manual_observations(
        binding,
        observations,
        originals,
        retained,
        trusted_witness_sha256=sha256(retained),
        controls=controls,
    )
    materials, eligibility, decisions, pins = delivery_fixture(
        tmp_path, binding, report, packages, persons, at=NOW + timedelta(minutes=6)
    )
    if adverse == "missing_actual_delivery":
        decisions = decisions[:4] + decisions[5:]
        pins = tuple(sha256(d) for d in decisions)
    elif adverse == "permission_as_acceptance":
        record = m.ManualDecisionOriginal.model_validate_json(decisions[4]).model_copy(
            update={"state": "PROSPECTIVE_PERMISSION"}
        )
        decisions = (
            *decisions[:4],
            canonical_json_bytes(record.model_dump(mode="json")),
            *decisions[5:],
        )
        pins = tuple(sha256(d) for d in decisions)
    elif adverse == "wrong_role":
        materials = materials[::-1]
    elif adverse == "same_human":
        persons = (
            persons[0],
            persons[1].model_copy(update={"private_person_token": persons[0].private_person_token}),
        )
    elif adverse == "exposed":
        persons = (persons[0].model_copy(update={"machine_answers_seen": True}), persons[1])
    elif adverse == "forged_isolation":
        report = report.model_copy(
            update={"outcomes": report.outcomes[:1], "complete_consistency": True}
        )
    elif adverse == "substituted_decision":
        decisions = (
            *decisions[:5],
            decisions[5].replace(b"synthetic-owner", b"synthetic-stranger"),
        )
    with pytest.raises(ValueError):
        m.verify_manual_delivery(
            binding,
            report,
            materials,
            eligibility,
            decisions,
            trusted_decision_sha256s=pins,
            at=NOW + timedelta(hours=2) if adverse == "stale" else NOW + timedelta(minutes=6),
            people=persons,
            packages=packages,
        )


def store_fixture(tmp_path: Path) -> tuple[Any, Path, Path, dict[str, bytes], Any]:
    m = api()
    binding, _, _ = fixture()
    admission = component_admission(binding, (blank("annotator-a"), blank("annotator-b")), people())
    root, checkpoint = tmp_path / "consumer", tmp_path / "independent-index"
    root.mkdir()
    checkpoint.mkdir()
    m.initialize_manual_store(root, checkpoint, admission)
    files = blank()
    complete(files)
    receipt = m.intake_manual_originals(
        root, checkpoint, admission, files, at=NOW + timedelta(minutes=7)
    )
    return admission, root, checkpoint, files, receipt


@pytest.mark.parametrize(
    "adverse",
    [
        "missing_completion",
        "missing_confirmation",
        "wrong_witness",
        "forged_pin",
        "unconfirmed_draft",
    ],
)
def test_accepted_publication_requires_completion_and_independent_confirmation(
    tmp_path: Path, adverse: str
) -> None:
    m = api()
    admission, root, checkpoint, files, receipt = store_fixture(tmp_path)
    original_forms = {name: files[name] for name in m.FORM_HEADERS}
    evidence = list(
        synthetic_publication_evidence(admission, receipt, at=NOW + timedelta(minutes=8))
    )
    if adverse in ("missing_completion", "missing_confirmation"):
        evidence[1 if adverse == "missing_completion" else 2] = evidence[0]
    elif adverse == "wrong_witness":
        original = evidence[2].original.model_copy(
            update={"witness_ref": "synthetic-forged-witness"}
        )
        evidence[2] = evidence[2].model_copy(
            update={"original": original, "trusted_sha256": m.digest(original)}
        )
    elif adverse == "forged_pin":
        evidence[2] = evidence[2].model_copy(update={"trusted_sha256": "f" * 64})
    elif adverse == "unconfirmed_draft":
        files = blank()
    with pytest.raises(ValueError):
        m.publish_manual_accepted(
            root, checkpoint, admission, files, receipt, *evidence, predecessor=None
        )
    assert m.read_manual_history(root, checkpoint, admission) == ()
    assert m.read_manual_intake(root, checkpoint, admission, m.digest(receipt)) == original_forms


def test_supersession_preserves_first_original_and_rejects_second_current_branch(
    tmp_path: Path,
) -> None:
    m = api()
    admission, root, checkpoint, files, first_intake = store_fixture(tmp_path)
    first_evidence = synthetic_publication_evidence(
        admission, first_intake, at=NOW + timedelta(minutes=8)
    )
    first = m.publish_manual_accepted(
        root, checkpoint, admission, files, first_intake, *first_evidence, predecessor=None
    )
    first_bytes = (root / "accepted-000001.json").read_bytes()
    second_intake = m.intake_manual_originals(
        root, checkpoint, admission, files, at=NOW + timedelta(minutes=9)
    )
    second_evidence = synthetic_publication_evidence(
        admission, second_intake, at=NOW + timedelta(minutes=10)
    )
    for predecessor in (None, "f" * 64):
        with pytest.raises(ValueError):
            m.publish_manual_accepted(
                root,
                checkpoint,
                admission,
                files,
                second_intake,
                *second_evidence,
                predecessor=predecessor,
            )
    second = m.publish_manual_accepted(
        root,
        checkpoint,
        admission,
        files,
        second_intake,
        *second_evidence,
        predecessor=m.digest(first),
    )
    assert second.supersedes == m.digest(first)
    assert (root / "accepted-000001.json").read_bytes() == first_bytes
    assert len(m.read_manual_history(root, checkpoint, admission)) == 2


@pytest.mark.parametrize("fault", ["partial_accepted", "partial_intake", "corrupt_checkpoint"])
def test_partial_or_corrupt_history_is_retained_and_never_repaired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    m = api()
    admission, root, checkpoint, files, receipt = store_fixture(tmp_path)
    original_publish = m.publish
    if fault == "corrupt_checkpoint":
        path = next(checkpoint.glob("intake-*.json"))
        path.write_bytes(b"corrupt independent checkpoint")
    else:

        def interrupt(directory: Any, name: str, raw: bytes) -> None:
            if directory.resolved == checkpoint.resolve() and name.startswith(
                "accepted-" if fault == "partial_accepted" else "intake-"
            ):
                raise OSError("synthetic publication fault after original bytes")
            original_publish(directory, name, raw)

        monkeypatch.setattr(m, "publish", interrupt)
        with pytest.raises(OSError):
            if fault == "partial_accepted":
                evidence = synthetic_publication_evidence(
                    admission, receipt, at=NOW + timedelta(minutes=8)
                )
                m.publish_manual_accepted(
                    root, checkpoint, admission, files, receipt, *evidence, predecessor=None
                )
            else:
                m.intake_manual_originals(
                    root, checkpoint, admission, files, at=NOW + timedelta(minutes=9)
                )
        monkeypatch.undo()
    before = {
        str(p): p.read_bytes() for p in [*root.rglob("*"), *checkpoint.rglob("*")] if p.is_file()
    }
    for _ in range(2):  # read-only recovery attempts, not mutation retries
        with pytest.raises(ValueError):
            m.read_manual_history(root, checkpoint, admission)
        assert {
            str(p): p.read_bytes()
            for p in [*root.rglob("*"), *checkpoint.rglob("*")]
            if p.is_file()
        } == before


def test_bad_forms_are_retained_as_originals_not_accepted(tmp_path: Path) -> None:
    m = api()
    admission, root, checkpoint, files, _ = store_fixture(tmp_path)
    files["annotations.csv"] = b"literal invalid original\r\nnot a form\r\n"
    receipt = m.intake_manual_originals(
        root, checkpoint, admission, files, at=NOW + timedelta(minutes=10)
    )
    assert receipt.validation_error and not receipt.mechanically_complete
    assert (
        m.read_manual_intake(root, checkpoint, admission, m.digest(receipt))["annotations.csv"]
        == files["annotations.csv"]
    )
    assert m.read_manual_history(root, checkpoint, admission) == ()


def test_real_storage_default_and_historical_unissued_routes_remain_closed(tmp_path: Path) -> None:
    m = api()
    binding, _, _ = fixture()
    admission = component_admission(binding, (blank("annotator-a"), blank("annotator-b")), people())
    with pytest.raises(ValueError):
        m.ManualStoreAdmission.model_validate_json(
            canonical_json_bytes(
                admission.model_dump(mode="json")
                | {"run_id": "m2-02-v1", "mode": "MANUALLY_WITNESSED"}
            )
        )
    from peru_conflicts.execution.launch import production_launch_preflight

    with pytest.raises(ValueError):
        production_launch_preflight()


def test_manual_view_rejects_private_extra_files_even_if_metadata_rehashed(tmp_path: Path) -> None:
    m = api()
    package = blank()
    view = build_neutral_view(package, tmp_path / "m2-readiness-view-test")
    data = view.model_dump(mode="json", exclude={"view_sha256"})
    data["file_hashes"]["coordinator/comparisons.json"] = "d" * 64
    data["view_sha256"] = sha256(canonical_json_bytes(data) + b"\n")
    view = type(view).model_validate_json(canonical_json_bytes(data))
    with pytest.raises(ValueError):
        m.manual_material_identity(package, view, field_registry_sha256="c" * 64)


def test_additive_manual_schema_has_current_distinct_receipts() -> None:
    m = api()
    assert hasattr(m, "manual_schema_bytes"), "manual schema export not implemented"
    root = Path(__file__).resolve().parents[2]
    assert (
        root / "schemas/execution/owner_assisted_v1.json"
    ).read_bytes() == m.manual_schema_bytes()


@pytest.mark.parametrize("corruption", ["missing", "changed"])
def test_top_level_schema_check_rejects_manual_schema_drift(
    tmp_path: Path, corruption: str
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    export = [
        sys.executable,
        "scripts/export_schemas.py",
        "--output",
        str(tmp_path),
    ]
    written = subprocess.run(export, cwd=repo_root, check=False, capture_output=True, text=True)
    assert written.returncode == 0, written.stdout + written.stderr
    manual = tmp_path / "execution" / "owner_assisted_v1.json"
    assert manual.read_bytes() == api().manual_schema_bytes()
    command = [*export, "--check"]
    current = subprocess.run(command, cwd=repo_root, check=False, capture_output=True, text=True)
    assert current.returncode == 0, current.stdout + current.stderr

    if corruption == "missing":
        manual.unlink()
    else:
        manual.write_bytes(b"{}\n")
    drifted = subprocess.run(command, cwd=repo_root, check=False, capture_output=True, text=True)
    assert drifted.returncode == 1, drifted.stdout + drifted.stderr
    assert drifted.stdout.strip() == (
        "Generated owner-assisted-v1 schema differs from registered models."
    )
    assert not drifted.stderr
