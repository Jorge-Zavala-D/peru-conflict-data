"""Deterministic benchmark metrics over source-preserving annotation values."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from peru_conflicts.benchmark.models import (
    AnnotationState,
    EvidenceAnchor,
    EvidenceGranularity,
    EvidenceRequirement,
)
from peru_conflicts.hashing import canonical_json_bytes

OBJECT_MATCH_FIELDS: dict[str, tuple[str, ...]] = {
    "actor": ("name_original", "actor_type_original", "role_original"),
    "alert": (
        "alert_date",
        "alert_type_original",
        "risk_original",
        "location_text_original",
        "text_original",
    ),
    "agreement": (
        "agreement_date_original",
        "agreement_date_precision_original",
        "case_description_original",
        "text_original",
        "responsibility_original",
        "deadline_original",
        "compliance_progress_original",
    ),
    "case_observation": ("unit_id",),
    "dp_action": (
        "action_date",
        "action_type_original",
        "intervention_category_original",
        "intervention_subtype_original",
        "intervention_hierarchy_original",
        "description_original",
    ),
    "demand": (
        "text_original",
        "theme_original",
        "category_original",
        "competent_entity_original",
    ),
    "dialogue_event": (
        "event_date_original",
        "event_date_precision_original",
        "description_original",
        "status_original",
    ),
    "location": (
        "location_text_original",
        "department_original",
        "province_original",
        "district_original",
        "population_center_original",
        "relationship_original",
    ),
    "mediation_observation": (
        "unit_id",
        "start_date_original",
        "start_date_precision_original",
        "status_original",
        "requester_original",
        "actors_original",
        "mediation_type_original",
        "mediator_original",
        "case_description_original",
        "demands_original",
        "progress_original",
    ),
    "protest_event": (
        "event_date_original",
        "event_date_precision_original",
        "measure_type_original",
        "actors_text_original",
        "location_text_original",
        "demand_text_original",
    ),
    "violence_event": (
        "event_date_original",
        "event_date_precision_original",
        "violence_type_original",
        "description_original",
        "fatalities_total",
        "injured_total",
        "casualty_components",
    ),
}


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
class StrictAnnotationMetric:
    correct: int
    incorrect: int
    missing: int
    extra: int
    gold_total: int
    prediction_total: int
    strict_denominator: int
    strict_exact_accuracy: float


@dataclass(frozen=True, slots=True)
class EvidenceMetrics:
    complete: int
    total: int
    completeness: float
    missing_evidence: int
    wrong_report_id: int
    wrong_report_number: int
    missing_source_sha: int
    wrong_source_sha: int
    missing_pages: int
    extra_pages: int
    missing_section: int
    wrong_section: int
    missing_required_locator: int
    invalid_granularity: int


@dataclass(frozen=True, slots=True)
class BenchmarkEvaluation:
    strict_fields: StrictAnnotationMetric
    object_metrics: tuple[tuple[str, DetectionMetrics], ...]
    evidence: EvidenceMetrics
    gate_passed: bool


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


def strict_annotation_accuracy(
    gold: Sequence[ComparableAnnotation],
    predicted: Sequence[ComparableAnnotation],
) -> StrictAnnotationMetric:
    """Score all gold keys and penalize every additional prediction key.

    The denominator is ``gold_total + extra``. Incorrect and missing gold values
    are already represented within ``gold_total``; unsupported prediction keys
    extend the denominator so hallucinated fields or cardinality positions cannot
    receive a perfect score.
    """

    gold_keys = [annotation.key for annotation in gold]
    predicted_keys = [annotation.key for annotation in predicted]
    if len(gold_keys) != len(set(gold_keys)):
        raise ValueError("gold annotation keys must be unique")
    if len(predicted_keys) != len(set(predicted_keys)):
        raise ValueError("prediction annotation keys must be unique")
    gold_by_key = {annotation.key: annotation.value for annotation in gold}
    predicted_by_key = {annotation.key: annotation.value for annotation in predicted}
    shared = gold_by_key.keys() & predicted_by_key.keys()
    correct = sum(gold_by_key[key] == predicted_by_key[key] for key in shared)
    incorrect = len(shared) - correct
    missing = len(gold_by_key.keys() - predicted_by_key.keys())
    extra = len(predicted_by_key.keys() - gold_by_key.keys())
    denominator = len(gold_by_key) + extra
    return StrictAnnotationMetric(
        correct=correct,
        incorrect=incorrect,
        missing=missing,
        extra=extra,
        gold_total=len(gold_by_key),
        prediction_total=len(predicted_by_key),
        strict_denominator=denominator,
        strict_exact_accuracy=_safe_ratio(correct, denominator),
    )


def multiset_object_metrics(
    gold_objects: Sequence[Mapping[str, object]],
    predicted_objects: Sequence[Mapping[str, object]],
    *,
    match_fields: tuple[str, ...],
) -> DetectionMetrics:
    def signature(item: Mapping[str, object]) -> bytes:
        if set(item) != set(match_fields):
            raise ValueError(
                "object projections must exactly match the versioned projection fields"
            )
        return canonical_json_bytes({field: item[field] for field in match_fields})

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


def _has_typed_locator(anchor: EvidenceAnchor) -> bool:
    if anchor.granularity is EvidenceGranularity.SECTION:
        return True
    if anchor.granularity is EvidenceGranularity.SPAN:
        return anchor.source_span is not None
    if anchor.granularity is EvidenceGranularity.BOUNDING_BOX:
        return anchor.source_bbox is not None
    if anchor.granularity is EvidenceGranularity.TABLE_CELL:
        return bool(
            anchor.source_table and anchor.table_row_original and anchor.table_column_original
        )
    if anchor.granularity is EvidenceGranularity.PAGE_ONLY:
        return bool(anchor.page_only_rationale)
    return False


def evaluate_evidence_requirements(
    requirements: Sequence[EvidenceRequirement],
    predicted_anchors: Mapping[tuple[str, str, str, int], Sequence[EvidenceAnchor]],
) -> EvidenceMetrics:
    """Evaluate real anchors against exact custody, page, section, and locator rules."""

    requirement_keys = [requirement.slot.key for requirement in requirements]
    if len(requirement_keys) != len(set(requirement_keys)):
        raise ValueError("evidence requirement slots must be unique")

    complete = 0
    missing_evidence = 0
    wrong_report_id = 0
    wrong_report_number = 0
    missing_source_sha = 0
    wrong_source_sha = 0
    missing_pages = 0
    extra_pages = 0
    missing_section = 0
    wrong_section = 0
    missing_required_locator = 0
    invalid_granularity = 0

    for requirement in requirements:
        anchors = tuple(predicted_anchors.get(requirement.slot.key, ()))
        before = (
            missing_evidence,
            wrong_report_id,
            wrong_report_number,
            missing_source_sha,
            wrong_source_sha,
            missing_pages,
            extra_pages,
            missing_section,
            wrong_section,
            missing_required_locator,
            invalid_granularity,
        )
        if not anchors:
            missing_evidence += 1
            missing_pages += len(requirement.pages)
        else:
            actual_pages = Counter(anchor.page for anchor in anchors)
            expected_pages = Counter(requirement.pages)
            missing_pages += sum((expected_pages - actual_pages).values())
            extra_pages += sum((actual_pages - expected_pages).values())
            for anchor in anchors:
                if anchor.report_id != requirement.report_id:
                    wrong_report_id += 1
                if anchor.report_number != requirement.report_number:
                    wrong_report_number += 1
                raw_sha = getattr(anchor, "source_sha256", None)
                if not isinstance(raw_sha, str):
                    missing_source_sha += 1
                elif raw_sha != requirement.source_sha256:
                    wrong_source_sha += 1
                raw_section = getattr(anchor, "section", None)
                if not isinstance(raw_section, str) or not raw_section.strip():
                    missing_section += 1
                elif raw_section not in requirement.sections:
                    wrong_section += 1
                if anchor.granularity not in requirement.allowed_granularities:
                    invalid_granularity += 1
                if not _has_typed_locator(anchor):
                    missing_required_locator += 1
        after = (
            missing_evidence,
            wrong_report_id,
            wrong_report_number,
            missing_source_sha,
            wrong_source_sha,
            missing_pages,
            extra_pages,
            missing_section,
            wrong_section,
            missing_required_locator,
            invalid_granularity,
        )
        if after == before:
            complete += 1

    total = len(requirements)
    return EvidenceMetrics(
        complete=complete,
        total=total,
        completeness=_safe_ratio(complete, total),
        missing_evidence=missing_evidence,
        wrong_report_id=wrong_report_id,
        wrong_report_number=wrong_report_number,
        missing_source_sha=missing_source_sha,
        wrong_source_sha=wrong_source_sha,
        missing_pages=missing_pages,
        extra_pages=extra_pages,
        missing_section=missing_section,
        wrong_section=wrong_section,
        missing_required_locator=missing_required_locator,
        invalid_granularity=invalid_granularity,
    )


def evaluate_benchmark(
    gold_annotations: Sequence[ComparableAnnotation],
    predicted_annotations: Sequence[ComparableAnnotation],
    *,
    gold_objects: Mapping[str, Sequence[Mapping[str, object]]],
    predicted_objects: Mapping[str, Sequence[Mapping[str, object]]],
    evidence_requirements: Sequence[EvidenceRequirement],
    predicted_evidence: Mapping[tuple[str, str, str, int], Sequence[EvidenceAnchor]],
) -> BenchmarkEvaluation:
    """Run the mandatory versioned M3 gate over all field, object, and evidence paths."""

    required_object_types = set(OBJECT_MATCH_FIELDS)
    if (
        set(gold_objects) != required_object_types
        or set(predicted_objects) != required_object_types
    ):
        raise ValueError("benchmark evaluation requires the complete fixed object-type population")

    strict_fields = strict_annotation_accuracy(gold_annotations, predicted_annotations)
    gold_slots = {annotation.key for annotation in gold_annotations}
    prediction_slots = {annotation.key for annotation in predicted_annotations}
    requirement_slots = [requirement.slot.key for requirement in evidence_requirements]
    if len(requirement_slots) != len(set(requirement_slots)):
        raise ValueError("evidence requirement slots must be unique")
    if set(requirement_slots) != gold_slots:
        raise ValueError("evidence requirements must exactly cover every gold annotation slot")
    if not set(predicted_evidence).issubset(prediction_slots):
        raise ValueError("evidence may only reference prediction slots")
    object_metrics = tuple(
        (
            object_type,
            multiset_object_metrics(
                gold_objects[object_type],
                predicted_objects[object_type],
                match_fields=OBJECT_MATCH_FIELDS[object_type],
            ),
        )
        for object_type in sorted(OBJECT_MATCH_FIELDS)
    )
    evidence = evaluate_evidence_requirements(evidence_requirements, predicted_evidence)
    gate_passed = (
        strict_fields.strict_exact_accuracy == 1.0
        and all(
            metric.false_positive == 0 and metric.false_negative == 0
            for _, metric in object_metrics
        )
        and evidence.complete == evidence.total
    )
    return BenchmarkEvaluation(
        strict_fields=strict_fields,
        object_metrics=object_metrics,
        evidence=evidence,
        gate_passed=gate_passed,
    )
