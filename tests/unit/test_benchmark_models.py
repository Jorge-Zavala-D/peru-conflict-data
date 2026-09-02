from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

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


def test_locked_submission_is_immutable_complete_and_annotator_consistent() -> None:
    submission = AnnotatorSubmission(
        submission_id="submission-a",
        annotator_id="annotator-a",
        unit_id=_unit().unit_id,
        partition_role=PartitionRole.PROTOCOL_PILOT,
        status=SubmissionStatus.LOCKED,
        locked_at=datetime(2026, 9, 2, tzinfo=UTC),
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
    receipt = BenchmarkCoverageReceipt(
        receipt_id="coverage-1",
        unit_id=_unit().unit_id,
        required_field_keys=("case_month.phase_original", "violence_event.fatalities_total"),
        observed_field_keys=("case_month.phase_original",),
        explicit_non_value_field_keys=("violence_event.fatalities_total",),
    )
    assert set(receipt.required_field_keys) == (
        set(receipt.observed_field_keys) | set(receipt.explicit_non_value_field_keys)
    )
    with pytest.raises(ValidationError, match="accounted"):
        BenchmarkCoverageReceipt.model_validate(
            {**receipt.model_dump(), "explicit_non_value_field_keys": ()}
        )
    with pytest.raises(ValidationError, match="unique"):
        BenchmarkCoverageReceipt.model_validate(
            {
                **receipt.model_dump(),
                "observed_field_keys": (
                    "case_month.phase_original",
                    "case_month.phase_original",
                ),
            }
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
