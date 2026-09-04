"""Versioned source-oriented records for the conflict-monitoring domain."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, Field, model_validator

from peru_conflicts.models.common import (
    Confidence,
    Identifier,
    JsonDocument,
    ModelInvocation,
    ReferencePeriod,
    ScalarValue,
    Sha256,
    SourceBBox,
    SourceSpan,
    TransitionEvidence,
    VersionedModel,
)


class ReportIdentityEvidenceType(StrEnum):
    """Evidence classes allowed to support report number or reference period."""

    DOCUMENT_VISIBLE = "document_visible"
    OFFICIAL_METADATA = "official_metadata"
    EMBEDDED_PDF_TITLE = "embedded_pdf_title"


class ReportRecord(VersionedModel):
    report_id: Identifier
    source_version_id: Identifier
    report_number: int | None = Field(default=None, ge=1)
    reference_period: ReferencePeriod | None = None
    report_number_evidence_types: tuple[ReportIdentityEvidenceType, ...] = ()
    report_number_provenance_ids: tuple[Identifier, ...] = ()
    reference_period_evidence_types: tuple[ReportIdentityEvidenceType, ...] = ()
    reference_period_provenance_ids: tuple[Identifier, ...] = ()
    publication_date: date | None = None
    title_original: str | None = None
    source_url_original: str | None = None
    source_filename: Identifier
    canonical_filename: str | None = None
    sha256: Sha256
    byte_size: int = Field(ge=0)
    page_count: int | None = Field(default=None, ge=1)
    source_status: str | None = None
    native_text_status: str | None = None
    format_regime: str | None = None
    supersedes_source_version_id: str | None = None
    provenance_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def require_qualified_identity_evidence(self) -> Self:
        qualifying = {
            ReportIdentityEvidenceType.DOCUMENT_VISIBLE,
            ReportIdentityEvidenceType.OFFICIAL_METADATA,
        }
        for label, value, evidence_types, provenance_ids in (
            (
                "report number",
                self.report_number,
                self.report_number_evidence_types,
                self.report_number_provenance_ids,
            ),
            (
                "reference period",
                self.reference_period,
                self.reference_period_evidence_types,
                self.reference_period_provenance_ids,
            ),
        ):
            if value is None:
                continue
            if not set(evidence_types).intersection(qualifying):
                raise ValueError(
                    f"{label} requires document-visible or official metadata evidence; "
                    "an embedded PDF title is not sufficient"
                )
            if not provenance_ids:
                raise ValueError(f"{label} requires provenance IDs")
        return self


class IndicatorBasis(StrEnum):
    """Whether a monthly indicator is copied from a source or calculated."""

    SOURCE_REPORTED = "source_reported"
    DERIVED = "derived"


class ReportMonthAggregate(VersionedModel):
    report_month_id: Identifier
    report_id: Identifier
    metric_original: Identifier
    indicator_basis: IndicatorBasis
    value: ScalarValue = None
    unit_original: str | None = None
    scope_original: str | None = None
    provenance_ids: tuple[Identifier, ...] = ()
    derivation_name: Identifier | None = None
    derivation_version: Identifier | None = None
    upstream_record_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def validate_indicator_basis(self) -> Self:
        has_derivation = (
            self.derivation_name is not None
            or self.derivation_version is not None
            or bool(self.upstream_record_ids)
        )
        if self.indicator_basis is IndicatorBasis.SOURCE_REPORTED:
            if not self.provenance_ids:
                raise ValueError("source_reported indicators require provenance IDs")
            if has_derivation:
                raise ValueError("source_reported indicators cannot include derivation metadata")
        else:
            if (
                self.derivation_name is None
                or self.derivation_version is None
                or not self.upstream_record_ids
            ):
                raise ValueError(
                    "derived indicators require derivation name, version, and upstream records"
                )
        return self


class ConflictCase(VersionedModel):
    case_id: Identifier
    official_code: str | None = None
    canonical_name: str | None = None
    identity_method: str | None = None
    identity_confidence: Confidence | None = None
    provenance_ids: tuple[Identifier, ...] = ()


class CaseName(VersionedModel):
    case_name_id: Identifier
    case_id: Identifier
    report_id: Identifier
    name_original: Identifier
    name_normalized: str | None = None
    provenance_ids: tuple[str, ...] = ()


class CaseMonth(VersionedModel):
    case_month_id: Identifier
    case_id: Identifier
    report_id: Identifier
    reference_period: ReferencePeriod
    official_code_original: str | None = None
    name_original: str | None = None
    stock_status_original: str | None = None
    stock_status_normalized: str | None = None
    phase_original: str | None = None
    phase_normalized: str | None = None
    conflict_type_original: str | None = None
    conflict_type_normalized: str | None = None
    case_description_original: str | None = None
    transitions: tuple[TransitionEvidence, ...] = ()
    monthly_facts_original: str | None = None
    provenance_ids: tuple[str, ...] = ()


class CaseReportedIndicator(VersionedModel):
    """A value the source reports for a case-month, never a value derived from events."""

    case_reported_indicator_id: Identifier
    case_month_id: Identifier
    case_id: Identifier
    report_id: Identifier
    metric_original: Identifier
    value: ScalarValue
    unit_original: str | None = None
    scope_original: str | None = None
    provenance_ids: tuple[Identifier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_source_value(self) -> Self:
        if self.value is None:
            raise ValueError("a case-reported indicator requires a non-null source value")
        return self


class Location(VersionedModel):
    location_id: Identifier
    location_text_original: Identifier
    department_original: str | None = None
    province_original: str | None = None
    district_original: str | None = None
    population_center_original: str | None = None
    department_normalized: str | None = None
    province_normalized: str | None = None
    district_normalized: str | None = None
    population_center_normalized: str | None = None
    ubigeo: str | None = None
    match_method: str | None = None
    crosswalk_version: str | None = None
    match_confidence: Confidence | None = None
    provenance_ids: tuple[Identifier, ...] = ()


class CaseLocation(VersionedModel):
    case_location_id: Identifier
    case_id: Identifier
    report_id: Identifier
    location_id: Identifier
    relationship_original: str | None = None
    provenance_ids: tuple[str, ...] = ()


class Actor(VersionedModel):
    actor_id: Identifier
    name_original: Identifier
    name_normalized: str | None = None
    actor_type_original: str | None = None
    actor_type_normalized: str | None = None
    provenance_ids: tuple[Identifier, ...] = ()


class CaseActor(VersionedModel):
    case_actor_id: Identifier
    case_id: Identifier
    report_id: Identifier
    actor_id: Identifier
    role_original: str | None = None
    role_normalized: str | None = None
    provenance_ids: tuple[str, ...] = ()


class Demand(VersionedModel):
    demand_id: Identifier
    text_original: str | None = None
    text_normalized: str | None = None
    theme_original: str | None = None
    theme_normalized: str | None = None
    category_original: str | None = None
    category_normalized: str | None = None
    competent_entity_original: str | None = None
    provenance_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def require_source_dimension(self) -> Self:
        if not any(
            value is not None and value.strip()
            for value in (
                self.text_original,
                self.theme_original,
                self.category_original,
                self.competent_entity_original,
            )
        ):
            raise ValueError("a demand requires at least one source-visible demand dimension")
        return self


class CaseDemand(VersionedModel):
    case_demand_id: Identifier
    case_id: Identifier
    report_id: Identifier
    demand_id: Identifier
    provenance_ids: tuple[str, ...] = ()


class ProtestEvent(VersionedModel):
    protest_event_id: Identifier
    report_id: Identifier
    event_date: date | None = None
    event_date_original: str | None = None
    event_date_precision_original: str | None = None
    measure_type_original: str | None = None
    measure_type_normalized: str | None = None
    actors_text_original: str | None = None
    location_text_original: str | None = None
    demand_text_original: str | None = None
    violence_explicit: bool | None = None
    provenance_ids: tuple[str, ...] = ()


class CaseProtestLink(VersionedModel):
    case_protest_link_id: Identifier
    case_id: Identifier
    protest_event_id: Identifier
    link_method: Identifier
    confidence: Confidence | None = None
    provenance_ids: tuple[Identifier, ...] = Field(min_length=1)


class CasualtyComponent(VersionedModel):
    component_original: Identifier
    fatalities: int | None = Field(default=None, ge=0)
    injured: int | None = Field(default=None, ge=0)


class ViolenceEvent(VersionedModel):
    violence_event_id: Identifier
    report_id: Identifier
    case_id: str | None = None
    protest_event_id: str | None = None
    event_date: date | None = None
    event_date_original: str | None = None
    event_date_precision_original: str | None = None
    violence_type_original: str | None = None
    description_original: str | None = None
    fatalities_total: int | None = Field(default=None, ge=0)
    injured_total: int | None = Field(default=None, ge=0)
    casualty_components: tuple[CasualtyComponent, ...] = ()
    provenance_ids: tuple[str, ...] = ()


class DialogueEvent(VersionedModel):
    dialogue_event_id: Identifier
    report_id: Identifier
    case_id: str | None = None
    mediation_process_id: Identifier | None = None
    event_date: date | None = None
    event_date_original: str | None = None
    event_date_precision_original: str | None = None
    description_original: str | None = None
    status_original: str | None = None
    provenance_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def require_mediation_link_provenance(self) -> Self:
        if self.mediation_process_id is not None and not self.provenance_ids:
            raise ValueError("mediation_process_id links require provenance IDs")
        return self


class MediationProcess(VersionedModel):
    """Optional longitudinal identity, created only when cross-report evidence supports it."""

    mediation_process_id: Identifier
    case_id: Identifier | None = None
    canonical_label: str | None = None
    identity_method: Identifier
    identity_confidence: Confidence | None = None
    provenance_ids: tuple[Identifier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_case_link_provenance(self) -> Self:
        if self.case_id is not None and not self.provenance_ids:
            raise ValueError("case_id links require provenance IDs")
        return self


class MediationObservation(VersionedModel):
    """One source-local mediation block in one report; identity links are optional."""

    mediation_observation_id: Identifier
    report_id: Identifier
    mediation_process_id: Identifier | None = None
    case_id: Identifier | None = None
    start_date: date | None = None
    start_date_original: str | None = None
    start_date_precision_original: str | None = None
    status_original: str | None = None
    requester_original: str | None = None
    actors_original: str | None = None
    mediation_type_original: str | None = None
    mediator_original: str | None = None
    case_description_original: str | None = None
    demands_original: str | None = None
    progress_original: str | None = None
    provenance_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def require_link_provenance(self) -> Self:
        if (
            self.case_id is not None or self.mediation_process_id is not None
        ) and not self.provenance_ids:
            raise ValueError("mediation observation links require provenance IDs")
        return self


class Agreement(VersionedModel):
    agreement_id: Identifier
    report_id: Identifier
    case_id: str | None = None
    agreement_date: date | None = None
    agreement_date_original: str | None = None
    agreement_date_precision_original: str | None = None
    case_description_original: str | None = None
    text_original: str | None = None
    compliance_progress_original: str | None = None
    responsibility_original: str | None = None
    deadline_original: str | None = None
    provenance_ids: tuple[str, ...] = ()


class DefensoriaAction(VersionedModel):
    dp_action_id: Identifier
    report_id: Identifier
    case_id: str | None = None
    action_date: date | None = None
    action_type_original: str | None = None
    intervention_category_original: str | None = None
    intervention_category_normalized: str | None = None
    intervention_subtype_original: str | None = None
    intervention_subtype_normalized: str | None = None
    intervention_hierarchy_original: tuple[str, ...] = ()
    description_original: str | None = None
    provenance_ids: tuple[str, ...] = ()


class Alert(VersionedModel):
    alert_id: Identifier
    report_id: Identifier
    case_id: str | None = None
    alert_date: date | None = None
    text_original: str | None = None
    alert_type_original: str | None = None
    risk_original: str | None = None
    location_text_original: str | None = None
    provenance_ids: tuple[str, ...] = ()


class CaseRelationship(VersionedModel):
    relationship_id: Identifier
    case_id_from: Identifier
    case_id_to: Identifier
    relationship_type_original: Identifier
    relationship_type_normalized: str | None = None
    effective_period: ReferencePeriod | None = None
    confidence: Confidence | None = None
    provenance_ids: tuple[Identifier, ...] = Field(min_length=1)


class ExtractionMethod(StrEnum):
    NATIVE_TEXT = "native_text"
    LAYOUT = "layout"
    TABLE = "table"
    OCR = "ocr"
    RULE_BASED = "rule_based"
    PROBABILISTIC_MODEL = "probabilistic_model"
    MANUAL = "manual"


class ProvenanceRecord(VersionedModel):
    provenance_id: Identifier
    object_type: Identifier
    object_id: Identifier
    field_name: Identifier
    source_report_id: Identifier
    source_sha256: Sha256
    source_page: int | None = Field(default=None, ge=1)
    source_section: str | None = None
    source_table: str | None = None
    source_bbox: SourceBBox | None = None
    source_span: SourceSpan | None = None
    source_text: str | None = None
    extraction_method: ExtractionMethod
    extractor_name: str | None = None
    extractor_version: str | None = None
    parser_version: str | None = None
    model_invocation: ModelInvocation | None = None
    confidence: Confidence | None = None
    review_status: str | None = None

    @model_validator(mode="after")
    def require_probabilistic_metadata(self) -> Self:
        if (
            self.extraction_method is ExtractionMethod.PROBABILISTIC_MODEL
            and self.model_invocation is None
        ):
            raise ValueError("model_invocation is required for probabilistic provenance")
        if (
            self.extraction_method is not ExtractionMethod.PROBABILISTIC_MODEL
            and self.model_invocation is not None
        ):
            raise ValueError("model_invocation is only valid for probabilistic provenance")
        return self


class DiscrepancyType(StrEnum):
    PARSER_ERROR = "PARSER_ERROR"
    SOURCE_INCONSISTENCY = "SOURCE_INCONSISTENCY"
    SOURCE_AMBIGUITY = "SOURCE_AMBIGUITY"
    MISSING_SOURCE_EVIDENCE = "MISSING_SOURCE_EVIDENCE"
    CROSS_SOURCE_CONFLICT = "CROSS_SOURCE_CONFLICT"
    POTENTIAL_EDITORIAL_ERROR = "POTENTIAL_EDITORIAL_ERROR"


class DiscrepancyRecord(VersionedModel):
    discrepancy_id: Identifier
    report_id: Identifier
    discrepancy_type: DiscrepancyType
    severity: str | None = None
    value_a: ScalarValue = None
    provenance_a_ids: tuple[Identifier, ...] = ()
    value_b: ScalarValue = None
    provenance_b_ids: tuple[Identifier, ...] = ()
    status: str | None = None
    classification_rationale: Identifier
    parser_version: Identifier
    review_id: str | None = None

    @model_validator(mode="after")
    def require_type_appropriate_evidence(self) -> Self:
        if (
            self.discrepancy_type is not DiscrepancyType.MISSING_SOURCE_EVIDENCE
            and not self.provenance_a_ids
        ):
            raise ValueError("provenance_a_ids is required for this discrepancy type")
        if (
            self.discrepancy_type
            in {
                DiscrepancyType.SOURCE_INCONSISTENCY,
                DiscrepancyType.CROSS_SOURCE_CONFLICT,
            }
            and not self.provenance_b_ids
        ):
            raise ValueError("both provenance sides are required for this discrepancy type")
        return self


class ManualReviewItem(VersionedModel):
    review_id: Identifier
    object_type: Identifier
    object_id: str | None = None
    issue_type: Identifier
    candidate_payloads_json: tuple[JsonDocument, ...] = ()
    machine_suggestion_json: JsonDocument | None = None
    machine_model_invocation: ModelInvocation | None = None
    evidence_provenance_ids: tuple[Identifier, ...] = Field(min_length=1)
    neighboring_periods: tuple[ReferencePeriod, ...] = ()
    review_status: Identifier
    second_review_required: bool = False
    created_at: AwareDatetime
    parser_version: Identifier

    @model_validator(mode="after")
    def require_machine_metadata(self) -> Self:
        if (self.machine_suggestion_json is None) != (self.machine_model_invocation is None):
            raise ValueError(
                "machine_suggestion_json and machine_model_invocation must be supplied together"
            )
        return self


class AdjudicationRecord(VersionedModel):
    adjudication_id: Identifier
    review_id: Identifier
    decision_original: Identifier
    decision_action: Identifier
    decision_payload_json: JsonDocument | None = None
    rationale: Identifier
    reviewer_id: Identifier
    decided_at: AwareDatetime
    parser_version: Identifier
    evidence_provenance_ids: tuple[Identifier, ...] = Field(min_length=1)
    supersedes_adjudication_id: str | None = None
    second_reviewer_id: str | None = None
    second_reviewed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_review_chain(self) -> Self:
        if self.supersedes_adjudication_id == self.adjudication_id:
            raise ValueError("an adjudication cannot supersede itself")
        if (self.second_reviewer_id is None) != (self.second_reviewed_at is None):
            raise ValueError("second reviewer and timestamp must be supplied together")
        if self.second_reviewer_id == self.reviewer_id:
            raise ValueError("second reviewer must differ from the first reviewer")
        return self
