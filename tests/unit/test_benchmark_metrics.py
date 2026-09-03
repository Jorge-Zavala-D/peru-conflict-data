from __future__ import annotations

import pytest

import peru_conflicts.benchmark as benchmark
import peru_conflicts.benchmark.metrics as benchmark_metrics
from peru_conflicts.benchmark import AnnotationState
from peru_conflicts.benchmark.metrics import (
    ComparableAnnotation,
    binary_detection_metrics,
    exact_annotation_accuracy,
    exact_page_accuracy,
    multiset_object_metrics,
    provenance_completeness,
)
from peru_conflicts.models import SourceBBox, SourceSpan

SHA = "a" * 64


def _annotation(
    *,
    domain_object_type: str = "case_month",
    field_name: str = "phase_original",
    cardinality_index: int = 0,
    state: AnnotationState = AnnotationState.OBSERVED,
    raw_value_json: str | None = '"Diálogo"',
) -> ComparableAnnotation:
    return ComparableAnnotation(
        "unit-a",
        domain_object_type,
        field_name,
        cardinality_index,
        state,
        raw_value_json,
    )


def _empty_object_populations() -> dict[str, tuple[dict[str, object], ...]]:
    return {object_type: () for object_type in benchmark_metrics.OBJECT_MATCH_FIELDS}


def _span_anchor(*, page: int = 6, source_sha256: str = SHA) -> benchmark.EvidenceAnchor:
    return benchmark.EvidenceAnchor(
        report_id="report-264",
        report_number=264,
        source_sha256=source_sha256,
        page=page,
        section="Mediación",
        granularity=benchmark.EvidenceGranularity.SPAN,
        source_span=SourceSpan(start=10, end=35),
        source_text="Tipo de mediación: Pasiva",
    )


def _evidence_requirement(
    *,
    slot: benchmark.AnnotationSlot | None = None,
    allowed_granularities: tuple[benchmark.EvidenceGranularity, ...] = (
        benchmark.EvidenceGranularity.SPAN,
    ),
) -> benchmark.EvidenceRequirement:
    return benchmark.EvidenceRequirement(
        slot=slot
        or benchmark.AnnotationSlot(
            unit_id="unit-a",
            domain_object_type="case_month",
            cardinality_index=0,
            field_name="phase_original",
        ),
        report_id="report-264",
        report_number=264,
        source_sha256=SHA,
        pages=(6,),
        sections=("Mediación",),
        allowed_granularities=allowed_granularities,
    )


def _object_projection(object_type: str, **values: object) -> dict[str, object]:
    projection: dict[str, object] = {
        field_name: None for field_name in benchmark_metrics.OBJECT_MATCH_FIELDS[object_type]
    }
    projection.update(values)
    return projection


def _evaluate(
    gold: tuple[ComparableAnnotation, ...],
    predicted: tuple[ComparableAnnotation, ...],
    *,
    gold_objects: dict[str, tuple[dict[str, object], ...]] | None = None,
    predicted_objects: dict[str, tuple[dict[str, object], ...]] | None = None,
) -> benchmark_metrics.BenchmarkEvaluation:
    gold_slot = benchmark.AnnotationSlot(
        unit_id=gold[0].unit_id,
        domain_object_type=gold[0].domain_object_type,
        cardinality_index=gold[0].cardinality_index,
        field_name=gold[0].field_name,
    )
    requirement = _evidence_requirement(slot=gold_slot)
    prediction_slots = {annotation.key for annotation in predicted}
    return benchmark_metrics.evaluate_benchmark(
        gold,
        predicted,
        gold_objects=gold_objects or _empty_object_populations(),
        predicted_objects=predicted_objects or _empty_object_populations(),
        evidence_requirements=(requirement,),
        predicted_evidence=(
            {requirement.slot.key: (_span_anchor(),)}
            if requirement.slot.key in prediction_slots
            else {}
        ),
    )


def test_detection_metrics_cover_perfect_false_positive_and_false_negative() -> None:
    perfect = binary_detection_metrics({"a", "b"}, {"a", "b"})
    assert perfect.precision == 1
    assert perfect.recall == 1

    imperfect = binary_detection_metrics({"a", "b"}, {"b", "c"})
    assert imperfect.true_positive == 1
    assert imperfect.false_positive == 1
    assert imperfect.false_negative == 1
    assert imperfect.precision == 0.5
    assert imperfect.recall == 0.5


def test_exact_page_accuracy_counts_missing_and_mismatched_predictions() -> None:
    result = exact_page_accuracy(
        {"case-a": (2, 3), "case-b": (7,), "case-c": (9,)},
        {"case-a": (2, 3), "case-b": (8,)},
    )
    assert result.correct == 1
    assert result.total == 3
    assert result.accuracy == 1 / 3


def test_exact_annotation_accuracy_distinguishes_missing_zero_and_not_applicable() -> None:
    gold = (
        ComparableAnnotation(
            "unit-a", "violence_event", "fatalities_total", 0, AnnotationState.EXPLICIT_ZERO, "0"
        ),
        ComparableAnnotation(
            "unit-a", "violence_event", "injured_total", 0, AnnotationState.NOT_REPORTED, None
        ),
        ComparableAnnotation(
            "unit-a", "dialogue_event", "status_original", 0, AnnotationState.NOT_APPLICABLE, None
        ),
    )
    prediction = (
        gold[0],
        ComparableAnnotation(
            "unit-a", "violence_event", "injured_total", 0, AnnotationState.EXPLICIT_ZERO, "0"
        ),
    )
    result = exact_annotation_accuracy(gold, prediction)
    assert result.correct == 1
    assert result.total == 3


def test_exact_annotation_accuracy_rejects_duplicate_keys_without_order_dependence() -> None:
    gold = (
        ComparableAnnotation(
            "unit-a", "case_month", "phase_original", 0, AnnotationState.OBSERVED, '"Diálogo"'
        ),
    )
    right = gold[0]
    wrong = ComparableAnnotation(
        "unit-a", "case_month", "phase_original", 0, AnnotationState.OBSERVED, '"Crisis"'
    )

    for predictions in ((wrong, right), (right, wrong)):
        with pytest.raises(ValueError, match="prediction annotation keys must be unique"):
            exact_annotation_accuracy(gold, predictions)


def test_multiset_matching_counts_duplicate_objects_without_collapsing_them() -> None:
    gold = (
        {"name": "Actor A", "role": "demandante"},
        {"name": "Actor A", "role": "demandante"},
        {"name": "Actor B", "role": "entidad"},
    )
    predicted = (
        {"name": "Actor A", "role": "demandante"},
        {"name": "Actor B", "role": "entidad"},
        {"name": "Actor C", "role": "entidad"},
    )
    result = multiset_object_metrics(gold, predicted, match_fields=("name", "role"))
    assert result.true_positive == 2
    assert result.false_positive == 1
    assert result.false_negative == 1


def test_provenance_completeness_measures_required_evidence_coverage() -> None:
    result = provenance_completeness((True, True, False, True))
    assert result.correct == 3
    assert result.total == 4
    assert result.accuracy == 0.75


@pytest.mark.parametrize(
    "extra",
    [
        _annotation(field_name="unsupported_scalar"),
        _annotation(cardinality_index=99),
    ],
    ids=("extra-scalar", "extra-cardinality-index"),
)
def test_strict_evaluator_penalizes_extra_annotation_keys(extra: ComparableAnnotation) -> None:
    gold = (_annotation(),)
    result = _evaluate(gold, (gold[0], extra))

    assert result.strict_fields.correct == 1
    assert result.strict_fields.extra == 1
    assert result.strict_fields.gold_total == 1
    assert result.strict_fields.prediction_total == 2
    assert result.strict_fields.strict_denominator == 2
    assert result.strict_fields.strict_exact_accuracy == 0.5
    assert result.gate_passed is False


def test_strict_evaluator_penalizes_one_hundred_unsupported_values() -> None:
    gold = (_annotation(),)
    extras = tuple(_annotation(field_name=f"unsupported_{index}") for index in range(100))
    result = _evaluate(gold, (gold[0], *extras))

    assert result.strict_fields.extra == 100
    assert result.strict_fields.strict_exact_accuracy == 1 / 101
    assert result.gate_passed is False


@pytest.mark.parametrize(
    ("predicted", "expected"),
    [
        ((), {"correct": 0, "incorrect": 0, "missing": 1, "extra": 0}),
        (
            (_annotation(raw_value_json='"Crisis"'),),
            {"correct": 0, "incorrect": 1, "missing": 0, "extra": 0},
        ),
        (
            (_annotation(state=AnnotationState.NOT_REPORTED, raw_value_json=None),),
            {"correct": 0, "incorrect": 1, "missing": 0, "extra": 0},
        ),
    ],
    ids=("missing", "wrong-value", "wrong-state"),
)
def test_strict_evaluator_penalizes_missing_wrong_and_wrong_state(
    predicted: tuple[ComparableAnnotation, ...], expected: dict[str, int]
) -> None:
    result = _evaluate((_annotation(),), predicted)

    assert {
        "correct": result.strict_fields.correct,
        "incorrect": result.strict_fields.incorrect,
        "missing": result.strict_fields.missing,
        "extra": result.strict_fields.extra,
    } == expected
    assert result.gate_passed is False


@pytest.mark.parametrize(
    ("gold", "predicted"),
    [
        (
            _annotation(
                domain_object_type="violence_event",
                field_name="injured_total",
                state=AnnotationState.EXPLICIT_ZERO,
                raw_value_json="0",
            ),
            _annotation(
                domain_object_type="violence_event",
                field_name="injured_total",
                state=AnnotationState.NOT_REPORTED,
                raw_value_json=None,
            ),
        ),
        (
            _annotation(state=AnnotationState.NOT_APPLICABLE, raw_value_json=None),
            _annotation(state=AnnotationState.NOT_REPORTED, raw_value_json=None),
        ),
    ],
    ids=("explicit-zero-versus-not-reported", "not-applicable-versus-not-reported"),
)
def test_strict_evaluator_keeps_annotation_states_distinct(
    gold: ComparableAnnotation, predicted: ComparableAnnotation
) -> None:
    result = _evaluate((gold,), (predicted,))
    assert result.strict_fields.incorrect == 1
    assert result.gate_passed is False


def test_authoritative_evaluator_rejects_duplicate_prediction_keys() -> None:
    gold = (_annotation(),)
    with pytest.raises(ValueError, match="prediction annotation keys must be unique"):
        _evaluate(gold, (gold[0], gold[0]))


@pytest.mark.parametrize(
    "object_type",
    [
        "actor",
        "demand",
        "protest_event",
        "violence_event",
        "dialogue_event",
        "mediation_observation",
        "agreement",
        "dp_action",
        "alert",
        "case_observation",
    ],
)
def test_authoritative_evaluator_penalizes_every_extra_repeated_object(
    object_type: str,
) -> None:
    gold_annotations = (_annotation(),)
    predicted_objects = _empty_object_populations()
    first_field = benchmark_metrics.OBJECT_MATCH_FIELDS[object_type][0]
    predicted_objects[object_type] = (
        _object_projection(object_type, **{first_field: "unsupported-object"}),
    )

    result = _evaluate(
        gold_annotations,
        gold_annotations,
        predicted_objects=predicted_objects,
    )
    object_metric = dict(result.object_metrics)[object_type]

    assert object_metric.false_positive == 1
    assert object_metric.precision == 0
    assert result.gate_passed is False


@pytest.mark.parametrize(
    ("object_type", "field_name"),
    [
        ("protest_event", "actors_text_original"),
        ("alert", "alert_type_original"),
        ("dp_action", "intervention_hierarchy_original"),
        ("agreement", "case_description_original"),
    ],
)
def test_object_matching_uses_actual_source_visible_model_fields(
    object_type: str, field_name: str
) -> None:
    result = benchmark_metrics.multiset_object_metrics(
        (_object_projection(object_type, **{field_name: "source value a"}),),
        (_object_projection(object_type, **{field_name: "source value b"}),),
        match_fields=benchmark_metrics.OBJECT_MATCH_FIELDS[object_type],
    )

    assert result.true_positive == 0
    assert result.false_positive == 1
    assert result.false_negative == 1


def test_normative_object_matching_rejects_incomplete_or_extra_projection_fields() -> None:
    fields = benchmark_metrics.OBJECT_MATCH_FIELDS["mediation_observation"]

    for invalid in ({}, {**_object_projection("mediation_observation"), "unexpected": True}):
        with pytest.raises(ValueError, match="exactly match the versioned projection fields"):
            benchmark_metrics.multiset_object_metrics(
                (_object_projection("mediation_observation", requester_original="Comunidad"),),
                (invalid,),
                match_fields=fields,
            )


def test_mediation_object_projection_scores_requester_difference() -> None:
    result = benchmark_metrics.multiset_object_metrics(
        (_object_projection("mediation_observation", requester_original="Comunidad A"),),
        (_object_projection("mediation_observation", requester_original="Comunidad B"),),
        match_fields=benchmark_metrics.OBJECT_MATCH_FIELDS["mediation_observation"],
    )

    assert result.true_positive == 0
    assert result.false_positive == 1
    assert result.false_negative == 1


def test_authoritative_evaluator_rejects_missing_required_object_population() -> None:
    gold_annotations = (_annotation(),)
    incomplete = _empty_object_populations()
    del incomplete["actor"]

    with pytest.raises(ValueError, match="complete fixed object-type population"):
        _evaluate(gold_annotations, gold_annotations, gold_objects=incomplete)


def test_authoritative_evaluator_requires_evidence_for_every_gold_slot() -> None:
    gold = (_annotation(),)

    with pytest.raises(ValueError, match="exactly cover every gold annotation slot"):
        benchmark_metrics.evaluate_benchmark(
            gold,
            gold,
            gold_objects=_empty_object_populations(),
            predicted_objects=_empty_object_populations(),
            evidence_requirements=(),
            predicted_evidence={},
        )


def test_authoritative_evaluator_rejects_evidence_for_unpredicted_slot() -> None:
    gold = (_annotation(),)
    requirement = _evidence_requirement()
    extra_slot = _annotation(field_name="unsupported_scalar").key

    with pytest.raises(ValueError, match="evidence may only reference prediction slots"):
        benchmark_metrics.evaluate_benchmark(
            gold,
            gold,
            gold_objects=_empty_object_populations(),
            predicted_objects=_empty_object_populations(),
            evidence_requirements=(requirement,),
            predicted_evidence={
                requirement.slot.key: (_span_anchor(),),
                extra_slot: (_span_anchor(),),
            },
        )


def test_evidence_metric_accepts_span_without_bbox_and_bbox_without_span() -> None:
    slot_key = _evidence_requirement().slot.key
    span = benchmark_metrics.evaluate_evidence_requirements(
        (_evidence_requirement(allowed_granularities=(benchmark.EvidenceGranularity.SPAN,)),),
        {slot_key: (_span_anchor(),)},
    )
    bbox_anchor = benchmark.EvidenceAnchor(
        report_id="report-264",
        report_number=264,
        source_sha256=SHA,
        page=6,
        section="Mediación",
        granularity=benchmark.EvidenceGranularity.BOUNDING_BOX,
        source_bbox=SourceBBox(x0=1, y0=2, x1=3, y1=4),
    )
    bbox_requirement = _evidence_requirement(
        allowed_granularities=(benchmark.EvidenceGranularity.BOUNDING_BOX,)
    )
    bbox = benchmark_metrics.evaluate_evidence_requirements(
        (bbox_requirement,), {bbox_requirement.slot.key: (bbox_anchor,)}
    )

    assert span.complete == span.total == 1
    assert bbox.complete == bbox.total == 1


def test_evidence_metric_enforces_table_cell_and_page_only_requirements() -> None:
    table_anchor = benchmark.EvidenceAnchor(
        report_id="report-264",
        report_number=264,
        source_sha256=SHA,
        page=6,
        section="Mediación",
        granularity=benchmark.EvidenceGranularity.TABLE_CELL,
        source_table="Mediaciones",
        table_row_original="Machupicchu",
        table_column_original="Estado",
    )
    page_anchor = benchmark.EvidenceAnchor(
        report_id="report-264",
        report_number=264,
        source_sha256=SHA,
        page=6,
        section="Mediación",
        granularity=benchmark.EvidenceGranularity.PAGE_ONLY,
        page_only_rationale="The whole page is the bounded format observation.",
    )

    for granularity, anchor in (
        (benchmark.EvidenceGranularity.TABLE_CELL, table_anchor),
        (benchmark.EvidenceGranularity.PAGE_ONLY, page_anchor),
    ):
        requirement = _evidence_requirement(allowed_granularities=(granularity,))
        result = benchmark_metrics.evaluate_evidence_requirements(
            (requirement,), {requirement.slot.key: (anchor,)}
        )
        assert result.complete == result.total == 1


def test_evidence_metric_reports_wrong_custody_page_section_and_granularity() -> None:
    requirement = _evidence_requirement()
    wrong = benchmark.EvidenceAnchor(
        report_id="report-264",
        report_number=264,
        source_sha256="b" * 64,
        page=7,
        section="Otra sección",
        granularity=benchmark.EvidenceGranularity.BOUNDING_BOX,
        source_bbox=SourceBBox(x0=1, y0=2, x1=3, y1=4),
    )

    result = benchmark_metrics.evaluate_evidence_requirements(
        (requirement,), {requirement.slot.key: (wrong,)}
    )

    assert result.complete == 0
    assert result.wrong_source_sha == 1
    assert result.missing_pages == 1
    assert result.extra_pages == 1
    assert result.wrong_section == 1
    assert result.invalid_granularity == 1


def test_evidence_metric_rejects_wrong_report_identity() -> None:
    requirement = _evidence_requirement()
    wrong_report = benchmark.EvidenceAnchor(
        report_id="wrong-report",
        report_number=999,
        source_sha256=SHA,
        page=6,
        section="Mediación",
        granularity=benchmark.EvidenceGranularity.SPAN,
        source_span=SourceSpan(start=10, end=35),
    )

    result = benchmark_metrics.evaluate_evidence_requirements(
        (requirement,), {requirement.slot.key: (wrong_report,)}
    )

    assert result.complete == 0
    assert result.wrong_report_id == 1
    assert result.wrong_report_number == 1
