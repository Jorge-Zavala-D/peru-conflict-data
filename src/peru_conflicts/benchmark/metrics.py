"""Deterministic benchmark metrics over source-preserving annotation values."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from peru_conflicts.benchmark.models import AnnotationState
from peru_conflicts.hashing import canonical_json_bytes


@dataclass(frozen=True, slots=True)
class DetectionMetrics:
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float
    recall: float


@dataclass(frozen=True, slots=True)
class AccuracyMetric:
    correct: int
    total: int
    accuracy: float


@dataclass(frozen=True, slots=True)
class ComparableAnnotation:
    unit_id: str
    domain_object_type: str
    field_name: str
    cardinality_index: int
    state: AnnotationState
    raw_value_json: str | None

    @property
    def key(self) -> tuple[str, str, str, int]:
        return (
            self.unit_id,
            self.domain_object_type,
            self.field_name,
            self.cardinality_index,
        )

    @property
    def value(self) -> tuple[AnnotationState, str | None]:
        return (self.state, self.raw_value_json)


def _safe_ratio(numerator: int, denominator: int) -> float:
    return 1.0 if denominator == 0 else numerator / denominator


def binary_detection_metrics(gold_ids: set[str], predicted_ids: set[str]) -> DetectionMetrics:
    true_positive = len(gold_ids & predicted_ids)
    false_positive = len(predicted_ids - gold_ids)
    false_negative = len(gold_ids - predicted_ids)
    return DetectionMetrics(
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=_safe_ratio(true_positive, true_positive + false_positive),
        recall=_safe_ratio(true_positive, true_positive + false_negative),
    )


def exact_page_accuracy(
    gold_pages: Mapping[str, tuple[int, ...]],
    predicted_pages: Mapping[str, tuple[int, ...]],
) -> AccuracyMetric:
    correct = sum(predicted_pages.get(key) == pages for key, pages in gold_pages.items())
    return AccuracyMetric(
        correct=correct, total=len(gold_pages), accuracy=_safe_ratio(correct, len(gold_pages))
    )


def exact_annotation_accuracy(
    gold: Sequence[ComparableAnnotation],
    predicted: Sequence[ComparableAnnotation],
) -> AccuracyMetric:
    gold_keys = [annotation.key for annotation in gold]
    predicted_keys = [annotation.key for annotation in predicted]
    if len(gold_keys) != len(set(gold_keys)):
        raise ValueError("gold annotation keys must be unique")
    if len(predicted_keys) != len(set(predicted_keys)):
        raise ValueError("prediction annotation keys must be unique")
    predicted_by_key = {annotation.key: annotation.value for annotation in predicted}
    correct = sum(predicted_by_key.get(annotation.key) == annotation.value for annotation in gold)
    return AccuracyMetric(
        correct=correct, total=len(gold), accuracy=_safe_ratio(correct, len(gold))
    )


def multiset_object_metrics(
    gold_objects: Sequence[Mapping[str, object]],
    predicted_objects: Sequence[Mapping[str, object]],
    *,
    match_fields: tuple[str, ...],
) -> DetectionMetrics:
    def signature(item: Mapping[str, object]) -> bytes:
        return canonical_json_bytes({field: item.get(field) for field in match_fields})

    gold = Counter(signature(item) for item in gold_objects)
    predicted = Counter(signature(item) for item in predicted_objects)
    true_positive = sum((gold & predicted).values())
    false_positive = sum((predicted - gold).values())
    false_negative = sum((gold - predicted).values())
    return DetectionMetrics(
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=_safe_ratio(true_positive, true_positive + false_positive),
        recall=_safe_ratio(true_positive, true_positive + false_negative),
    )


def provenance_completeness(has_required_evidence: Iterable[bool]) -> AccuracyMetric:
    values = tuple(has_required_evidence)
    correct = sum(values)
    return AccuracyMetric(
        correct=correct, total=len(values), accuracy=_safe_ratio(correct, len(values))
    )
