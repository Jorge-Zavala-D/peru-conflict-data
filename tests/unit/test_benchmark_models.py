from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

import peru_conflicts.benchmark as benchmark
from peru_conflicts.benchmark import (
    AnnotationDisagreement,
    AnnotationState,
    AnnotationUnit,
    AnnotationUnitType,
    AnnotatorSubmission,
    BenchmarkCoverageReceipt,
    BenchmarkPartition,
    BenchmarkPartitionAssignment,
    EvidenceAnchor,
    EvidenceGranularity,
    FieldAnnotation,
    GoldAdjudication,
    PartitionRole,
    SubmissionStatus,
    derive_annotation_unit_id,
)
from peru_conflicts.models import SourceSpan

SHA = "a" * 64


def _anchor() -> EvidenceAnchor:
    return EvidenceAnchor(
        report_id="report-264",
        report_number=264,
        source_sha256=SHA,
        page=6,
        section="Unidad Funcional de Prevención y Gestión de Conflictos Sociales",
        granularity=EvidenceGranularity.SPAN,
        source_span=SourceSpan(start=10, end=35),
        source_text="Tipo de mediación: Pasiva",
    )


def _unit() -> AnnotationUnit:
    pages = (5, 6, 7)
    return AnnotationUnit(
        unit_id=derive_annotation_unit_id(
            report_number=264,
            source_sha256=SHA,
            unit_type=AnnotationUnitType.CASE_OBSERVATION,
            pages=pages,
            source_locator="mediation:machupicchu-concetur-torontoy",
        ),
        report_id="report-264",
        report_number=264,
        source_sha256=SHA,
        pages=pages,
        unit_type=AnnotationUnitType.CASE_OBSERVATION,
        source_locator="mediation:machupicchu-concetur-torontoy",
        sections=("Mediación",),
    )


def _observed_annotation() -> FieldAnnotation:
    return FieldAnnotation(
        annotation_id="annotation-a",
        unit_id=_unit().unit_id,
        annotator_id="annotator-a",
        domain_object_type="mediation_observation",
        field_name="mediation_type_original",
        state=AnnotationState.OBSERVED,
        raw_value_json='"Pasiva"',
        evidence_anchors=(_anchor(),),
        cardinality_index=0,
    )


def _object_instance(
    *,
    domain_object_type: str = "mediation_observation",
    cardinality_index: int = 0,
    required_field_names: tuple[str, ...] = ("mediation_type_original",),
) -> benchmark.AnnotationObjectInstance:
    return benchmark.AnnotationObjectInstance(
        unit_id=_unit().unit_id,
        domain_object_type=domain_object_type,
        cardinality_index=cardinality_index,
        required_field_names=required_field_names,
    )


def _locked_submission(
    *,
    submission_id: str,
    annotator_id: str,
    partition_role: PartitionRole = PartitionRole.PROTOCOL_PILOT,
    status: SubmissionStatus = SubmissionStatus.LOCKED,
    unit_id: str | None = None,
    cardinality_indexes: tuple[int, ...] = (0,),
) -> AnnotatorSubmission:
    resolved_unit_id = unit_id or _unit().unit_id
    instances = tuple(
        benchmark.AnnotationObjectInstance(
            unit_id=resolved_unit_id,
            domain_object_type="mediation_observation",
            cardinality_index=index,
            required_field_names=("mediation_type_original",),
        )
        for index in cardinality_indexes
    )
    annotations = tuple(
        FieldAnnotation(
            annotation_id=f"annotation-{annotator_id}-{index}",
            unit_id=resolved_unit_id,
            annotator_id=annotator_id,
            domain_object_type="mediation_observation",
            field_name="mediation_type_original",
            state=AnnotationState.OBSERVED,
            raw_value_json='"Pasiva"',
            evidence_anchors=(_anchor(),),
            cardinality_index=index,
        )
        for index in cardinality_indexes
    )
    return AnnotatorSubmission(
        submission_id=submission_id,
        annotator_id=annotator_id,
        unit_id=resolved_unit_id,
        partition_role=partition_role,
        status=status,
        locked_at=(
            datetime(2026, 9, 2, tzinfo=UTC) if status is not SubmissionStatus.DRAFT else None
        ),
        object_inventory=instances,
        annotations=annotations,
    )


def test_annotation_unit_id_is_deterministic_and_model_enforces_it() -> None:
    unit = _unit()
    assert unit.unit_id == _unit().unit_id

    with pytest.raises(ValidationError, match="deterministic unit ID"):
        unit.model_copy(update={"unit_id": "annotation-unit-wrong"}).__class__.model_validate(
            {**unit.model_dump(), "unit_id": "annotation-unit-wrong"}
        )


def test_benchmark_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="unexpected"):
        AnnotationUnit.model_validate({**_unit().model_dump(), "unexpected": True})


def test_annotation_states_do_not_collapse_missing_zero_and_not_applicable() -> None:
    zero = FieldAnnotation(
        annotation_id="zero",
        unit_id=_unit().unit_id,
        annotator_id="annotator-a",
        domain_object_type="violence_event",
        field_name="fatalities_total",
        state=AnnotationState.EXPLICIT_ZERO,
        raw_value_json="0",
        evidence_anchors=(_anchor(),),
    )
    missing = zero.model_copy(
        update={
            "annotation_id": "missing",
            "state": AnnotationState.NOT_REPORTED,
            "raw_value_json": None,
        }
    )
    not_applicable = missing.model_copy(
        update={"annotation_id": "na", "state": AnnotationState.NOT_APPLICABLE}
    )

    assert len({zero.state, missing.state, not_applicable.state}) == 3
    with pytest.raises(ValidationError, match="explicit_zero"):
        FieldAnnotation.model_validate({**zero.model_dump(), "raw_value_json": "1"})
    with pytest.raises(ValidationError, match="must not carry a raw value"):
        FieldAnnotation.model_validate({**missing.model_dump(), "raw_value_json": "0"})
    with pytest.raises(ValidationError, match="source_ambiguous"):
        FieldAnnotation.model_validate(
            {
                **missing.model_dump(),
                "annotation_id": "ambiguous",
                "state": AnnotationState.SOURCE_AMBIGUOUS,
                "uncertainty_comment": None,
            }
        )


def test_evidence_anchor_enforces_granularity_contract() -> None:
    with pytest.raises(ValidationError, match="source_span"):
        EvidenceAnchor.model_validate({**_anchor().model_dump(), "source_span": None})
    with pytest.raises(ValidationError, match="page_only_rationale"):
        EvidenceAnchor.model_validate(
            {
                **_anchor().model_dump(),
                "granularity": EvidenceGranularity.PAGE_ONLY,
                "source_span": None,
                "page_only_rationale": None,
            }
        )

    for mutation in (
        {
            "granularity": EvidenceGranularity.PAGE_ONLY,
            "source_span": None,
            "page_only_rationale": "   ",
        },
        {
            "granularity": EvidenceGranularity.TABLE_CELL,
            "source_span": None,
            "source_table": "   ",
            "table_row_original": "row",
            "table_column_original": "column",
        },
    ):
        with pytest.raises(ValidationError, match="requires"):
            EvidenceAnchor.model_validate({**_anchor().model_dump(), **mutation})


def test_evidence_requirement_rejects_section_as_a_locator_alternative() -> None:
    with pytest.raises(ValidationError, match="typed locator granularities"):
        benchmark.EvidenceRequirement(
            slot=benchmark.AnnotationSlot(
                unit_id=_unit().unit_id,
                domain_object_type="case_month",
                cardinality_index=0,
                field_name="phase_original",
            ),
            report_id="report-264",
            report_number=264,
            source_sha256=SHA,
            pages=(6,),
            sections=("Mediación",),
            allowed_granularities=(benchmark.EvidenceGranularity.SECTION,),
        )


def test_locked_submission_is_immutable_complete_and_annotator_consistent() -> None:
    submission = AnnotatorSubmission(
        submission_id="submission-a",
        annotator_id="annotator-a",
        unit_id=_unit().unit_id,
        partition_role=PartitionRole.PROTOCOL_PILOT,
        status=SubmissionStatus.LOCKED,
        locked_at=datetime(2026, 9, 2, tzinfo=UTC),
        object_inventory=(_object_instance(),),
        annotations=(_observed_annotation(),),
    )
    assert submission.status is SubmissionStatus.LOCKED
    with pytest.raises(ValidationError, match="locked_at"):
        AnnotatorSubmission.model_validate({**submission.model_dump(), "locked_at": None})
    with pytest.raises(ValidationError, match="annotator"):
        AnnotatorSubmission.model_validate(
            {
                **submission.model_dump(),
                "annotations": (
                    {**_observed_annotation().model_dump(), "annotator_id": "annotator-b"},
                ),
            }
        )


def test_disagreement_and_gold_adjudication_preserve_both_submissions() -> None:
    disagreement = AnnotationDisagreement(
        disagreement_id="disagreement-1",
        unit_id=_unit().unit_id,
        submission_a_id="submission-a",
        submission_b_id="submission-b",
        annotation_a_ids=("annotation-a",),
        annotation_b_ids=("annotation-b",),
        issue_type="value_mismatch",
        created_at=datetime(2026, 9, 3, tzinfo=UTC),
    )
    adjudication = GoldAdjudication(
        adjudication_id="gold-adjudication-1",
        disagreement_id=disagreement.disagreement_id,
        decision_original="Retener la lectura visible en la página 6.",
        decision_action="select_supported_value",
        reviewer_id="reviewer-1",
        decided_at=datetime(2026, 9, 4, tzinfo=UTC),
        evidence_anchors=(_anchor(),),
    )

    assert disagreement.submission_a_id != disagreement.submission_b_id
    assert adjudication.disagreement_id == disagreement.disagreement_id
    with pytest.raises(ValidationError, match="must differ"):
        AnnotationDisagreement.model_validate(
            {**disagreement.model_dump(), "submission_b_id": "submission-a"}
        )


def test_coverage_receipt_requires_every_field_to_be_accounted_for_once() -> None:
    phase_instance = benchmark.AnnotationObjectInstance(
        unit_id=_unit().unit_id,
        domain_object_type="case_month",
        cardinality_index=0,
        required_field_names=("phase_original",),
    )
    violence_instance = benchmark.AnnotationObjectInstance(
        unit_id=_unit().unit_id,
        domain_object_type="violence_event",
        cardinality_index=0,
        required_field_names=("fatalities_total",),
    )
    observed_slot = benchmark.AnnotationSlot(
        unit_id=_unit().unit_id,
        domain_object_type="case_month",
        cardinality_index=0,
        field_name="phase_original",
    )
    non_value_slot = benchmark.AnnotationSlot(
        unit_id=_unit().unit_id,
        domain_object_type="violence_event",
        cardinality_index=0,
        field_name="fatalities_total",
    )
    receipt = BenchmarkCoverageReceipt(
        receipt_id="coverage-1",
        unit_id=_unit().unit_id,
        object_inventory=(phase_instance, violence_instance),
        observed_slots=(observed_slot,),
        explicit_non_value_slots=(non_value_slot,),
    )
    assert set(receipt.required_slots) == (
        set(receipt.observed_slots) | set(receipt.explicit_non_value_slots)
    )
    with pytest.raises(ValidationError, match="accounted"):
        BenchmarkCoverageReceipt.model_validate(
            {**receipt.model_dump(), "explicit_non_value_slots": ()}
        )
    with pytest.raises(ValidationError, match="unique"):
        BenchmarkCoverageReceipt.model_validate(
            {
                **receipt.model_dump(),
                "observed_slots": (observed_slot.model_dump(), observed_slot.model_dump()),
            }
        )


def test_instance_aware_coverage_rejects_one_actor_when_five_are_required() -> None:
    inventory = tuple(
        benchmark.AnnotationObjectInstance(
            unit_id=_unit().unit_id,
            domain_object_type="actor",
            cardinality_index=index,
            required_field_names=("name_original",),
        )
        for index in range(5)
    )
    only_one_actor = benchmark.AnnotationSlot(
        unit_id=_unit().unit_id,
        domain_object_type="actor",
        cardinality_index=0,
        field_name="name_original",
    )

    with pytest.raises(ValidationError, match="accounted"):
        BenchmarkCoverageReceipt(
            receipt_id="incomplete-five-actor-coverage",
            unit_id=_unit().unit_id,
            object_inventory=inventory,
            observed_slots=(only_one_actor,),
        )


def test_locked_submission_requires_every_declared_instance_slot() -> None:
    complete = _locked_submission(
        submission_id="submission-complete",
        annotator_id="annotator-a",
        cardinality_indexes=(0, 1),
    )
    assert len(complete.object_inventory) == 2

    with pytest.raises(ValidationError, match="every declared object field"):
        AnnotatorSubmission.model_validate(
            {**complete.model_dump(), "annotations": (complete.annotations[0].model_dump(),)}
        )


def test_independent_submission_validation_rejects_same_annotator() -> None:
    submission_a = _locked_submission(submission_id="submission-a", annotator_id="annotator-a")
    submission_b = _locked_submission(submission_id="submission-b", annotator_id="annotator-a")

    with pytest.raises(ValueError, match="annotator IDs must differ"):
        benchmark.validate_independent_submissions(
            submission_a, submission_b, submission_history=(submission_a, submission_b)
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"unit_id": "annotation-unit-other"}, "same annotation unit"),
        ({"partition_role": PartitionRole.HELD_OUT_EVALUATION}, "same partition role"),
        ({"status": SubmissionStatus.DRAFT, "locked_at": None}, "must both be locked"),
        ({"status": SubmissionStatus.SUPERSEDED}, "must both be locked"),
    ],
)
def test_independent_submission_validation_rejects_invalid_pairings(
    mutation: dict[str, object], message: str
) -> None:
    submission_a = _locked_submission(submission_id="submission-a", annotator_id="annotator-a")
    base_b = _locked_submission(submission_id="submission-b", annotator_id="annotator-b")
    submission_b = base_b.model_copy(update=mutation)

    with pytest.raises(ValueError, match=message):
        benchmark.validate_independent_submissions(
            submission_a, submission_b, submission_history=(submission_a, submission_b)
        )


def test_independent_submission_validation_surfaces_object_count_mismatch() -> None:
    submission_a = _locked_submission(
        submission_id="submission-a",
        annotator_id="annotator-a",
        cardinality_indexes=(0, 1, 2, 3, 4),
    )
    submission_b = _locked_submission(
        submission_id="submission-b",
        annotator_id="annotator-b",
        cardinality_indexes=(0, 1, 2, 3),
    )

    mismatches = benchmark.validate_independent_submissions(
        submission_a, submission_b, submission_history=(submission_a, submission_b)
    )

    assert [
        mismatch.model_dump(exclude={"benchmark_schema_version"}) for mismatch in mismatches
    ] == [
        {
            "domain_object_type": "mediation_observation",
            "submission_a_count": 5,
            "submission_b_count": 4,
        }
    ]


def test_independent_submission_validation_rejects_locked_submission_with_successor() -> None:
    stale_a = _locked_submission(submission_id="submission-a-old", annotator_id="annotator-a")
    current_a = _locked_submission(submission_id="submission-a-current", annotator_id="annotator-a")
    current_a = current_a.model_copy(update={"supersedes_submission_id": stale_a.submission_id})
    submission_b = _locked_submission(submission_id="submission-b", annotator_id="annotator-b")

    with pytest.raises(ValueError, match="locked and current"):
        benchmark.validate_independent_submissions(
            stale_a,
            submission_b,
            submission_history=(stale_a, current_a, submission_b),
        )


def test_partition_freezes_unique_report_level_roles() -> None:
    partition = BenchmarkPartition(
        partition_id="m2-ten-report-split-v1",
        assignments=tuple(
            BenchmarkPartitionAssignment(report_number=report, role=role)
            for report, role in (
                (260, PartitionRole.PARSER_DEVELOPMENT),
                (261, PartitionRole.HELD_OUT_EVALUATION),
                (262, PartitionRole.PARSER_DEVELOPMENT),
                (263, PartitionRole.HELD_OUT_EVALUATION),
                (264, PartitionRole.PROTOCOL_PILOT),
                (265, PartitionRole.HELD_OUT_EVALUATION),
                (266, PartitionRole.PARSER_DEVELOPMENT),
                (267, PartitionRole.HELD_OUT_EVALUATION),
                (268, PartitionRole.PARSER_DEVELOPMENT),
                (269, PartitionRole.PROTOCOL_PILOT),
            )
        ),
    )
    assert len(partition.assignments) == 10
    with pytest.raises(ValidationError, match="unique"):
        BenchmarkPartition(
            partition_id="duplicate",
            assignments=(
                BenchmarkPartitionAssignment(report_number=264, role=PartitionRole.PROTOCOL_PILOT),
                BenchmarkPartitionAssignment(
                    report_number=264, role=PartitionRole.HELD_OUT_EVALUATION
                ),
            ),
        )


def _acceptance_gate_payload() -> dict[str, object]:
    return {
        "gate_id": "m3-acceptance-gates-v1",
        "policy_status": benchmark.GatePolicyStatus.OWNER_REVIEW_DRAFT,
        "owner_approval_required": True,
        "owner_approved": False,
        "source_references": (
            "docs/execution_plan.md#M3-02",
            "docs/execution_plan.md#M3-03",
            "docs/execution_plan.md#M3-04",
        ),
        "case_detection_precision_threshold": 0.99,
        "case_detection_recall_threshold": 0.99,
        "exact_page_attribution_threshold": 0.99,
        "strict_source_value_accuracy_threshold": 0.99,
        "evidence_completeness_threshold": 1.0,
        "evidence_policy_interpretation": "PROPOSED_OWNER_GATE_INTERPRETATION",
        "object_metric_policy": "selected_thresholds_with_all_metrics_reported",
        "object_metric_thresholds": (),
        "require_critical_parser_errors_closed": True,
        "require_arithmetic_discrepancies_classified": True,
    }


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -0.01, 1.01, "0.99"])
def test_acceptance_gate_thresholds_are_strict_finite_unit_intervals(invalid: object) -> None:
    payload = _acceptance_gate_payload()
    payload["case_detection_precision_threshold"] = invalid

    with pytest.raises(ValidationError):
        benchmark.BenchmarkAcceptanceGateSpec.model_validate(payload)


def test_draft_acceptance_gate_cannot_claim_owner_approval() -> None:
    payload = _acceptance_gate_payload()
    payload["owner_approved"] = True

    with pytest.raises(ValidationError, match="draft gate policy cannot be owner approved"):
        benchmark.BenchmarkAcceptanceGateSpec.model_validate(payload)


def test_object_metric_thresholds_are_unique_and_registered() -> None:
    payload = _acceptance_gate_payload()
    payload["object_metric_thresholds"] = (
        benchmark.ObjectMetricThreshold(
            object_type="actor", precision_threshold=0.99, recall_threshold=0.99
        ),
        benchmark.ObjectMetricThreshold(
            object_type="actor", precision_threshold=0.9, recall_threshold=0.9
        ),
    )

    with pytest.raises(ValidationError, match="object metric threshold types must be unique"):
        benchmark.BenchmarkAcceptanceGateSpec.model_validate(payload)


def test_gate_metric_result_cannot_override_unrounded_comparison() -> None:
    with pytest.raises(ValidationError, match="unrounded threshold comparison"):
        benchmark.BenchmarkGateMetricResult(
            metric_name="strict_source_value_accuracy",
            threshold=0.99,
            observed=0.989999,
            missing=False,
            passed=True,
        )
