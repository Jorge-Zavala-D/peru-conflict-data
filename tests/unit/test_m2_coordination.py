"""Private coordinator contracts, using synthetic tokens only."""

import pytest
from pydantic import ValidationError

from peru_conflicts.benchmark.models import PartitionRole
from peru_conflicts.execution import coordination
from peru_conflicts.execution.packages import build_package, verify_package
from peru_conflicts.execution.references import build_manifest


def test_distinct_unexposed_humans_are_required() -> None:
    a = coordination.EligibilityAttestation(
        role="annotator-a",
        private_person_token="synthetic-person-a",
        distinct_human_confirmed=True,
        machine_answers_seen=False,
        parser_predictions_seen=False,
        machine_prefill_seen=False,
        other_submission_seen=False,
        partition_labels_received=False,
    )
    b = a.model_copy(update={"role": "annotator-b"})
    with pytest.raises(ValueError, match="distinct"):
        coordination.verify_eligibility(a, b)
    b = b.model_copy(update={"private_person_token": "synthetic-person-b"})
    coordination.verify_eligibility(a, b)
    with pytest.raises(ValueError):
        coordination.verify_eligibility(a, b.model_copy(update={"machine_answers_seen": True}))


def test_held_out_routing_is_private_and_cannot_be_development_visible() -> None:
    pages = {1: b"Pure synthetic reference.\n"}
    package = build_package(
        "synthetic-run", "annotator-a", [(build_manifest(261, "a" * 64, pages, "b" * 64), pages)]
    )
    manifest = verify_package(package)
    context = coordination.build_context(manifest, {261: PartitionRole.HELD_OUT_EVALUATION})
    assert context.routes[0].sealed
    assert not context.routes[0].development_visible
    assert "held_out" not in package["PACKAGE_MANIFEST.json"].decode()
    assert "coordinator" not in package
    with pytest.raises(ValidationError):
        coordination.SubmissionRoute.model_validate(
            {
                "report_number": 261,
                "partition_role": PartitionRole.HELD_OUT_EVALUATION,
                "sealed": False,
                "development_visible": True,
            }
        )
    with pytest.raises(ValueError):
        coordination.build_context(manifest, {260: PartitionRole.PARSER_DEVELOPMENT})


def test_context_rejects_changed_package_binding() -> None:
    pages = {1: b"Synthetic\n"}
    manifest = verify_package(
        build_package(
            "synthetic-run",
            "annotator-a",
            [(build_manifest(260, "a" * 64, pages, "b" * 64), pages)],
        )
    )
    context = coordination.build_context(manifest, {260: PartitionRole.PARSER_DEVELOPMENT})
    with pytest.raises(ValueError):
        coordination.verify_context(context.model_copy(update={"package_id": "f" * 64}), manifest)


def test_unbound_context_is_not_production_preflight_authority() -> None:
    # The old context has only role/package routing, no eligibility issuance chain.
    with pytest.raises(ValueError, match="both"):
        coordination.production_lock_preflight((), (), (), ())
