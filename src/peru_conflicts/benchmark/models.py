"""Versioned technical contract for independent human benchmark annotation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.models.common import (
    Identifier,
    JsonDocument,
    Sha256,
    SourceBBox,
    SourceSpan,
    StrictModel,
)

BENCHMARK_SCHEMA_VERSION = "0.1.0"
BenchmarkThreshold = Annotated[
    float,
    Field(strict=True, ge=0.0, le=1.0, allow_inf_nan=False),
]

BENCHMARK_OBJECT_TYPES = frozenset(
    {
        "actor",
        "alert",
        "agreement",
        "case_observation",
        "dp_action",
        "demand",
        "dialogue_event",
        "location",
        "mediation_observation",
        "protest_event",
        "violence_event",
    }
)


class BenchmarkVersionedModel(StrictModel):
    """Base for the independently versioned benchmark technical contract."""

    benchmark_schema_version: Literal["0.1.0"] = BENCHMARK_SCHEMA_VERSION


class AnnotationUnitType(StrEnum):
    REPORT = "report"
    REPORT_MONTH_AGGREGATE = "report_month_aggregate"
    CASE_OBSERVATION = "case_observation"
    CASE_SUBOBJECT = "case_subobject"
    REPORT_ANNEX_EVENT = "report_annex_event"
    SOURCE_ONLY_OBJECT = "source_only_object"


class EvidenceGranularity(StrEnum):
    PAGE_ONLY = "page_only"
    SECTION = "section"
    SPAN = "span"
    BOUNDING_BOX = "bounding_box"
    TABLE_CELL = "table_cell"


class AnnotationState(StrEnum):
    OBSERVED = "observed"
    EXPLICIT_ZERO = "explicit_zero"
    NOT_REPORTED = "not_reported"
    NOT_APPLICABLE = "not_applicable"
    SOURCE_AMBIGUOUS = "source_ambiguous"
    STRUCTURALLY_UNAVAILABLE = "structurally_unavailable"
    ILLEGIBLE_UNINSPECTABLE = "illegible_uninspectable"
    ANNOTATION_UNCERTAIN = "annotation_uncertain"


class PartitionRole(StrEnum):
    PROTOCOL_PILOT = "protocol_pilot"
    PARSER_DEVELOPMENT = "parser_development"
    HELD_OUT_EVALUATION = "held_out_evaluation"


class SubmissionStatus(StrEnum):
    DRAFT = "draft"
    LOCKED = "locked"
    SUPERSEDED = "superseded"


class GatePolicyStatus(StrEnum):
    OWNER_REVIEW_DRAFT = "owner_review_draft"
    OWNER_APPROVED = "owner_approved"


class GateAcceptanceState(StrEnum):
    ACCEPTED = "accepted"
    MISSING_REQUIRED_METRICS = "missing_required_metrics"
    QUANTITATIVE_THRESHOLDS_FAILED = "quantitative_thresholds_failed"
    REVIEW_CLOSURE_FAILED = "review_closure_failed"
    OWNER_APPROVAL_REQUIRED = "owner_approval_required"


def derive_annotation_unit_id(
    *,
    report_number: int,
    source_sha256: str,
    unit_type: AnnotationUnitType,
    pages: tuple[int, ...],
    source_locator: str,
) -> str:
    """Derive an opaque stable ID solely from immutable source boundaries."""

    payload = {
        "pages": list(pages),
        "report_number": report_number,
        "source_locator": source_locator,
        "source_sha256": source_sha256,
        "unit_type": unit_type.value,
    }
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()[:24]
    return f"annotation-unit-{digest}"


class AnnotationUnit(BenchmarkVersionedModel):
    unit_id: Identifier
    report_id: Identifier
    report_number: int = Field(ge=1)
    source_sha256: Sha256
    pages: tuple[int, ...] = Field(min_length=1)
    unit_type: AnnotationUnitType
    source_locator: Identifier
    sections: tuple[Identifier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_source_boundary(self) -> Self:
        if tuple(sorted(set(self.pages))) != self.pages or any(page < 1 for page in self.pages):
            raise ValueError("annotation-unit pages must be positive, sorted, and unique")
        expected = derive_annotation_unit_id(
            report_number=self.report_number,
            source_sha256=self.source_sha256,
            unit_type=self.unit_type,
            pages=self.pages,
            source_locator=self.source_locator,
        )
        if self.unit_id != expected:
            raise ValueError("unit_id must equal the deterministic unit ID")
        return self


class EvidenceAnchor(BenchmarkVersionedModel):
    report_id: Identifier
    report_number: int = Field(ge=1)
    source_sha256: Sha256
    page: int = Field(ge=1)
    section: Identifier
    granularity: EvidenceGranularity
    source_table: str | None = None
    table_row_original: str | None = None
    table_column_original: str | None = None
    source_span: SourceSpan | None = None
    source_bbox: SourceBBox | None = None
    source_text: str | None = None
    page_only_rationale: str | None = None

    @model_validator(mode="after")
    def validate_granularity(self) -> Self:
        if self.granularity is EvidenceGranularity.SPAN and self.source_span is None:
            raise ValueError("span evidence requires source_span")
        if self.granularity is EvidenceGranularity.BOUNDING_BOX and self.source_bbox is None:
            raise ValueError("bounding-box evidence requires source_bbox")
        if self.granularity is EvidenceGranularity.TABLE_CELL and (
            not isinstance(self.source_table, str)
            or not self.source_table.strip()
            or not isinstance(self.table_row_original, str)
            or not self.table_row_original.strip()
            or not isinstance(self.table_column_original, str)
            or not self.table_column_original.strip()
        ):
            raise ValueError("table-cell evidence requires table, row, and column labels")
        if self.granularity is EvidenceGranularity.PAGE_ONLY and (
            not isinstance(self.page_only_rationale, str) or not self.page_only_rationale.strip()
        ):
            raise ValueError("page-only evidence requires page_only_rationale")
        return self


class AnnotationSlot(BenchmarkVersionedModel):
    """One source-bounded object-instance field within an annotation unit."""

    unit_id: Identifier
    domain_object_type: Identifier
    cardinality_index: int = Field(ge=0)
    field_name: Identifier

    @property
    def key(self) -> tuple[str, str, str, int]:
        return (
            self.unit_id,
            self.domain_object_type,
            self.field_name,
            self.cardinality_index,
        )


class AnnotationObjectInstance(BenchmarkVersionedModel):
    """A report-local object instance declared independently by one annotator."""

    unit_id: Identifier
    domain_object_type: Identifier
    cardinality_index: int = Field(ge=0)
    required_field_names: tuple[Identifier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_required_fields(self) -> Self:
        if len(self.required_field_names) != len(set(self.required_field_names)):
            raise ValueError("object-instance required field names must be unique")
        return self

    @property
    def key(self) -> tuple[str, str, int]:
        return (self.unit_id, self.domain_object_type, self.cardinality_index)

    @property
    def required_slots(self) -> tuple[AnnotationSlot, ...]:
        return tuple(
            AnnotationSlot(
                unit_id=self.unit_id,
                domain_object_type=self.domain_object_type,
                cardinality_index=self.cardinality_index,
                field_name=field_name,
            )
            for field_name in self.required_field_names
        )


class EvidenceRequirement(BenchmarkVersionedModel):
    """Exact custody, page, section, and typed-locator requirement for one slot."""

    slot: AnnotationSlot
    report_id: Identifier
    report_number: int = Field(ge=1)
    source_sha256: Sha256
    pages: tuple[int, ...] = Field(min_length=1)
    sections: tuple[Identifier, ...] = Field(min_length=1)
    allowed_granularities: tuple[EvidenceGranularity, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_requirement(self) -> Self:
        if tuple(sorted(set(self.pages))) != self.pages or any(page < 1 for page in self.pages):
            raise ValueError("evidence requirement pages must be positive, sorted, and unique")
        if len(self.sections) != len(set(self.sections)):
            raise ValueError("evidence requirement sections must be unique")
        if len(self.allowed_granularities) != len(set(self.allowed_granularities)):
            raise ValueError("allowed evidence granularities must be unique")
        locator_granularities = {
            EvidenceGranularity.SPAN,
            EvidenceGranularity.BOUNDING_BOX,
            EvidenceGranularity.TABLE_CELL,
            EvidenceGranularity.PAGE_ONLY,
        }
        if not set(self.allowed_granularities).issubset(locator_granularities):
            raise ValueError("evidence requirements allow only typed locator granularities")
        return self


class FieldAnnotation(BenchmarkVersionedModel):
    annotation_id: Identifier
    unit_id: Identifier
    annotator_id: Identifier
    domain_object_type: Identifier
    field_name: Identifier
    state: AnnotationState
    raw_value_json: JsonDocument | None = None
    evidence_anchors: tuple[EvidenceAnchor, ...] = Field(min_length=1)
    uncertainty_comment: str | None = None
    cardinality_index: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_state_value(self) -> Self:
        if self.state is AnnotationState.OBSERVED and self.raw_value_json is None:
            raise ValueError("observed annotations require a raw value")
        if self.state is AnnotationState.EXPLICIT_ZERO:
            if self.raw_value_json is None or json.loads(self.raw_value_json) != 0:
                raise ValueError("explicit_zero annotations require the numeric value 0")
            if json.loads(self.raw_value_json) is False:
                raise ValueError("explicit_zero cannot be represented by boolean false")
        no_value_states = {
            AnnotationState.NOT_REPORTED,
            AnnotationState.NOT_APPLICABLE,
            AnnotationState.STRUCTURALLY_UNAVAILABLE,
            AnnotationState.ILLEGIBLE_UNINSPECTABLE,
        }
        if self.state in no_value_states and self.raw_value_json is not None:
            raise ValueError(f"{self.state.value} must not carry a raw value")
        states_requiring_comment = {
            AnnotationState.SOURCE_AMBIGUOUS,
            AnnotationState.ANNOTATION_UNCERTAIN,
        }
        if self.state in states_requiring_comment and not self.uncertainty_comment:
            raise ValueError(f"{self.state.value} requires an uncertainty comment")
        return self


class AnnotatorSubmission(BenchmarkVersionedModel):
    submission_id: Identifier
    annotator_id: Identifier
    unit_id: Identifier
    partition_role: PartitionRole
    status: SubmissionStatus
    locked_at: AwareDatetime | None = None
    supersedes_submission_id: Identifier | None = None
    object_inventory: tuple[AnnotationObjectInstance, ...] = ()
    annotations: tuple[FieldAnnotation, ...] = ()

    @model_validator(mode="after")
    def validate_submission(self) -> Self:
        if self.status is SubmissionStatus.LOCKED and self.locked_at is None:
            raise ValueError("locked submissions require locked_at")
        if self.status is SubmissionStatus.DRAFT and self.locked_at is not None:
            raise ValueError("draft submissions cannot have locked_at")
        if self.status is SubmissionStatus.LOCKED and not self.annotations:
            raise ValueError("locked submissions require annotations")
        if self.status is SubmissionStatus.LOCKED and not self.object_inventory:
            raise ValueError("locked submissions require an object inventory")
        if any(instance.unit_id != self.unit_id for instance in self.object_inventory):
            raise ValueError("every object instance must have the submission unit ID")
        inventory_keys = [instance.key for instance in self.object_inventory]
        if len(inventory_keys) != len(set(inventory_keys)):
            raise ValueError("submission object-instance keys must be unique")
        if any(annotation.annotator_id != self.annotator_id for annotation in self.annotations):
            raise ValueError("every annotation must have the submission annotator ID")
        if any(annotation.unit_id != self.unit_id for annotation in self.annotations):
            raise ValueError("every annotation must have the submission unit ID")
        keys = [
            (
                annotation.domain_object_type,
                annotation.field_name,
                annotation.cardinality_index,
            )
            for annotation in self.annotations
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("submission annotation keys must be unique")
        if self.status is SubmissionStatus.LOCKED:
            required_slots = {
                slot.key for instance in self.object_inventory for slot in instance.required_slots
            }
            annotation_slots = {
                (
                    annotation.unit_id,
                    annotation.domain_object_type,
                    annotation.field_name,
                    annotation.cardinality_index,
                )
                for annotation in self.annotations
            }
            if annotation_slots != required_slots:
                raise ValueError("every declared object field must be annotated exactly once")
        if self.supersedes_submission_id == self.submission_id:
            raise ValueError("a submission cannot supersede itself")
        return self


class ObjectInstanceCountMismatch(BenchmarkVersionedModel):
    """A source-object count disagreement between two independent submissions."""

    domain_object_type: Identifier
    submission_a_count: int = Field(ge=0)
    submission_b_count: int = Field(ge=0)

    @model_validator(mode="after")
    def require_mismatch(self) -> Self:
        if self.submission_a_count == self.submission_b_count:
            raise ValueError("object-instance count mismatch values must differ")
        return self


def validate_independent_submissions(
    submission_a: AnnotatorSubmission,
    submission_b: AnnotatorSubmission,
    *,
    submission_history: Sequence[AnnotatorSubmission],
) -> tuple[ObjectInstanceCountMismatch, ...]:
    """Validate a normative current independent A/B pair and return count disagreements."""

    history_by_id: dict[str, AnnotatorSubmission] = {}
    for submission in submission_history:
        if submission.submission_id in history_by_id:
            raise ValueError("submission history IDs must be unique")
        history_by_id[submission.submission_id] = submission
    for submission in (submission_a, submission_b):
        if history_by_id.get(submission.submission_id) != submission:
            raise ValueError(
                "independent submissions must be present exactly in submission history"
            )

    superseded_ids = {
        submission.supersedes_submission_id
        for submission in submission_history
        if submission.status is SubmissionStatus.LOCKED
        and submission.supersedes_submission_id is not None
    }

    if submission_a.submission_id == submission_b.submission_id:
        raise ValueError("independent submission IDs must differ")
    if submission_a.annotator_id == submission_b.annotator_id:
        raise ValueError("independent annotator IDs must differ")
    if submission_a.unit_id != submission_b.unit_id:
        raise ValueError("independent submissions must cover the same annotation unit")
    if submission_a.partition_role is not submission_b.partition_role:
        raise ValueError("independent submissions must have the same partition role")
    if (
        submission_a.status is not SubmissionStatus.LOCKED
        or submission_b.status is not SubmissionStatus.LOCKED
        or submission_a.submission_id in superseded_ids
        or submission_b.submission_id in superseded_ids
    ):
        raise ValueError("independent submissions must both be locked and current")

    counts_a: dict[str, int] = {}
    counts_b: dict[str, int] = {}
    for instance in submission_a.object_inventory:
        counts_a[instance.domain_object_type] = counts_a.get(instance.domain_object_type, 0) + 1
    for instance in submission_b.object_inventory:
        counts_b[instance.domain_object_type] = counts_b.get(instance.domain_object_type, 0) + 1
    return tuple(
        ObjectInstanceCountMismatch(
            domain_object_type=object_type,
            submission_a_count=counts_a.get(object_type, 0),
            submission_b_count=counts_b.get(object_type, 0),
        )
        for object_type in sorted(counts_a.keys() | counts_b.keys())
        if counts_a.get(object_type, 0) != counts_b.get(object_type, 0)
    )


class AnnotationDisagreement(BenchmarkVersionedModel):
    disagreement_id: Identifier
    unit_id: Identifier
    submission_a_id: Identifier
    submission_b_id: Identifier
    annotation_a_ids: tuple[Identifier, ...] = Field(min_length=1)
    annotation_b_ids: tuple[Identifier, ...] = Field(min_length=1)
    issue_type: Identifier
    status: Literal["open", "adjudicated"] = "open"
    created_at: AwareDatetime

    @model_validator(mode="after")
    def require_independent_submissions(self) -> Self:
        if self.submission_a_id == self.submission_b_id:
            raise ValueError("disagreement submissions must differ")
        return self


class GoldAdjudication(BenchmarkVersionedModel):
    adjudication_id: Identifier
    disagreement_id: Identifier
    decision_original: Identifier
    decision_action: Identifier
    decision_value_json: JsonDocument | None = None
    reviewer_id: Identifier
    decided_at: AwareDatetime
    evidence_anchors: tuple[EvidenceAnchor, ...] = Field(min_length=1)
    supersedes_adjudication_id: Identifier | None = None

    @model_validator(mode="after")
    def prevent_self_supersession(self) -> Self:
        if self.supersedes_adjudication_id == self.adjudication_id:
            raise ValueError("an adjudication cannot supersede itself")
        return self


class BenchmarkCoverageReceipt(BenchmarkVersionedModel):
    receipt_id: Identifier
    unit_id: Identifier
    object_inventory: tuple[AnnotationObjectInstance, ...] = Field(min_length=1)
    observed_slots: tuple[AnnotationSlot, ...] = ()
    explicit_non_value_slots: tuple[AnnotationSlot, ...] = ()

    @property
    def required_slots(self) -> tuple[AnnotationSlot, ...]:
        return tuple(
            sorted(
                (slot for instance in self.object_inventory for slot in instance.required_slots),
                key=lambda slot: slot.key,
            )
        )

    @model_validator(mode="after")
    def require_complete_coverage(self) -> Self:
        if any(instance.unit_id != self.unit_id for instance in self.object_inventory):
            raise ValueError("every object instance must have the receipt unit ID")
        if any(slot.unit_id != self.unit_id for slot in self.observed_slots):
            raise ValueError("every observed slot must have the receipt unit ID")
        if any(slot.unit_id != self.unit_id for slot in self.explicit_non_value_slots):
            raise ValueError("every explicit non-value slot must have the receipt unit ID")
        inventory_keys = [instance.key for instance in self.object_inventory]
        if len(inventory_keys) != len(set(inventory_keys)):
            raise ValueError("coverage object-instance keys must be unique")
        required = {slot.key for slot in self.required_slots}
        observed = {slot.key for slot in self.observed_slots}
        non_value = {slot.key for slot in self.explicit_non_value_slots}
        if len(observed) != len(self.observed_slots):
            raise ValueError("observed slots must be unique")
        if len(non_value) != len(self.explicit_non_value_slots):
            raise ValueError("explicit non-value slots must be unique")
        if observed & non_value:
            raise ValueError("slots cannot be both observed and explicit non-value")
        if observed | non_value != required:
            raise ValueError(
                "every required object-instance field must be accounted for exactly once"
            )
        return self


class BenchmarkPartitionAssignment(BenchmarkVersionedModel):
    report_number: int = Field(ge=1)
    role: PartitionRole


class BenchmarkPartition(BenchmarkVersionedModel):
    partition_id: Identifier
    assignments: tuple[BenchmarkPartitionAssignment, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_assignments(self) -> Self:
        reports = [assignment.report_number for assignment in self.assignments]
        if len(reports) != len(set(reports)):
            raise ValueError("partition report assignments must be unique")
        roles = {assignment.role for assignment in self.assignments}
        if len(self.assignments) >= 3 and roles != set(PartitionRole):
            raise ValueError("a benchmark partition must contain all three roles")
        return self


class ObjectMetricThreshold(BenchmarkVersionedModel):
    object_type: Identifier
    precision_threshold: BenchmarkThreshold
    recall_threshold: BenchmarkThreshold

    @model_validator(mode="after")
    def require_registered_object_type(self) -> Self:
        if self.object_type not in BENCHMARK_OBJECT_TYPES:
            raise ValueError("object metric threshold type must be registered")
        return self


class BenchmarkAcceptanceGateSpec(BenchmarkVersionedModel):
    """Versioned policy applied separately to deterministic benchmark metrics."""

    gate_id: Identifier
    policy_status: GatePolicyStatus
    owner_approval_required: Literal[True] = True
    owner_approved: bool
    source_references: tuple[Identifier, ...] = Field(min_length=1)
    case_detection_precision_threshold: BenchmarkThreshold
    case_detection_recall_threshold: BenchmarkThreshold
    exact_page_attribution_threshold: BenchmarkThreshold
    strict_source_value_accuracy_threshold: BenchmarkThreshold
    evidence_completeness_threshold: BenchmarkThreshold
    evidence_policy_interpretation: Literal["PROPOSED_OWNER_GATE_INTERPRETATION"]
    object_metric_policy: Literal["selected_thresholds_with_all_metrics_reported"]
    object_metric_thresholds: tuple[ObjectMetricThreshold, ...] = ()
    require_critical_parser_errors_closed: bool
    require_arithmetic_discrepancies_classified: bool

    @model_validator(mode="after")
    def validate_policy_state(self) -> Self:
        if len(self.source_references) != len(set(self.source_references)):
            raise ValueError("gate source references must be unique")
        object_types = [threshold.object_type for threshold in self.object_metric_thresholds]
        if len(object_types) != len(set(object_types)):
            raise ValueError("object metric threshold types must be unique")
        if self.policy_status is GatePolicyStatus.OWNER_REVIEW_DRAFT and self.owner_approved:
            raise ValueError("draft gate policy cannot be owner approved")
        if self.policy_status is GatePolicyStatus.OWNER_APPROVED and not self.owner_approved:
            raise ValueError("owner-approved gate policy must record owner approval")
        return self


class BenchmarkReviewClosureState(BenchmarkVersionedModel):
    """Later reviewed M3-04 facts that numerical metrics cannot establish."""

    critical_parser_errors_closed: bool | None = None
    arithmetic_discrepancies_classified: bool | None = None


class BenchmarkGateMetricResult(BenchmarkVersionedModel):
    metric_name: Identifier
    threshold: BenchmarkThreshold
    observed: float | None
    missing: bool
    passed: bool

    @model_validator(mode="after")
    def validate_missing_state(self) -> Self:
        if self.missing != (self.observed is None):
            raise ValueError("gate metric missing state must match the observed value")
        expected_pass = self.observed is not None and self.observed >= self.threshold
        if self.passed != expected_pass:
            raise ValueError(
                "gate metric pass state must follow the unrounded threshold comparison"
            )
        return self


class BenchmarkGateResult(BenchmarkVersionedModel):
    gate_id: Identifier
    metric_components: tuple[BenchmarkGateMetricResult, ...] = Field(min_length=1)
    missing_required_metrics: bool
    overall_quantitative_pass: bool
    review_closure_pass: bool
    owner_approval_pass: bool
    final_acceptance: GateAcceptanceState

    @model_validator(mode="after")
    def validate_result_state(self) -> Self:
        metric_names = [component.metric_name for component in self.metric_components]
        if len(metric_names) != len(set(metric_names)):
            raise ValueError("gate metric result names must be unique")
        missing = any(component.missing for component in self.metric_components)
        quantitative = all(component.passed for component in self.metric_components)
        if self.missing_required_metrics != missing:
            raise ValueError("missing-required-metrics result is inconsistent")
        if self.overall_quantitative_pass != quantitative:
            raise ValueError("quantitative gate result is inconsistent")
        if missing:
            expected = GateAcceptanceState.MISSING_REQUIRED_METRICS
        elif not quantitative:
            expected = GateAcceptanceState.QUANTITATIVE_THRESHOLDS_FAILED
        elif not self.review_closure_pass:
            expected = GateAcceptanceState.REVIEW_CLOSURE_FAILED
        elif not self.owner_approval_pass:
            expected = GateAcceptanceState.OWNER_APPROVAL_REQUIRED
        else:
            expected = GateAcceptanceState.ACCEPTED
        if self.final_acceptance is not expected:
            raise ValueError("final gate acceptance state is inconsistent")
        return self


BENCHMARK_MODEL_REGISTRY: dict[str, type[BenchmarkVersionedModel]] = {
    "annotation_object_instance": AnnotationObjectInstance,
    "annotation_disagreement": AnnotationDisagreement,
    "annotation_slot": AnnotationSlot,
    "annotation_unit": AnnotationUnit,
    "annotator_submission": AnnotatorSubmission,
    "benchmark_coverage_receipt": BenchmarkCoverageReceipt,
    "benchmark_acceptance_gate_spec": BenchmarkAcceptanceGateSpec,
    "benchmark_gate_metric_result": BenchmarkGateMetricResult,
    "benchmark_gate_result": BenchmarkGateResult,
    "benchmark_partition": BenchmarkPartition,
    "benchmark_partition_assignment": BenchmarkPartitionAssignment,
    "benchmark_review_closure_state": BenchmarkReviewClosureState,
    "evidence_anchor": EvidenceAnchor,
    "evidence_requirement": EvidenceRequirement,
    "field_annotation": FieldAnnotation,
    "gold_adjudication": GoldAdjudication,
    "object_instance_count_mismatch": ObjectInstanceCountMismatch,
    "object_metric_threshold": ObjectMetricThreshold,
}
