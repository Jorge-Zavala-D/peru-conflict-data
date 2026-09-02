from __future__ import annotations

import pytest

from peru_conflicts.benchmark import AnnotationState
from peru_conflicts.benchmark.metrics import (
    ComparableAnnotation,
    binary_detection_metrics,
    exact_annotation_accuracy,
    exact_page_accuracy,
    multiset_object_metrics,
    provenance_completeness,
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
