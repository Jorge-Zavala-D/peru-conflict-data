"""Strict provisional records for source discovery before PDF acquisition."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from peru_conflicts.models.common import Identifier, ReferencePeriod, StrictModel

DISCOVERY_SCHEMA_VERSION = "0.1.0"


class IdentitySubject(StrEnum):
    """Candidate identity fields that discovery evidence may support."""

    REPORT_NUMBER = "report_number"
    REFERENCE_PERIOD = "reference_period"


class IdentityEvidenceType(StrEnum):
    """Technical classes of evidence encountered before acquisition."""

    DOCUMENT_VISIBLE = "document_visible"
    OFFICIAL_METADATA = "official_metadata"
    FILENAME = "filename"
    EMBEDDED_PDF_TITLE = "embedded_pdf_title"


class UrlRole(StrEnum):
    """Distinct roles an observed URL may play during discovery."""

    DISCOVERY_SURFACE = "discovery_surface"
    LANDING_PAGE = "landing_page"
    DIRECT_DOWNLOAD = "direct_download"


class CandidateSourceRelationType(StrEnum):
    """Pre-hash source relations permitted during M1 discovery."""

    APPEARS_SAME_REPORT = "appears_same_report"


class IdentityEvidence(StrictModel):
    """One observed value paired with its candidate identity interpretation."""

    subject: IdentitySubject
    evidence_type: IdentityEvidenceType
    candidate_value: Identifier
    observed_value: Identifier
    source_url: Identifier
    captured_at: AwareDatetime
    source_excerpt: str | None = None
    uncertainty_note: str | None = None


class RedirectHop(StrictModel):
    """One structured HTTP redirect edge, without retrieving a binary body."""

    role: Literal["redirect_hop"] = "redirect_hop"
    from_url: Identifier
    to_url: Identifier
    status_code: int = Field(ge=300, le=399)
    captured_at: AwareDatetime

    @model_validator(mode="after")
    def require_distinct_urls(self) -> Self:
        if self.from_url == self.to_url:
            raise ValueError("a redirect hop must change the URL")
        return self


class UrlObservation(StrictModel):
    """One encountered URL with a single explicit discovery role."""

    observation_id: Identifier
    role: UrlRole
    url: Identifier
    captured_at: AwareDatetime
    http_status: int | None = Field(default=None, ge=100, le=599)
    content_type: str | None = None
    redirect_hops: tuple[RedirectHop, ...] = ()
    uncertainty_note: str | None = None


class CandidateSourceRelation(StrictModel):
    """An uncertain relation between official URLs before byte hashing is authorized."""

    relation_id: Identifier
    source_url: Identifier
    related_source_url: Identifier
    relation_type: CandidateSourceRelationType
    captured_at: AwareDatetime
    rationale: Identifier
    uncertainty_note: str | None = None

    @model_validator(mode="after")
    def require_distinct_urls(self) -> Self:
        if self.source_url == self.related_source_url:
            raise ValueError("a candidate source relation requires two distinct URLs")
        return self


class CoverageExpectation(StrictModel):
    """A research coverage-grid hypothesis, separate from observed source records."""

    expectation_kind: Literal["research_coverage_grid"] = "research_coverage_grid"
    reference_period: ReferencePeriod
    rationale: Identifier


class ProvisionalDiscoveryRecord(StrictModel):
    """A provisional report candidate assembled solely from discovery evidence."""

    schema_version: Literal["0.1.0"] = DISCOVERY_SCHEMA_VERSION
    discovery_record_id: Identifier
    candidate_report_number: int | None = Field(default=None, ge=1)
    candidate_reference_period: ReferencePeriod | None = None
    identity_evidence: tuple[IdentityEvidence, ...] = ()
    url_observations: tuple[UrlObservation, ...] = Field(min_length=1)
    candidate_source_relations: tuple[CandidateSourceRelation, ...] = ()
    coverage_expectations: tuple[CoverageExpectation, ...] = ()
    uncertainty_notes: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def require_qualified_identity_evidence(self) -> Self:
        qualifying_types = {
            IdentityEvidenceType.DOCUMENT_VISIBLE,
            IdentityEvidenceType.OFFICIAL_METADATA,
        }
        candidates = (
            (
                "candidate report number",
                self.candidate_report_number,
                IdentitySubject.REPORT_NUMBER,
            ),
            (
                "candidate reference period",
                self.candidate_reference_period,
                IdentitySubject.REFERENCE_PERIOD,
            ),
        )
        for label, value, subject in candidates:
            if value is None:
                continue
            candidate_value = str(value)
            paired = [
                evidence
                for evidence in self.identity_evidence
                if evidence.subject is subject and evidence.candidate_value == candidate_value
            ]
            if not paired:
                raise ValueError(f"{label} requires paired evidence for its exact subject/value")
            if not any(evidence.evidence_type in qualifying_types for evidence in paired):
                raise ValueError(
                    f"{label} requires document-visible or official metadata evidence; "
                    "filename or embedded PDF title evidence alone is insufficient"
                )
        return self
